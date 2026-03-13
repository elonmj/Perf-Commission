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


def already_done_today() -> bool:
    if not FLAG_PATH.exists():
        return False
    content = FLAG_PATH.read_text().strip()
    return content == str(date.today())


def mark_done():
    FLAG_PATH.write_text(str(date.today()))


def run_step(name: str, script: str, extra_args: list = None) -> bool:
    """Execute un script Python et retourne True si succes."""
    cmd = [sys.executable, str(ROOT / script)]
    if extra_args:
        cmd.extend(extra_args)

    print(f"\n{'='*60}")
    print(f"  ETAPE : {name}")
    print(f"  CMD   : {' '.join(cmd)}")
    print(f"{'='*60}\n")

    result = subprocess.run(cmd, cwd=str(ROOT))

    if result.returncode != 0:
        print(f"\n  ERREUR : {name} a echoue (exit code {result.returncode})")
        return False

    print(f"\n  OK : {name} termine avec succes.")
    return True


def notify_failure(step_name: str, error_detail: str = ""):
    """Envoie un email d'alerte en cas d'echec. Fallback sur plyer (Windows)."""
    subject = f"[ECHEC] Pipeline Perf_commissions — {step_name}"
    body = (
        f"L'etape '{step_name}' a echoue le {datetime.now().strftime('%Y-%m-%d %H:%M')}.\n\n"
        f"{error_detail}\n\n"
        f"Verifiez les logs sur le serveur."
    )

    # Tentative d'envoi email
    if GMAIL_USER and GMAIL_APP_PASSWORD and ADMIN_EMAIL:
        try:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = GMAIL_USER
            msg["To"] = ADMIN_EMAIL
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as srv:
                srv.login(GMAIL_USER, GMAIL_APP_PASSWORD)
                srv.send_message(msg)
            print(f"  Alerte email envoyee a {ADMIN_EMAIL}")
            return
        except Exception as exc:
            print(f"  Echec envoi email : {exc}")

    # Fallback : notification desktop (Windows seulement)
    try:
        from plyer import notification
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

    # Execution sequentielle
    for step in steps:
        name = step[0]
        script = step[1]
        extra = step[2] if len(step) > 2 else None

        ok = run_step(name, script, extra)
        if not ok:
            notify_failure(name)
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
