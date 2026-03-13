# Perf-Commission — Pipeline Quotidien de Commissions LKA

Pipeline automatise pour le suivi des performances (GADD / ADS) et le calcul des commissions agents.

## Architecture Hybride

```
┌─────────────────────────────────────────────────────────────────┐
│  SERVEUR (cron Linux)                                           │
│                                                                 │
│  run_server.sh (toutes les heures)                              │
│    ├── git pull origin main                                     │
│    └── python3 run_daily.py                                     │
│         ├── 00_fetch_mail.py   (Gmail API → inputs/*.xlsx)      │
│         ├── 01_process.py      (Excel → GADD/ADS long)          │
│         ├── 02_compile.py      (→ fichiers cumulatifs)          │
│         ├── 04_sync.py         (UPSERT MySQL)                   │
│         ├── 05_commission.py   (MySQL → Excel commissions)      │
│         └── 06_send_report.py  (Email → destinataire)           │
│                                                                 │
│  Alertes : email admin en cas d'echec                           │
│  Logs : 1 fichier/mois, auto-purge > 60 jours                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  PC LOCAL (BI)                                                  │
│                                                                 │
│  run_bi.py  (double-clic)                                       │
│    └── Lit config.py (AUTO_MODE / MANUAL)                       │
│    └── Se connecte a MySQL distant                              │
│    └── Genere les commissions dans outputs/                     │
│                                                                 │
│  Zero fichier Excel source necessaire                           │
│  Configuration : connections/config.py (bloc BI en bas)         │
└─────────────────────────────────────────────────────────────────┘
```

## Structure du Projet

```
Perf-Commission/
  connections/
    config.py          # Configuration + Credentials (via .env) + Bloc BI
    connect.py         # Factory SQLAlchemy engine
    credentials.json   # OAuth Gmail (dans .gitignore)
  mysql/
    setup_db.py        # DDL : CREATE DATABASE + tables + vues
    setup_tarifs.py    # INSERT/UPDATE des regles tarifaires
  scripts/
    00_fetch_mail.py   # Gmail API → telecharge GLOBALE PERFORMANCE
    01_process.py      # Extraction openpyxl → GADD/ADS long + agent_info
    02_compile.py      # Fusion dans fichiers cumulatifs (wide)
    03_upload.py       # Chargement initial MySQL (TRUNCATE + INSERT)
    04_sync.py         # UPSERT quotidien (INSERT ON DUPLICATE KEY)
    05_commission.py   # Generation Excel commissions (config-driven)
    06_send_report.py  # Envoi email via Gmail API
  run_daily.py         # Orchestrateur serveur (00→06, flag + email alertes)
  run_bi.py            # Point d'entree BI local (double-clic)
  run_server.sh        # Lanceur cron Linux (git pull + logs mensuels)
  run_pipeline.bat     # Lanceur Windows Task Scheduler (legacy)
  .env.example         # Template des variables d'environnement
```

## Installation

### 1. Cloner et configurer les secrets

```bash
git clone https://github.com/elonmj/Perf-Commission.git
cd Perf-Commission
cp .env.example .env
# Editer .env avec les vrais mots de passe
```

### 2. Dependances Python

```bash
pip install pandas openpyxl sqlalchemy pymysql python-dotenv
# Pour Gmail API :
pip install google-auth google-auth-oauthlib google-api-python-client
```

### 3. Base de donnees MySQL

```bash
python mysql/setup_db.py           # Creer la base + tables + vues
python mysql/setup_tarifs.py       # Inserer les regles tarifaires
```

## Deploiement Serveur (Cron Linux)

```bash
# Sur le serveur (ex: root@vmi2705246)
cd /opt
git clone https://github.com/elonmj/Perf-Commission.git perf_commissions
cd perf_commissions
python3 -m venv venv
source venv/bin/activate
pip install pandas openpyxl sqlalchemy pymysql python-dotenv google-auth google-auth-oauthlib google-api-python-client
cp .env.example .env && nano .env   # Remplir les secrets
chmod +x run_server.sh

# Ajouter au cron (toutes les heures)
crontab -e
# 0 * * * * /opt/perf_commissions/run_server.sh
```

## Utilisation BI (Local)

### Mode Automatique (par defaut)

Le script prend les **3 derniers jours** disponibles en base :

```bash
python run_bi.py
```

### Mode Manuel

Dans `connections/config.py`, modifier :

```python
AUTO_MODE        = False
MANUAL_END_DATE  = "2026-03-10"   # Fin de la plage
MANUAL_RANGE_DAYS = 7             # 7 jours en arriere
```

Puis lancer `python run_bi.py`. Les fichiers sortent dans `outputs/`.

### Arguments CLI (avance)

```bash
# Date unique
python scripts/05_commission.py --date 2026-03-10

# Plage explicite
python scripts/05_commission.py --week 2026-02-27 2026-03-08
```

## Tables MySQL

| Table | Cle | Description |
|-------|-----|-------------|
| `agent_perf_info` | user_name (PK) | Infos agent (nom, region, superviseur...) |
| `daily_gadd` | user_name + perf_date (PK) | GADD par agent par jour |
| `daily_ads` | user_name + perf_date (PK) | ADS par agent par jour |
| `commission_tarifs` | id (PK) | Regles tarifaires par canal/jour/periode |

## Vues SQL

| Vue | Usage |
|-----|-------|
| `vw_commission_gadd` | Joint GADD + agent + tarifs → commission calculee |
| `vw_commission_ads` | Joint ADS + agent + tarifs → commission calculee |

## Regles Git

- **Pousse sur Git** : code source, config (sans secrets), `.env.example`
- **Jamais sur Git** : `.env`, `credentials.json`, `token.json`, `inputs/`, `outputs/`, `cumul/`, `data/`, `logs/`
