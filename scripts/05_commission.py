"""
scripts/05_commission.py -- Génération du fichier Excel de commissions
Architecture "Data-Driven"
Design UX Mobile-first avec en-tête figé, matrice tarifaire et colonnes épurées !
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, date

import pandas as pd
from sqlalchemy import text
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

ROOT = Path(__file__).parent.parent
OUTPUTS = ROOT / "outputs"

sys.path.insert(0, str(ROOT))
from connections.config import (
    MYSQL_DATABASE, TABLE_DAILY_GADD,
    AUTO_MODE, AUTO_DAYS_RANGE, MANUAL_END_DATE, MANUAL_RANGE_DAYS,
)
from connections.connect import make_engine

# ─── CONSTANTES DE STYLE ───────────────────────────────────────────────────────
HEADER_FONT  = Font(bold=True, color="FFFFFF", size=11)
HEADER_FILL  = PatternFill(start_color="2F5496", end_color="2F5496", fill_type="solid")
HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)

SUB_HEADER_FONT = Font(bold=True, color="000000", size=10)
SUB_HEADER_FILL = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")

THIN_BORDER  = Border(
    left=Side(style="thin"), right=Side(style="thin"),
    top=Side(style="thin"), bottom=Side(style="thin"),
)
CURRENCY_FMT = '#,##0'

# ─── HELPERS ───────────────────────────────────────────────────────────────────
def format_date_fr(d: date) -> str:
    jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    mois = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
    return f"{jours[d.weekday()]} {d.day} {mois[d.month-1]} {d.year}"

def auto_width(ws):
    for col in ws.columns:
        max_len = 0
        col_letter = col[0].column_letter
        for cell in col:
            val = str(cell.value) if cell.value is not None else ""
            max_len = max(max_len, len(val))
        ws.column_dimensions[col_letter].width = min(max_len + 3, 25)

def fetch_data(engine, view_name, val_col, comm_col, date_start, date_end):
    sql = text(f"""
        SELECT 
            user_name,
            superviseur AS nom_prenom_superviseur,
            agent_name,
            msisdn_momo,
            real_channel,
            periode_nom,
            taux_{val_col}_applique AS pu,
            SUM({val_col}) AS nb_total,
            SUM({comm_col}) AS amt_total
        FROM {view_name}
        WHERE perf_date BETWEEN :ds AND :de
        GROUP BY 
            user_name, superviseur, agent_name, msisdn_momo, real_channel, periode_nom, taux_{val_col}_applique
    """)
    with engine.connect() as conn:
        return pd.read_sql(sql, conn, params={"ds": date_start, "de": date_end})

def pivot_data(df, qty_label="Add"):
    if df.empty:
        return pd.DataFrame()

    records = []
    group_cols = ['user_name', 'nom_prenom_superviseur', 'agent_name', 'msisdn_momo', 'real_channel']
    grouped = df.groupby(group_cols, dropna=False)

    for name, group in grouped:
        r = {
            'USER NAME': name[0],
            'Superviseur': name[1],
            'AGENT_NAME': name[2],
            'MSISDN': name[3],
            'CANAL': name[4],
            f'TOTAL {qty_label}': group['nb_total'].sum(),
            'TOTAL A PAYER': group['amt_total'].sum()
        }

        for p in ['Semaine', 'Dimanche']:
            s_group = group[group['periode_nom'] == p]
            if not s_group.empty:
                r[f'{qty_label} {p}'] = s_group['nb_total'].sum()
                r[f'Mnt {p}'] = s_group['amt_total'].sum()
            else:
                r[f'{qty_label} {p}'] = 0
                r[f'Mnt {p}'] = 0

        records.append(r)
        
    res_df = pd.DataFrame(records)
    cols = [
        'USER NAME', 'Superviseur', 'AGENT_NAME', 'MSISDN', 'CANAL',
        f'TOTAL {qty_label}', 'TOTAL A PAYER',
        f'{qty_label} Semaine', 'Mnt Semaine',
        f'{qty_label} Dimanche', 'Mnt Dimanche'
    ]

    for col in cols:
        if col not in res_df.columns:
            res_df[col] = 0
            
    return res_df[cols].sort_values(by='TOTAL A PAYER', ascending=False)

def build_tariff_grid(engine, group_channels, data_type, date_ref):
    table_col = "taux_gadd" if "Add" in data_type else "taux_ads"
    ch = ", ".join([f"'{c}'" for c in group_channels])
    
    sql = text(f"""
        SELECT periode_nom, MAX({table_col}) as val
        FROM commission_tarifs
        WHERE type_agent IN ({ch})
          AND :d BETWEEN date_debut AND date_fin
        GROUP BY periode_nom
    """)
    row = {'Semaine': 0, 'Dimanche': 0}
    with engine.connect() as conn:
        res = conn.execute(sql, {"d": date_ref}).fetchall()
        for r in res:
            p = r[0]
            val = int(r[1])
            if p in row:
                row[p] = val
    return [row]

def write_sheet(wb, sheet_name, df_pivot, date_start, date_end, data_type="GADD", engine=None, group_channels=None):
    ws = wb.create_sheet(sheet_name)
    if df_pivot.empty:
        ws.cell(1, 1, f"Pas de données pour {data_type}")
        return

    # 1. EN-TÊTE : Période en colonne 1
    ws.cell(1, 1, f"Du {format_date_fr(date_start)}").font = Font(bold=True, italic=True)
    ws.cell(2, 1, f"Au {format_date_fr(date_end)}").font = Font(bold=True, italic=True)

    # 2. MINI-TABLEAU TARIFAIRE (Commence à la colonne 2)
    t_headers = ["PU Semaine", "PU Weekend", "PU Dimanche"]
    t_keys = ["Semaine", "Weekend", "Dimanche"]
    
    # Récupération des données tarifs (uniquement si un groupe de canaux est fourni)
    if group_channels:
        tariffs = build_tariff_grid(engine, group_channels, data_type, date_end)
        item = tariffs[0] if tariffs else {}
    else:
        item = {}  # Pas de grille tarifaire pour les feuilles combinées

    # Filtrage : On ne garde que les tarifs > 0
    active_pairs = [(h, k) for h, k in zip(t_headers, t_keys) if item.get(k, 0) > 0]
    
    for idx, (h, k) in enumerate(active_pairs, 2): # Colonne B (2) et suivantes
        # En-tête
        cell_h = ws.cell(1, idx, h)
        cell_h.font = SUB_HEADER_FONT
        cell_h.fill = SUB_HEADER_FILL
        cell_h.border = THIN_BORDER
        cell_h.alignment = Alignment(horizontal="center")
        
        # Valeur
        cell_v = ws.cell(2, idx, item.get(k, 0))
        cell_v.border = THIN_BORDER
        cell_v.number_format = CURRENCY_FMT

    # 3. EN-TÊTES DU TABLEAU DE DONNÉES (Ligne 3)
    start_data_row = 3

    # 3. EN-TÊTES DU TABLEAU DE DONNÉES
    headers = list(df_pivot.columns)
    for c, h in enumerate(headers, 1):
        cell = ws.cell(start_data_row, c, h)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = HEADER_ALIGN
        cell.border = THIN_BORDER

    # Identification des types de colonnes
    currency_cols = [h for h in headers if h.startswith("Mnt") or h == "TOTAL A PAYER"]
    cur_indices = [headers.index(x)+1 for x in currency_cols]
    
    qty_cols = [h for h in headers if h.startswith("Add") or h.startswith("ADS") or h.startswith("TOTAL Add") or h.startswith("TOTAL ADS")]
    qty_indices = [headers.index(x)+1 for x in qty_cols]

    # 4. ÉCRITURE DES LIGNES
    current_row = start_data_row + 1
    for r_idx, row in enumerate(df_pivot.itertuples(index=False), current_row):
        for c_idx, val in enumerate(row, 1):
            cell = ws.cell(r_idx, c_idx, val)
            
            if headers[c_idx-1] == 'MSISDN' and pd.notna(val) and str(val).strip() != "":
                try: cell.value = int(val)
                except: cell.value = val

            if headers[c_idx-1] == 'USER NAME':
                cell.value = str(val).lower() if val else ""

            if val is None or pd.isna(val) or val == 0:
                if c_idx in cur_indices or c_idx in qty_indices:
                    cell.value = 0
                else:
                    cell.value = ""
                
            cell.border = THIN_BORDER
            
            if c_idx in cur_indices: cell.number_format = CURRENCY_FMT
            if c_idx in qty_indices: cell.number_format = '0'

    # 5. LIGNE DES TOTAUX
    last_row = len(df_pivot) + start_data_row
    t_row = last_row + 1
    ws.cell(t_row, 5, "TOTAL GLOBAL").font = Font(bold=True)
    ws.cell(t_row, 5).border = THIN_BORDER
    
    sum_cols = qty_indices + cur_indices
    for c in sum_cols:
        col_ltr = ws.cell(2, c).column_letter
        ws.cell(t_row, c, f"=SUM({col_ltr}{start_data_row+1}:{col_ltr}{last_row})")
        ws.cell(t_row, c).font = Font(bold=True)
        ws.cell(t_row, c).border = THIN_BORDER
        if c in cur_indices: ws.cell(t_row, c).number_format = CURRENCY_FMT

    auto_width(ws)
    
    # 6. GEL DES VOLETS (FREEZE PANES)
    # Ligne 1-2 : Tarifs, Ligne 3 : En-têtes, Colonne A : User Name
    # Geler au niveau de B4 permet de garder l'en-tête (Ligne 3) statique avec les dates, et le nom figé.
    ws.freeze_panes = "B4"

def resolve_date_range(engine, args):
    """Determine la plage de dates selon : args CLI > config.py > extractions outputs."""
    from datetime import timedelta
    import re
    import os

    # 1. Arguments CLI explicites (prioritaires)
    if args.week:
        return (datetime.strptime(args.week[0], "%Y-%m-%d").date(),
                datetime.strptime(args.week[1], "%Y-%m-%d").date())
    if args.date:
        d = datetime.strptime(args.date, "%Y-%m-%d").date()
        return (d, d)

    # 2. Config BI (AUTO_MODE ou MANUAL)
    if AUTO_MODE:
        with engine.connect() as conn:
            row = conn.execute(text(f"SELECT MAX(perf_date) FROM {TABLE_DAILY_GADD}")).fetchone()
        if not row or not row[0]:
            print("Aucune donnee dans daily_gadd.")
            sys.exit(1)
        end = row[0]
        
        # Trouver la dernière date traitée dans les fichiers du répertoire outputs/
        pattern_old = r"commission_.*?(\d{4}-\d{2}-\d{2})\.xlsx$"
        pattern_new = r"Variables .* (\d{2}-\d{2}-\d{4})\.xlsx$"
        pattern_unified = r"Commission LKA .* (\d{2}-\d{2}-\d{4})\.xlsx$"
        
        dates_trouvees = []
        if os.path.exists(OUTPUTS):
            for f in os.listdir(OUTPUTS):
                # Ancien format
                m_old = re.search(pattern_old, f)
                if m_old:
                    dates_trouvees.append(datetime.strptime(m_old.group(1), "%Y-%m-%d").date())
                
                # Ancien format multi-fichier
                m_new = re.search(pattern_new, f)
                if m_new:
                    dates_trouvees.append(datetime.strptime(m_new.group(1), "%d-%m-%Y").date())

                # Format unifié (fichier unique)
                m_uni = re.search(pattern_unified, f)
                if m_uni:
                    dates_trouvees.append(datetime.strptime(m_uni.group(1), "%d-%m-%Y").date())
                    
        if dates_trouvees:
            last_comm_date = max(dates_trouvees)
            dyn_start = last_comm_date + timedelta(days=1)
            
            if dyn_start > end:
                start = end
            else:
                start = dyn_start
        else:
            # Fallback global si aucun fichier de commission précédent n'existe
            start = end - timedelta(days=AUTO_DAYS_RANGE - 1)

        return (start, end)
    else:
        end = datetime.strptime(MANUAL_END_DATE, "%Y-%m-%d").date()
        start = end - timedelta(days=MANUAL_RANGE_DAYS - 1)
        return (start, end)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--week", nargs=2, default=None)
    args = parser.parse_args()

    engine = make_engine(MYSQL_DATABASE)

    date_start, date_end = resolve_date_range(engine, args)

    print(f"=== Génération des Commissions (UX Mobile-First) ===")
    print(f"    Période : {format_date_fr(date_start)} -> {format_date_fr(date_end)}")

    df_gadd_raw = fetch_data(engine, "vw_commission_gadd", "gadd", "commission_gadd", date_start, date_end)
    df_ads_raw  = fetch_data(engine, "vw_commission_ads", "ads", "commission_ads", date_start, date_end)

    FILE_GROUPS = {
        "BA Animation": ["Animation Pick-up", "Animation POS"],
        "BA Classiques & BA AGENCE": ["BA CLASSIQUE", "BA_AGENCE"],
        "MA Acquisition": ["MA"]
    }

    OUTPUTS.mkdir(exist_ok=True)

    wb = Workbook()
    if wb.active is not None:
        wb.remove(wb.active)

    # Combiner tous les groupes en 2 feuilles : GADD (tous agents) + ADS/New Users (tous agents)
    gadd_frames = []
    ads_frames  = []

    for group_name, group_channels in FILE_GROUPS.items():
        df_g_grp = df_gadd_raw[df_gadd_raw['real_channel'].isin(group_channels)].copy() if not df_gadd_raw.empty else pd.DataFrame()
        df_a_grp = df_ads_raw[df_ads_raw['real_channel'].isin(group_channels)].copy()  if not df_ads_raw.empty  else pd.DataFrame()

        if not df_g_grp.empty:
            gadd_frames.append(pivot_data(df_g_grp, qty_label="Add"))
        if not df_a_grp.empty:
            ads_frames.append(pivot_data(df_a_grp, qty_label="ADS"))

    df_all_gadd = (
        pd.concat(gadd_frames, ignore_index=True)
          .sort_values('TOTAL A PAYER', ascending=False)
          .reset_index(drop=True)
        if gadd_frames else pd.DataFrame()
    )
    df_all_ads = (
        pd.concat(ads_frames, ignore_index=True)
          .sort_values('TOTAL A PAYER', ascending=False)
          .reset_index(drop=True)
        if ads_frames else pd.DataFrame()
    )

    write_sheet(wb, "GADD", df_all_gadd, date_start, date_end, "Tous - GADD",
                engine=engine, group_channels=None)
    write_sheet(wb, "ADS (New Users)", df_all_ads, date_start, date_end, "Tous - ADS",
                engine=engine, group_channels=None)

    print("\n✅ Feuilles ajoutées : GADD, ADS (New Users)")

    out_name = f"Commission LKA {date_start.strftime('%d-%m-%Y')} - {date_end.strftime('%d-%m-%Y')}.xlsx"
    out_path = OUTPUTS / out_name
    wb.save(out_path)
    
    print(f"\n✅ Fichier généré : {out_path.name}")

if __name__ == "__main__":
    main()