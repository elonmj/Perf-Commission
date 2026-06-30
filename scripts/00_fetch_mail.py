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
import re
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
MAIL_QUERY = (
    'subject:(PERFORMANCE OR PERFORMANCES OR PERORMANCE OR PERFOMANCE OR PEERFORMANCE OR PERFRMANCE) '
    'subject:(GLOBAL OR GLOBALE OR GLOBALES) '
    'has:attachment filename:xlsx'
)

# Lecture (scopes)
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

def load_processed_ids() -> dict:
    if not PROCESSED_IDS_FILE.exists():
        return {}
    try:
        data = json.loads(PROCESSED_IDS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            # Migration de l'ancien format vers le nouveau
            return {m_id: {"status": "success", "last_step_completed": "ALL"} for m_id in data}
        if isinstance(data, dict):
            return data
        return {}
    except Exception:
        return {}

def mark_processing_started(msg_id: str):
    PROCESSED_IDS_FILE.parent.mkdir(exist_ok=True)
    ids = load_processed_ids()
    if msg_id not in ids:
        ids[msg_id] = {"status": "pending", "last_step_completed": "00 - Fetch Mail"}
    
    PROCESSED_IDS_FILE.write_text(json.dumps(ids, indent=4), encoding="utf-8")


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


def list_matching_messages(service, max_results: int = 20) -> list[dict]:
    """Retourne les mails Gmail correspondant au sujet attendu, du plus recent au plus ancien."""
    print(f"  Recherche : [{MAIL_QUERY}]")

    max_retries = 3
    results = {}
    for attempt in range(1, max_retries + 1):
        try:
            results = (
                service.users()
                .messages()
                .list(userId="me", q=MAIL_QUERY, maxResults=max_results)
                .execute()
            )
            break
        except Exception as e:
            if attempt == max_retries:
                raise RuntimeError(
                    f"API Gmail injoignable apres {max_retries} tentatives : {e}"
                ) from e
            print(
                "  [Reseau] Instabilite avec Google. "
                f"Nouvelle tentative ({attempt}/{max_retries}) dans 10 secondes..."
            )
            time.sleep(10)

    return results.get("messages", [])


def get_latest_matching_message() -> dict | None:
    """Retourne le mail Gmail le plus recent correspondant au sujet attendu."""
    service = get_gmail_service()
    messages = list_matching_messages(service, max_results=1)
    if not messages:
        return None
    return messages[0]


def extract_filename_date(filename: str) -> tuple[int, int, int] | None:
    match = re.search(r"(20\d{2})(\d{2})(\d{2})", filename)
    if match:
        return tuple(int(part) for part in match.groups())

    match = re.search(r"(\d{2})[-_/](\d{2})[-_/](20\d{2})", filename)
    if match:
        day, month, year = (int(part) for part in match.groups())
        return (year, month, day)

    return None


def iter_attachment_candidates(payload: dict, depth: int = 0, order_start: int = 0):
    filename = payload.get("filename") or ""
    if filename.lower().endswith(".xlsx"):
        attachment_id = payload.get("body", {}).get("attachmentId")
        if attachment_id:
            yield {
                "filename": filename,
                "attachment_id": attachment_id,
                "depth": depth,
                "order": order_start,
                "size": int(payload.get("body", {}).get("size") or 0),
                "filename_date": extract_filename_date(filename),
            }
            order_start += 1

    for part in payload.get("parts", []):
        for candidate in iter_attachment_candidates(part, depth + 1, order_start):
            yield candidate
            order_start = candidate["order"] + 1


def choose_attachment_candidate(payload: dict) -> dict | None:
    candidates = list(iter_attachment_candidates(payload))
    if not candidates:
        return None

    def ranking_key(candidate: dict):
        return (
            -candidate["depth"],
            candidate["filename_date"] or (0, 0, 0),
            candidate["size"],
            candidate["order"],
        )

    return max(candidates, key=ranking_key)


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

    try:
        messages = list_matching_messages(service, max_results=20)
    except RuntimeError as exc:
        print(f"  [Erreur Réseau] {exc}")
        sys.exit(1)

    if not messages:
        print("  Aucun mail trouvé avec ce sujet.")
        return None

    print(f"  {len(messages)} mail(s) trouvé(s).")
    
    processed_ids = load_processed_ids()
    downloaded = None

    for msg in messages:
        msg_id = msg["id"]
        
        if msg_id in processed_ids:
            if processed_ids[msg_id].get("status") == "success":
                continue
            else:
                print(f"  [Historique] Mail partiellement traité trouvé : {msg_id}. Reprise ou retéléchargement.")
                
        message = (
            service.users().messages().get(userId="me", id=msg_id).execute()
        )

        candidate = choose_attachment_candidate(message.get("payload", {}))
        if candidate:
            print(
                "  [DEBUG] Pièce jointe retenue : "
                f"'{candidate['filename']}' (profondeur={candidate['depth']}, "
                f"taille={candidate['size']})"
            )

            attachment = (
                service.users()
                .messages()
                .attachments()
                .get(userId="me", messageId=msg_id, id=candidate["attachment_id"])
                .execute()
            )

            file_data = base64.urlsafe_b64decode(
                attachment["data"].encode("UTF-8")
            )
            dest = INPUTS / candidate["filename"]
            dest.write_bytes(file_data)
            print(f"  Fichier sauvegardé : {dest.name}")

            # Historique granulaire : fetch termine, les etapes suivantes restent a executer.
            mark_processing_started(msg_id)
            print("  [Historique] Mail marque comme telecharge (status=pending).")

            downloaded = dest

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
