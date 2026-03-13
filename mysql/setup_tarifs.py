import sys
from sqlalchemy import text
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from connections.connect import make_engine
from connections.config import MYSQL_DATABASE

def setup_tarifs():
    engine = make_engine(MYSQL_DATABASE)
    try:
        with engine.begin() as conn:
            print("1. Creation de la table commission_tarifs...")
            conn.execute(text("DROP TABLE IF EXISTS commission_tarifs;"))
            conn.execute(text("""
            CREATE TABLE commission_tarifs (
                id              INT AUTO_INCREMENT PRIMARY KEY,
                type_agent      VARCHAR(50)     NOT NULL,
                promotion       VARCHAR(100)    NOT NULL,
                date_debut      DATE            NOT NULL,
                date_fin        DATE            NOT NULL,
                jour_debut      TINYINT         NULL,
                jour_fin        TINYINT         NULL,
                taux_gadd       DECIMAL(10,2)   NOT NULL DEFAULT 0,
                taux_ads        DECIMAL(10,2)   NOT NULL DEFAULT 0,
                periode_nom     VARCHAR(50)     NOT NULL
            );
            """))

            print("2. Insertion des regles d'acquisition...")
            # Jours dans MySQL (fonction DAYOFWEEK): 1=Dimanche, 2=Lundi, 3=Mardi, 4=Mercredi, 5=Jeudi, 6=Vendredi, 7=Samedi
            conn.execute(text("""
            INSERT INTO commission_tarifs (type_agent, promotion, date_debut, date_fin, jour_debut, jour_fin, taux_gadd, taux_ads, periode_nom) VALUES
            -- BA (Classiques & Agence)
            ('BA', 'Campagne Actuelle', '2026-02-27', '2099-12-31', 2, 7, 200, 100, 'Semaine'),
            ('BA_AGENCE', 'Campagne Actuelle', '2026-02-27', '2099-12-31', 2, 7, 200, 100, 'Semaine'),
            ('BA', 'Campagne Actuelle', '2026-02-27', '2099-12-31', 1, 1, 300, 100, 'Dimanche'),
            ('BA_AGENCE', 'Campagne Actuelle', '2026-02-27', '2099-12-31', 1, 1, 300, 100, 'Dimanche'),

            -- Animation
            ('Animation Pick-up', 'Campagne Actuelle', '2026-02-27', '2099-12-31', 2, 7, 200, 100, 'Semaine'),
            ('Animation POS', 'Campagne Actuelle', '2026-02-27', '2099-12-31', 2, 7, 200, 100, 'Semaine'),
            ('Animation Pick-up', 'Campagne Actuelle', '2026-02-27', '2099-12-31', 1, 1, 300, 100, 'Dimanche'),
            ('Animation POS', 'Campagne Actuelle', '2026-02-27', '2099-12-31', 1, 1, 300, 100, 'Dimanche'),

            -- Master Agents (MA)   week-end = Vendredi et Samedi (200 + 100 cashback) = 300, Dimanche = 300
            -- Note: New User data = 100 (Ads) sauf MA qui ne s'en occupe pas (taux_ads=0)
            ('MA', 'Campagne Actuelle', '2026-02-27', '2099-12-31', 2, 5, 100, 0, 'Semaine'),
            ('MA', 'Campagne Actuelle', '2026-02-27', '2099-12-31', 6, 7, 300, 0, 'Weekend'),
            ('MA', 'Campagne Actuelle', '2026-02-27', '2099-12-31', 1, 1, 300, 0, 'Dimanche');
            """))

            print("3. Creation de la vue vw_commission_gadd...")
            conn.execute(text("""
            CREATE OR REPLACE VIEW vw_commission_gadd AS
            SELECT
                p.user_name, a.superviseur, a.agent_name, a.msisdn_momo, a.real_channel, a.region, a.tss, 
                p.perf_date, p.gadd, 
                COALESCE(t.periode_nom, 'Autre') AS periode_nom,
                COALESCE(t.taux_gadd, 0) AS taux_gadd_applique,
                p.gadd * COALESCE(t.taux_gadd, 0) AS commission_gadd
            FROM daily_gadd p
            LEFT JOIN agent_perf_info a ON p.user_name = a.user_name
            LEFT JOIN commission_tarifs t
                ON  t.type_agent = a.real_channel
                AND p.perf_date BETWEEN t.date_debut AND t.date_fin
                AND (t.jour_debut IS NULL OR DAYOFWEEK(p.perf_date) BETWEEN t.jour_debut AND t.jour_fin);
            """))
            
            print("4. Creation de la vue vw_commission_ads...")
            conn.execute(text("""
            CREATE OR REPLACE VIEW vw_commission_ads AS
            SELECT
                p.user_name, a.superviseur, a.agent_name, a.msisdn_momo, a.real_channel, a.region, a.tss, 
                p.perf_date, p.ads, 
                COALESCE(t.periode_nom, 'Autre') AS periode_nom,
                COALESCE(t.taux_ads, 0) AS taux_ads_applique,
                p.ads * COALESCE(t.taux_ads, 0) AS commission_ads
            FROM daily_ads p
            LEFT JOIN agent_perf_info a ON p.user_name = a.user_name
            LEFT JOIN commission_tarifs t
                ON  t.type_agent = a.real_channel
                AND p.perf_date BETWEEN t.date_debut AND t.date_fin
                AND (t.jour_debut IS NULL OR DAYOFWEEK(p.perf_date) BETWEEN t.jour_debut AND t.jour_fin);
            """))
            print("Termine avec succes ! La table est remplie et les vues sont pretes.")
    except Exception as e:
        print(f"Erreur lors du setup: {e}")

if __name__ == "__main__":
    setup_tarifs()
