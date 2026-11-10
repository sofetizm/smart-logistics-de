from etl.db import connect, log


def verify(as_of):
    with connect() as conn:
        checks = {
            "source_reconciliation": """SELECT (SELECT count(*) FROM raw.prices)=
              (SELECT count(*) FROM core.prices)+(SELECT count(*) FROM core.dq_quarantine_prices)""",
            "core_quarantine_disjoint": """SELECT NOT EXISTS(SELECT 1 FROM core.prices
              JOIN core.dq_quarantine_prices USING(price_id))""",
            "future_actuals_masked": """SELECT NOT EXISTS(SELECT 1 FROM mart.ml_price_predictions
              WHERE score_kind='future' AND (actual_price_rub IS NOT NULL OR abs_error_rub IS NOT NULL OR ape_pct IS NOT NULL))""",
            "corridor_order": """SELECT NOT EXISTS(SELECT 1 FROM mart.market_corridor
              WHERE p25_trip>median_trip OR median_trip>p75_trip OR p25_km>median_km OR median_km>p75_km)""",
            "no_future_market": "SELECT NOT EXISTS(SELECT 1 FROM mart.market_corridor WHERE last_price_date>%s)",
            "one_prediction_per_deal_model": """SELECT NOT EXISTS(SELECT 1 FROM mart.ml_price_predictions
              GROUP BY model_id,price_id HAVING count(*)>1)""",
        }
        results = {name:conn.execute(query,(as_of,) if name=="no_future_market" else None).fetchone()[0]
                   for name,query in checks.items()}
        stats = {name:conn.execute("SELECT count(*) FROM " + table).fetchone()[0]
                 for name,table in [("raw_rows","raw.prices"),("core_rows","core.prices"),
                  ("quarantine_rows","core.dq_quarantine_prices"),("market_cells","mart.market_corridor"),
                  ("prediction_rows","mart.ml_price_predictions")]}
    log("verification", checks=results, **stats)
    if not all(results.values()):
        raise AssertionError(results)
    return dict(checks=results, **stats)
