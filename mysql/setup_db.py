"""
mysql/setup_db.py — Création de la base lka_perf_commissions et de ses tables.

Usage :
  py -3 mysql/setup_db.py            # créer la base + tables
  py -3 mysql/setup_db.py --drop     # supprimer et recréer
"""

import sys
import os
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sqlalchemy import text
from connections.connect import make_engine
from connections.config import (
    MYSQL_DATABASE, TABLE_DAILY_GADD, TABLE_DAILY_ADS,
    MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD,
)


DDL_DAILY_GADD = f"""
CREATE TABLE IF NOT EXISTS `{TABLE_DAILY_GADD}` (
    `user_name`    VARCHAR(255) NOT NULL,
    `perf_date`    DATE         NOT NULL,
    `gadd`         INT          DEFAULT 0,
    PRIMARY KEY (`user_name`, `perf_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

DDL_DAILY_ADS = f"""
CREATE TABLE IF NOT EXISTS `{TABLE_DAILY_ADS}` (
    `user_name`    VARCHAR(255) NOT NULL,
    `perf_date`    DATE         NOT NULL,
    `ads`          INT          DEFAULT 0,
    PRIMARY KEY (`user_name`, `perf_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

DDL_COMMISSION_TARIFS = """
CREATE TABLE IF NOT EXISTS `commission_tarifs` (
    `id`                 INT AUTO_INCREMENT PRIMARY KEY,
    `type_agent`         VARCHAR(50)     NOT NULL,
    `promotion`          VARCHAR(100)    NOT NULL DEFAULT 'Campagne Actuelle',
    `date_debut`         DATE            NOT NULL,
    `date_fin`           DATE            NOT NULL,
    `jour_debut`         TINYINT         NULL COMMENT 'DAYOFWEEK: 1=Dim, 2=Lun, ..., 7=Sam',
    `jour_fin`           TINYINT         NULL,
    `seuil_min`          INT             NOT NULL DEFAULT 0     COMMENT 'Volume min new adds (gadd) inclus',
    `seuil_max`          INT             NOT NULL DEFAULT 99999 COMMENT 'Volume max new adds (gadd) inclus',
    `taux_gadd`          DECIMAL(10,2)   NOT NULL DEFAULT 0,
    `taux_ads`           DECIMAL(10,2)   NOT NULL DEFAULT 0,
    `periode_nom`        VARCHAR(50)     NOT NULL COMMENT 'Semaine, Weekend, Dimanche'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

VIEW_GADD = """
CREATE OR REPLACE VIEW vw_commission_gadd AS
SELECT
    p.user_name, a.supervisor_full_name as superviseur, a.agent_name, a.momo_msisdn as msisdn_momo, a.real_channel, a.region, a.tss_name as tss,
    p.perf_date, p.gadd,
    COALESCE(MAX(t.periode_nom), 'Autre') AS periode_nom,
    CASE WHEN p.gadd > 0
         THEN ROUND(COALESCE(SUM(GREATEST(0, LEAST(p.gadd, t.seuil_max) - GREATEST(t.seuil_min, 1) + 1) * t.taux_gadd), 0) / p.gadd, 4)
         ELSE COALESCE(MAX(t.taux_gadd), 0)
    END AS taux_gadd_applique,
    COALESCE(SUM(GREATEST(0, LEAST(p.gadd, t.seuil_max) - GREATEST(t.seuil_min, 1) + 1) * t.taux_gadd), 0) AS commission_gadd,
    COALESCE(SUM(GREATEST(0, LEAST(p.gadd, t.seuil_max, 10) - GREATEST(t.seuil_min, 1)  + 1) * t.taux_gadd), 0) AS commission_gadd_t1,
    COALESCE(SUM(GREATEST(0, LEAST(p.gadd, t.seuil_max)     - GREATEST(t.seuil_min, 11) + 1) * t.taux_gadd), 0) AS commission_gadd_t2
FROM daily_gadd p
LEFT JOIN lka_client_mtn.lka_usernames a ON p.user_name = a.user_name
LEFT JOIN commission_tarifs t
    ON  t.type_agent = CASE
            WHEN a.real_channel IN ('BA CLASSIQUE', 'BA') THEN 'BA'
            WHEN a.real_channel IN ('BA AGENCE', 'BA_AGENCE') THEN 'BA_AGENCE'
            ELSE a.real_channel
        END
    AND p.perf_date BETWEEN t.date_debut AND t.date_fin
    AND (t.jour_debut IS NULL OR DAYOFWEEK(p.perf_date) BETWEEN t.jour_debut AND t.jour_fin)
GROUP BY p.user_name, a.supervisor_full_name, a.agent_name, a.momo_msisdn,
         a.real_channel, a.region, a.tss_name, p.perf_date, p.gadd;
"""

VIEW_ADS = """
CREATE OR REPLACE VIEW vw_commission_ads AS
SELECT
    p.user_name, a.supervisor_full_name as superviseur, a.agent_name, a.momo_msisdn as msisdn_momo, a.real_channel, a.region, a.tss_name as tss,
    p.perf_date, p.ads,
    COALESCE(MAX(t.periode_nom), 'Autre') AS periode_nom,
    CASE WHEN p.ads > 0
         THEN ROUND(COALESCE(SUM(GREATEST(0, LEAST(p.ads, t.seuil_max) - GREATEST(t.seuil_min, 1) + 1) * t.taux_ads), 0) / p.ads, 4)
         ELSE COALESCE(MAX(t.taux_ads), 0)
    END AS taux_ads_applique,
    COALESCE(SUM(GREATEST(0, LEAST(p.ads, t.seuil_max) - GREATEST(t.seuil_min, 1) + 1) * t.taux_ads), 0) AS commission_ads,
    COALESCE(SUM(GREATEST(0, LEAST(p.ads, t.seuil_max, 10) - GREATEST(t.seuil_min, 1)  + 1) * t.taux_ads), 0) AS commission_ads_t1,
    COALESCE(SUM(GREATEST(0, LEAST(p.ads, t.seuil_max)     - GREATEST(t.seuil_min, 11) + 1) * t.taux_ads), 0) AS commission_ads_t2
FROM daily_ads p
LEFT JOIN lka_client_mtn.lka_usernames a ON p.user_name = a.user_name
LEFT JOIN commission_tarifs t
    ON  t.type_agent = CASE
            WHEN a.real_channel IN ('BA CLASSIQUE', 'BA') THEN 'BA'
            WHEN a.real_channel IN ('BA AGENCE', 'BA_AGENCE') THEN 'BA_AGENCE'
            ELSE a.real_channel
        END
    AND p.perf_date BETWEEN t.date_debut AND t.date_fin
    AND (t.jour_debut IS NULL OR DAYOFWEEK(p.perf_date) BETWEEN t.jour_debut AND t.jour_fin)
GROUP BY p.user_name, a.supervisor_full_name, a.agent_name, a.momo_msisdn,
         a.real_channel, a.region, a.tss_name, p.perf_date, p.ads;
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--drop", action="store_true", help="DROP tables avant de recréer")
    args = parser.parse_args()

    # Connexion sans spécifier la base (pour CREATE DATABASE)
    from sqlalchemy import create_engine
    url = (
        f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
        f"@{MYSQL_HOST}:{MYSQL_PORT}/?charset=utf8mb4"
    )
    engine_root = create_engine(url, pool_pre_ping=True)

    print(f"Connexion → {MYSQL_HOST}:{MYSQL_PORT}")
    with engine_root.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` "
                          f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
        conn.commit()
        print(f"  Base '{MYSQL_DATABASE}' : OK")

    # Connexion à la base cible
    engine = make_engine()
    with engine.connect() as conn:
        if args.drop:
            print("\n  DROP tables (--drop) ...")
            for t in [TABLE_DAILY_GADD, TABLE_DAILY_ADS, "agent_perf_info"]:
                conn.execute(text(f"DROP TABLE IF EXISTS `{t}`"))
            conn.commit()
            print("  Tables supprimées.")

        print(f"\n  Création des tables ...")
        conn.execute(text(DDL_DAILY_GADD))
        conn.execute(text(DDL_DAILY_ADS))
        conn.execute(text(DDL_COMMISSION_TARIFS))
        conn.commit()
        print(f"  {TABLE_DAILY_GADD} : OK")
        print(f"  {TABLE_DAILY_ADS} : OK")
        print(f"  commission_tarifs : OK")

        print("\n  Création des vues SQL...")
        conn.execute(text(VIEW_GADD))
        conn.execute(text(VIEW_ADS))
        conn.commit()
        print(f"  vw_commission_gadd : OK")
        print(f"  vw_commission_ads : OK")

        # Grant powerbi SELECT
        try:
            conn.execute(text(
                f"GRANT SELECT ON `{MYSQL_DATABASE}`.* TO 'powerbi'@'%'"
            ))
            conn.commit()
            print(f"\n  GRANT SELECT → powerbi : OK")
        except Exception as e:
            print(f"\n  GRANT powerbi : {e}")

        # Vérification
        tables = conn.execute(text("SHOW TABLES")).fetchall()
        print(f"\n  Tables dans {MYSQL_DATABASE} : {[t[0] for t in tables]}")

    print("\nSetup terminé.")


if __name__ == "__main__":
    main()
