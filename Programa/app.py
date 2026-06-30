"""
Aplicació de seguiment de preus de productes en diferents webs.
Executar amb:  streamlit run app.py
"""
import os
import streamlit as st
import pandas as pd
import plotly.express as px

import database as db
from scraper import detectar_candidats, obtenir_preu, obtenir_preu_amb_fallback
from excel_export import exportar_excel, EXCEL_PATH

st.set_page_config(page_title="Seguiment de preus", layout="wide")
db.init_db()

st.title("🍾 Seguiment de preus — Escumosos")

tab_dashboard, tab_productes, tab_urls, tab_export = st.tabs(
    ["📊 Dashboard", "📦 Productes", "🔗 URLs / Botigues", "📥 Excel"]
)

# ============================================================
# TAB DASHBOARD
# ============================================================
with tab_dashboard:
    productes = db.llistar_productes()

    if not productes:
        st.info("Encara no hi ha productes. Vés a la pestanya 'Productes' per afegir-ne un.")
    else:
        noms = {p["nom"]: p["id"] for p in productes}
        nom_sel = st.selectbox("Selecciona un producte", list(noms.keys()))
        producte_id = noms[nom_sel]

        urls = db.llistar_urls(producte_id)

        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("🔄 Actualitza preus ara", use_container_width=True):
                fallits = []
                with st.spinner("Consultant les webs..."):
                    for u in urls:
                        if not u["selector_css"]:
                            # URL configurada com a "només manual": no s'intenta scrapejar.
                            continue
                        preu, error, nou_sel, nou_idx = obtenir_preu_amb_fallback(
                            u["url"], u["selector_css"], index=u["index_element"]
                        )
                        db.guardar_preu(u["id"], preu, error)
                        if nou_sel and (nou_sel != u["selector_css"] or nou_idx != u["index_element"]):
                            db.actualitzar_selector(u["id"], nou_sel, nou_idx)
                        if preu is None:
                            fallits.append(u["botiga"])
                if fallits:
                    st.warning(
                        "No s'ha pogut extreure el preu automàticament per: "
                        + ", ".join(fallits)
                        + ". Pots introduir-lo a mà a la pestanya 'URLs / Botigues'."
                    )
                else:
                    st.success("Preus actualitzats!")
                st.rerun()

        registres = db.historic_per_producte(producte_id)

        if not registres:
            st.warning("Encara no hi ha cap preu registrat per aquest producte. Prem 'Actualitza preus ara'.")
        else:
            df = pd.DataFrame(
                [(r["data_hora"], r["botiga"], r["preu"], r["error"],
                  "Sí" if r["es_manual"] else "No") for r in registres],
                columns=["Data", "Botiga", "Preu", "Error", "Manual"]
            )
            df["Data"] = pd.to_datetime(df["Data"], format="mixed")

            fig = px.line(
                df.dropna(subset=["Preu"]),
                x="Data", y="Preu", color="Botiga", markers=True,
                title=f"Evolució de preu — {nom_sel}"
            )
            fig.update_layout(yaxis_title="Preu (€)", xaxis_title="Data")
            fig.update_xaxes(
                type="date",
                dtick=86400000,  # un dia, en mil·lisegons: força que cada "tick" sigui un dia sencer
                tickformat="%d-%m-%Y",
            )
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("Últim preu per botiga")
            BOTIGUES_PER_FILA = 5
            for i in range(0, len(urls), BOTIGUES_PER_FILA):
                fila = urls[i:i + BOTIGUES_PER_FILA]
                cols = st.columns(BOTIGUES_PER_FILA)
                for c, u in zip(cols, fila):
                    ultim = db.ultim_preu(u["id"])
                    with c:
                        if ultim and ultim["preu"] is not None:
                            etiqueta = u["botiga"] + (" ✏️" if ultim["es_manual"] else "")
                            st.metric(etiqueta, f"{ultim['preu']:.2f} €")
                            if ultim["es_manual"]:
                                st.caption("✏️ Preu manual")
                        else:
                            st.metric(u["botiga"], "—")

            with st.expander("Veure dades en taula"):
                df_taula = df.copy()
                df_taula["Data"] = df_taula["Data"].dt.strftime("%d-%m-%Y")
                df_taula = df_taula.sort_values("Data", ascending=False)

                n_registres = len(df_taula)
                n_mostrar = st.slider(
                    "Quants registres recents vols veure",
                    min_value=min(10, n_registres),
                    max_value=n_registres,
                    value=min(20, n_registres),
                ) if n_registres > 10 else n_registres

                st.dataframe(df_taula.head(n_mostrar), use_container_width=True)

# ============================================================
# TAB PRODUCTES
# ============================================================
with tab_productes:
    st.subheader("Afegir nou producte")
    with st.form("form_producte", clear_on_submit=True):
        nom = st.text_input("Nom del producte (ex: Cava Brut Nature 75cl)")
        categoria = st.text_input("Categoria (opcional)")
        enviat = st.form_submit_button("Afegir producte")
        if enviat:
            if nom.strip():
                try:
                    db.afegir_producte(nom.strip(), categoria.strip())
                    st.success(f"Producte '{nom}' afegit!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: ja existeix un producte amb aquest nom o hi ha un problema ({e})")
            else:
                st.warning("El nom no pot estar buit")

    st.divider()
    st.subheader("Productes existents")
    productes = db.llistar_productes()
    for p in productes:
        c1, c2 = st.columns([5, 1])
        c1.write(f"**{p['nom']}**  ·  {p['categoria'] or '—'}")
        if c2.button("🗑️ Eliminar", key=f"del_prod_{p['id']}"):
            db.eliminar_producte(p["id"])
            st.rerun()

# ============================================================
# TAB URLS — detecció automàtica + selecció manual si hi ha diversos preus
# ============================================================
with tab_urls:
    productes = db.llistar_productes()
    if not productes:
        st.info("Primer afegeix algun producte a la pestanya 'Productes'.")
    else:
        noms = {p["nom"]: p["id"] for p in productes}
        nom_sel2 = st.selectbox("Producte", list(noms.keys()), key="sel_urls")
        producte_id2 = noms[nom_sel2]

        st.subheader(f"Afegir URL per «{nom_sel2}»")
        st.caption(
            "Només cal el nom de la botiga i la URL. Si la pàgina té un únic "
            "preu, es detecta i s'afegeix automàticament. Si en té diversos "
            "(p.ex. diferents mides d'ampolla), et deixarà triar quin és el correcte."
        )

        botiga = st.text_input("Nom de la botiga (ex: Vinissimus)", key="input_botiga")
        url = st.text_input("URL del producte", key="input_url")

        if st.button("🔍 Cercar preu"):
            if not botiga.strip() or not url.strip():
                st.warning("Cal indicar el nom de la botiga i la URL")
            else:
                with st.spinner("Provant diferents llocs de la pàgina per trobar el preu..."):
                    candidats, error = detectar_candidats(url.strip())

                if not candidats:
                    st.error(error)
                    st.session_state["url_pendent"] = (botiga.strip(), url.strip())
                elif len(candidats) == 1:
                    c = candidats[0]
                    db.afegir_url(producte_id2, botiga.strip(), url.strip(), c["selector"], c["index"])
                    nova_url = db.llistar_urls(producte_id2)[-1]
                    db.guardar_preu(nova_url["id"], c["preu"])
                    st.success(f"Preu trobat: **{c['preu']:.2f} €**. URL afegida!")
                    st.rerun()
                else:
                    # Diversos preus trobats: cal que l'usuari triï el correcte.
                    st.session_state["candidats_pendents"] = candidats
                    st.session_state["candidats_botiga"] = botiga.strip()
                    st.session_state["candidats_url"] = url.strip()

        # Si hi ha diversos candidats pendents de triar
        if "candidats_pendents" in st.session_state:
            candidats = st.session_state["candidats_pendents"]
            st.warning(
                f"S'han trobat **{len(candidats)} preus diferents** a la pàgina "
                "(probablement per diferents formats/mides). Tria quin és el correcte:"
            )
            opcions = [
                f"{c['preu']:.2f} € — context: {c['context']}"
                for c in candidats
            ]
            tria = st.radio("Preu correcte", opcions, key="tria_candidat")
            idx_triat = opcions.index(tria)

            if st.button("✅ Confirmar selecció"):
                c = candidats[idx_triat]
                botiga_p = st.session_state["candidats_botiga"]
                url_p = st.session_state["candidats_url"]
                db.afegir_url(producte_id2, botiga_p, url_p, c["selector"], c["index"])
                nova_url = db.llistar_urls(producte_id2)[-1]
                db.guardar_preu(nova_url["id"], c["preu"])
                st.success(f"URL afegida amb el preu {c['preu']:.2f} €")
                del st.session_state["candidats_pendents"]
                del st.session_state["candidats_botiga"]
                del st.session_state["candidats_url"]
                st.rerun()

        # Si la detecció automàtica ha fallat del tot
        if "url_pendent" in st.session_state:
            botiga_p, url_p = st.session_state["url_pendent"]
            st.info(
                f"No s'ha trobat cap preu automàticament per «{botiga_p}». "
                "Com a últim recurs, indica el selector CSS manualment "
                "(clic dret sobre el preu a la web → Inspeccionar → Copy selector), "
                "o bé introdueix el preu a mà."
            )
            selector_manual = st.text_input("Selector CSS manual", key="selector_manual")
            if st.button("Provar selector manual"):
                preu2, error2 = obtenir_preu(url_p, selector_manual)
                if preu2 is not None:
                    db.afegir_url(producte_id2, botiga_p, url_p, selector_manual, 0)
                    nova_url = db.llistar_urls(producte_id2)[-1]
                    db.guardar_preu(nova_url["id"], preu2)
                    st.success(f"Preu trobat: {preu2:.2f} €. URL afegida!")
                    del st.session_state["url_pendent"]
                    st.rerun()
                else:
                    st.error(error2)

            st.divider()
            st.write("✏️ **O introdueix el preu manualment** (no es podrà actualitzar automàticament):")
            preu_manual_nou = st.number_input(
                "Preu (€)", min_value=0.0, step=0.01, format="%.2f", key="preu_manual_nou"
            )
            if st.button("✏️ Afegir amb preu manual"):
                # selector_css buit = URL marcada com "només manual": l'app no
                # intentarà extreure'l automàticament en les properes actualitzacions.
                db.afegir_url(producte_id2, botiga_p, url_p, "", 0)
                nova_url = db.llistar_urls(producte_id2)[-1]
                db.guardar_preu_manual(nova_url["id"], preu_manual_nou)
                st.success(f"Preu manual de {preu_manual_nou:.2f} € afegit per «{botiga_p}»")
                del st.session_state["url_pendent"]
                st.rerun()

        st.divider()
        st.subheader("URLs configurades")
        urls = db.llistar_urls(producte_id2)
        for u in urls:
            c1, c2, c3, c4, c5 = st.columns([3, 1, 1, 1, 1])
            ultim = db.ultim_preu(u["id"])
            if ultim and ultim["preu"] is not None:
                marca_manual = " ✏️ (manual)" if ultim["es_manual"] else ""
                preu_text = f"{ultim['preu']:.2f} €{marca_manual}"
            else:
                preu_text = "—"
            nom_botiga_mostrat = u["botiga"] + (" 🛑 (sense scraping)" if not u["selector_css"] else "")
            c1.write(f"**{nom_botiga_mostrat}** — {u['url']}  \nÚltim preu: {preu_text}")

            if u["selector_css"]:
                if c2.button("🧪 Tornar a provar", key=f"test_{u['id']}"):
                    with st.spinner("Provant..."):
                        preu, error, nou_sel, nou_idx = obtenir_preu_amb_fallback(
                            u["url"], u["selector_css"], index=u["index_element"]
                        )
                    if error:
                        st.error(error + " — pots introduir el preu manualment amb el botó ✏️.")
                    else:
                        st.success(f"Preu trobat: {preu:.2f} €")
                        db.guardar_preu(u["id"], preu)
                        if nou_sel and (nou_sel != u["selector_css"] or nou_idx != u["index_element"]):
                            db.actualitzar_selector(u["id"], nou_sel, nou_idx)
                        st.rerun()

                if c3.button("🔁 Triar altre preu", key=f"retriar_{u['id']}"):
                    st.session_state[f"retriant_{u['id']}"] = True
            else:
                c2.write("")
                c3.write("")

            if c4.button("✏️ Preu manual", key=f"manual_{u['id']}"):
                st.session_state[f"manual_form_{u['id']}"] = True

            if c5.button("🗑️", key=f"del_url_{u['id']}"):
                db.eliminar_url(u["id"])
                st.rerun()

            # Formulari per introduir/corregir el preu manualment.
            if st.session_state.get(f"manual_form_{u['id']}"):
                with st.form(f"form_manual_{u['id']}"):
                    valor_inicial = float(ultim["preu"]) if ultim and ultim["preu"] is not None else 0.0
                    preu_manual = st.number_input(
                        f"Preu manual per «{u['botiga']}» (€)",
                        min_value=0.0, step=0.01, format="%.2f", value=valor_inicial
                    )
                    desar = st.form_submit_button("✅ Desar preu manual")
                    if desar:
                        db.guardar_preu_manual(u["id"], preu_manual)
                        st.session_state[f"manual_form_{u['id']}"] = False
                        st.success(f"Preu manual de {preu_manual:.2f} € desat per «{u['botiga']}» (marcat com a manual)")
                        st.rerun()

            # Permet re-triar quin dels preus de la pàgina és el correcte,
            # útil si la botiga ha canviat de mides o l'app va triar malament.
            if st.session_state.get(f"retriant_{u['id']}"):
                with st.spinner("Cercant tots els preus de la pàgina..."):
                    candidats2, error3 = detectar_candidats(u["url"])
                if not candidats2:
                    st.error(error3 or "No s'ha trobat cap preu")
                else:
                    opcions2 = [f"{c['preu']:.2f} € — context: {c['context']}" for c in candidats2]
                    tria2 = st.radio(
                        f"Preu correcte per {u['botiga']}", opcions2, key=f"tria2_{u['id']}"
                    )
                    if st.button("✅ Confirmar", key=f"confirma2_{u['id']}"):
                        idx2 = opcions2.index(tria2)
                        c2sel = candidats2[idx2]
                        db.actualitzar_selector(u["id"], c2sel["selector"], c2sel["index"])
                        db.guardar_preu(u["id"], c2sel["preu"])
                        st.session_state[f"retriant_{u['id']}"] = False
                        st.success(f"Actualitzat a {c2sel['preu']:.2f} €")
                        st.rerun()

# ============================================================
# TAB EXCEL — sempre actualitza el mateix fitxer, no en crea un nou
# ============================================================
with tab_export:
    st.subheader("Excel de seguiment")
    st.write(
        f"Cada vegada que premis el botó s'actualitza **el mateix fitxer** "
        f"(`{EXCEL_PATH}`) amb les dades més recents — no es crea un Excel nou cada cop."
    )
    if st.button("🔄 Actualitzar Excel"):
        try:
            path = exportar_excel()
            st.success(f"Fitxer '{path}' actualitzat correctament.")
        except PermissionError:
            st.error(
                f"No s'ha pogut escriure '{EXCEL_PATH}' perquè sembla que el "
                "tens obert a l'Excel (o a un altre programa) en aquest moment. "
                "Tanca'l i torna a prémer el botó."
            )

    if os.path.exists(EXCEL_PATH):
        with open(EXCEL_PATH, "rb") as f:
            st.download_button(
                "📥 Descarregar Excel",
                f,
                file_name=EXCEL_PATH,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    else:
        st.info("Encara no s'ha generat l'Excel. Prem 'Actualitzar Excel'.")