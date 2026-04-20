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
Le Task Scheduler l'appelle  ; si le flag du jour
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
import json
import importlib.util
from email.mime.text import MIMEText
from pathlib import Path
from datetime import datetime, date

ROOT = Path(__file__).parent

sys.path.insert(0, str(ROOT))
from connections.config import (
    FLAG_FILE, GMAIL_USER, GMAIL_APP_PASSWORD, SMTP_HOST, SMTP_PORT, ADMIN_EMAIL,
)

FLAG_PATH = ROOT / FLAG_FILE
PROCESSED_IDS_FILE = ROOT / "data" / "processed_mail_ids.json"


import time


def load_processed_state() -> dict:
    if not PROCESSED_IDS_FILE.exists():
        return {}
    try:
        data = json.loads(PROCESSED_IDS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            # Compatibilite ancien format
            return {m_id: {"status": "success", "last_step_completed": "ALL"} for m_id in data}
        if isinstance(data, dict):
            return data
        return {}
    except Exception:
        return {}


def save_processed_state(state: dict):
    PROCESSED_IDS_FILE.parent.mkdir(exist_ok=True)
    PROCESSED_IDS_FILE.write_text(json.dumps(state, indent=4), encoding="utf-8")


def get_latest_pending_mail_id(state: dict) -> str | None:
    # Prend le dernier mail pendings insere dans le dict (ordre d'insertion Python)
    pending = [m_id for m_id, meta in state.items() if isinstance(meta, dict) and meta.get("status") == "pending"]
    if not pending:
        return None
    return pending[-1]


def mark_step_completed(mail_id: str, step_name: str):
    state = load_processed_state()
    if mail_id not in state or not isinstance(state[mail_id], dict):
        state[mail_id] = {"status": "pending", "last_step_completed": step_name}
    else:
        state[mail_id]["status"] = "pending"
        state[mail_id]["last_step_completed"] = step_name
    save_processed_state(state)


def mark_mail_success(mail_id: str):
    state = load_processed_state()
    if mail_id not in state or not isinstance(state[mail_id], dict):
        state[mail_id] = {"status": "success", "last_step_completed": "ALL"}
    else:
        state[mail_id]["status"] = "success"
        state[mail_id]["last_step_completed"] = "ALL"
    save_processed_state(state)


def get_resume_steps(steps: list, mail_id: str | None, state: dict) -> list:
    """Retourne la liste d'etapes a executer en mode reprise."""
    if not mail_id:
        return steps

    mail_meta = state.get(mail_id, {})
    if not isinstance(mail_meta, dict):
        mail_meta = {}
    last_completed = mail_meta.get("last_step_completed")

    # En reprise, on ne refetch pas si le mail est deja telecharge.
    steps_wo_fetch = [s for s in steps if s[0] != "00 - Fetch Mail"]

    if not last_completed:
        return steps_wo_fetch

    for idx, step in enumerate(steps_wo_fetch):
        if step[0] == last_completed:
            return steps_wo_fetch[idx + 1 :]

    return steps_wo_fetch


def load_fetch_mail_module():
    spec = importlib.util.spec_from_file_location(
        "fetch_mail_module",
        ROOT / "scripts" / "00_fetch_mail.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Impossible de charger scripts/00_fetch_mail.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get_latest_unprocessed_mail_id(processed_state: dict) -> str | None:
    """Retourne l'id du dernier mail Gmail correspondant s'il n'est pas marque success."""
    try:
        fetch_mail = load_fetch_mail_module()
        latest_message = fetch_mail.get_latest_matching_message()
    except Exception as exc:
        print(f"  [Check Mail] Controle Gmail impossible, skip du rerun mail: {exc}")
        return None

    if not latest_message:
        return None

    latest_id = latest_message.get("id")
    latest_meta = processed_state.get(latest_id, {}) if latest_id else {}
    latest_status = latest_meta.get("status") if isinstance(latest_meta, dict) else None

    if latest_status == "success":
        return None

    return latest_id


def has_unprocessed_latest_mail(processed_state: dict) -> bool:
    """Retourne True si le dernier mail Gmail correspondant n'a pas encore ete traite avec succes."""
    latest_id = get_latest_unprocessed_mail_id(processed_state)
    if not latest_id:
        return False

    print(f"  [Check Mail] Nouveau mail ou mail non finalise detecte: {latest_id}")
    return True

def has_pending_retries() -> bool:
    """Verifie s'il y a des jours/metrics en attente de reprise."""
    try:
        spec = importlib.util.spec_from_file_location(
            "commission05",
            ROOT / "scripts" / "05_commission.py",
        )
        if spec is None or spec.loader is None:
            return False
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        state = mod.load_commission_state()
        return bool(state.get("pending_retries", []))
    except Exception:
        return False

def already_done_today(processed_state: dict, check_new_mail: bool = True) -> bool:
    if not FLAG_PATH.exists():
        return False
    content = FLAG_PATH.read_text().strip()
    is_today = content == str(date.today())
    if not is_today:
        return False
    # Si le flag est d'aujourd'hui mais qu'il y a des retries en attente,
    # permettre la relance intra-jour pour rejouer les jours anomaliques
    if has_pending_retries():
        return False
    if check_new_mail and has_unprocessed_latest_mail(processed_state):
        return False
    return True


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
    parser.add_argument("--force", action="store_true", help="Ignorer le flag et forcer l'execution")
    parser.add_argument("--skip-fetch", action="store_true", help="Sauter le fetch mail (pour tests)")
    parser.add_argument("--skip-send", action="store_true", help="Sauter l'envoi email")
    parser.add_argument("--initial", action="store_true", help="Premier chargement (utilise 03 au lieu de 04)")
    parser.add_argument("--force-send-all", action="store_true", help="Forcer TOUS les e-mails de reporting à s'envoyer (bypass trackers)")
    
    args = parser.parse_args()

    if args.force_send_all:
        import os
        os.environ["FORCE_SEND_ALL"] = "1"
        args.skip_fetch = True  # On ne fetch pas
        args.force = True       # On ignore le last_success

    print(f"=== Pipeline Perf Commissions — {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")
    print()

    processed_state = load_processed_state()
    current_mail_id = get_latest_pending_mail_id(processed_state)
    latest_unprocessed_mail_id = None

    if not args.skip_fetch:
        latest_unprocessed_mail_id = get_latest_unprocessed_mail_id(processed_state)

    if current_mail_id and latest_unprocessed_mail_id and latest_unprocessed_mail_id != current_mail_id:
        last_step = processed_state.get(current_mail_id, {}).get("last_step_completed", "?")
        print(
            "  [Reprise] Ancien mail pending detecte "
            f"({current_mail_id}, dernier step OK: {last_step}) mais un mail plus recent "
            f"attend le traitement ({latest_unprocessed_mail_id}). Priorite au dernier mail."
        )
        current_mail_id = None

    if current_mail_id:
        last_step = processed_state.get(current_mail_id, {}).get("last_step_completed", "?")
        print(f"  [Reprise] Mail pending detecte: {current_mail_id} (dernier step OK: {last_step})")

    # Verifier le flag
    if not args.force and already_done_today(processed_state, check_new_mail=not args.skip_fetch):
        print(f"  Pipeline deja execute aujourd'hui ({date.today()}).")
        print(f"  Utilisez --force pour relancer.")
        sys.exit(0)

    steps = []

    if not args.force_send_all:
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

    # Reprise intelligente: reprendre a la prochaine etape non reussie pour le mail pending.
    if current_mail_id:
        original_len = len(steps)
        steps = get_resume_steps(steps, current_mail_id, processed_state)
        if len(steps) != original_len:
            print(f"  [Reprise] {original_len - len(steps)} etape(s) sautee(s), reprise pipeline en cours.")

    # Execution sequentielle
    for step in steps:
        name = step[0]
        script = step[1]
        extra = step[2] if len(step) > 2 else None

        ok, err_log, code = run_step(name, script, extra)
        if name == "00 - Fetch Mail" and code == 2:
            if current_mail_id:
                print(f"\n  Aucun nouveau mail, reprise maintenue sur mail pending: {current_mail_id}")
                continue
            print("\n  Aucun nouveau mail PERFORMANCE GLOBALE. Pipeline arrêté sans erreur.")
            sys.exit(0)

        if ok:
            # Si le fetch a pu telecharger, on recharge l'etat pour capter le nouveau mail pending.
            if name == "00 - Fetch Mail":
                processed_state = load_processed_state()
                current_mail_id = get_latest_pending_mail_id(processed_state)
            if current_mail_id and name.startswith(("01 -", "02 -", "03 -", "04 -", "05 -", "06 -", "07 -", "08 -", "09 -")):
                mark_step_completed(current_mail_id, name)

        if not ok:
            # Tronque très grand log d'erreur avant de l'envoyer dans l'email
            err_body = err_log[-3500:] if len(err_log) > 3500 else err_log
            notify_failure(name, f"LOG D'ERREUR/Traceback :\n{err_body}")
            print(f"\n  PIPELINE ARRETE a l'etape : {name}")
            sys.exit(1)

    # Succes
    if current_mail_id:
        mark_mail_success(current_mail_id)
        print(f"  [Historique] Mail marque success : {current_mail_id}")

    mark_done()
    print(f"\n{'='*60}")
    print(f"  PIPELINE TERMINE AVEC SUCCES")
    print(f"  Flag : {FLAG_PATH}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
