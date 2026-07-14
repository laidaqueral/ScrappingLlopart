"""
Script d'actualitzacio automatica de preus - Llopart
Executa el mateix que el boto 'Actualitza preus ara' de l'app pero sense
obrir cap interficie grafica. Ideal per al Programador de tasques de Windows.

Com executar manualment per provar:
    python actualitzar_preus_auto.py

Com configurar al Programador de tasques de Windows:
    Programa: python.exe  (o la ruta completa, ex: C:\Python312\python.exe)
    Arguments: "C:\ruta\carpeta\actualitzar_preus_auto.py"
    Inici en: C:\ruta\carpeta\   <-- important! ha de ser la carpeta de l'app
"""

import os
import sys
from datetime import datetime

# Assegura que el script troba els moduls de l'app (database, scraper, excel_export)
# tant si s'executa directament com des del Programador de tasques.
CARPETA_APP = os.path.dirname(os.path.abspath(__file__))
os.chdir(CARPETA_APP)
sys.path.insert(0, CARPETA_APP)

import database as db
from scraper import obtenir_preu_amb_fallback
from excel_export import exportar_excel

LOG_PATH = os.path.join(CARPETA_APP, "actualitzacio_auto.log")


def log(missatge):
    ara = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linia = f"[{ara}] {missatge}"
    print(linia)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(linia + "\n")


def main():
    log("=" * 55)
    log("Inici actualitzacio automatica de preus")

    db.init_db()

    productes = db.llistar_productes()
    if not productes:
        log("No hi ha cap producte configurat. Sortint.")
        return

    total_urls = 0
    total_ok = 0
    total_error = 0

    for producte in productes:
        log(f"--- Producte: {producte['nom']} ---")
        urls = db.llistar_urls(producte["id"])

        for u in urls:
            total_urls += 1
            botiga = u["botiga"]

            # URLs sense selector = introduides manualment, no s'intenten scrapejar
            if not u["selector_css"]:
                log(f"  {botiga}: sense scraping (preu manual), s'omet.")
                continue

            log(f"  {botiga}: consultant {u['url'][:60]}...")
            preu, error, nou_sel, nou_idx, nou_pw = obtenir_preu_amb_fallback(
                u["url"],
                u["selector_css"],
                usar_playwright=bool(u["usa_playwright"]),
                index=u["index_element"]
            )

            db.guardar_preu(u["id"], preu, error)

            # Si el selector ha canviat (fallback ha trobat un millor), l'actualitzem
            if nou_sel and (nou_sel != u["selector_css"] or nou_idx != u["index_element"]):
                db.actualitzar_selector(u["id"], nou_sel, nou_idx, nou_pw)
                log(f"  {botiga}: selector actualitzat a '{nou_sel}'")

            if preu is not None:
                log(f"  {botiga}: OK → {preu:.2f} €")
                total_ok += 1
            else:
                log(f"  {botiga}: ERROR → {error}")
                total_error += 1

    log(f"Scraping finalitzat: {total_ok} ok, {total_error} errors de {total_urls} URLs.")

    log("Generant Excel...")
    try:
        path = exportar_excel()
        log(f"Excel generat correctament: {path}")
    except PermissionError:
        log("ERROR: No s'ha pogut desar l'Excel perque esta obert. Tanca'l i torna a executar.")
    except Exception as exc:
        log(f"ERROR generant Excel: {exc}")

    log("Actualitzacio completada.")
    log("=" * 55)


if __name__ == "__main__":
    main()