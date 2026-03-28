"""
mysql/update_view_superviseur.py
Script dédié à la création ou la mise à jour des vues des superviseurs.
"""

import sys
import os
from sqlalchemy import text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from connections.connect import make_engine


# Convertit l'ancienne table statique en vue dynamique
VIEW_SUPERVISEUR_INFO = """
CREATE OR REPLACE VIEW vw_superviseur_info AS
SELECT
    supervisor_first_name AS superviseur_name,
    NULL AS msisdn_momo,
    IF(UPPER(supervisor_first_name) IN ('ROLAND', 'SAMUEL BOSSOU', 'VINCENT DE PAULE', 'VINCENT DE PAUL'), 'Mercenaire', 'Classiques') AS type_superviseur,
    MAX(region) AS region,
    2340 AS target_mensuel
FROM lka_client_mtn.lka_usernames
WHERE supervisor_first_name IS NOT NULL AND supervisor_first_name != ''
GROUP BY supervisor_first_name;
"""

VIEW_SUPERVISEUR = """
CREATE OR REPLACE VIEW vw_commission_superviseur AS

WITH
Mensuel_Gadd AS (
    SELECT
        a.supervisor_first_name as superviseur,
        DATE_FORMAT(g.perf_date, '%Y-%m') AS perf_month,
        COUNT(DISTINCT a.user_name) AS nb_ba_total,
        SUM(g.gadd) AS total_new_add
    FROM lka_client_mtn.lka_usernames a
    JOIN daily_gadd g ON a.user_name = g.user_name
    WHERE a.supervisor_first_name IS NOT NULL AND a.supervisor_first_name != ''
    GROUP BY a.supervisor_first_name, DATE_FORMAT(g.perf_date, '%Y-%m')
),

Daily_Active_BAs AS (
    SELECT
        a.supervisor_first_name as superviseur,
        DATE_FORMAT(g.perf_date, '%Y-%m') as perf_month,
        g.perf_date,
        COUNT(DISTINCT a.user_name) AS active_bas
    FROM lka_client_mtn.lka_usernames a
    JOIN daily_gadd g ON a.user_name = g.user_name
    WHERE g.gadd > 0 AND a.supervisor_first_name IS NOT NULL AND a.supervisor_first_name != ''
    GROUP BY a.supervisor_first_name, DATE_FORMAT(g.perf_date, '%Y-%m'), g.perf_date
),

Monthly_Active_Days AS (
    SELECT superviseur, perf_month, COUNT(*) as jours_actifs_15
    FROM Daily_Active_BAs
    WHERE active_bas >= 15
    GROUP BY superviseur, perf_month
)

SELECT
    s.superviseur_name,
    s.type_superviseur,
    m.perf_month,
    m.nb_ba_total,
    s.target_mensuel,
    m.total_new_add,
    COALESCE(mad.jours_actifs_15, 0) AS jours_actifs_15,

    IF(s.type_superviseur != 'Mercenaire',
        IF(m.nb_ba_total >= 15, 40000, (m.nb_ba_total / 15) * 40000), 
        IF(COALESCE(mad.jours_actifs_15, 0) >= 20, 60000, 0)
    ) AS prime_fixe,

    IF((m.total_new_add / NULLIF(s.target_mensuel, 0)) >= 1, 50000, (m.total_new_add / NULLIF(s.target_mensuel, 0)) * 50000) AS prime_variable,

    IF(s.type_superviseur != 'Mercenaire',
        IF(COALESCE(mad.jours_actifs_15, 0) >= 20, 20000, 0),
        0
    ) AS prime_15ba_jour,

    IF(s.type_superviseur = 'Mercenaire', m.total_new_add * 5, 0) AS prime_mercenaire
FROM vw_superviseur_info s
LEFT JOIN Mensuel_Gadd m ON m.superviseur = s.superviseur_name
LEFT JOIN Monthly_Active_Days mad ON mad.superviseur = s.superviseur_name AND mad.perf_month = m.perf_month;
"""

def replace_superviseur_view():
    engine = make_engine()
    with engine.connect() as conn:
        print("Mise à jour pour les Superviseurs...")
        try:
            # Drop old physical table if it exists to avoid confusion
            conn.execute(text("DROP TABLE IF EXISTS superviseur_info;"))
        except Exception:
            pass

        try:
            conn.execute(text(VIEW_SUPERVISEUR_INFO))
            conn.execute(text(VIEW_SUPERVISEUR))
            conn.commit()
            print(" Succès : vue 'vw_superviseur_info' et 'vw_commission_superviseur' créées !")
        except Exception as e:
            print(f"Erreur : {e}")

if __name__ == "__main__":
    replace_superviseur_view()
