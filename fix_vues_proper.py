import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from connections.connect import make_engine
from connections.config import MYSQL_DATABASE
from sqlalchemy import text

engine = make_engine(MYSQL_DATABASE)

# Step 1: Remove the BA tarifs I inserted (cleanup)
print("=== Step 1: Removing duplicated BA tarifs from commission_tarifs ===\n")

sql = text("""
    DELETE FROM commission_tarifs
    WHERE type_agent = 'BA'
""")

with engine.connect() as conn:
    result = conn.execute(sql)
    conn.commit()
    print(f"  Deleted {result.rowcount} rows\n")

# Verify
sql = text("""
    SELECT COUNT(*) as cnt
    FROM commission_tarifs
    WHERE type_agent = 'BA'
""")

with engine.connect() as conn:
    result = conn.execute(sql)
    cnt = result.fetchone()[0]
    print(f"  Remaining BA tarifs: {cnt} (should be 0)\n")

# Step 2: Recreate vw_commission_gadd with proper channel normalization
print("=== Step 2: Recreating vw_commission_gadd ===\n")

sql = text("""
    CREATE OR REPLACE VIEW vw_commission_gadd AS
    SELECT 
        p.user_name,
        a.supervisor_full_name AS superviseur,
        a.agent_name,
        a.momo_msisdn AS msisdn_momo,
        a.real_channel,
        a.region,
        a.tss_name AS tss,
        p.perf_date,
        p.gadd,
        COALESCE(t.periode_nom, 'Autre') AS periode_nom,
        COALESCE(t.taux_gadd, 0) AS taux_gadd_applique,
        (p.gadd * COALESCE(t.taux_gadd, 0)) AS commission_gadd
    FROM daily_gadd p
    LEFT JOIN lka_client_mtn.lka_usernames a ON p.user_name = a.user_name
    LEFT JOIN commission_tarifs t ON (
        t.type_agent = CASE WHEN a.real_channel = 'BA' THEN 'BA CLASSIQUE' ELSE a.real_channel END
        AND p.perf_date BETWEEN t.date_debut AND t.date_fin
        AND (t.jour_debut IS NULL OR DAYOFWEEK(p.perf_date) BETWEEN t.jour_debut AND t.jour_fin)
    )
""")

with engine.connect() as conn:
    conn.execute(sql)
    conn.commit()
    print("  vw_commission_gadd recreated successfully\n")

# Step 3: Recreate vw_commission_ads with proper channel normalization
print("=== Step 3: Recreating vw_commission_ads ===\n")

sql = text("""
    CREATE OR REPLACE VIEW vw_commission_ads AS
    SELECT 
        p.user_name,
        a.supervisor_full_name AS superviseur,
        a.agent_name,
        a.momo_msisdn AS msisdn_momo,
        a.real_channel,
        a.region,
        a.tss_name AS tss,
        p.perf_date,
        p.ads,
        COALESCE(t.periode_nom, 'Autre') AS periode_nom,
        COALESCE(t.taux_ads, 0) AS taux_ads_applique,
        (p.ads * COALESCE(t.taux_ads, 0)) AS commission_ads
    FROM daily_ads p
    LEFT JOIN lka_client_mtn.lka_usernames a ON p.user_name = a.user_name
    LEFT JOIN commission_tarifs t ON (
        t.type_agent = CASE WHEN a.real_channel = 'BA' THEN 'BA CLASSIQUE' ELSE a.real_channel END
        AND p.perf_date BETWEEN t.date_debut AND t.date_fin
        AND (t.jour_debut IS NULL OR DAYOFWEEK(p.perf_date) BETWEEN t.jour_debut AND t.jour_fin)
    )
""")

with engine.connect() as conn:
    conn.execute(sql)
    conn.commit()
    print("  vw_commission_ads recreated successfully\n")

# Step 4: Verify commissions work for BA agents
print("=== Step 4: Verifying BA agents get commissions ===\n")

names = ['Eugene.Koffi', 'Bonou.Bonou', 'Karim.Boukari']

for name in names:
    print(f"\n{name}:")
    
    sql = text("""
        SELECT 
            perf_date,
            gadd,
            taux_gadd_applique,
            commission_gadd
        FROM vw_commission_gadd
        WHERE user_name = :name
          AND perf_date BETWEEN '2026-05-18' AND '2026-05-20'
        ORDER BY perf_date
    """)
    
    with engine.connect() as conn:
        result = conn.execute(sql, {"name": name})
        rows = result.fetchall()
        for row in rows:
            print(f"  {row[0]}: gadd={row[1]}, tarif={row[2]}, comm={row[3]}")

print("\n=== ALL DONE ===")
