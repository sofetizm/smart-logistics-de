DELETE FROM mart.market_corridor;
INSERT INTO mart.market_corridor
WITH source_months AS (
 SELECT price_id,date_trunc('month',price_date)::date AS month,max(price_date) AS last_price_date
 FROM core.price_dates WHERE price_date<=%(as_of)s GROUP BY 1,2
), aggregate_cells AS (
 SELECT pm.month,p.loading_city_gcid,p.unloading_city_gcid,b.body_group,p.weight_category,
 percentile_cont(ARRAY[0.25,0.5,0.75]) WITHIN GROUP (ORDER BY p.price_rub::float8) AS trip,
 avg(p.price_rub)::float8 AS avg_trip,
 percentile_cont(ARRAY[0.25,0.5,0.75]) WITHIN GROUP
   (ORDER BY p.price_rub::float8 / NULLIF(p.distance,0)) AS km,
 count(DISTINCT p.price_id) AS trips_count,
 count(DISTINCT p.organization_id) FILTER(WHERE p.price_type IN (3,9)) AS carriers_count,
 stddev_samp(p.price_rub)::float8 / NULLIF(avg(p.price_rub)::float8,0) AS cv_rate,
 max(pm.last_price_date) AS last_price_date
 FROM core.prices p JOIN source_months pm USING(price_id)
 JOIN core.price_bodies b USING(price_id)
 WHERE p.is_fact AND p.price_type IN (1,2,3,4,5,9) AND NOT p.complex AND NOT p.outlier_mark
 AND p.price>0 AND p.price_rub>0 AND p.distance>0
 AND pm.last_price_date<=%(as_of)s
 GROUP BY pm.month,p.loading_city_gcid,p.unloading_city_gcid,b.body_group,p.weight_category
)
SELECT a.month,a.loading_city_gcid,a.unloading_city_gcid,a.body_group,a.weight_category,
 a.trip[1],a.trip[2],a.trip[3],a.avg_trip,a.km[1],a.km[2],a.km[3],
 a.trips_count,a.carriers_count,a.cv_rate,
 (a.trip[2]/NULLIF(prev.trip[2],0)-1)*100,
 (a.trip[2]/NULLIF(yr.trip[2],0)-1)*100,
 a.last_price_date,
 CASE WHEN a.trips_count>=30 AND a.carriers_count>=5
 AND %(as_of)s::date-a.last_price_date BETWEEN 0 AND 30 THEN 'HIGH'
 WHEN a.trips_count>=10 THEN 'MEDIUM' ELSE 'LOW_DATA' END,
 %(as_of)s::date
FROM aggregate_cells a
LEFT JOIN aggregate_cells prev ON prev.month=(a.month-INTERVAL '1 month')::date
 AND prev.loading_city_gcid=a.loading_city_gcid AND prev.unloading_city_gcid=a.unloading_city_gcid
 AND prev.body_group=a.body_group AND prev.weight_category=a.weight_category
LEFT JOIN aggregate_cells yr ON yr.month=(a.month-INTERVAL '1 year')::date
 AND yr.loading_city_gcid=a.loading_city_gcid AND yr.unloading_city_gcid=a.unloading_city_gcid
 AND yr.body_group=a.body_group AND yr.weight_category=a.weight_category;
