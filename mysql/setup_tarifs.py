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
                seuil_min       INT             NOT NULL DEFAULT 0,
                seuil_max       INT             NOT NULL DEFAULT 99999,
                taux_gadd       DECIMAL(10,2)   NOT NULL DEFAULT 0,
                taux_ads        DECIMAL(10,2)   NOT NULL DEFAULT 0,
                periode_nom     VARCHAR(50)     NOT NULL
            );
            """))

            print("2. Insertion des regles d'acquisition...")
            # Jours dans MySQL (fonction DAYOFWEEK): 1=Dimanche, 2=Lundi, 3=Mardi, 4=Mercredi, 5=Jeudi, 6=Vendredi, 7=Samedi
            conn.execute(text("""
            INSERT INTO commission_tarifs (type_agent, promotion, date_debut, date_fin, jour_debut, jour_fin, taux_gadd, taux_ads, periode_nom) VALUES
            -- ANCIENNES REGLES (Jusqu'au 15 Mars 2026 inclus)
            -- BA (Classiques & Agence)
            ('BA', 'Campagne Actuelle', '2026-02-27', '2026-03-15', 2, 5, 100, 100, 'Semaine'),
            ('BA', 'Campagne Actuelle', '2026-02-27', '2026-03-15', 6, 7, 300, 100, 'Weekend'),
            ('BA', 'Campagne Actuelle', '2026-02-27', '2026-03-15', 1, 1, 400, 100, 'Dimanche'),

            ('BA_AGENCE', 'Campagne Actuelle', '2026-02-27', '2026-03-15', 2, 5, 100, 100, 'Semaine'),
            ('BA_AGENCE', 'Campagne Actuelle', '2026-02-27', '2026-03-15', 6, 7, 300, 100, 'Weekend'),
            ('BA_AGENCE', 'Campagne Actuelle', '2026-02-27', '2026-03-15', 1, 1, 400, 100, 'Dimanche'),

            -- Animation
            ('Animation Pick-up', 'Campagne Actuelle', '2026-02-27', '2026-03-15', 2, 5, 200, 100, 'Semaine'),
            ('Animation Pick-up', 'Campagne Actuelle', '2026-02-27', '2026-03-15', 6, 7, 200, 100, 'Weekend'),
            ('Animation Pick-up', 'Campagne Actuelle', '2026-02-27', '2026-03-15', 1, 1, 300, 100, 'Dimanche'),

            ('Animation POS', 'Campagne Actuelle', '2026-02-27', '2026-03-15', 2, 5, 200, 100, 'Semaine'),
            ('Animation POS', 'Campagne Actuelle', '2026-02-27', '2026-03-15', 6, 7, 200, 100, 'Weekend'),
            ('Animation POS', 'Campagne Actuelle', '2026-02-27', '2026-03-15', 1, 1, 300, 100, 'Dimanche'),

            -- Master Agents (MA)   week-end = Vendredi et Samedi (200 + 100 cashback) = 300, Dimanche = (300 + 100 cashback) = 400
            -- Note: New User data = 100 (Ads) sauf MA qui ne s'en occupe pas (taux_ads=0)
            ('MA', 'Campagne Actuelle', '2026-02-27', '2026-03-15', 2, 5, 100, 0, 'Semaine'),
            ('MA', 'Campagne Actuelle', '2026-02-27', '2026-03-15', 6, 7, 300, 0, 'Weekend'),
            ('MA', 'Campagne Actuelle', '2026-02-27', '2026-03-15', 1, 1, 400, 0, 'Dimanche'),

            -- NOUVELLES REGLES (A partir du 16 Mars 2026)
            -- Pour tout le monde: New add 200 en semaine et samedi, 300 dimanche. Ads 100
            -- Le dimanche reste fige a 300 jusqu'au 20 Juin 2026 inclus (paliers a partir du 21).
            ('BA', 'Campagne Actuelle', '2026-03-16', '2099-12-31', 2, 7, 200, 100, 'Semaine'),
            ('BA', 'Campagne Actuelle', '2026-03-16', '2026-06-20', 1, 1, 300, 100, 'Dimanche'),

            ('BA_AGENCE', 'Campagne Actuelle', '2026-03-16', '2099-12-31', 2, 7, 200, 100, 'Semaine'),
            ('BA_AGENCE', 'Campagne Actuelle', '2026-03-16', '2026-06-20', 1, 1, 300, 100, 'Dimanche'),

            ('Animation Pick-up', 'Campagne Actuelle', '2026-03-16', '2099-12-31', 2, 7, 200, 100, 'Semaine'),
            ('Animation Pick-up', 'Campagne Actuelle', '2026-03-16', '2026-06-20', 1, 1, 300, 100, 'Dimanche'),

            ('Animation POS', 'Campagne Actuelle', '2026-03-16', '2099-12-31', 2, 7, 200, 100, 'Semaine'),
            ('Animation POS', 'Campagne Actuelle', '2026-03-16', '2026-06-20', 1, 1, 300, 100, 'Dimanche'),

            ('MA', 'Campagne Actuelle', '2026-03-16', '2099-12-31', 2, 7, 200, 100, 'Semaine'),
            ('MA', 'Campagne Actuelle', '2026-03-16', '2026-06-20', 1, 1, 300, 100, 'Dimanche');
            """))

            print("2b. Insertion des paliers dimanche (a partir du 21 Juin 2026)...")
            # Paliers MARGINAUX / PROGRESSIFS sur le volume de new adds (gadd) du jour :
            #   - les 10 premieres adds (1 a 10)  -> 300 / add
            #   - les adds suivantes (11 et plus) -> 400 / add
            # Ex : 15 adds = 10*300 + 5*400 = 5000 (et NON 15*400). La vue somme les
            # contributions de chaque palier (voir vw_commission_gadd).
            # taux_ads identique (100) sur les deux paliers : ADS inchange.
            conn.execute(text("""
            INSERT INTO commission_tarifs (type_agent, promotion, date_debut, date_fin, jour_debut, jour_fin, seuil_min, seuil_max, taux_gadd, taux_ads, periode_nom) VALUES
            ('BA', 'Campagne Actuelle', '2026-06-21', '2099-12-31', 1, 1, 0, 10, 300, 100, 'Dimanche'),
            ('BA', 'Campagne Actuelle', '2026-06-21', '2099-12-31', 1, 1, 11, 99999, 400, 100, 'Dimanche'),

            ('BA_AGENCE', 'Campagne Actuelle', '2026-06-21', '2099-12-31', 1, 1, 0, 10, 300, 100, 'Dimanche'),
            ('BA_AGENCE', 'Campagne Actuelle', '2026-06-21', '2099-12-31', 1, 1, 11, 99999, 400, 100, 'Dimanche'),

            ('Animation Pick-up', 'Campagne Actuelle', '2026-06-21', '2099-12-31', 1, 1, 0, 10, 300, 100, 'Dimanche'),
            ('Animation Pick-up', 'Campagne Actuelle', '2026-06-21', '2099-12-31', 1, 1, 11, 99999, 400, 100, 'Dimanche'),

            ('Animation POS', 'Campagne Actuelle', '2026-06-21', '2099-12-31', 1, 1, 0, 10, 300, 100, 'Dimanche'),
            ('Animation POS', 'Campagne Actuelle', '2026-06-21', '2099-12-31', 1, 1, 11, 99999, 400, 100, 'Dimanche'),

            ('MA', 'Campagne Actuelle', '2026-06-21', '2099-12-31', 1, 1, 0, 10, 300, 100, 'Dimanche'),
            ('MA', 'Campagne Actuelle', '2026-06-21', '2099-12-31', 1, 1, 11, 99999, 400, 100, 'Dimanche');
            """))

            print("3. Creation de la vue vw_commission_gadd...")
            # Calcul MARGINAL : on NE filtre PAS par seuil dans le JOIN ; on somme la
            # contribution de chaque palier qui chevauche [1, gadd] :
            #   contribution = GREATEST(0, LEAST(gadd, seuil_max) - GREATEST(seuil_min,1) + 1) * taux
            # Pour les regles a un seul palier (0-99999) cela vaut simplement gadd*taux.
            # GROUP BY -> une seule ligne par (agent, jour).
            conn.execute(text("""
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
                -- Decomposition marginale : part des 10 premieres adds (<=10) et part au-dela (>10).
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
            """))

            print("4. Creation de la vue vw_commission_ads...")
            conn.execute(text("""
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
            """))
            print("Termine avec succes ! La table est remplie et les vues sont pretes.")
    except Exception as e:
        print(f"Erreur lors du setup: {e}")

if __name__ == "__main__":
    setup_tarifs()
