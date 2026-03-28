#!/bin/bash
set -e

echo "=== Cleanup et Run Pipeline ==="
cd /opt/perf_commissions

echo ""
echo "1️⃣ Backup du fichier processed_mail_ids.json..."
cp data/processed_mail_ids.json data/processed_mail_ids.json.backup

echo ""
echo "2️⃣ Suppression du dernier ID..."
python3 << 'PYTHON_EOF'
import json

with open("data/processed_mail_ids.json", "r") as f:
    data = json.load(f)

print(f"Avant: {len(data)} IDs")
if len(data) > 0:
    last_id = data.pop()
    print(f"ID supprimé: {last_id}")

with open("data/processed_mail_ids.json", "w") as f:
    json.dump(data, f)

print(f"Après: {len(data)} IDs")
PYTHON_EOF

echo ""
echo "3️⃣ Lancement du pipeline avec --force --send-all..."
python3 run_daily.py --force --send-all

echo ""
echo "✅ Pipeline terminé!"
