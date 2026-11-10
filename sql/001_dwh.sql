CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS mart;
CREATE SCHEMA IF NOT EXISTS ops;

CREATE OR REPLACE FUNCTION core.weight_cat(w double precision) RETURNS text
LANGUAGE sql IMMUTABLE STRICT AS $$
 SELECT CASE WHEN round(w::numeric,1)>=30 THEN 'G20T'
 WHEN round(w::numeric,1)>=10 THEN 'FTL' WHEN round(w::numeric,1)>=5 THEN '10T'
 WHEN round(w::numeric,1)>=2.5 THEN '5T' WHEN round(w::numeric,1)>=0.5 THEN 'L5T' ELSE 'OTH' END
$$;
CREATE OR REPLACE FUNCTION core.body_group(code integer, std integer DEFAULT NULL) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
 SELECT CASE WHEN code IS NULL THEN 'Не указан'
 WHEN code IN (56,57,58,59,60,61) OR std=56 THEN 'Тент'
 WHEN code IN (4,46,47,48) OR std=4 THEN 'Рефрижератор'
 WHEN code=2 OR std=2 THEN 'Изотерм'
 WHEN code IN (1,15) OR std=15 THEN 'Борт' ELSE 'Прочие' END
$$;
CREATE TABLE IF NOT EXISTS core.cities (
 gc_id integer PRIMARY KEY, source_id bigint NOT NULL, name text NOT NULL,
 full_name_local text NOT NULL, region text NOT NULL, latitude float8, longitude float8
);
CREATE TABLE IF NOT EXISTS core.prices (
 price_id bigint PRIMARY KEY, loading_date date NOT NULL, created_at timestamp,
 loading_city_gcid integer NOT NULL, unloading_city_gcid integer NOT NULL,
 distance float8 NOT NULL CHECK(distance>0), total_weight float8 NOT NULL CHECK(total_weight>=0),
 total_volume float8 NOT NULL CHECK(total_volume>=0), price float8 NOT NULL CHECK(price>0),
 currency_code text NOT NULL, nearest_rate_date date, fx_rate float8 NOT NULL,
 price_rub numeric NOT NULL CHECK(price_rub>0),
 organization_id integer, price_type smallint NOT NULL, is_fact boolean NOT NULL,
 complex boolean NOT NULL, outlier_mark boolean NOT NULL,
 weight_category text NOT NULL, volume_category text NOT NULL
);
CREATE INDEX IF NOT EXISTS core_prices_date_idx ON core.prices(loading_date);
CREATE TABLE IF NOT EXISTS core.price_bodies (
 price_id bigint NOT NULL REFERENCES core.prices ON DELETE CASCADE,
 body_group text NOT NULL, PRIMARY KEY(price_id,body_group)
);
CREATE TABLE IF NOT EXISTS core.price_dates (
 price_id bigint NOT NULL REFERENCES core.prices ON DELETE CASCADE,
 price_date date NOT NULL,
 PRIMARY KEY(price_id,price_date)
);
CREATE INDEX IF NOT EXISTS core_month_idx ON core.price_dates(price_date,price_id);
CREATE TABLE IF NOT EXISTS core.dq_quarantine_prices (
 price_id bigint PRIMARY KEY, loading_date date NOT NULL,
 reason_codes text[] NOT NULL, raw_payload jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS quarantine_date_idx ON core.dq_quarantine_prices(loading_date);
CREATE TABLE IF NOT EXISTS ops.etl_runs (
 run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 started_at timestamptz NOT NULL DEFAULT now(), start_date date, end_date date,
 rows_read bigint, rows_loaded bigint, rows_quarantined bigint, mart_rows bigint
);
CREATE TABLE IF NOT EXISTS mart.market_corridor (
 month date NOT NULL, loading_city_gcid integer NOT NULL, unloading_city_gcid integer NOT NULL,
 body_group text NOT NULL, weight_category text NOT NULL,
 p25_trip float8, median_trip float8, p75_trip float8, avg_trip float8,
 p25_km float8, median_km float8, p75_km float8,
 trips_count bigint NOT NULL, carriers_count bigint NOT NULL, cv_rate float8,
 mom_pct float8, yoy_pct float8, last_price_date date NOT NULL,
 reliability_level text NOT NULL, as_of date NOT NULL,
 PRIMARY KEY(month,loading_city_gcid,unloading_city_gcid,body_group,weight_category)
);
CREATE INDEX IF NOT EXISTS corridor_route_idx ON mart.market_corridor
 (loading_city_gcid,unloading_city_gcid,body_group,weight_category,month);
CREATE OR REPLACE VIEW mart.mart_route_card AS
 SELECT m.*, o.name AS loading_city, d.name AS unloading_city
 FROM mart.market_corridor m JOIN core.cities o ON o.gc_id=m.loading_city_gcid
 JOIN core.cities d ON d.gc_id=m.unloading_city_gcid;
CREATE TABLE IF NOT EXISTS mart.ml_models (
 model_id text PRIMARY KEY, model_name text NOT NULL, as_of date NOT NULL,
 train_start date NOT NULL, test_start date NOT NULL, metrics jsonb NOT NULL,
 feature_names jsonb NOT NULL, parameters jsonb NOT NULL, trained_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS mart.ml_price_predictions (
 model_id text NOT NULL REFERENCES mart.ml_models, price_id bigint NOT NULL,
 loading_date date NOT NULL, loading_city_gcid integer NOT NULL, unloading_city_gcid integer NOT NULL,
 body_group text NOT NULL, score_kind text NOT NULL CHECK(score_kind IN ('test','future')),
 actual_price_rub float8, predicted_price_rub float8 NOT NULL CHECK(predicted_price_rub>0),
 abs_error_rub float8, ape_pct float8, model_name text NOT NULL,
 scored_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(model_id,price_id),
 CHECK(score_kind<>'future' OR (actual_price_rub IS NULL AND abs_error_rub IS NULL AND ape_pct IS NULL))
);
