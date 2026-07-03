"""
Generació d'un Excel amb un full per producte.
Cada full té: Botiga | % vs preu botiga | Data1 | Data2 | ... amb l'evolució
de preus, columnes de Botiga i % fixes en fer scroll, i un gràfic de línies
natiu d'Excel.
Els preus introduïts manualment (no extrets per scraping) es marquen amb un
to taronja i cursiva.
"""
import pandas as pd
from openpyxl.chart import LineChart, Reference
from openpyxl.chart.series import SeriesLabel
from openpyxl.chart.data_source import StrRef
from openpyxl.utils import get_column_letter
from openpyxl.styles import PatternFill, Font

import database as db
import os

# Nom de fitxer FIX: sempre s'actualitza el mateix Excel, no se'n crea un nou cada vegada.
# Es pot apuntar a una carpeta de xarxa compartida amb la variable d'entorn
# PREUS_EXCEL_PATH (igual que PREUS_DB_PATH a database.py).
EXCEL_PATH = os.environ.get("PREUS_EXCEL_PATH", "seguiment_preus.xlsx")

MANUAL_FILL = PatternFill(start_color="FFE8B8", end_color="FFE8B8", fill_type="solid")
MANUAL_FONT = Font(italic=True)
BOLD_FONT = Font(bold=True)
PCT_POSITIU_FONT = Font(color="007A33")   # verd: % positiu
PCT_NEGATIU_FONT = Font(color="C00000")   # vermell: % negatiu


def _nom_full_valid(nom):
    """Excel no permet certs caràcters ni més de 31 caràcters al nom del full."""
    invalid = r'[]:*?/\\'
    for ch in invalid:
        nom = nom.replace(ch, "")
    return nom[:31] if nom else "Producte"


def _ultim_valor_no_nul(fila, columnes_data):
    """Retorna el darrer valor no nul d'una fila, recorrent les columnes
    de data d'esquerra a dreta (de més antiga a més recent) i quedant-se
    amb el més recent que tingui valor."""
    valor = None
    for col in columnes_data:
        v = fila[col]
        if pd.notna(v):
            valor = v
    return valor


def exportar_excel(path=None):
    """Genera/actualitza l'Excel. Sempre fa servir el mateix fitxer (EXCEL_PATH)
    tret que s'indiqui un altre path explícitament, de manera que cada cop
    que es crida s'actualitza el mateix document en lloc de crear-ne un nou."""
    if path is None:
        path = EXCEL_PATH
    productes = db.llistar_productes()

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        if not productes:
            pd.DataFrame({"Avís": ["Encara no hi ha productes carregats"]}).to_excel(
                writer, sheet_name="Info", index=False
            )

        for prod in productes:
            registres = db.historic_per_producte(prod["id"])
            preu_referencia = prod["preu_referencia"]

            if not registres:
                df_pivot = pd.DataFrame({"Botiga": []})
                df_manual = pd.DataFrame()
                columnes_data = []
            else:
                df = pd.DataFrame(
                    [(r["data_hora"], r["botiga"], r["preu"], bool(r["es_manual"]))
                     for r in registres],
                    columns=["Data", "Botiga", "Preu", "Manual"]
                )
                # Files = Botiga, Columnes = Data
                df_pivot = df.pivot_table(
                    index="Botiga", columns="Data", values="Preu", aggfunc="first"
                ).reset_index()
                # Mateixa estructura però amb el flag de "manual" per saber
                # quines cel·les cal marcar visualment.
                df_manual = df.pivot_table(
                    index="Botiga", columns="Data", values="Manual", aggfunc="first"
                ).reset_index()

                columnes_data = [c for c in df_pivot.columns if c != "Botiga"]

                # Columna de % respecte el preu de botiga (referència), calculada
                # a partir de l'últim preu conegut de cada botiga.
                if preu_referencia:
                    percentatges = []
                    for _, fila in df_pivot.iterrows():
                        ultim = _ultim_valor_no_nul(fila, columnes_data)
                        if ultim is None:
                            percentatges.append(None)
                        else:
                            percentatges.append((ultim - preu_referencia) / preu_referencia)
                else:
                    percentatges = [None] * len(df_pivot)

                df_pivot.insert(1, "% vs preu botiga", percentatges)

                # Ordena les files pel % vs preu botiga, de més barat a més
                # car. Les botigues sense % calculable (perquè el producte
                # no té preu de referència, o encara no té cap preu) queden
                # al final.
                df_pivot = df_pivot.sort_values(
                    "% vs preu botiga", ascending=True, na_position="last"
                ).reset_index(drop=True)

            nom_full = _nom_full_valid(prod["nom"])
            df_pivot.to_excel(writer, sheet_name=nom_full, index=False)

            ws = writer.sheets[nom_full]

            if not df_pivot.empty:
                n_rows = len(df_pivot)

                # Capçalera en negreta
                for c_idx in range(1, len(df_pivot.columns) + 1):
                    ws.cell(row=1, column=c_idx).font = BOLD_FONT

                # Columna A (Botiga) en negreta, i columna B (%) formatada com a
                # percentatge amb signe i color segons sigui més car/barat.
                for r_idx in range(n_rows):
                    fila_excel = r_idx + 2
                    ws.cell(row=fila_excel, column=1).font = BOLD_FONT

                    cel_pct = ws.cell(row=fila_excel, column=2)
                    valor_pct = df_pivot.iloc[r_idx]["% vs preu botiga"]
                    if pd.notna(valor_pct):
                        cel_pct.number_format = "+0.0%;-0.0%"
                        cel_pct.font = PCT_POSITIU_FONT if valor_pct > 0 else PCT_NEGATIU_FONT
                    else:
                        cel_pct.value = "—"

                # Fixa (freeze) la columna A (Botiga) i B (%) en fer scroll,
                # a més de la fila de capçalera.
                ws.freeze_panes = "C2"

                # Ajusta l'amplada de cada columna al contingut més llarg
                # que hi ha en ella (capçalera inclosa). La columna de % es
                # tracta a part perquè el valor guardat és numèric (0.083)
                # però es mostra formatat com a percentatge (+8.3%).
                for c_idx in range(1, len(df_pivot.columns) + 1):
                    col_letter = get_column_letter(c_idx)
                    if c_idx == 2:
                        ws.column_dimensions[col_letter].width = 16
                        continue
                    llargada_max = 0
                    for r_idx in range(1, n_rows + 2):
                        valor = ws.cell(row=r_idx, column=c_idx).value
                        if valor is not None:
                            llargada_max = max(llargada_max, len(str(valor)))
                    ws.column_dimensions[col_letter].width = llargada_max + 2

            # Pinta de taronja i en cursiva les cel·les amb preu introduït a mà,
            # i dóna format de dos decimals a totes les cel·les de preu.
            # Es busca per nom de botiga (no per posició), ja que les files
            # estan ordenades pel % i ja no coincideixen amb l'ordre original.
            if columnes_data:
                df_manual_idx = df_manual.set_index("Botiga") if not df_manual.empty else None
                for r_idx in range(len(df_pivot)):
                    nom_botiga_fila = df_pivot.iloc[r_idx]["Botiga"]
                    for c_offset, col_name in enumerate(columnes_data):
                        cell = ws.cell(row=r_idx + 2, column=c_offset + 3)
                        if cell.value is not None:
                            cell.number_format = "0.00"

                        es_manual = False
                        if df_manual_idx is not None and nom_botiga_fila in df_manual_idx.index:
                            try:
                                es_manual = bool(df_manual_idx.loc[nom_botiga_fila, col_name])
                            except KeyError:
                                es_manual = False
                        if es_manual:
                            cell.fill = MANUAL_FILL
                            cell.font = MANUAL_FONT

            # Afegir gràfic de línies natiu si hi ha dades.
            # Cada FILA (botiga) és una sèrie; només es grafica el bloc de
            # preus (columnes de data), no la columna de %. El títol de cada
            # sèrie s'assigna a mà a partir del nom de la botiga (columna A),
            # ja que les columnes de dades ja no són contigües amb la A.
            GENERAR_GRAFIC = False  # posa-ho a True si el vols tornar a activar
            if GENERAR_GRAFIC and not df_pivot.empty and columnes_data:
                n_rows = df_pivot.shape[0]
                primera_col_dades = 3  # C
                ultima_col_dades = 2 + len(columnes_data)

                chart = LineChart()
                chart.title = f"Evolució de preu — {prod['nom']}"
                chart.y_axis.title = "Preu (€)"
                chart.x_axis.title = "Data"
                chart.style = 2
                chart.width = 24
                chart.height = 12

                data = Reference(
                    ws, min_col=primera_col_dades, max_col=ultima_col_dades,
                    min_row=1, max_row=n_rows + 1
                )
                chart.add_data(data, titles_from_data=False, from_rows=True)

                cats = Reference(
                    ws, min_col=primera_col_dades, max_col=ultima_col_dades,
                    min_row=1, max_row=1
                )
                chart.set_categories(cats)

                # Assigna el nom de cada sèrie (fila) a partir de la columna A.
                for i, serie in enumerate(chart.series):
                    fila_excel = i + 2
                    serie.tx = SeriesLabel(strRef=StrRef(f"'{nom_full}'!$A${fila_excel}"))

                col_grafic = get_column_letter(ultima_col_dades + 2)
                ws.add_chart(chart, f"{col_grafic}2")

    return path