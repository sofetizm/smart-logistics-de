import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from psycopg.types.json import Jsonb
from psycopg import ClientCursor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, mean_absolute_percentage_error
from etl.db import connect, log, sql_file, LOCK_ID
from ml.features import build_features, split_masks, CATEGORICAL, FEATURES


def train_and_score(train_start, test_start, as_of, artifact_dir, iterations=None):
    if not train_start < test_start <= as_of:
        raise ValueError("Require train_start < test_start <= as_of")
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    params = dict(iterations=iterations or int(os.getenv("MODEL_ITERATIONS", "600")),
                  depth=7, learning_rate=0.06, loss_function="RMSE", random_seed=20261026,
                  thread_count=int(os.getenv("MODEL_THREADS", "2")),
                  allow_writing_files=False, verbose=False)
    with connect() as conn:
        conn.autocommit = True
        conn.execute("SELECT pg_advisory_lock(%s)", (LOCK_ID,))
        with conn.transaction():
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            cur = conn.execute(sql_file("030_ml_dataset.sql"), {"train_start":train_start,"as_of":as_of})
            rows = pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])
            if rows.empty:
                raise ValueError("No ML rows: run ETL first")
            train, test, future = split_masks(rows, train_start, test_start, as_of)
            if train.sum()<2 or test.sum()<2:
                raise ValueError("Need at least two train and two test rows")
            log("ml_dataset", train_rows=int(train.sum()),test_rows=int(test.sum()),future_rows=int(future.sum()))
            x = build_features(rows)
            log("ml_training_started", iterations=params["iterations"])

            model = CatBoostRegressor(**params)
            model.fit(x.loc[train], rows.loc[train,"price_rub"], cat_features=CATEGORICAL)
            log("ml_training_complete")
            score_mask = test | future
            scored = rows.loc[score_mask].copy()
            prediction = np.maximum(model.predict(x.loc[score_mask]), 0.01)
            scored["prediction"] = prediction
            y = rows.loc[test,"price_rub"].to_numpy()
            yhat = scored.loc[test.loc[score_mask],"prediction"].to_numpy()
            metrics = dict(r2=float(r2_score(y,yhat)), mape_pct=float(mean_absolute_percentage_error(y,yhat)*100),
                           rmse_rub=float(np.sqrt(mean_squared_error(y,yhat))), mae_rub=float(mean_absolute_error(y,yhat)),
                           train_rows=int(train.sum()), test_rows=int(test.sum()), future_rows=int(future.sum()))

            digest = hashlib.sha256(pd.util.hash_pandas_object(
                pd.concat([x.loc[train], rows.loc[train,["price_id","price_rub"]]], axis=1), index=False
            ).values.tobytes() + json.dumps(params, sort_keys=True).encode() +
                f"{train_start}/{test_start}/{as_of}/features-v1/catboost-1.2.8".encode()).hexdigest()[:20]
            model_id = "catboost_" + digest
            model_name = "CatBoostRegressor-1.2.8-features-v1"
            model_path = artifact_dir / (model_id + ".cbm")
            temp_path = model_path.with_suffix(".tmp")
            model.save_model(str(temp_path))
            temp_path.replace(model_path)
            conn.execute("""INSERT INTO mart.ml_models
             (model_id,model_name,as_of,train_start,test_start,metrics,feature_names,parameters)
             VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(model_id) DO UPDATE SET metrics=EXCLUDED.metrics""",
             (model_id,model_name,as_of,train_start,test_start,Jsonb(metrics),Jsonb(FEATURES),Jsonb(params)))
            conn.execute("DELETE FROM mart.ml_price_predictions WHERE model_id=%s", (model_id,))
            records = []
            for row in scored.itertuples(index=False):
                is_future = row.loading_date > as_of
                actual = None if is_future else row.price_rub
                error = None if is_future else abs(actual-row.prediction)
                records.append((model_id,row.price_id,row.loading_date,row.loading_city_gcid,
                                row.unloading_city_gcid,row.body_group,"future" if is_future else "test",
                                actual,row.prediction,error,None if is_future else error/actual*100,model_name))
            log("ml_publishing", rows=len(records))
            insert_sql = """INSERT INTO mart.ml_price_predictions
              (model_id,price_id,loading_date,loading_city_gcid,unloading_city_gcid,body_group,score_kind,
               actual_price_rub,predicted_price_rub,abs_error_rub,ape_pct,model_name) VALUES """
            placeholder = "(" + ",".join(["%s"]*12) + ")"
            with ClientCursor(conn) as writer:
                for offset in range(0,len(records),1000):
                    batch = records[offset:offset+1000]
                    writer.execute(insert_sql + ",".join([placeholder]*len(batch)),
                                   [value for record in batch for value in record])
    report = dict(model_id=model_id,model_name=model_name,as_of=str(as_of),train_start=str(train_start),
                  test_start=str(test_start),metrics=metrics,features=FEATURES,parameters=params)
    report_temp = artifact_dir / "metrics.tmp"
    report_temp.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    report_temp.replace(artifact_dir / "metrics.json")
    log("ml_complete", model_id=model_id, **metrics)
    return report
