"""
scripts/00_fetch_mail.py — Récupération du fichier GLOBALE PERFORMANCE
via l'API Gmail (OAuth 2.0).

Première exécution : ouvre le navigateur pour l'authentification Google.
Un token.json est créé et réutilisé pour les fois suivantes.

Usage :
  py -3 scripts/00_fetch_mail.py
  py -3 scripts/00_fetch_mail.py --date 2026-03-10
"""

import sys
import base64
import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from connections.config import EMAIL_SUBJECT_PATTERN

INPUTS = ROOT / "inputs"
CREDS_FILE = ROOT / "connections" / "credentials.json"
TOKEN_FILE = ROOT / "connections" / "token.json"
PROCESSED_IDS_FILE = ROOT / "data" / "processed_mail_ids.json"

# Lecture (scopes)
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

def load_processed_ids() -> set:
    if not PROCESSED_IDS_FILE.exists():
        return set()
    try:
        return set(json.loads(PROCESSED_IDS_FILE.read_text(encoding="utf-8")))
    except:
        return set()

def save_processed_id(msg_id: str):
    PROCESSED_IDS_FILE.parent.mkdir(exist_ok=True)
    ids = load_processed_ids()
    ids.add(msg_id)
    PROCESSED_IDS_FILE.write_text(json.dumps(list(ids)), encoding="utf-8")


def notify_desktop(title: str, message: str):
    """Notification desktop (Windows toast via plyer)."""
    try:
        import importlib
        notification = importlib.import_module("plyer.notification")
        notification.notify(title=title, message=message, timeout=10)
    except ImportError:
        print(f"  [NOTIF] {title} — {message}")
    except Exception as e:
        print(f"  [NOTIF fallback] {title} — {message} ({e})")


def get_gmail_service():
    """
    Authentification OAuth 2.0 et création du service Gmail API.

    Returns:
        googleapiclient.discovery.Resource: Service Gmail.
    """
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(
            str(TOKEN_FILE), SCOPES
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDS_FILE.exists():
                print(f"  ERREUR: {CREDS_FILE} introuvable.")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=creds)


def fetch_attachment(target_date: datetime | None = None) -> Path | None:
    """
    Cherche le mail PERFORMANCE GLOBALE non-lu via l'API Gmail
    et télécharge la pièce jointe .xlsx dans inputs/.

    Parameters:
        target_date (datetime): Date cible (optionnel).

    Returns:
        Path du fichier téléchargé, ou None si rien trouvé.
    """
    if target_date is None:
        target_date = datetime.now()

    INPUTS.mkdir(exist_ok=True)
    service = get_gmail_service()
    print("  Authentification API Gmail réussie.")

    # Recherche ultra-souple : tolère les "S" finaux et la mention "FW:"
    query = 'subject:(PERFORMANCE OR PERFORMANCES) subject:(GLOBALE OR GLOBALES)'
    print(f"  Recherche : [{query}]")

    # Retry logic pour pallier aux instabilités réseau du serveur
    max_retries = 3
    results = {}
    for attempt in range(1, max_retries + 1):
        try:
            results = (
                service.users().messages().list(userId="me", q=query, maxResults=20).execute()
            )
            break
        except Exception as e:
            if attempt == max_retries:
                print(f"  [Erreur Réseau] API Gmail injoignable après {max_retries} tentatives : {e}")
                sys.exit(1)
            print(f"  [Réseau] Instabilité avec Google. Nouvelle tentative ({attempt}/{max_retries}) dans 10 secondes...")
            time.sleep(10)

    messages = results.get("messages", [])

    if not messages:
        print("  Aucun mail trouvé avec ce sujet.")
        return None

    print(f"  {len(messages)} mail(s) trouvé(s).")
    
    processed_ids = load_processed_ids()
    downloaded = None

    for msg in messages:
        msg_id = msg["id"]
        
        if msg_id in processed_ids:
            continue
            
        def get_all_parts(payload):
            parts = [payload]
            if "parts" in payload:
                for p in payload["parts"]:
                    parts.extend(get_all_parts(p))
            return parts

        message = (
            service.users().messages().get(userId="me", id=msg_id).execute()
        )

        all_parts = get_all_parts(message.get("payload", {}))
        for part in all_parts:
            filename = part.get("filename")
            if not filename or not filename.lower().endswith(".xlsx"):
                continue

            attachment_id = part["body"].get("attachmentId")
            if not attachment_id:
                continue

            print(f"  Pièce jointe : {filename}")

            attachment = (
                service.users()
                .messages()
                .attachments()
                .get(userId="me", messageId=msg_id, id=attachment_id)
                .execute()
            )

            file_data = base64.urlsafe_b64decode(
                attachment["data"].encode("UTF-8")
            )
            dest = INPUTS / filename
            dest.write_bytes(file_data)
            print(f"  Fichier sauvegardé : {dest.name}")

            # Enregistrer l'ID comme traité (au lieu de le marquer comme lu)
            save_processed_id(msg_id)
            print("  [Historique] Mail marqué comme traité.")

            downloaded = dest
            break

        if downloaded:
            break

    return downloaded


def main():
    """Point d'entrée principal."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="Date cible YYYY-MM-DD")
    args = parser.parse_args()

    target = (
        datetime.strptime(args.date, "%Y-%m-%d") if args.date else None
    )

    print("=== 00_fetch_mail.py — Récupération GLOBALE PERFORMANCE ===\n")
    result = fetch_attachment(target)

    if result:
        print(f"\n  Succès : {result}")
        sys.exit(0)
    else:
        msg = (
            "Pas de fichier PERFORMANCE GLOBALE trouvé"
            f" ({datetime.now():%Y-%m-%d %H:%M})"
        )
        print(f"\n  {msg}")
        notify_desktop("Perf_commissions", msg)
        sys.exit(2)


if __name__ == "__main__":
    main()
