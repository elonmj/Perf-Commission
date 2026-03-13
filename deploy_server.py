"""
deploy_server.py — Deploiement automatise du pipeline sur le serveur distant.

Utilise Paramiko (SSH + SFTP) pour :
  1. Cloner/pull le repo GitHub
  2. Creer le venv Python + installer les dependances
  3. Transferer .env, credentials.json, token.json (secrets)
  4. Creer les dossiers de travail (inputs, outputs, cumul, logs, reports, data)
  5. Rendre run_server.sh executable
  6. Installer le cron job (toutes les heures)

Usage :
  py -3 deploy_server.py                # deploiement complet
  py -3 deploy_server.py --skip-clone   # ne pas re-cloner (juste MAJ secrets/cron)
  py -3 deploy_server.py --dry-run      # afficher les commandes sans les executer

Pre-requis :
  pip install paramiko
"""

import sys
import os
import argparse
import time
from pathlib import Path

try:
    import paramiko
except ImportError:
    print("ERREUR: paramiko n'est pas installe.")
    print("  pip install paramiko")
    sys.exit(1)

# ─── CONFIGURATION ──────────────────────────────────────────────────────────
ROOT = Path(__file__).parent

# Charger les secrets depuis le .env local
sys.path.insert(0, str(ROOT))
from connections.config import SSH_HOST, SSH_USER, SSH_PASS

SERVER_HOST     = SSH_HOST
SERVER_USER     = SSH_USER
SERVER_PASS     = SSH_PASS
SERVER_PORT     = 22

REMOTE_BASE     = "/opt/perf_commissions"
REPO_URL        = "https://github.com/elonmj/Perf-Commission.git"
PYTHON          = "python3"
CRON_SCHEDULE   = "0 * * * *"  # toutes les heures

# Fichiers secrets a transferer (local → serveur)
LOCAL_ENV           = ROOT / ".env"
LOCAL_CREDENTIALS   = ROOT / "connections" / "credentials.json"
LOCAL_TOKEN         = ROOT / "connections" / "token.json"

# Contenu du .env serveur (MySQL en localhost car le serveur EST le host MySQL)
SERVER_ENV_CONTENT = """\
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
"""


def ssh_connect():
    """Etablit une connexion SSH vers le serveur."""
    print(f"  Connexion SSH → {SERVER_USER}@{SERVER_HOST}:{SERVER_PORT}")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=SERVER_HOST,
        port=SERVER_PORT,
        username=SERVER_USER,
        password=SERVER_PASS,
        timeout=30,
    )
    print("  Connexion etablie.")
    return client


def run_cmd(client, cmd, description="", check=True):
    """Execute une commande SSH et affiche le resultat."""
    if description:
        print(f"\n  [{description}]")
    print(f"  $ {cmd}")

    stdin, stdout, stderr = client.exec_command(cmd, timeout=300)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()

    if out:
        for line in out.split("\n"):
            print(f"    {line}")
    if err and exit_code != 0:
        for line in err.split("\n"):
            print(f"    [stderr] {line}")

    if check and exit_code != 0:
        print(f"  ERREUR: commande echouee (exit {exit_code})")
        if not description.startswith("(optionnel)"):
            raise RuntimeError(f"Commande echouee: {cmd}")

    return exit_code, out, err


def sftp_upload_string(sftp, content, remote_path, description=""):
    """Ecrit une chaine de caracteres directement dans un fichier distant."""
    if description:
        print(f"  [SFTP] {description} → {remote_path}")
    with sftp.file(remote_path, "w") as f:
        f.write(content)
    print(f"    OK ({len(content)} octets)")


def sftp_upload_file(sftp, local_path, remote_path, description=""):
    """Transfere un fichier local vers le serveur."""
    if description:
        print(f"  [SFTP] {description}")
    local_path = Path(local_path)
    if not local_path.exists():
        print(f"    ATTENTION: {local_path} n'existe pas, skip.")
        return False
    print(f"    {local_path} → {remote_path}")
    sftp.put(str(local_path), remote_path)
    size = local_path.stat().st_size
    print(f"    OK ({size} octets)")
    return True


def deploy(skip_clone=False, dry_run=False):
    """Pipeline de deploiement complet."""
    print("=" * 60)
    print("  DEPLOIEMENT SERVEUR — Perf Commissions")
    print("=" * 60)

    if dry_run:
        print("\n  *** MODE DRY-RUN : aucune action ne sera executee ***\n")
        print(f"  Serveur : {SERVER_USER}@{SERVER_HOST}")
        print(f"  Chemin  : {REMOTE_BASE}")
        print(f"  Repo    : {REPO_URL}")
        print(f"  Cron    : {CRON_SCHEDULE} {REMOTE_BASE}/run_server.sh")
        print("\n  Fichiers a transferer :")
        print(f"    .env (genere pour localhost)")
        print(f"    credentials.json ({LOCAL_CREDENTIALS})")
        print(f"    token.json ({LOCAL_TOKEN})")
        return

    client = ssh_connect()
    sftp = client.open_sftp()

    try:
        # ── 1. Clone ou Pull ────────────────────────────────────────────
        if not skip_clone:
            # Verifier si le dossier existe deja
            exit_code, out, _ = run_cmd(
                client, f"test -d {REMOTE_BASE} && echo 'EXISTS' || echo 'NEW'",
                description="Verification du dossier distant", check=False
            )

            if "EXISTS" in out:
                run_cmd(client,
                    f"cd {REMOTE_BASE} && git fetch origin && git reset --hard origin/main",
                    description="Pull des dernieres modifications")
            else:
                run_cmd(client,
                    f"git clone {REPO_URL} {REMOTE_BASE}",
                    description="Clone du repository")
        else:
            print("\n  [Skip clone] --skip-clone active")

        # ── 2. Creer les dossiers de travail ────────────────────────────
        dirs = ["inputs", "outputs", "cumul", "logs", "reports", "data"]
        dirs_str = " ".join(f"{REMOTE_BASE}/{d}" for d in dirs)
        run_cmd(client,
            f"mkdir -p {dirs_str}",
            description="Creation des dossiers de travail")

        # ── 3. Venv + Dependances ───────────────────────────────────────
        run_cmd(client,
            f"cd {REMOTE_BASE} && {PYTHON} -m venv venv",
            description="Creation du venv Python")

        run_cmd(client,
            f"cd {REMOTE_BASE} && source venv/bin/activate && "
            f"pip install --upgrade pip && "
            f"pip install pandas openpyxl sqlalchemy pymysql "
            f"python-dotenv google-auth google-auth-oauthlib google-api-python-client",
            description="Installation des dependances Python")

        # ── 4. Transfert des secrets ────────────────────────────────────
        # .env avec MYSQL_HOST=127.0.0.1 (localhost sur le serveur)
        sftp_upload_string(sftp,
            SERVER_ENV_CONTENT,
            f"{REMOTE_BASE}/.env",
            description=".env (MySQL localhost)")

        # credentials.json (OAuth Gmail)
        sftp_upload_file(sftp,
            LOCAL_CREDENTIALS,
            f"{REMOTE_BASE}/connections/credentials.json",
            description="credentials.json (OAuth Gmail)")

        # token.json (refresh token Gmail)
        sftp_upload_file(sftp,
            LOCAL_TOKEN,
            f"{REMOTE_BASE}/connections/token.json",
            description="token.json (refresh token Gmail)")

        # ── 5. Permissions ──────────────────────────────────────────────
        run_cmd(client,
            f"chmod +x {REMOTE_BASE}/run_server.sh",
            description="chmod +x run_server.sh")

        run_cmd(client,
            f"chmod 600 {REMOTE_BASE}/.env "
            f"{REMOTE_BASE}/connections/credentials.json "
            f"{REMOTE_BASE}/connections/token.json",
            description="Protection des fichiers secrets (600)")

        # ── 6. Installation du cron ─────────────────────────────────────
        cron_line = f"{CRON_SCHEDULE} {REMOTE_BASE}/run_server.sh >> /dev/null 2>&1"

        # Lire le crontab actuel, retirer l'ancien job s'il existe, ajouter le nouveau
        run_cmd(client,
            f'(crontab -l 2>/dev/null | grep -v "perf_commissions" ; '
            f'echo "{cron_line}") | crontab -',
            description="Installation du cron job (toutes les heures)")

        # Verifier
        run_cmd(client,
            "crontab -l",
            description="Verification du crontab")

        # ── 7. Test de connexion MySQL ──────────────────────────────────
        run_cmd(client,
            f"cd {REMOTE_BASE} && source venv/bin/activate && "
            f"{PYTHON} connections/connect.py",
            description="Test de connexion MySQL")

        # ── 8. Verification finale ──────────────────────────────────────
        run_cmd(client,
            f"ls -la {REMOTE_BASE}/",
            description="Contenu du dossier deploye")

        print("\n" + "=" * 60)
        print("  DEPLOIEMENT TERMINE AVEC SUCCES")
        print(f"  Le cron s'executera toutes les heures.")
        print(f"  Pipeline : {REMOTE_BASE}/run_server.sh")
        print(f"  Logs     : {REMOTE_BASE}/logs/pipeline_YYYY-MM.log")
        print("=" * 60)

    finally:
        sftp.close()
        client.close()
        print("\n  Connexion SSH fermee.")


def main():
    parser = argparse.ArgumentParser(description="Deploiement serveur Perf Commissions")
    parser.add_argument("--skip-clone", action="store_true",
                        help="Ne pas cloner/pull le repo (MAJ secrets/cron uniquement)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Afficher les actions sans les executer")
    args = parser.parse_args()

    deploy(skip_clone=args.skip_clone, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
