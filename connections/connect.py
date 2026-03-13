"""
connections/connect.py — Fonctions de connexion réutilisables.

Usage :
    from connections.connect import make_engine, test_connection
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from connections.config import connection_string, MYSQL_HOST, MYSQL_PORT, MYSQL_DATABASE

MAX_RETRIES = 5
RETRY_DELAY = 10  # secondes


def make_engine(database: str = MYSQL_DATABASE):
    engine = create_engine(connection_string(database), pool_pre_ping=True)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return engine
        except Exception as exc:
            if attempt == MAX_RETRIES:
                raise
            print(f"  ⚠ Connexion echouee (tentative {attempt}/{MAX_RETRIES}): {exc.__class__.__name__} — retry dans {RETRY_DELAY}s")
            time.sleep(RETRY_DELAY)
    return engine


def test_connection(database: str = MYSQL_DATABASE) -> bool:
    try:
        engine = make_engine(database)
        with engine.connect() as conn:
            version = conn.execute(text("SELECT VERSION()")).scalar()
            db_now  = conn.execute(text("SELECT NOW()")).scalar()
            print(f"  Connexion OK  →  {MYSQL_HOST}:{MYSQL_PORT}/{database}")
            print(f"  MySQL version : {version}")
            print(f"  Heure serveur : {db_now}")
        return True
    except Exception as exc:
        print(f"  ERREUR connexion : {exc}")
        return False


if __name__ == "__main__":
    print("=== Test de connexion MySQL Perf_commissions ===\n")
    ok = test_connection()
    if ok:
        try:
            engine = make_engine()
            with engine.connect() as conn:
                tables = conn.execute(text("SHOW TABLES")).fetchall()
                print(f"\n  Tables : {[t[0] for t in tables]}")
        except Exception:
            print("\n  Base non trouvée (lancer mysql/setup_db.py d'abord)")
    sys.exit(0 if ok else 1)
