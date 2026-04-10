#!/usr/bin/env bash
# ============================================================================
# run_server.sh — Lanceur cron Linux pour le pipeline Perf_commissions
#
# Installe via crontab -e :
#   */15 * * * * /opt/perf_commissions/run_server.sh >> /dev/null 2>&1
#
# Le script :
#   1. git pull (applique les MAJ de code poussees sur main)
#   2. Lance run_daily.py (qui verifie lui-meme le flag du jour)
#   3. Ecrit les logs dans logs/pipeline_YYYY-MM.log (1 fichier/mois)
#   4. Supprime les logs > 60 jours
# ============================================================================

# Strict mode : -e (exit on error), -u (undefined vars), -o pipefail
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ─── 0. Configuration des logs ────────────────────────────────────────────────
mkdir -p logs
LOG_FILE="logs/pipeline_$(date +%Y-%m).log"

# ─── 1. Mise à jour du code avec Retry ──────────────────────────────────────
MAX_RETRIES=5
RETRY_COUNT=0
SUCCESS=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if git fetch origin main --quiet; then
        git reset --hard origin/main --quiet || true
        git pull origin main --quiet || true
        SUCCESS=true
        break
    else
        RETRY_COUNT=$((RETRY_COUNT + 1))
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Echec connexion GitHub (tentative $RETRY_COUNT/$MAX_RETRIES). Nouvelle tentative dans 10s..." >> "$LOG_FILE"
        sleep 10
    fi
done

if [ "$SUCCESS" = false ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] CRITICAL: Impossible de mettre à jour depuis GitHub après $MAX_RETRIES tentatives. Exécution avec le code local actuel." >> "$LOG_FILE"
fi

# ─── 2. Activer le venv ─────────────────────────────────────────────────────
if [ -d "venv" ]; then
    set +u  # desactive brievement la verification pour activer le venv sans crasher sous cron
    source venv/bin/activate
    set -u  # reactive la securite stricte
fi

# ─── 3. Lancement du Pipeline ───────────────────────────────────────────────
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
