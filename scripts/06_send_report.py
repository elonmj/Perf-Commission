"""
scripts/06_send_report.py -- Etape 6 : envoi du fichier commission par email
via l'API Gmail (OAuth 2.0).

Envoie le dernier fichier commission en piece jointe avec corps HTML.

Usage :
  py -3 scripts/06_send_report.py
  py -3 scripts/06_send_report.py --file outputs/commission_2026-03-04_au_2026-03-10.xlsx
  py -3 scripts/06_send_report.py --to josaphatahouanye@gmail.com
"""

import sys
import json
import base64
import argparse
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

ROOT = Path(__file__).parent.parent
OUTPUTS = ROOT / "outputs"
CREDS_FILE = ROOT / "connections" / "credentials.json"
TOKEN_FILE = ROOT / "connections" / "token.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

sys.path.insert(0, str(ROOT))
from connections.config import (
    GMAIL_USER,
    COMMISSION_RECIPIENT, COMMISSION_SUBJECT_TPL,
    SYNC_ERRORS_FILE,
)


def find_latest_commission(override: str = None) -> Path:
    if override:
        p = Path(override)
        if not p.exists():
            p = ROOT / override
        if not p.exists():
            raise FileNotFoundError(f"Fichier introuvable : {override}")
        return p

    files = sorted(
        OUTPUTS.glob("commission_*.xlsx"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError("Aucun fichier commission dans outputs/")
    return files[0]


def load_sync_errors() -> list[str]:
    """Charge les erreurs de sync depuis le fichier JSON."""
    path = Path(SYNC_ERRORS_FILE)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def build_html_body(date_part: str, file_name: str, sync_errors: list[str]) -> str:
    """Construit le corps HTML de l'email."""
    errors_html = ""
    if sync_errors:
        rows = "".join(
            f'<tr><td style="padding:6px 12px;border:1px solid #e0e0e0;color:#c0392b;">'
            f'⚠ {e}</td></tr>' for e in sync_errors
        )
        errors_html = f"""
        <div style="margin-top:20px;padding:15px;background:#fff3cd;border-left:4px solid #ffc107;border-radius:4px;">
            <h3 style="margin:0 0 10px;color:#856404;">⚠ Alertes de synchronisation</h3>
            <table style="border-collapse:collapse;width:100%;">
                {rows}
            </table>
        </div>
        """
    else:
        errors_html = """
        <div style="margin-top:20px;padding:15px;background:#d4edda;border-left:4px solid #28a745;border-radius:4px;">
            <p style="margin:0;color:#155724;">✅ Synchronisation MySQL terminée sans erreur.</p>
        </div>
        """

    return f"""
    <html>
    <body style="font-family:Segoe UI,Arial,sans-serif;color:#333;max-width:700px;margin:auto;">
        <div style="background:#2F5496;color:white;padding:20px;border-radius:8px 8px 0 0;">
            <h1 style="margin:0;font-size:22px;">📊 Commission LKA — {date_part}</h1>
            <p style="margin:5px 0 0;opacity:0.9;">Pipeline automatique Perf Commissions</p>
        </div>

        <div style="padding:20px;background:#f8f9fa;border:1px solid #e0e0e0;border-top:none;">
            <h2 style="color:#2F5496;margin-top:0;">Fichier joint</h2>
            <p>📎 <strong>{file_name}</strong></p>

            <h3 style="color:#2F5496;">Contenu du fichier :</h3>
            <table style="border-collapse:collapse;width:100%;">
                <tr style="background:#2F5496;color:white;">
                    <th style="padding:8px 12px;text-align:left;">Feuille</th>
                    <th style="padding:8px 12px;text-align:left;">Description</th>
                </tr>
                <tr style="background:white;">
                    <td style="padding:8px 12px;border:1px solid #e0e0e0;"><strong>Résumé</strong></td>
                    <td style="padding:8px 12px;border:1px solid #e0e0e0;">Taux de commission, totaux GADD/ADS, commission globale</td>
                </tr>
                <tr style="background:#f2f2f2;">
                    <td style="padding:8px 12px;border:1px solid #e0e0e0;"><strong>GADD</strong></td>
                    <td style="padding:8px 12px;border:1px solid #e0e0e0;">Détail GADD par agent avec formules de commission</td>
                </tr>
                <tr style="background:white;">
                    <td style="padding:8px 12px;border:1px solid #e0e0e0;"><strong>ADS</strong></td>
                    <td style="padding:8px 12px;border:1px solid #e0e0e0;">Détail ADS par agent avec formules de commission</td>
                </tr>
            </table>

            <p style="margin-top:15px;font-size:13px;color:#666;">
                💡 Les formules de commission sont préservées — ouvrez avec Excel pour recalculer.
            </p>

            {errors_html}
        </div>

        <div style="padding:15px;background:#e9ecef;border-radius:0 0 8px 8px;text-align:center;font-size:12px;color:#888;">
            Pipeline LKA Perf Commissions — Envoi automatique
        </div>
    </body>
    </html>
    """


def get_gmail_service():
    """Authentification OAuth 2.0 pour l'envoi Gmail."""
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


def send_email(file_path: Path, recipient: str):
    """Envoie le fichier par email via l'API Gmail OAuth 2.0 avec corps HTML."""
    stem = file_path.stem
    date_part = stem.replace("commission_", "")
    subject = COMMISSION_SUBJECT_TPL.format(date=date_part)

    sync_errors = load_sync_errors()

    msg = MIMEMultipart("mixed")
    msg["From"] = GMAIL_USER
    msg["To"] = recipient
    msg["Subject"] = subject

    html_body = build_html_body(date_part, file_path.name, sync_errors)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # Piece jointe
    with open(file_path, "rb") as f:
        part = MIMEBase(
            "application",
            "vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header(
        "Content-Disposition",
        f"attachment; filename={file_path.name}",
    )
    msg.attach(part)

    # Envoi via API Gmail
    service = get_gmail_service()
    raw_message = base64.urlsafe_b64encode(
        msg.as_bytes()
    ).decode("utf-8")

    print(f"  Envoi via API Gmail...")
    service.users().messages().send(
        userId="me", body={"raw": raw_message}
    ).execute()

    print(f"  Email envoye a {recipient}")
    print(f"  Sujet : {subject}")
    if sync_errors:
        print(f"  {len(sync_errors)} alerte(s) incluse(s) dans le mail.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=None, help="Chemin fichier commission")
    parser.add_argument("--to", default=None, help="Destinataire (defaut: config)")
    args = parser.parse_args()

    print("=== 06_send_report.py -- Envoi commission (HTML) ===\n")

    file_path = find_latest_commission(args.file)
    recipient = args.to or COMMISSION_RECIPIENT

    print(f"  Fichier   : {file_path.name}")
    print(f"  Dest.     : {recipient}")
    print()

    send_email(file_path, recipient)

    print()
    print("Envoi termine.")


if __name__ == "__main__":
    main()
