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
CREATE TABLE IF NOT EXISTS `superviseur_info` (
    `superviseur_name`  VARCHAR(255) PRIMARY KEY,
    `msisdn_momo`       BIGINT,
    `type_superviseur`  VARCHAR(50) COMMENT 'Classiques, Acquisition, Mercenaire',
    `region`            VARCHAR(100),
    `target_mensuel`    INT DEFAULT 2340
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

# Vue principale pour regrouper les statistiques et primes du Superviseur
VIEW_SUPERVISEUR = """
CREATE OR REPLACE VIEW vw_commission_superviseur AS

WITH 
-- 1. Mois de référence pour tous les GADD
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

-- 2. Sous-requête pour la règle "15 BAs productifs par jour"
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
    
    -- PRIME 1 : FIXE
    -- Superviseur classique : 40000 (Prorata si < 15 BA)
    -- Superviseur Mercenaire : 60000 (Condition : >= 20 jours à 15 BA actifs)
    IF(s.type_superviseur != 'Mercenaire', 
        IF(m.nb_ba_total >= 15, 40000, (m.nb_ba_total / 15) * 40000), 
        IF(COALESCE(mad.jours_actifs_15, 0) >= 20, 60000, 0)
    ) AS prime_fixe,
    
    -- PRIME 2 : VARIABLE PERF
    -- Les deux ont 50000 de variable, au prorata d'atteinte
    IF((m.total_new_add / s.target_mensuel) >= 1, 50000, (m.total_new_add / s.target_mensuel) * 50000) AS prime_variable,

    -- PRIME 3 : COMMISSION SUPPLEMENTAIRE (15 BA PAR JOUR)
    -- Classique : Si le superviseur valide 20 jours avec au moins 15 BAs -> prime de 20000
    IF(s.type_superviseur != 'Mercenaire',
        IF(COALESCE(mad.jours_actifs_15, 0) >= 20, 20000, 0),
        0
    ) AS prime_15ba_jour,

    -- PRIME 4 : MERCENAIRE ACTIVATION (Uniquement pour ce type)
    -- Prime unitaire de 5 FCFA par New Add
    IF(s.type_superviseur = 'Mercenaire', m.total_new_add * 5, 0) AS prime_mercenaire

FROM superviseur_info s
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
            print("✓ Succès : Table 'superviseur_info' et vue 'vw_commission_superviseur' créées !")
        except Exception as e:
            print(f"Erreur : {e}")

if __name__ == "__main__":
    replace_superviseur_view()
