#!/usr/bin/env bash
# ============================================================================
# run_server.sh — Lanceur cron Linux pour le pipeline Perf_commissions
#
# Installe via crontab -e :
#   0 * * * * /opt/perf_commissions/run_server.sh >> /dev/null 2>&1
#
# Le script :
#   1. git pull (applique les MAJ de code poussees sur main)
#   2. Lance run_daily.py (qui verifie lui-meme le flag du jour)
#   3. Ecrit les logs dans logs/pipeline_YYYY-MM.log (1 fichier/mois)
#   4. Supprime les logs > 60 jours
# ============================================================================

# Retire le -u pour eviter les crash a cause du venv virtuel sous cron
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ─── 1. Mise a jour du code ─────────────────────────────────────────────────
git pull origin main --quiet 2>/dev/null || true

# ─── 2. Activer le venv ─────────────────────────────────────────────────────
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# ─── 3. Log mensuel ─────────────────────────────────────────────────────────
mkdir -p logs
LOG_FILE="logs/pipeline_$(date +%Y-%m).log"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === Lancement pipeline ===" >> "$LOG_FILE"

# Capture le code de sortie sans faire planter le script à cause de 'set -e'
EXIT_CODE=0
python3 run_daily.py >> "$LOG_FILE" 2>&1 || EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ECHEC (exit $EXIT_CODE)" >> "$LOG_FILE"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] SUCCES" >> "$LOG_FILE"
fi

# ─── 4. Nettoyage des vieux logs (> 60 jours) ──────────────────────────────
find logs/ -name "pipeline_*.log" -mtime +60 -delete 2>/dev/null || true

exit $EXIT_CODE
