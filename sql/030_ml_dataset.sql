SELECT p.price_id,p.loading_date,p.loading_city_gcid,p.unloading_city_gcid,
 p.distance,p.total_weight,p.total_volume,p.weight_category,p.volume_category,
 p.price_rub::float8 AS price_rub,p.is_fact,p.price_type,p.complex,p.outlier_mark,
 o.region AS origin_region,d.region AS destination_region,
 o.gc_id::text AS origin_city,d.gc_id::text AS destination_city,
 o.latitude AS origin_latitude,o.longitude AS origin_longitude,
 d.latitude AS destination_latitude,d.longitude AS destination_longitude,
 b.body_group
FROM core.prices p
JOIN core.cities o ON o.gc_id=p.loading_city_gcid
JOIN core.cities d ON d.gc_id=p.unloading_city_gcid
JOIN LATERAL (
 SELECT string_agg(body_group,' | ' ORDER BY body_group) AS body_group
 FROM core.price_bodies WHERE price_id=p.price_id
) b ON true
WHERE p.loading_date >= %(train_start)s AND NOT p.complex
AND (
 (p.loading_date<=%(as_of)s AND p.is_fact AND p.price_type IN (1,2,3,4,5,9) AND NOT p.outlier_mark)
 OR p.loading_date>%(as_of)s
)
ORDER BY p.loading_date,p.price_id;
