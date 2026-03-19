"""
run_daily.py -- Orchestrateur du pipeline quotidien Perf_commissions.

Enchaine les etapes dans l'ordre :
  00 → Fetch mail (GLOBALE PERFORMANCE)
  01 → Process (extraction GADD/ADS)
  02 → Compile (mise a jour cumulatifs)
  04 → Sync (UPSERT MySQL)
  05 → Commission (generation Excel)
  06 → Send report (envoi email)

Flag file : ecrit la date dans last_success.txt apres succes.
Le Task Scheduler l'appelle a 8h, 12h, 18h ; si le flag du jour
existe deja, le pipeline est saute.

Usage :
  py -3 run_daily.py
  py -3 run_daily.py --force       (ignore le flag)
  py -3 run_daily.py --skip-fetch  (sauter 00, utile en test)
  py -3 run_daily.py --skip-send   (sauter 06, pas d'email)
"""

import sys
import subprocess
import argparse
import smtplib
import traceback
from email.mime.text import MIMEText
from pathlib import Path
from datetime import datetime, date

ROOT = Path(__file__).parent

sys.path.insert(0, str(ROOT))
from connections.config import (
    FLAG_FILE, GMAIL_USER, GMAIL_APP_PASSWORD, SMTP_HOST, SMTP_PORT, ADMIN_EMAIL,
)

FLAG_PATH = ROOT / FLAG_FILE


import time

def already_done_today() -> bool:
    if not FLAG_PATH.exists():
        return False
    content = FLAG_PATH.read_text().strip()
    return content == str(date.today())


def mark_done():
    FLAG_PATH.write_text(str(date.today()))


def run_step(name: str, script: str, extra_args: list | None = None) -> tuple[bool, str, int]:
    """Execute un script Python et retourne (succes, traceback_si_echec, code_retour)."""
    start_time = time.time()

    cmd = [sys.executable, str(ROOT / script)]
    if extra_args:
        cmd.extend(extra_args)

    print(f"\n{'='*60}")
    print(f"  ETAPE : {name}")
    print(f"  CMD   : {' '.join(cmd)}")
    print(f"{'='*60}\n")

    # Capture de la sortie pour récupérer le traceback
    result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    
    elapsed = time.time() - start_time

    # Affichage de la sortie capturée
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")

    print(f"\n  ⏱️ Temps d'exécution : {elapsed:.2f} secondes")

    if result.returncode != 0:
        print(f"\n  ERREUR : {name} a echoue (exit code {result.returncode})")
        error_log = result.stderr if result.stderr.strip() else result.stdout
        return False, error_log, result.returncode

    print(f"\n  OK : {name} termine avec succes.")
    return True, "", 0


def notify_failure(step_name: str, error_detail: str = ""):
    """Envoie un email d'alerte en cas d'echec. Fallback sur plyer (Windows)."""
    subject = f"[ECHEC] Pipeline Perf_commissions — {step_name}"
    body = (
        f"L'etape '{step_name}' a echoue le {datetime.now().strftime('%Y-%m-%d %H:%M')}.\n\n"
        f"{error_detail}\n\n"
        f"Verifiez les logs sur le serveur."
    )

    # Tentative d'envoi email d'alerte via l'API Gmail OAuth 2.0
    if ADMIN_EMAIL:
        try:
            import base64
            from email.mime.multipart import MIMEMultipart
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            msg = MIMEMultipart()
            msg["Subject"] = subject
            msg["From"] = GMAIL_USER or "me"
            msg["To"] = ADMIN_EMAIL
            msg.attach(MIMEText(body, "plain", "utf-8"))

            token_path = ROOT / "connections" / "token.json"
            if token_path.exists():
                creds = Credentials.from_authorized_user_file(str(token_path))
                service = build("gmail", "v1", credentials=creds)
                raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
                service.users().messages().send(userId="me", body={"raw": raw_message}).execute()
                print(f"  Alerte email envoyee a {ADMIN_EMAIL} via l'API Gmail")
                return
            else:
                print("  Echec envoi email : token.json introuvable.")
        except Exception as exc:
            print(f"  Echec envoi email via API : {exc}")

    # Fallback : notification desktop (Windows seulement)
    try:
        import importlib
        notification = importlib.import_module("plyer.notification")
        notification.notify(
            title=subject,
            message=f"L'etape '{step_name}' a echoue. Verifiez les logs.",
            timeout=10,
        )
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="Ignorer le flag et forcer l'execution")
    parser.add_argument("--skip-fetch", action="store_true",
                        help="Sauter le fetch mail (pour tests)")
    parser.add_argument("--skip-send", action="store_true",
                        help="Sauter l'envoi email")
    parser.add_argument("--initial", action="store_true",
                        help="Premier chargement (utilise 03 au lieu de 04)")
    args = parser.parse_args()

    print(f"=== Pipeline Perf Commissions — {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")
    print()

    # Verifier le flag
    if not args.force and already_done_today():
        print(f"  Pipeline deja execute aujourd'hui ({date.today()}).")
        print(f"  Utilisez --force pour relancer.")
        sys.exit(0)

    steps = []

    # 00 — Fetch mail
    if not args.skip_fetch:
        steps.append(("00 - Fetch Mail", "scripts/00_fetch_mail.py"))

    # 01 — Process
    steps.append(("01 - Process", "scripts/01_process.py"))

    # 02 — Compile
    steps.append(("02 - Compile", "scripts/02_compile.py"))

    # 03 ou 04 — Upload ou Sync
    if args.initial:
        steps.append(("03 - Upload Initial", "scripts/03_upload.py", ["--confirm"]))
    else:
        steps.append(("04 - Sync", "scripts/04_sync.py"))

    # 05 — Commission
    steps.append(("05 - Commission", "scripts/05_commission.py"))

    # 06 — Send
    if not args.skip_send:
        steps.append(("06 - Send Report", "scripts/06_send_report.py"))

    # 07, 08, 09 - Rapports Périodiques (auto-régulés, aucun envoi si déjà fait)
    if not args.skip_send:
        steps.append(("07 - Weekly BA Activity", "scripts/07_weekly_ba_activity.py"))
        steps.append(("08 - Weekly Sup KPI", "scripts/08_weekly_sup_kpi.py"))
        steps.append(("09 - Monthly Financial", "scripts/09_monthly_financial.py"))

    # Execution sequentielle
    for step in steps:
        name = step[0]
        script = step[1]
        extra = step[2] if len(step) > 2 else None

        ok, err_log, code = run_step(name, script, extra)
        if name == "00 - Fetch Mail" and code == 2:
            print("\n  Aucun nouveau mail PERFORMANCE GLOBALE. Pipeline arrêté sans erreur.")
            sys.exit(0)
        if not ok:
            # Tronque très grand log d'erreur avant de l'envoyer dans l'email
            err_body = err_log[-3500:] if len(err_log) > 3500 else err_log
            notify_failure(name, f"LOG D'ERREUR/Traceback :\n{err_body}")
            print(f"\n  PIPELINE ARRETE a l'etape : {name}")
            sys.exit(1)

    # Succes
    mark_done()
    print(f"\n{'='*60}")
    print(f"  PIPELINE TERMINE AVEC SUCCES")
    print(f"  Flag : {FLAG_PATH}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
