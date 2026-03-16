import sys
import os
from sqlalchemy import text

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from connections.connect import make_engine

def populate():
    engine = make_engine()
    with engine.connect() as conn:
        print("Injection des superviseurs...")
        conn.execute(text("""
            INSERT IGNORE INTO superviseur_info (superviseur_name, type_superviseur, target_mensuel) 
            SELECT DISTINCT superviseur, 'Classiques', 2340 
            FROM agent_perf_info 
            WHERE superviseur IS NOT NULL AND superviseur != ''
        """))
        conn.execute(text("""
            UPDATE superviseur_info 
            SET type_superviseur = 'Mercenaire' 
            WHERE UPPER(superviseur_name) IN ('ROLAND', 'SAMUEL BOSSOU', 'VINCENT DE PAULE', 'VINCENT DE PAUL')
        """))
        conn.commit()
        print("✓ Terminé.")

if __name__ == '__main__':
    populate()