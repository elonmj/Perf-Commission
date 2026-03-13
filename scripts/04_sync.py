"""
scripts/04_sync.py -- Etape 4 : synchronisation quotidienne vers MySQL.

Lit les outputs du jour (gadd_long, ads_long, agent_info) produits par
01_process.py et fait un UPSERT (INSERT ... ON DUPLICATE KEY UPDATE) :
  - daily_gadd  : clef (user_name, perf_date)
  - daily_ads   : clef (user_name, perf_date)
  - agent_perf_info : clef (user_name)

Usage :
  py -3 scripts/04_sync.py
"""

import sys
import json
from pathlib import Path
from datetime import datetime

import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).parent.parent
OUTPUTS = ROOT / "outputs"

sys.path.insert(0, str(ROOT))
from connections.config import (
    MYSQL_DATABASE, TABLE_DAILY_GADD, TABLE_DAILY_ADS,
    TABLE_AGENT_INFO, MSISDN_COLS, AGENT_COLUMNS,
    SYNC_ERRORS_FILE,
)
from connections.connect import make_engine


def find_latest(prefix: str) -> Path | None:
    files = sorted(
        OUTPUTS.glob(f"{prefix}_*.xlsx"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    return files[0] if files else None


def upsert_agent_info(engine, path: Path) -> list[str]:
    """UPSERT agent_perf_info (cle = user_name) — batch mode. Retourne les erreurs."""
    errors = []
    df = pd.read_excel(path)
    for col in MSISDN_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    # Filtrer user_name invalides
    df["user_name"] = df["user_name"].astype(str).str.strip()
    invalid_mask = (
        df["user_name"].isna() | (df["user_name"] == "") |
        df["user_name"].str.replace(".", "", regex=False)
        .str.replace("-", "", regex=False).str.replace("_", "", regex=False)
        .str.isdigit()
    )
    n_invalid = invalid_mask.sum()
    if n_invalid > 0:
        errors.append(f"agent_perf_info : {n_invalid} lignes ignorees (user_name invalide)")
    df = df[~invalid_mask]

    df = df.drop_duplicates(subset=["user_name"], keep="last")

    update_cols = [c for c in AGENT_COLUMNS if c != "user_name" and c in df.columns]
    update_clause = ", ".join(f"{c} = VALUES({c})" for c in update_cols)

    all_cols = ["user_name"] + update_cols
    placeholders = ", ".join(f"%({c})s" for c in all_cols)
    col_names = ", ".join(all_cols)

    sql_str = (
        f"INSERT INTO {TABLE_AGENT_INFO} ({col_names}) "
        f"VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {update_clause}"
    )

    rows = df[all_cols].to_dict("records")
    clean_rows = []
    for row in rows:
        clean = {}
        for k, v in row.items():
            if v is None or (not isinstance(v, str) and pd.isna(v)):
                clean[k] = None
            elif k in MSISDN_COLS:
                try:
                    clean[k] = int(v)
                except (ValueError, TypeError):
                    clean[k] = None
            else:
                clean[k] = str(v) if v is not None else None
        clean_rows.append(clean)

    # Use raw connection for batch executemany
    raw_conn = engine.raw_connection()
    try:
        cursor = raw_conn.cursor()
        cursor.executemany(sql_str, clean_rows)
        raw_conn.commit()
    except Exception as e:
        errors.append(f"agent_perf_info : erreur MySQL — {e}")
        raw_conn.rollback()
    finally:
        raw_conn.close()

    print(f"  agent_perf_info : {len(clean_rows)} agents synchronises")
    return errors


def upsert_daily_metric(engine, path: Path, table: str, value_col: str) -> list[str]:
    """UPSERT daily_gadd ou daily_ads (cle = user_name + perf_date) — batch. Retourne les erreurs."""
    errors = []
    df = pd.read_excel(path)
    df["user_name"] = df["user_name"].astype(str).str.strip()
    invalid_mask = (
        df["user_name"].isna() | (df["user_name"] == "") |
        df["user_name"].str.replace(".", "", regex=False)
        .str.replace("-", "", regex=False).str.replace("_", "", regex=False)
        .str.isdigit()
    )
    n_invalid = invalid_mask.sum()
    if n_invalid > 0:
        errors.append(f"{table} : {n_invalid} lignes ignorees (user_name invalide)")
    df = df[~invalid_mask]

    df["perf_date"] = pd.to_datetime(df["perf_date"]).dt.date
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce").fillna(0).astype(int)

    # Dedup
    df = df.drop_duplicates(subset=["user_name", "perf_date"], keep="last")

    sql_str = (
        f"INSERT INTO {table} (user_name, perf_date, {value_col}) "
        f"VALUES (%(user_name)s, %(perf_date)s, %({value_col})s) "
        f"ON DUPLICATE KEY UPDATE {value_col} = VALUES({value_col})"
    )

    rows = []
    for _, row in df.iterrows():
        rows.append({
            "user_name": str(row["user_name"]),
            "perf_date": str(row["perf_date"]),
            value_col: int(row[value_col]),
        })

    raw_conn = engine.raw_connection()
    try:
        cursor = raw_conn.cursor()
        cursor.executemany(sql_str, rows)
        raw_conn.commit()
    except Exception as e:
        errors.append(f"{table} : erreur MySQL — {e}")
        raw_conn.rollback()
    finally:
        raw_conn.close()

    dates = sorted(df["perf_date"].unique())
    print(f"  {table} : {len(rows)} lignes synchronisees "
          f"({dates[0]} -> {dates[-1] if len(dates) > 1 else dates[0]})")
    return errors


def main():
    print("=== 04_sync.py -- Synchronisation quotidienne MySQL ===\n")

    engine = make_engine(MYSQL_DATABASE)
    all_errors = []

    # ── Agent info ────────────────────────────────────────────────────────────
    agent_path = find_latest("agent_info")
    if agent_path:
        print(f"Agent info : {agent_path.name}")
        all_errors.extend(upsert_agent_info(engine, agent_path))
    else:
        print("  Pas de fichier agent_info dans outputs/.")
    print()

    # ── GADD ──────────────────────────────────────────────────────────────────
    gadd_path = find_latest("gadd_long")
    if gadd_path:
        print(f"GADD : {gadd_path.name}")
        all_errors.extend(upsert_daily_metric(engine, gadd_path, TABLE_DAILY_GADD, "gadd"))
    else:
        print("  Pas de fichier gadd_long dans outputs/.")
    print()

    # ── ADS ───────────────────────────────────────────────────────────────────
    ads_path = find_latest("ads_long")
    if ads_path:
        print(f"ADS : {ads_path.name}")
        all_errors.extend(upsert_daily_metric(engine, ads_path, TABLE_DAILY_ADS, "ads"))
    else:
        print("  Pas de fichier ads_long dans outputs/.")

    # ── Rapport d'erreurs ─────────────────────────────────────────────────────
    print()
    # Sauvegarder les erreurs pour l'email
    errors_path = Path(SYNC_ERRORS_FILE)
    errors_path.parent.mkdir(parents=True, exist_ok=True)
    errors_path.write_text(json.dumps(all_errors, ensure_ascii=False), encoding="utf-8")

    if all_errors:
        print("=" * 60)
        print("RAPPORT DE SYNC — ERREURS / AVERTISSEMENTS :")
        for e in all_errors:
            print(f"  ⚠ {e}")
        print("=" * 60)
    else:
        print("Synchronisation terminee sans erreur.")

    print("Prochaine etape : py -3 scripts/05_commission.py")


if __name__ == "__main__":
    main()
