# Seguiment de preus — Escumosos

Aplicació per fer seguiment del preu d'uns productes (caves, escumosos...) en
diferents webs de venda, de manera visual (gràfics) i exportable a Excel
(un full per producte).

## Instal·lació

```bash
pip install -r requirements.txt
```

## Execució

```bash
streamlit run app.py
```

S'obrirà automàticament al navegador (normalment a http://localhost:8501).

## Com funciona

1. **Pestanya "Productes"**: afegeix els productes que vols seguir (ex: "Cava
   Brut Nature 75cl").
2. **Pestanya "URLs / Botigues"**: per cada producte, afegeix les URLs de les
   diferents webs on es ven, indicant el **selector CSS** del preu.
   - Per trobar el selector: obre la pàgina al navegador → clic dret sobre el
     preu → "Inspeccionar" → clic dret sobre l'HTML ressaltat al inspector →
     "Copy" → "Copy selector".
   - Pots provar el selector amb el botó "🧪 Provar" abans de guardar-lo.
3. **Pestanya "Dashboard"**: selecciona un producte i prem "Actualitza preus
   ara" per fer scraping de totes les seves URLs. Veuràs un gràfic amb
   l'evolució de preus de cada botiga.
4. **Pestanya "Exportar Excel"**: genera un `.xlsx` amb un full per producte
   (taula + gràfic natiu d'Excel).

## Automatitzar l'actualització diària de preus

Per no haver d'obrir l'app cada dia, pots crear un script que s'executi sol:

Crea un fitxer `actualitza_diari.py`:

```python
import database as db
from scraper import obtenir_preu

db.init_db()
for u in db.llistar_urls():
    preu, error = obtenir_preu(u["url"], u["selector_css"])
    db.guardar_preu(u["id"], preu, error)
print("Actualització completada")
```

I programa'l:
- **Linux/Mac**: amb `cron` (`crontab -e` i afegir una línia tipus
  `0 8 * * * cd /ruta/al/projecte && python actualitza_diari.py`)
- **Windows**: amb el "Programador de tasques" (Task Scheduler)

## Webs amb JavaScript (preu no carrega amb el mètode estàndard)

Si en provar un selector dona error perquè la web carrega el preu amb
JavaScript (és habitual en e-commerce moderns), cal:

```bash
pip install playwright
playwright install chromium
```

I a `app.py`, quan es crida `obtenir_preu(...)`, afegir `usar_playwright=True`.

## Estructura de fitxers

```
escumosos_app/
├── app.py              # Interfície (Streamlit)
├── database.py         # Base de dades SQLite
├── scraper.py           # Lògica de scraping
├── excel_export.py      # Generació de l'Excel
├── requirements.txt
├── preus.db             # Es crea automàticament en primer ús
└── README.md
```

## Limitacions a tenir en compte

- Algunes webs bloquegen el scraping automàtic (Cloudflare, captatxes...). Si
  passa, cal investigar alternatives (APIs oficials de la botiga si en
  tenen, o reduir la freqüència de consultes).
- Revisa els Termes i Condicions de cada web abans de fer scraping habitual.
- Si una botiga canvia el disseny de la seva pàgina, el selector CSS pot
  quedar obsolet i caldrà actualitzar-lo des de la pestanya "URLs / Botigues".
