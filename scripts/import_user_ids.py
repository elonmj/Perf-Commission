"""
scripts/import_user_ids.py - Importe les ID Pulse depuis un fichier Excel 
pour mettre a jour la table agent_perf_info dans MySQL.
"""

import sys
import os
import argparse
from pathlib import Path
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from connections.connect import make_engine
from connections.config import TABLE_AGENT_INFO

DEFAULT_INPUT = ROOT / "data" / "UserID.xlsx"

def import_user_ids(input_path: Path):
    if not input_path.exists():
        print(f"ERREUR : Fichier introuvable - {input_path}")
        sys.exit(1)

    print(f"Lecture de : {input_path.name}")
    df = pd.read_excel(input_path)

    df.columns = df.columns.str.strip().str.lower()
    
    col_user = next((c for c in df.columns if 'user' in c or 'nom' in c), None)
    col_id = next((c for c in df.columns if 'id' in c or 'pulse' in c), None)

    if not col_user or not col_id:
        print(f"ERREUR : Colonnes introuvables. Colonnes actuelles : {df.columns.tolist()}")
        sys.exit(1)

    print(f"Mapping détecté : Username -> '{col_user}', ID -> '{col_id}'")
    df = df[df[col_user].notna() & df[col_id].notna()]
    
    engine = make_engine()
    
    with engine.connect() as conn:
        try:
            conn.execute(text(f"ALTER TABLE `{TABLE_AGENT_INFO}` ADD COLUMN `id_pulse` VARCHAR(100) DEFAULT NULL"))
            conn.commit()
            print("Colonne `id_pulse` ajoutee a la table.")
        except Exception:
            pass

    updated_count = 0
    with engine.connect() as conn:
        for _, row in df.iterrows():
            username = str(row[col_user]).strip()
            id_pulse = str(row[col_id]).strip()
            
            if id_pulse.endswith('.0'):
                id_pulse = id_pulse[:-2]

            upd = conn.execute(text(
                f"UPDATE `{TABLE_AGENT_INFO}` SET `id_pulse` = :id_pulse WHERE `user_name` = :username"
            ), {"id_pulse": id_pulse, "username": username})
            
            updated_count += upd.rowcount
            
        conn.commit()

    print(f"Succès : {updated_count} IDs ont été mis à jour.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Chemin du fichier Excel")
    args = parser.parse_args()
    import_user_ids(Path(args.input))

if __name__ == "__main__":
    main()
