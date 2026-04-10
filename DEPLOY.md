# Deploiement Manuel — Perf Commissions sur Serveur

Commandes a executer en SSH sur `root@75.119.154.255`.

---

## 1. Cloner le repository

```bash
cd /opt
git clone https://github.com/elonmj/Perf-Commission.git perf_commissions
cd /opt/perf_commissions
```

## 2. Creer le venv Python et installer les dependances

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install pandas openpyxl sqlalchemy pymysql python-dotenv google-auth google-auth-oauthlib google-api-python-client
```

## 3. Creer les dossiers de travail

```bash
mkdir -p inputs outputs cumul logs reports data
```

## 4. Creer le fichier .env (secrets)

```bash
cat > /opt/perf_commissions/.env << 'EOF'
# ─── MYSQL (localhost car le pipeline tourne sur le meme serveur) ────────────
PERF_MYSQL_HOST=127.0.0.1
PERF_MYSQL_PORT=3306
PERF_MYSQL_USER=root
PERF_MYSQL_PASSWORD=LkaRoot2025Secure!
PERF_MYSQL_DATABASE=lka_perf_commissions

# ─── SSH (pas necessaire sur le serveur lui-meme) ───────────────────────────
PERF_SSH_HOST=127.0.0.1
PERF_SSH_USER=root
PERF_SSH_PASS=

# ─── GMAIL ──────────────────────────────────────────────────────────────────
PERF_GMAIL_USER=joselonm@gmail.com
PERF_GMAIL_APP_PASSWORD=nvtg hgzd arpr dmvl

# ─── ALERTES ────────────────────────────────────────────────────────────────
PERF_ADMIN_EMAIL=joselonm@gmail.com
EOF
```

## 5. Transferer les fichiers OAuth Gmail

Depuis ton PC Windows, ouvre un terminal PowerShell :

```powershell
scp D:\LKA\Perf_commissions\connections\credentials.json root@75.119.154.255:/opt/perf_commissions/connections/credentials.json
scp D:\LKA\Perf_commissions\connections\token.json root@75.119.154.255:/opt/perf_commissions/connections/token.json
```

## 6. Proteger les fichiers secrets

De retour en SSH sur le serveur :

```bash
chmod 600 /opt/perf_commissions/.env
chmod 600 /opt/perf_commissions/connections/credentials.json
chmod 600 /opt/perf_commissions/connections/token.json
```

## 7. Rendre le lanceur executable

```bash
chmod +x /opt/perf_commissions/run_server.sh
```

## 8. Tester la connexion MySQL

```bash
cd /opt/perf_commissions
source venv/bin/activate
python3 connections/connect.py
```

Attendu : `Connexion OK → 127.0.0.1:3306/lka_perf_commissions`

## 9. Test manuel du pipeline

```bash
cd /opt/perf_commissions
source venv/bin/activate
python3 run_daily.py --force --skip-send
```

## 10. Installer le cron job

```bash
(crontab -l 2>/dev/null | grep -v "perf_commissions" ; echo "10,40 * * * * /opt/perf_commissions/run_server.sh") | crontab -
```

Verifier :

```bash
crontab -l
```

Attendu : `10,40 * * * * /opt/perf_commissions/run_server.sh`

---

## Comment ca marche ensuite

| Heure | Comportement |
|-------|----------|
| XX:10 | Cron lance `run_server.sh` → `git pull` + `run_daily.py` |
| XX:10 | `run_daily.py` verifie `last_success.txt` → pas de flag → lance le pipeline |
| XX:10 | Si pas de mail : le script echoue proprement, email d'alerte envoye |
| XX:40 | Cron relance → toujours pas de flag → reessaie |
| XX+1:10 | Relance via nouveau cron toutes les heures |
| ...   | Repeat à :10 et :40 jusqu'a ce que le mail d'Abraham arrive |
| YY:10 (ou YY:40) | Mail trouve → pipeline complet → `last_success.txt` = date du jour |
| YY+1:10 (ou YY:40 suivant) | Cron relance → flag du jour existe MAIS retries en attente → relance quand meme |
| YY+2:10 | Cron relance → retries terminees ou aucune → exit 0 instantanement |

Les logs sont dans `/opt/perf_commissions/logs/pipeline_2026-03.log` (1 fichier/mois, purge auto > 60 jours).

---

## Pour mettre a jour le code plus tard

Depuis ton PC, tu push sur GitHub. Le serveur fait `git pull` automatiquement a chaque heure avant de lancer le pipeline. Pas besoin de se reconnecter en SSH.
