SELECT month,loading_city,unloading_city,body_group,weight_category,
       p25_trip,median_trip,p75_trip,median_km,trips_count,carriers_count,
       cv_rate,mom_pct,yoy_pct,reliability_level
FROM mart.mart_route_card WHERE month='2026-10-01'
ORDER BY trips_count DESC LIMIT 20;

SELECT month,p25_trip,median_trip,p75_trip,p25_km,median_km,p75_km,
       trips_count,carriers_count,reliability_level
FROM mart.mart_route_card
WHERE loading_city_gcid=1001 AND unloading_city_gcid=1003
  AND body_group='Тент' AND weight_category='FTL'
ORDER BY month;

SELECT reason,count(*) FROM core.dq_quarantine_prices,
unnest(reason_codes) reason GROUP BY reason ORDER BY count(*) DESC;

SELECT model_id,metrics FROM mart.ml_models ORDER BY trained_at DESC;
SELECT score_kind,count(*),avg(abs_error_rub),avg(ape_pct)
FROM mart.ml_price_predictions
WHERE model_id=(SELECT model_id FROM mart.ml_models ORDER BY trained_at DESC LIMIT 1)
GROUP BY score_kind;
