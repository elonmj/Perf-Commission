import sys
import os
import json
import base64
import mimetypes
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import text
from email.message import EmailMessage
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.styles import Font, PatternFill, Alignment

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from connections.config import MYSQL_DATABASE, TABLE_DAILY_GADD, RECIPIENTS_WEEKLY_BA_ACTIVITY
from connections.connect import make_engine
import importlib

fetch_mail = importlib.import_module("scripts.00_fetch_mail")
get_gmail_service = fetch_mail.get_gmail_service

TRACKER_FILE = ROOT / "data" / "processed_ba_activity_weeks.json"

def get_last_completed_week(max_date):
    days_since_saturday = (max_date.weekday() - 5) % 7
    last_saturday = max_date - timedelta(days=days_since_saturday)
    last_sunday = last_saturday - timedelta(days=6)
    return last_sunday, last_saturday

def load_processed_weeks():
    if not TRACKER_FILE.exists(): return []
    try: return json.loads(TRACKER_FILE.read_text(encoding="utf-8"))
    except: return []

def save_processed_week(week_id):
    TRACKER_FILE.parent.mkdir(exist_ok=True)
    weeks = load_processed_weeks()
    if week_id not in weeks:
        weeks.append(week_id)
        TRACKER_FILE.write_text(json.dumps(weeks), encoding="utf-8")

def send_email_with_attachment(service, subject, html_content, attachment_path, to_emails):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = "me"
    msg["To"] = to_emails

    msg.add_alternative(html_content, subtype='html')

    path = Path(attachment_path)
    if path.exists():
        ctype, encoding = mimetypes.guess_type(str(path))
        if ctype is None or encoding is not None:
            ctype = 'application/octet-stream'
        maintype, subtype = ctype.split('/', 1)
        with open(path, 'rb') as f:
            msg.add_attachment(f.read(), maintype=maintype, subtype=subtype, filename=path.name)
            
    raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    service.users().messages().send(userId="me", body={"raw": raw_message}).execute()

def format_excel_headers(ws, fill_color="E26B0A", font_color="FFFFFF"):
    header_fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type="solid")
    for cell in ws[1]:
        cell.font = Font(bold=True, color=font_color)
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = 18
    ws.freeze_panes = "A2"

def generate_ba_actif_weekly(engine, start_week, end_week):
    month_str = end_week.strftime('%Y-%m')
    start_of_month = pd.to_datetime(f"{month_str}-01").date()

    # Query with Region included and no generic "Username oui"
    query = f"""
    SELECT 
        a.user_name as `USER NAME`,
        'LKA SERVICES' as `DEALER`,
        a.region as `REGION`,
        a.departement as `DEPARTEMENT`,
        a.commune as `COMMUNE`,
        'LKA SERVICES' as `ENTERPRISE_NAME`,
        a.agent_name as `AGENT_NAME`,
        a.msisdn_momo as `MOMO_MSISDN`,
        a.p2p as `P2P MSISDN`,
        a.real_channel as `REAL_CHANNEL`,
        a.superviseur as `Superviseur`,
        '' as `SUP_MOMO_MSISDN`,
        a.tss as `TSS NAME`,
        a.real_channel as `OTHER DEALERS`,
        a.msisdn_momo as `Numero Pulse`,
        a.id_pulse as `Id pulse`,
        g.perf_date as `perf_date`,
        COALESCE(g.gadd, 0) as `gadd`
    FROM agent_perf_info a
    LEFT JOIN daily_gadd g ON a.user_name = g.user_name 
                          AND g.perf_date >= '{start_of_month}' 
                          AND g.perf_date <= '{end_week}'
    WHERE a.superviseur IS NOT NULL AND a.superviseur != ''
    """
    df = pd.read_sql(query, engine)
    
    idx_cols = [
        'REGION', 'Superviseur', 'USER NAME', 'DEALER', 'DEPARTEMENT', 'COMMUNE', 
        'ENTERPRISE_NAME', 'AGENT_NAME', 'MOMO_MSISDN', 'P2P MSISDN', 
        'REAL_CHANNEL', 'SUP_MOMO_MSISDN', 'TSS NAME', 
        'OTHER DEALERS', 'Numero Pulse', 'Id pulse'
    ]
    
    pivot_df = df.pivot_table(index=idx_cols, columns='perf_date', values='gadd', aggfunc='sum')
    pivot_df = pivot_df.reset_index()
    pivot_df = pivot_df.loc[:, pivot_df.columns.notnull()]
        
    date_range = pd.date_range(start=start_of_month, end=end_week)
    for dt in date_range:
        if dt.date() not in pivot_df.columns:
            pivot_df[dt.date()] = 0
            
    date_cols = [c for c in pivot_df.columns if type(c) == type(start_of_month) or isinstance(c, datetime)]
    date_cols_sorted = sorted(date_cols)

    pivot_df = pivot_df[idx_cols + date_cols_sorted].fillna(0).copy()
    
    month_dates = [c for c in date_cols_sorted]
    last_week_dates = [c for c in date_cols_sorted if pd.to_datetime(c).date() >= start_week and pd.to_datetime(c).date() <= end_week]
    
    pivot_df['Actif pour le mois'] = (pivot_df[month_dates].sum(axis=1) > 0).astype(int)
    pivot_df['Actif La semaine denier'] = (pivot_df[last_week_dates].sum(axis=1) > 0).astype(int)
    
    recap = pivot_df.groupby(['REGION', 'Superviseur']).agg(
        Nb_des_BA=('USER NAME', 'count'),
        Nb_Actif_pour_le_mois=('Actif pour le mois', 'sum'),
        Nb_Actif_La_semaine_denier=('Actif La semaine denier', 'sum')
    ).reset_index()
    
    recap.rename(columns={
        'Superviseur': 'Description', 
        'Nb_des_BA': 'Nb des BA', 
        'Nb_Actif_pour_le_mois': 'Nb Actif pour le mois', 
        'Nb_Actif_La_semaine_denier': 'Nb Actif La semaine denier'
    }, inplace=True)
                           
    recap['PCT Actif le mois'] = recap['Nb Actif pour le mois'] / recap['Nb des BA']
    recap['PCT Actif la semaine dernier'] = recap['Nb Actif La semaine denier'] / recap['Nb des BA']
    
    # Sort regions/superviseurs by best performance (descending)
    recap = recap.sort_values(by='PCT Actif le mois', ascending=False)
    # Sort pivot exactly by region and supervisor, but we keep it simple for now
    pivot_df = pivot_df.sort_values(by=['REGION', 'Superviseur'])

    output_dir = os.path.join(ROOT, "outputs")
    os.makedirs(output_dir, exist_ok=True)
    out_file = os.path.join(output_dir, f"Weekly_BA_Actif_par_Superviseur_{start_week}_to_{end_week}.xlsx")
    
    with pd.ExcelWriter(out_file, engine='openpyxl') as writer:
        recap.to_excel(writer, sheet_name='Recap', index=False)
        pivot_df.to_excel(writer, sheet_name='New Add', index=False)
        
        ws_recap = writer.sheets['Recap']
        format_excel_headers(ws_recap, fill_color="4F81BD")
        for row in ws_recap.iter_rows(min_row=2, max_row=ws_recap.max_row, min_col=6, max_col=7):
            for cell in row:
                cell.number_format = '0.00%'

        ws_new_add = writer.sheets['New Add']
        format_excel_headers(ws_new_add, fill_color="4F81BD")

    return out_file

def main():
    print("=== 07_weekly_ba_activity.py ===")
    engine = make_engine(MYSQL_DATABASE)

    with engine.connect() as conn:
        row = conn.execute(text(f"SELECT MAX(perf_date) FROM {TABLE_DAILY_GADD}")).fetchone()
        
    if not row or not row[0]: return

    max_date = row[0]
    start_date, end_date = get_last_completed_week(max_date)
    week_id = f"{start_date.strftime('%Y-%m-%d')}_to_{end_date.strftime('%Y-%m-%d')}"
    
    processed_weeks = load_processed_weeks()
    if week_id in processed_weeks:
        print(f"  Semaine {week_id} déjà traitée (BA Actif).")
        sys.exit(0)

    ba_file = generate_ba_actif_weekly(engine, start_date, end_date)
    
    service = get_gmail_service()
    html_ba = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333;">
        <h2 style="color: #4F81BD;">Activité Hebdomadaire des BA par Superviseur</h2>
        <p><strong>Période :</strong> Semaine du {start_date.strftime('%d/%m/%Y')} au {end_date.strftime('%d/%m/%Y')}</p>
        <p>Bonjour,</p>
        <p>Veuillez trouver ci-joint le bilan d'activité (BA Actifs) regroupé par Région et Superviseur, classé par les meilleures performances.</p>
        <p>L'onglet <strong>Recap</strong> donne vos KPIs globaux, et l'onglet <strong>New Add</strong> contient le détail journalier.</p>
        <br>
        <p style="font-size: 12px; color: #666;"><em>Service Reporting Automatisé</em></p>
      </body>
    </html>
    """
    subject_ba = f"📈 BA Actifs par Superviseur/Région ({start_date.strftime('%d/%m')} - {end_date.strftime('%d/%m')})"
    send_email_with_attachment(service, subject_ba, html_ba, ba_file, RECIPIENTS_WEEKLY_BA_ACTIVITY)

    save_processed_week(week_id)
    print("  Email Weekly BA Actif envoyé !")

if __name__ == "__main__":
    main()