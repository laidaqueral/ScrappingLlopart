"""
Mòdul de base de dades per a l'app de seguiment de preus.
Utilitza SQLite (un sol fitxer, sense necessitat de servidor).
"""
import sqlite3
from datetime import datetime
from contextlib import contextmanager

DB_PATH = "preus.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS productes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nom TEXT NOT NULL UNIQUE,
                categoria TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS urls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                producte_id INTEGER NOT NULL,
                botiga TEXT NOT NULL,
                url TEXT NOT NULL,
                selector_css TEXT NOT NULL,
                index_element INTEGER DEFAULT 0,
                actiu INTEGER DEFAULT 1,
                FOREIGN KEY (producte_id) REFERENCES productes(id)
            )
        """)
        # Migració suau per bases de dades creades amb una versió anterior
        # de l'esquema, que no tenien la columna index_element.
        columnes = [c[1] for c in conn.execute("PRAGMA table_info(urls)").fetchall()]
        if "index_element" not in columnes:
            conn.execute("ALTER TABLE urls ADD COLUMN index_element INTEGER DEFAULT 0")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS historic_preus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_id INTEGER NOT NULL,
                preu REAL,
                data_hora TEXT NOT NULL,
                error TEXT,
                FOREIGN KEY (url_id) REFERENCES urls(id)
            )
        """)


# ---------- PRODUCTES ----------
def afegir_producte(nom, categoria=""):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO productes (nom, categoria) VALUES (?, ?)",
            (nom, categoria)
        )


def llistar_productes():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM productes ORDER BY nom").fetchall()


def eliminar_producte(producte_id):
    with get_conn() as conn:
        url_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM urls WHERE producte_id=?", (producte_id,)
        ).fetchall()]
        for uid in url_ids:
            conn.execute("DELETE FROM historic_preus WHERE url_id=?", (uid,))
        conn.execute("DELETE FROM urls WHERE producte_id=?", (producte_id,))
        conn.execute("DELETE FROM productes WHERE id=?", (producte_id,))


# ---------- URLS ----------
def afegir_url(producte_id, botiga, url, selector_css, index_element=0):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO urls (producte_id, botiga, url, selector_css, index_element) VALUES (?, ?, ?, ?, ?)",
            (producte_id, botiga, url, selector_css, index_element)
        )


def llistar_urls(producte_id=None):
    with get_conn() as conn:
        if producte_id:
            return conn.execute(
                "SELECT * FROM urls WHERE producte_id=? ORDER BY botiga", (producte_id,)
            ).fetchall()
        return conn.execute("SELECT * FROM urls ORDER BY botiga").fetchall()


def eliminar_url(url_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM historic_preus WHERE url_id=?", (url_id,))
        conn.execute("DELETE FROM urls WHERE id=?", (url_id,))


def actualitzar_selector(url_id, nou_selector, nou_index=0):
    with get_conn() as conn:
        conn.execute(
            "UPDATE urls SET selector_css=?, index_element=? WHERE id=?",
            (nou_selector, nou_index, url_id)
        )


# ---------- HISTORIC PREUS ----------
def guardar_preu(url_id, preu, error=None):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO historic_preus (url_id, preu, data_hora, error) VALUES (?, ?, ?, ?)",
            (url_id, preu, datetime.now().isoformat(timespec="seconds"), error)
        )


def historic_per_producte(producte_id):
    """Retorna tots els registres de preus de totes les urls d'un producte."""
    with get_conn() as conn:
        return conn.execute("""
            SELECT h.data_hora, u.botiga, h.preu, h.error
            FROM historic_preus h
            JOIN urls u ON u.id = h.url_id
            WHERE u.producte_id = ?
            ORDER BY h.data_hora
        """, (producte_id,)).fetchall()


def ultim_preu(url_id):
    with get_conn() as conn:
        row = conn.execute("""
            SELECT preu, data_hora FROM historic_preus
            WHERE url_id=? AND preu IS NOT NULL
            ORDER BY data_hora DESC LIMIT 1
        """, (url_id,)).fetchone()
        return row
