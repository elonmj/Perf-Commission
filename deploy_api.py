"""
deploy_api.py — Déploiement de l'API FastAPI et Docker sur le serveur distant.

Ce script utilise Paramiko pour :
  1. Uploader les nouveaux fichiers (api.py, Dockerfile.api, docker-compose.yml...)
  2. Démarrer le conteneur Docker pour l'API sur le serveur

Usage :
  py -3 deploy_api.py
"""

import sys
import os
from pathlib import Path

try:
    import paramiko
except ImportError:
    print("ERREUR: paramiko n'est pas installe. (faites pip install paramiko)")
    sys.exit(1)

ROOT = Path(__file__).parent

# Charger les secrets
sys.path.insert(0, str(ROOT))
from connections.config import SSH_HOST, SSH_USER, SSH_PASS

SERVER_HOST = SSH_HOST
SERVER_USER = SSH_USER
SERVER_PASS = SSH_PASS
SERVER_PORT = 22

REMOTE_BASE = "/opt/perf_commissions"

# Fichiers spécifiques à l'API à transférer
FILES_TO_SYNC = [
    "api.py",
    "Dockerfile.api",
    "docker-compose.yml",
    "requirements-api.txt",
    "scripts/import_user_ids.py",
    "mysql/setup_db.py"
]

def ssh_connect():
    print(f"Connexion SSH -> {SERVER_USER}@{SERVER_HOST}:{SERVER_PORT}")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=SERVER_HOST,
        port=SERVER_PORT,
        username=SERVER_USER,
        password=SERVER_PASS,
        timeout=30,
    )
    return client

def run_cmd(client, cmd):
    print(f"\n$ {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=300)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()

    if out:
        for line in out.split("\n"):
            print(f"  {line}")
    if err and exit_code != 0:
        for line in err.split("\n"):
            print(f"  [stderr] {line}")
            
    return exit_code

def main():
    print("=" * 60)
    print("  DEPLOIEMENT API SUR LE SERVEUR")
    print("=" * 60)
    
    client = ssh_connect()
    sftp = client.open_sftp()
    
    print("\n--- 1. Transfert des fichiers ---")
    for file_path in FILES_TO_SYNC:
        local_path = ROOT / file_path
        remote_path = f"{REMOTE_BASE}/{file_path}"
        
        if local_path.exists():
            print(f"Upload : {file_path} -> {remote_path}")
            # Créer le répertoire de destination s'il n'existe pas (pour les scripts/)
            try:
                sftp.stat(os.path.dirname(remote_path))
            except IOError:
                run_cmd(client, f"mkdir -p {os.path.dirname(remote_path)}")

            sftp.put(str(local_path), remote_path)
        else:
            print(f"ATTENTION : Fichier introuvable - {local_path}")
            
    sftp.close()
    
    print("\n--- 2. Lancement du Docker API ---")
    # On utilise docker compose ou docker-compose (selon ce qui est dispo)
    cmd_docker = f"cd {REMOTE_BASE} && (docker compose up -d --build || docker-compose up -d --build)"
    run_cmd(client, cmd_docker)
    
    client.close()
    
    print("\n" + "=" * 60)
    print("DEPLOIEMENT TERMINE AVEC SUCCES.")
    print(f"L'API est maintenant en cours d'execution sur l'IP : {SERVER_HOST}:8000")
    print("=" * 60)

if __name__ == "__main__":
    main()
