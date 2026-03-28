"""
scripts/03_upload.py -- Etape 3 : chargement initial dans MySQL.

Lit les fichiers cumulatifs (GADD_cumul.xlsx, ADS_cumul.xlsx) et les outputs
agent_info, puis fait un chargement complet dans les tables MySQL :
  - daily_gadd  (TRUNCATE + INSERT)
  - daily_ads   (TRUNCATE + INSERT)

A utiliser pour le tout premier chargement ou pour un re-chargement complet.
Pour les mises a jour quotidiennes, utiliser 04_sync.py.

Usage :
  py -3 scripts/03_upload.py
  py -3 scripts/03_upload.py --confirm   (pas de confirmation interactive)
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).parent.parent
OUTPUTS = ROOT / "outputs"
CUMUL = ROOT / "cumul"

sys.path.insert(0, str(ROOT))
from connections.config import (
    MYSQL_DATABASE, TABLE_DAILY_GADD, TABLE_DAILY_ADS,
    
)
from connections.connect import make_engine


def load_cumul_to_long(path: Path, value_col: str) -> pd.DataFrame:
    """
    Charge un fichier cumulatif wide (Username, dates...) et le convertit
    en format long (user_name, perf_date, value_col).
    """
    df = pd.read_excel(path, sheet_name=0, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]

    # Filtrer Username invalides
    df = df[df["Username"].notna()]
    df = df[df["Username"].astype(str).str.strip() != ""]
    df = df[~df["Username"].astype(str).str.strip().str.replace(".", "", regex=False)
            .str.replace("-", "", regex=False).str.replace("_", "", regex=False)
            .str.isdigit()]

    date_cols = [c for c in df.columns if c != "Username"]

    # Filtrer dates futures
    from datetime import date as dt_date
    today = dt_date.today()
    valid_date_cols = []
    for c in date_cols:
        try:
            d = pd.to_datetime(c, format="%d/%m/%Y").date()
            if d <= today:
                valid_date_cols.append(c)
        except Exception:
            pass

    melted = df.melt(id_vars=["Username"], value_vars=valid_date_cols,
                     var_name="date_str", value_name=value_col)
    melted = melted.rename(columns={"Username": "user_name"})

    # Convertir date string DD/MM/YYYY en date
    melted["perf_date"] = pd.to_datetime(melted["date_str"], format="%d/%m/%Y", errors="coerce").dt.date
    melted = melted.dropna(subset=["perf_date"])

    # Convertir valeur
    melted[value_col] = pd.to_numeric(melted[value_col], errors="coerce").fillna(0).astype(int)

    # Exclure les 0 pour alleger
    melted = melted[melted[value_col] != 0]

    return melted[["user_name", "perf_date", value_col]].reset_index(drop=True)


def upload_daily_metric(engine, cumul_path: Path, table: str, value_col: str):
    """Charge un fichier cumulatif dans la table daily correspondante."""
    if not cumul_path.exists():
        print(f"  WARN: {cumul_path.name} introuvable. Table {table} ignoree.")
        return

    print(f"  Chargement {cumul_path.name} ...")
    df_long = load_cumul_to_long(cumul_path, value_col)

    # Selectionner colonnes pour la table (user_name, perf_date, value_col)
    df_upload = df_long[["user_name", "perf_date", value_col]].copy()
    # Dedup case-insensitive (MySQL utf8mb4_unicode_ci)
    df_upload["_key"] = df_upload["user_name"].str.lower() + "|" + df_upload["perf_date"].astype(str)
    df_upload = df_upload.drop_duplicates(subset=["_key"], keep="last").drop(columns=["_key"])

    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {table}"))

    df_upload.to_sql(table, engine, if_exists="append", index=False)
    dates_range = f"{df_upload['perf_date'].min()} -> {df_upload['perf_date'].max()}"
    print(f"  {table} : {len(df_upload)} lignes chargees ({dates_range})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", action="store_true",
                        help="Skip interactive confirmation")
    args = parser.parse_args()

    gadd_cumul = CUMUL / "GADD_cumul.xlsx"
    ads_cumul = CUMUL / "ADS_cumul.xlsx"

    print("=== 03_upload.py -- Chargement initial MySQL ===\n")
    print(f"  Base cible : {MYSQL_DATABASE}")
    print(f"  GADD cumul : {'OK' if gadd_cumul.exists() else 'MANQUANT'}")
    print(f"  ADS cumul  : {'OK' if ads_cumul.exists() else 'MANQUANT'}")
    print()

    if not args.confirm:
        resp = input("ATTENTION : cette operation va TRUNCATE les tables. Continuer ? (oui/non) : ")
        if resp.strip().lower() not in ("oui", "o", "yes", "y"):
            print("Annule.")
            sys.exit(0)

    engine = make_engine(MYSQL_DATABASE)

    # Agent info
        print()

    # GADD
    upload_daily_metric(engine, gadd_cumul, TABLE_DAILY_GADD, "gadd")
    print()

    # ADS
    upload_daily_metric(engine, ads_cumul, TABLE_DAILY_ADS, "ads")
    print()

    print("Chargement initial termine.")
    print("Pour les mises a jour quotidiennes : py -3 scripts/04_sync.py")


if __name__ == "__main__":
    main()
