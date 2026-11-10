CREATE TEMP TABLE batch_ids ON COMMIT DROP AS
 SELECT id FROM raw.prices WHERE loading_date >= %(start_date)s AND loading_date < %(end_date)s
 UNION SELECT price_id FROM core.prices WHERE loading_date >= %(start_date)s AND loading_date < %(end_date)s
 UNION SELECT price_id FROM core.dq_quarantine_prices
 WHERE loading_date >= %(start_date)s AND loading_date < %(end_date)s;
CREATE UNIQUE INDEX ON batch_ids(id);

DELETE FROM core.cities;
INSERT INTO core.cities
 SELECT DISTINCT ON(gc_id) gc_id,id,name,full_name_local,
 CASE WHEN position(',' IN full_name_local)>0 THEN
 COALESCE(NULLIF(btrim(substring(full_name_local FROM position(',' IN full_name_local)+1)),''),'UNKNOWN') ELSE 'UNKNOWN' END,
 latitude,longitude
 FROM raw.cities ORDER BY gc_id,id;

CREATE TEMP TABLE rates ON COMMIT DROP AS
 SELECT num_code,setting_date,min(value) AS value,count(DISTINCT value) AS n_values
 FROM raw.exchange_rates GROUP BY num_code,setting_date;
CREATE UNIQUE INDEX ON rates(num_code,setting_date);
CREATE TEMP TABLE staged ON COMMIT DROP AS
 SELECT p.*,to_jsonb(p) AS raw_payload,
 CASE WHEN p.currency_code='643' THEN 1.0 ELSE r.value END AS fx_rate,
 ARRAY_REMOVE(ARRAY[
 CASE WHEN NOT(p.price>0 AND p.price<'Infinity'::float8) THEN 'INVALID_PRICE' END,
 CASE WHEN p.currency_code='643' AND p.price<=1000 THEN 'RUB_PRICE_TOO_LOW' END,
 CASE WHEN NOT(p.distance>0 AND p.distance<'Infinity'::float8) THEN 'INVALID_DISTANCE' END,
 CASE WHEN NOT(p.total_weight>=0 AND p.total_weight<'Infinity'::float8) THEN 'INVALID_WEIGHT' END,
 CASE WHEN NOT(p.total_volume>=0 AND p.total_volume<'Infinity'::float8) THEN 'INVALID_VOLUME' END,
 CASE WHEN o.gc_id IS NULL THEN 'UNKNOWN_ORIGIN' END,
 CASE WHEN d.gc_id IS NULL THEN 'UNKNOWN_DESTINATION' END,
 CASE WHEN p.currency_code NOT IN ('643','840','978') THEN 'UNSUPPORTED_CURRENCY' END,
 CASE WHEN p.currency_code IN ('840','978') AND r.setting_date IS NULL THEN 'MISSING_FX_RATE' END,
 CASE WHEN p.currency_code IN ('840','978') AND r.n_values>1 THEN 'AMBIGUOUS_FX_RATE' END,
 CASE WHEN p.currency_code IN ('840','978') AND NOT(r.value>0 AND r.value<'Infinity'::float8)
 THEN 'INVALID_FX_RATE' END
 ]::text[],NULL) AS reasons
 FROM raw.prices p JOIN batch_ids b ON b.id=p.id
 LEFT JOIN core.cities o ON o.gc_id=p.loading_city_gcid
 LEFT JOIN core.cities d ON d.gc_id=p.unloading_city_gcid
 LEFT JOIN rates r ON r.num_code=p.currency_code AND r.setting_date=p.nearest_rate_date;

DELETE FROM core.dq_quarantine_prices q USING batch_ids b WHERE q.price_id=b.id;
DELETE FROM core.prices p USING batch_ids b WHERE p.price_id=b.id;
INSERT INTO core.dq_quarantine_prices
 SELECT id,loading_date,reasons,raw_payload FROM staged WHERE cardinality(reasons)>0;
INSERT INTO core.prices
 SELECT id,loading_date,created_at,loading_city_gcid,unloading_city_gcid,
 distance,total_weight,total_volume,price,currency_code,nearest_rate_date,fx_rate,
 price::numeric * fx_rate::numeric,
 organization_id,price_type,is_fact,complex,outlier_mark,
 COALESCE(NULLIF(weight_category,''),core.weight_cat(total_weight)),
 COALESCE(NULLIF(volume_category,''),CASE WHEN total_volume>0 AND total_volume<=120 THEN 'FTL' ELSE 'OTH' END)
 FROM staged WHERE cardinality(reasons)=0;

INSERT INTO core.price_bodies
 SELECT DISTINCT p.price_id,core.body_group(COALESCE(pb.body_type_id,s.body_type),bt.std_id)
 FROM core.prices p JOIN staged s ON s.id=p.price_id
 LEFT JOIN raw.price_body_types pb ON pb.price_id=p.price_id
 LEFT JOIN raw.body_types bt ON bt.id=COALESCE(pb.body_type_id,s.body_type);
INSERT INTO core.price_dates
 SELECT DISTINCT p.price_id,pd.price_date
 FROM core.prices p JOIN batch_ids b ON b.id=p.price_id
 JOIN raw.price_dates pd ON pd.price_id=p.price_id;
