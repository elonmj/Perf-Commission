-- Commission views with channel normalization
-- BA is normalized to BA CLASSIQUE in the tariff join
--
-- superviseur : resolu via lka_supervisors (jointure sur supervisor_first_name),
-- pas directement depuis lka_usernames.supervisor_full_name qui peut etre
-- desynchronise/mal saisi a l'ingestion. COALESCE conserve le texte brut en
-- repli si le first_name ne matche aucune entree connue de lka_supervisors.
-- Voir incident 2026-07 (superviseur affiche "Zenontin Maxime" au lieu de
-- "AGBO Sewanou MAXIME" suite a une collision de premier prenom "MAXIME").

CREATE OR REPLACE VIEW vw_commission_gadd AS
SELECT
    p.user_name,
    COALESCE(s.supervisor_full_name, a.supervisor_full_name) AS superviseur,
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
LEFT JOIN lka_client_mtn.lka_supervisors s ON s.supervisor_first_name = a.supervisor_first_name
LEFT JOIN commission_tarifs t ON (
    t.type_agent = CASE WHEN a.real_channel = 'BA' THEN 'BA CLASSIQUE' ELSE a.real_channel END
    AND p.perf_date BETWEEN t.date_debut AND t.date_fin
    AND (t.jour_debut IS NULL OR DAYOFWEEK(p.perf_date) BETWEEN t.jour_debut AND t.jour_fin)
);

CREATE OR REPLACE VIEW vw_commission_ads AS
SELECT
    p.user_name,
    COALESCE(s.supervisor_full_name, a.supervisor_full_name) AS superviseur,
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
LEFT JOIN lka_client_mtn.lka_supervisors s ON s.supervisor_first_name = a.supervisor_first_name
LEFT JOIN commission_tarifs t ON (
    t.type_agent = CASE WHEN a.real_channel = 'BA' THEN 'BA CLASSIQUE' ELSE a.real_channel END
    AND p.perf_date BETWEEN t.date_debut AND t.date_fin
    AND (t.jour_debut IS NULL OR DAYOFWEEK(p.perf_date) BETWEEN t.jour_debut AND t.jour_fin)
);
