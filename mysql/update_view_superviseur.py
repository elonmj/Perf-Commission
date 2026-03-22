"""
mysql/update_view_superviseur.py
Script dédié à la création ou la mise à jour de la table et vue des superviseurs.
"""

import sys
import os
from sqlalchemy import text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from connections.connect import make_engine

DDL_SUPERVISEUR_INFO = """
CREATE TABLE IF NOT EXISTS superviseur_info (
    superviseur_name  VARCHAR(255) PRIMARY KEY,
    msisdn_momo       BIGINT,
    	ype_superviseur  VARCHAR(50) COMMENT 'Classiques, Acquisition, Mercenaire',
    
egion            VARCHAR(100),
    	arget_mensuel    INT DEFAULT 2340
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

VIEW_SUPERVISEUR = """
CREATE OR REPLACE VIEW vw_commission_superviseur AS

WITH
All_Sups AS (
    SELECT DISTINCT superviseur AS superviseur_name
    FROM agent_perf_info
    WHERE superviseur IS NOT NULL AND superviseur != ''
),

Ref_Sup AS (
    SELECT 
        a.superviseur_name,
        COALESCE(s.type_superviseur, 'Classiques') AS type_superviseur,
        COALESCE(s.target_mensuel, 2340) AS target_mensuel
    FROM All_Sups a
    LEFT JOIN superviseur_info s ON a.superviseur_name = s.superviseur_name
),

Mensuel_Gadd AS (
    SELECT
        a.superviseur,
        DATE_FORMAT(g.perf_date, '%Y-%m') AS perf_month,
        COUNT(DISTINCT a.user_name) AS nb_ba_total,
        SUM(g.gadd) AS total_new_add
    FROM agent_perf_info a
    JOIN daily_gadd g ON a.user_name = g.user_name
    WHERE a.superviseur IS NOT NULL AND a.superviseur != ''
    GROUP BY a.superviseur, DATE_FORMAT(g.perf_date, '%Y-%m')
),

Daily_Active_BAs AS (
    SELECT
        a.superviseur,
        DATE_FORMAT(g.perf_date, '%Y-%m') as perf_month,
        g.perf_date,
        COUNT(DISTINCT a.user_name) AS active_bas
    FROM agent_perf_info a
    JOIN daily_gadd g ON a.user_name = g.user_name
    WHERE g.gadd > 0 AND a.superviseur IS NOT NULL AND a.superviseur != ''
    GROUP BY a.superviseur, DATE_FORMAT(g.perf_date, '%Y-%m'), g.perf_date
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

    IF((m.total_new_add / s.target_mensuel) >= 1, 50000, (m.total_new_add / s.target_mensuel) * 50000) AS prime_variable,

    IF(s.type_superviseur != 'Mercenaire',
        IF(COALESCE(mad.jours_actifs_15, 0) >= 20, 20000, 0),
        0
    ) AS prime_15ba_jour,

    IF(s.type_superviseur = 'Mercenaire', m.total_new_add * 5, 0) AS prime_mercenaire
FROM Ref_Sup s
LEFT JOIN Mensuel_Gadd m ON m.superviseur = s.superviseur_name
LEFT JOIN Monthly_Active_Days mad ON mad.superviseur = s.superviseur_name AND mad.perf_month = m.perf_month;
"""

def replace_superviseur_view():
    engine = make_engine()
    with engine.connect() as conn:
        print("Mise à jour pour les Superviseurs...")
        try:
            conn.execute(text(DDL_SUPERVISEUR_INFO))
            conn.execute(text(VIEW_SUPERVISEUR))
            conn.commit()
            print(" Succès : Table 'superviseur_info' et vue 'vw_commission_superviseur' créées !")
        except Exception as e:
            print(f"Erreur : {e}")

if __name__ == "__main__":
    replace_superviseur_view()
