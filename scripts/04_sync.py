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
import time
from pathlib import Path
from datetime import datetime

import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).parent.parent
OUTPUTS = ROOT / "outputs"

sys.path.insert(0, str(ROOT))
from connections.config import (
    MYSQL_DATABASE, TABLE_DAILY_GADD, TABLE_DAILY_ADS,
    MSISDN_COLS, 
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


def execute_with_retry(engine, sql_str, rows, context_name, max_retries=5, delay=5):
    """Exécute une requête batch avec retry en cas de deconnexion MySQL."""
    for attempt in range(1, max_retries + 1):
        raw_conn = None
        try:
            raw_conn = engine.raw_connection()
            cursor = raw_conn.cursor()
            cursor.executemany(sql_str, rows)
            raw_conn.commit()
            return None
        except Exception as e:
            if raw_conn:
                try:
                    raw_conn.rollback()
                except Exception:
                    pass
            print(f"  [Retry] {context_name} : erreur MySQL — {e} (tentative {attempt}/{max_retries})")
            if attempt < max_retries:
                time.sleep(delay)
            else:
                return f"{context_name} : erreur MySQL finale — {e}"
        finally:
            if raw_conn:
                try:
                    raw_conn.close()
                except Exception:
                    pass
    return "Erreur inconnue."




def find_zero_regressions(engine, table: str, value_col: str, rows: list[dict]) -> list[dict]:
    """Detecte, AVANT ecriture, les cas ou une ligne entrante vaut 0 alors que
    la base contient deja une valeur strictement positive pour la meme cle
    (user_name, perf_date). Un 0 n'est jamais une correction legitime d'une
    valeur positive deja connue : c'est systematiquement le symptome d'une
    cellule source vide/mal calculee (ex. formule Excel non tiree jusqu'en
    bas) — jamais un vrai signal metier. Voir incident 2026-05/06 (audit
    scripts/audit_perf_zero_overwrites.py cote LKA_Automations)."""
    zero_keys = [(r["user_name"], r["perf_date"]) for r in rows if r[value_col] == 0]
    if not zero_keys:
        return []

    tmp_table = f"_tmp_zero_check_{value_col}"
    with engine.begin() as conn:
        conn.execute(text(f"DROP TEMPORARY TABLE IF EXISTS {tmp_table}"))
        conn.execute(text(
            f"CREATE TEMPORARY TABLE {tmp_table} (user_name VARCHAR(255), perf_date DATE, PRIMARY KEY (user_name, perf_date))"
        ))
        conn.execute(
            text(f"INSERT INTO {tmp_table} (user_name, perf_date) VALUES (:user_name, :perf_date)"),
            [{"user_name": u, "perf_date": d} for u, d in zero_keys],
        )
        existing = conn.execute(text(
            f"SELECT t.user_name, t.perf_date, m.{value_col} AS current_value "
            f"FROM {tmp_table} t JOIN {table} m "
            f"ON m.user_name = t.user_name AND m.perf_date = t.perf_date "
            f"WHERE m.{value_col} > 0"
        )).fetchall()
        conn.execute(text(f"DROP TEMPORARY TABLE IF EXISTS {tmp_table}"))

    return [
        {"user_name": r.user_name, "perf_date": str(r.perf_date), "current_value": r.current_value}
        for r in existing
    ]


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
        invalid_names = df.loc[invalid_mask, "user_name"].unique().tolist()
        errors.append(f"{table} : {n_invalid} lignes ignorees (user_name invalide: {', '.join(map(str, invalid_names))})")
    df = df[~invalid_mask]

    df["perf_date"] = pd.to_datetime(df["perf_date"]).dt.date
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce").fillna(0).astype(int)

    # Dedup
    df = df.drop_duplicates(subset=["user_name", "perf_date"], keep="last")

    rows = []
    for _, row in df.iterrows():
        rows.append({
            "user_name": str(row["user_name"]),
            "perf_date": str(row["perf_date"]),
            value_col: int(row[value_col]),
        })

    # ── Garde-fou anti-regression (detection + alerte) ─────────────────────
    # Un 0 entrant ne doit JAMAIS effacer silencieusement une valeur positive
    # deja synchronisee. On le detecte ICI pour alerter (email/Slack via
    # all_errors), en plus de la protection inconditionnelle au niveau SQL
    # ci-dessous qui, elle, empeche l'ecriture quoi qu'il arrive.
    try:
        blocked = find_zero_regressions(engine, table, value_col, rows)
    except Exception as e:
        blocked = []
        errors.append(f"{table} : verification anti-regression impossible ({e}) — protection SQL toujours active.")
    if blocked:
        detail = ", ".join(f"{b['user_name']}@{b['perf_date']} (etait {b['current_value']})" for b in blocked)
        errors.append(
            f"{table} : {len(blocked)} ecrasement(s) par 0 BLOQUE(S) — une valeur positive deja "
            f"connue a ete protegee contre un 0 entrant (probable cellule source vide/formule non "
            f"tiree) : {detail}"
        )
        print(f"  [PROTECTION] {table} : {len(blocked)} valeur(s) positive(s) protegee(s) contre un ecrasement par 0.")

    # ON DUPLICATE KEY UPDATE ne remplace JAMAIS une valeur positive existante
    # par un 0 entrant : c'est la garantie definitive, independante de toute
    # detection applicative. Un 0 n'est accepte que sur une ligne qui n'existe
    # pas encore, ou qui vaut deja 0. Toute autre valeur (0 ou positive) sur
    # une ligne existante non-nulle continue de s'appliquer normalement
    # (les vraies corrections restent possibles).
    sql_str = (
        f"INSERT INTO {table} (user_name, perf_date, {value_col}) "
        f"VALUES (%(user_name)s, %(perf_date)s, %({value_col})s) "
        f"ON DUPLICATE KEY UPDATE {value_col} = IF("
        f"VALUES({value_col}) = 0 AND {table}.{value_col} > 0, "
        f"{table}.{value_col}, VALUES({value_col}))"
    )

    err = execute_with_retry(engine, sql_str, rows, table)
    if err:
        errors.append(err)

    dates = sorted(df["perf_date"].unique())
    print(f"  {table} : {len(rows)} lignes synchronisees "
          f"({dates[0]} -> {dates[-1] if len(dates) > 1 else dates[0]})")
    return errors


def main():
    print("=== 04_sync.py -- Synchronisation quotidienne MySQL ===\n")

    engine = make_engine(MYSQL_DATABASE)
    all_errors = []

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
