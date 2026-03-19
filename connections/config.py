"""
connections/config.py — Paramètres de connexion MySQL + Gmail pour Perf_commissions.

C'est le SEUL endroit où changer les credentials si le serveur/mail change.

Les valeurs sensibles sont lues UNIQUEMENT via variables d'environnement.
Voir .env.example pour la liste complète.
En local : créer un fichier .env à la racine du projet (il est dans .gitignore).
"""

import os
from pathlib import Path

# ─── CHARGEMENT .env (si python-dotenv est installé) ────────────────────────
_env_path = Path(__file__).resolve().parent.parent / ".env"
try:
    from dotenv import load_dotenv
    load_dotenv(_env_path)
except ImportError:
    pass  # pas de dotenv → variables d'env système uniquement

# ─── SERVEUR MYSQL ────────────────────────────────────────────────────────────
MYSQL_HOST     = os.environ.get("PERF_MYSQL_HOST", "")
MYSQL_PORT     = int(os.environ.get("PERF_MYSQL_PORT", "3306"))

# ─── CREDENTIALS MYSQL ────────────────────────────────────────────────────────
MYSQL_USER     = os.environ.get("PERF_MYSQL_USER", "")
MYSQL_PASSWORD = os.environ.get("PERF_MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.environ.get("PERF_MYSQL_DATABASE", "lka_perf_commissions")

# ─── CONNEXION STRING ─────────────────────────────────────────────────────────
def connection_string(database: str = MYSQL_DATABASE) -> str:
    if not MYSQL_PASSWORD:
        raise RuntimeError("PERF_MYSQL_PASSWORD non défini. Voir .env.example.")
    return (
        f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
        f"@{MYSQL_HOST}:{MYSQL_PORT}/{database}?charset=utf8mb4"
    )

# ─── SSH (maintenance) ───────────────────────────────────────────────────────
SSH_HOST = os.environ.get("PERF_SSH_HOST", "")
SSH_USER = os.environ.get("PERF_SSH_USER", "root")
SSH_PASS = os.environ.get("PERF_SSH_PASS", "")

# ─── TABLES CIBLES ───────────────────────────────────────────────────────────
TABLE_DAILY_GADD    = "daily_gadd"
TABLE_DAILY_ADS     = "daily_ads"
TABLE_AGENT_INFO    = "agent_perf_info"

# ─── GMAIL IMAP / SMTP ───────────────────────────────────────────────────────
GMAIL_USER        = os.environ.get("PERF_GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.environ.get("PERF_GMAIL_APP_PASSWORD", "")
IMAP_HOST         = "imap.gmail.com"
IMAP_PORT         = 993
SMTP_HOST         = "smtp.gmail.com"
SMTP_PORT         = 465

# ─── PARAMÈTRES MAIL ─────────────────────────────────────────────────────────
EMAIL_SUBJECT_PATTERN   = "PERFORMANCE GLOBALE"
COMMISSION_RECIPIENT    = "g.fondzefe@lkaservices.com"
COMMISSION_SUBJECT_TPL  = "Commission LKA — {date}"

RECIPIENTS_MONTHLY_FINANCIAL  = os.environ.get("RECIPIENTS_MONTHLY_FINANCIAL", "g.fondzefe@lkaservices.com")
RECIPIENTS_WEEKLY_BA_ACTIVITY = os.environ.get("RECIPIENTS_WEEKLY_BA_ACTIVITY", "g.fondzefe@lkaservices.com")
RECIPIENTS_WEEKLY_SUP_KPI     = os.environ.get("RECIPIENTS_WEEKLY_SUP_KPI", "g.fondzefe@lkaservices.com")
PERF_SHEET_NAME        = "WEEKLYGLOBAL"
PERF_HEADER_ROW        = 5          # row 5 (1-indexed) = column headers
PERF_DATE_ROW          = 4          # row 4 = merged date headers
PERF_DATA_START_ROW    = 6          # data begins on row 6
PERF_AGENT_COL_START   = 5          # col E = user_name (1-indexed)
PERF_AGENT_COL_END     = 15         # col O = device_type
PERF_METRIC_COL_START  = 16         # col P = first GADD

# ─── COLONNES AGENT (ordre dans le fichier GLOBALE PERFORMANCE) ──────────────
AGENT_COLUMNS = [
    "user_name", "region", "departement", "commune", "agent_name",
    "msisdn_momo", "p2p", "real_channel", "superviseur", "tss", "device_type",
]

# ─── FICHIER ACQUISITION ──────────────────────────────────────────────────────
ACQUISITION_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "data", "Performance Acquisition Json new.xlsx")

# ─── MSISDN COLUMNS ──────────────────────────────────────────────────────────
MSISDN_COLS = ["msisdn_momo", "p2p"]

# ─── NORMALISATION RÉGIONS ────────────────────────────────────────────────────
REGION_NORMALIZATION = {
    "NORTH EAST":  "NORD EST",
    "NORTH WEST":  "NORD OUEST",
    "NORTH-EST":   "NORD EST",
    "NORTH-WEST":  "NORD OUEST",
    "NORD-EST":    "NORD EST",
    "NORD-OUEST":  "NORD OUEST",
    "SUD-EST":     "SUD EST",
    "SUD-OUEST":   "SUD OUEST",
    "Atlantique":  "ATLANTIQUE",
    "SUD EST ":    "SUD EST",
    "NORD EST ":   "NORD EST",
    "NORD OUEST ": "NORD OUEST",
    "SUD OUEST ":  "SUD OUEST",
}

# ─── CRON / ORCHESTRATEUR ────────────────────────────────────────────────────
RETRY_HOURS      = [8, 12, 18]       # heures de tentative (Task Scheduler)
FLAG_FILE         = "last_success.txt"

# ─── ALERTES ADMIN (pour notify_failure sur serveur) ────────────────────────
ADMIN_EMAIL = os.environ.get("PERF_ADMIN_EMAIL", "joselonm@gmail.com")

# ─── FICHIER D'ERREURS SYNC ──────────────────────────────────────────────────
SYNC_ERRORS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs", "sync_errors.json")

# ─── CONFIGURATION BI (Génération des Commissions) ─────────────────────────
# Mode AUTO : calcule les X derniers jours disponibles en base
AUTO_MODE        = True
AUTO_DAYS_RANGE  = 6

# Mode MANUEL : pour forcer une plage spécifique (mettre AUTO_MODE = False)
MANUAL_END_DATE   = "2026-03-10"   # Format AAAA-MM-JJ
MANUAL_RANGE_DAYS = 7              # Jours en arrière depuis MANUAL_END_DATE
