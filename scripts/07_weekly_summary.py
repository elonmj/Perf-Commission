import sys
import json
import base64
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import text
from email.message import EmailMessage

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from connections.config import MYSQL_DATABASE, TABLE_DAILY_GADD, COMMISSION_RECIPIENT, ADMIN_EMAIL
from connections.connect import make_engine
from scripts._00_fetch_mail import get_gmail_service

TRACKER_FILE = ROOT / "data" / "processed_weeks.json"

def get_last_completed_week(max_date):
    """
    Calcule la dernière semaine complète (Dimanche à Samedi) par rapport à max_date.
    Python weekday() : Lundi=0, ..., Samedi=5, Dimanche=6
    """
    days_since_saturday = (max_date.weekday() - 5) % 7
    last_saturday = max_date - timedelta(days=days_since_saturday)
    last_sunday = last_saturday - timedelta(days=6)
    
    return last_sunday, last_saturday

def load_processed_weeks():
    if not TRACKER_FILE.exists():
        return []
    try:
        return json.loads(TRACKER_FILE.read_text(encoding="utf-8"))
    except:
        return []

def save_processed_week(week_id):
    TRACKER_FILE.parent.mkdir(exist_ok=True)
    weeks = load_processed_weeks()
    if week_id not in weeks:
        weeks.append(week_id)
        TRACKER_FILE.write_text(json.dumps(weeks), encoding="utf-8")

def get_weekly_stats(engine, start_date, end_date):
    # Jointure avec la vue vw_commission_gadd / ads pour avoir les perfomances
    sql = text(f"""
        SELECT 
            superviseur, 
            real_channel,
            SUM(gadd) as total_gadd,
            SUM(commission_gadd) as total_commission
        FROM vw_commission_gadd
        WHERE perf_date BETWEEN :ds AND :de
        GROUP BY superviseur, real_channel
    """)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"ds": start_date, "de": end_date})
    return df

def send_weekly_email(service, html_content, start_date, end_date):
    subject = f"📊 Performance Globale - Bilan Hebdomadaire ({start_date.strftime('%d/%m')} au {end_date.strftime('%d/%m')})"
    
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = "me"
    # Send to admin and commission recipient
    msg["To"] = f"{COMMISSION_RECIPIENT}, {ADMIN_EMAIL}"
    
    msg.add_alternative(html_content, subtype='html')
    
    raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    service.users().messages().send(userId="me", body={"raw": raw_message}).execute()

def main():
    print("=== 07_weekly_summary.py -- Bilan Hebdomadaire ===")
    import importlib.util
    mod_name = "00_fetch_mail"
    spec = importlib.util.spec_from_file_location(mod_name, str(ROOT / "scripts" / "00_fetch_mail.py"))
    fetch_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fetch_mod)
    get_gmail_service = fetch_mod.get_gmail_service

    engine = make_engine(MYSQL_DATABASE)
    
    # 1. Obtenir la date max en base
    with engine.connect() as conn:
        row = conn.execute(text(f"SELECT MAX(perf_date) FROM {TABLE_DAILY_GADD}")).fetchone()
        
    if not row or not row[0]:
        print("  Aucune donnée en base. Annulation.")
        sys.exit(0)
        
    max_date = row[0] # date object
    
    start_date, end_date = get_last_completed_week(max_date)
    week_id = f"{start_date.strftime('%Y-%m-%d')}_to_{end_date.strftime('%Y-%m-%d')}"
    
    processed_weeks = load_processed_weeks()
    if week_id in processed_weeks:
        print(f"  Semaine {week_id} déjà traitée. Rien à faire.")
        sys.exit(0)
        
    print(f"  Nouvelle semaine détectée : {start_date} au {end_date}")
    print("  Calcul des statistiques...")
    
    df = get_weekly_stats(engine, start_date, end_date)
    
    if df.empty:
        print("  Aucune donnée pour cette période. Marquage comme traitée pour éviter des boucles.")
        save_processed_week(week_id)
        sys.exit(0)
        
    # KPI Globaux
    total_gadd = df['total_gadd'].sum()
    total_commission = df['total_commission'].sum()
    
    # Top 5 Superviseurs
    top_sups = df.groupby('superviseur')['total_gadd'].sum().nlargest(10)
    
    # HTML Email builder
    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333;">
        <h2 style="color: #2F5496;">Bilan Hebdomadaire LKA</h2>
        <p><strong>Période :</strong> Du Dimanche {start_date.strftime('%d/%m/%Y')} au Samedi {end_date.strftime('%d/%m/%Y')}</p>
        
        <div style="background-color: #f4f4f4; padding: 15px; border-radius: 5px; margin-bottom: 20px;">
            <h3 style="margin-top: 0;">📈 Chiffres Clés</h3>
            <ul style="list-style-type: none; padding-left: 0;">
                <li>🚀 <strong>Total GADD :</strong> {int(total_gadd):,}</li>
                <li>💰 <strong>Commissions Estimées (Gadd) :</strong> {int(total_commission):,} FCFA</li>
            </ul>
        </div>
        
        <h3>🏆 Top 10 Superviseurs (GADD)</h3>
        <table style="border-collapse: collapse; width: 100%; max-width: 600px;">
            <tr style="background-color: #2F5496; color: white;">
                <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">Superviseur</th>
                <th style="padding: 10px; border: 1px solid #ddd; text-align: center;">Total GADD</th>
            </tr>
    """
    
    for sup, gadd in top_sups.items():
        html += f"""
            <tr>
                <td style="padding: 10px; border: 1px solid #ddd;">{sup}</td>
                <td style="padding: 10px; border: 1px solid #ddd; text-align: center; font-weight: bold;">{int(gadd)}</td>
            </tr>
        """
        
    html += """
        </table>
        <br>
        <p style="font-size: 12px; color: #666; margin-top: 30px;">
            <em>Ce rapport est généré automatiquement par le pipeline Perf_commissions une fois la semaine complète de données réceptionnée en base de données.</em>
        </p>
      </body>
    </html>
    """
    
    print("  Envoi de l'email...")
    service = get_gmail_service()
    send_weekly_email(service, html, start_date, end_date)
    
    save_processed_week(week_id)
    print("  Rapport envoyé et semaine marquée comme traitée !")
    sys.exit(0)

if __name__ == "__main__":
    main()
