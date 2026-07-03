"""
Mòdul de scraping. Per cada URL es fa servir un selector CSS (configurat
per l'usuari des de la interfície) que apunta a l'element HTML que conté el preu.

Funciona amb webs estàtiques (requests + BeautifulSoup). Si una botiga carrega
el preu amb JavaScript, cal activar el mode Playwright (veure usar_playwright=True).
"""
import re
import json
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def _netejar_preu(text):
    """Converteix '49,90 €' / '€49.90' / '49.90€' a float 49.90"""
    if not text:
        return None
    text = text.strip()
    # treu tot el que no sigui dígit, coma o punt
    net = re.sub(r"[^\d,.]", "", text)
    if not net:
        return None
    # Format europeu: 1.234,56 -> 1234.56
    if "," in net and "." in net:
        net = net.replace(".", "").replace(",", ".")
    elif "," in net:
        net = net.replace(",", ".")
    try:
        return float(net)
    except ValueError:
        return None


# Llista de selectors habituals de preu en e-commerce, per ordre de probabilitat.
# S'hi van afegint selectors a mesura que es detecten noves botigues.
SELECTORS_COMUNS = [
    '[itemprop="price"]',
    'meta[property="product:price:amount"]',
    'meta[itemprop="price"]',
    '.price .amount',
    'span.price',
    '.product-price',
    '.precio',
    '.precio-actual',
    '.current-price',
    '#priceblock_ourprice',
    '#priceblock_dealprice',
    '.a-price .a-offscreen',
    '.a-price-whole',
    '.price-current',
    '.product__price',
    '.product-price__amount',
    '.woocommerce-Price-amount',
    '.price--withoutTax',
    'div.price',
    '.price',
    '[data-price]',
    '[class*="price"]',
]


def _candidats_json_ld(soup):
    """Moltes botigues (Woocommerce, Shopify, Prestashop...) inclouen el
    preu en un bloc de 'dades estructurades' pensat per a Google, separat
    del disseny visual de la pàgina. És una font molt fiable i no depèn
    del CSS, així que és la primera alternativa que provem si els
    selectors habituals no troben res."""
    candidats = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (TypeError, ValueError):
            continue
        candidats.extend(_cercar_preus_json(data))
    return candidats


def _cercar_preus_json(node, context=""):
    """Cerca recursivament claus de preu ('price', 'lowPrice', 'highPrice')
    dins d'un bloc de dades JSON-LD, que pot tenir estructures anidades."""
    trobats = []
    if isinstance(node, dict):
        nom_producte = node.get("name") or context
        for clau in ("price", "lowPrice", "highPrice"):
            if clau in node:
                preu = _netejar_preu(str(node[clau]))
                if preu is not None and 0 < preu < 100000:
                    trobats.append({
                        "selector": f"json-ld:{clau}",
                        "index": 0,
                        "preu": preu,
                        "text": str(node[clau]),
                        "context": nom_producte or "(dades estructurades JSON-LD)",
                    })
        for v in node.values():
            trobats.extend(_cercar_preus_json(v, nom_producte))
    elif isinstance(node, list):
        for item in node:
            trobats.extend(_cercar_preus_json(item, context))
    return trobats


def _obtenir_html(url, usar_playwright, timeout):
    if usar_playwright:
        return _obtenir_html_playwright(url, timeout)
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def _text_element(element):
    """Treu el text rellevant d'un element, ja sigui per get_text() o per
    atribut content/data-price (cas de <meta> o divs amb data-price)."""
    if element.name == "meta":
        return element.get("content", "")
    if element.has_attr("data-price"):
        return element.get("data-price", "")
    return element.get_text()


def detectar_preu(url, usar_playwright=False, timeout=15):
    """
    Prova automàticament una llista de selectors habituals. A diferència
    d'una detecció simple, recull TOTS els candidats trobats (pot haver-hi
    més d'un preu a la pàgina, p.ex. diferents formats/mides d'un mateix
    producte) perquè l'usuari pugui triar el correcte.

    Retorna (preu, selector, error) per compatibilitat retroactiva — es
    queda amb el primer candidat — i a més deixa els candidats complets
    disponibles via detectar_candidats().
    """
    candidats, error = detectar_candidats(url, usar_playwright, timeout)
    if not candidats:
        return None, None, error
    millor = candidats[0]
    return millor["preu"], millor["selector"], None


def detectar_candidats(url, usar_playwright=False, timeout=15):
    """
    Retorna (llista_candidats, error). Cada candidat és un dict:
    {selector, index (posició entre els elements que casen amb el selector),
     preu, text, context} on 'context' és un tros de text proper (per
    exemple el nom/format del producte) per ajudar a triar quin és el correcte.
    """
    try:
        html = _obtenir_html(url, usar_playwright, timeout)
    except requests.exceptions.RequestException as e:
        return [], f"Error de connexió: {e}"
    except Exception as e:
        return [], f"Error inesperat carregant la pàgina: {e}"

    soup = BeautifulSoup(html, "html.parser")
    candidats = []
    vistos = set()

    # 1) Primer provem les dades estructurades JSON-LD (molt fiables i
    #    independents del disseny visual de la pàgina).
    for c in _candidats_json_ld(soup):
        clau = (round(c["preu"], 2),)
        if clau not in vistos:
            vistos.add(clau)
            candidats.append(c)

    # 2) Després, la llista de selectors CSS habituals.
    for sel in SELECTORS_COMUNS:
        try:
            elements = soup.select(sel)
        except Exception:
            continue
        for idx, element in enumerate(elements):
            text = _text_element(element)
            preu = _netejar_preu(text)
            if preu is None or not (0 < preu < 100000):
                continue

            clau = (round(preu, 2),)
            if clau in vistos:
                # Evitem mostrar el mateix preu trobat per selectors diferents
                # com a candidats duplicats.
                continue
            vistos.add(clau)

            contexte = _contexte_proper(element)
            candidats.append({
                "selector": sel,
                "index": idx,
                "preu": preu,
                "text": text.strip(),
                "context": contexte,
            })

    return candidats, (None if candidats else (
        "No s'ha pogut trobar cap preu amb els selectors coneguts."
    ))


def _contexte_proper(element):
    """Busca text proper a l'element de preu (mida/format, nom de variant...)
    mirant elements germans i el contenidor pare, per ajudar a distingir
    quin preu correspon a quin format del producte (ex: 37,5cl vs 75cl)."""
    trossos = []

    pare = element.parent
    nivells = 0
    while pare is not None and nivells < 3:
        text_pare = pare.get_text(" ", strip=True)
        if text_pare and len(text_pare) < 200:
            trossos.append(text_pare)
            break
        pare = pare.parent
        nivells += 1

    if element.previous_sibling:
        text_sib = getattr(element.previous_sibling, "get_text", lambda **k: str(element.previous_sibling))()
        if text_sib:
            trossos.insert(0, text_sib.strip())

    contexte = " | ".join(t for t in trossos if t)
    return contexte[:150] if contexte else "(sense context detectat)"


def detectar_candidats_amb_fallback(url, timeout=15):
    """
    Intenta detectar el preu de la manera ràpida primer (peticions normals +
    JSON-LD + selectors CSS). Si no troba res I Playwright està instal·lat
    a l'ordinador, ho torna a provar automàticament amb Playwright (útil
    per a webs que carreguen el preu amb JavaScript), sense que l'usuari
    hagi de marcar-ho manualment.

    Retorna (candidats, error, es_necessita_playwright: bool).
    """
    candidats, error = detectar_candidats(url, usar_playwright=False, timeout=timeout)
    if candidats:
        return candidats, None, False

    try:
        import playwright  # noqa: F401
    except ImportError:
        # Playwright no instal·lat: ens quedem amb el resultat/error original.
        return candidats, error, False

    candidats_pw, error_pw = detectar_candidats(url, usar_playwright=True, timeout=timeout)
    if candidats_pw:
        return candidats_pw, None, True

    return [], error_pw or error, False


def obtenir_preu(url, selector_css, usar_playwright=False, timeout=15, index=0):
    """
    Llegeix el preu fent servir un selector concret ja conegut, agafant
    l'element número 'index' entre tots els que casen amb el selector
    (útil quan una pàgina té diversos preus, p.ex. diferents formats/mides
    d'un mateix producte).
    Retorna (preu: float|None, error: str|None)
    """
    try:
        html = _obtenir_html(url, usar_playwright, timeout)
        soup = BeautifulSoup(html, "html.parser")
        elements = soup.select(selector_css)
        if not elements:
            return None, f"Selector '{selector_css}' no trobat a la pàgina"
        if index >= len(elements):
            index = 0  # si la pàgina ha canviat i hi ha menys elements, agafem el primer
        element = elements[index]

        preu = _netejar_preu(_text_element(element))
        if preu is None:
            return None, f"No s'ha pogut interpretar el preu del text: '{element.get_text()}'"
        return preu, None

    except requests.exceptions.RequestException as e:
        return None, f"Error de connexió: {e}"
    except Exception as e:
        return None, f"Error inesperat: {e}"


def obtenir_preu_amb_fallback(url, selector_css, usar_playwright=False, timeout=15, index=0):
    """
    Intenta llegir el preu amb el selector+index ja guardats. Si falla,
    torna a intentar detectar-lo automàticament: primer amb JSON-LD i els
    selectors CSS habituals, i si tampoc troba res, amb Playwright (si està
    instal·lat), agafant el primer candidat trobat.
    Retorna (preu, error, nou_selector_o_None, nou_index_o_None, nou_usar_playwright_o_None).
    """
    preu, error = obtenir_preu(url, selector_css, usar_playwright, timeout, index)
    if preu is not None:
        return preu, None, None, None, None

    candidats, error2, es_necessita_playwright = detectar_candidats_amb_fallback(url, timeout)
    if candidats:
        c = candidats[0]
        return c["preu"], None, c["selector"], c["index"], es_necessita_playwright

    return None, error2 or error, None, None, None


def _obtenir_html_playwright(url, timeout):
    """Per a webs que carreguen el preu amb JavaScript."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url, timeout=timeout * 1000)
        page.wait_for_timeout(2000)  # espera que carregui el JS
        html = page.content()
        browser.close()
        return html