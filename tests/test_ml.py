from datetime import date,timedelta
from etl.pipeline import run_etl
from ml.train import train_and_score
from ml.features import FEATURES


def test_training_future_mask_and_repeated_scoring(db,add,tmp_path,monkeypatch):
    monkeypatch.setenv("MODEL_THREADS","1")
    for i in range(70):
        add(i+1,loading_date=date(2026,7,26)+timedelta(days=i),price=10000+i*100,
            bodies=[56,57,15])
    for i in range(22):
        add(i+101,loading_date=date(2026,10,5)+timedelta(days=i),price=18000+i*100)
    add(200,loading_date="2026-11-10",price=999999,price_type=6,is_fact=False,outlier_mark=True)
    run_etl(date(2026,1,1),date(2027,1,1),date(2026,10,26))
    args=(date(2026,7,26),date(2026,10,5),date(2026,10,26),tmp_path)
    report=train_and_score(*args,iterations=12)
    assert report["metrics"]["train_rows"]==70
    assert report["metrics"]["test_rows"]==22
    assert report["metrics"]["future_rows"]==1
    assert report["features"]==FEATURES
    assert db.execute("SELECT actual_price_rub,abs_error_rub,ape_pct FROM mart.ml_price_predictions WHERE price_id=200").fetchone()==(None,None,None)
    before=db.execute("SELECT price_id,predicted_price_rub,actual_price_rub FROM mart.ml_price_predictions ORDER BY price_id").fetchall()
    again=train_and_score(*args,iterations=12)
    assert again["model_id"]==report["model_id"]
    assert before==db.execute("SELECT price_id,predicted_price_rub,actual_price_rub FROM mart.ml_price_predictions ORDER BY price_id").fetchall()
    db.execute("UPDATE core.prices SET price_rub=price_rub*2 WHERE loading_date BETWEEN '2026-10-05' AND '2026-10-26'")
    changed=train_and_score(*args,iterations=12)
    assert changed["model_id"]==report["model_id"]
    assert changed["metrics"]["mae_rub"]!=report["metrics"]["mae_rub"]
    assert [(r[0],r[1]) for r in before]==db.execute("SELECT price_id,predicted_price_rub FROM mart.ml_price_predictions ORDER BY price_id").fetchall()


def test_more_than_one_prediction_batch(db,tmp_path,monkeypatch):
    monkeypatch.setenv("MODEL_THREADS","1")
    db.execute("""INSERT INTO raw.prices(id,loading_date,loading_city_gcid,unloading_city_gcid,
        distance,total_weight,total_volume,price,body_type)
        SELECT i,CASE WHEN i<=20 THEN DATE '2026-09-01' WHEN i<=25 THEN DATE '2026-10-05'
          ELSE DATE '2026-11-01' END,1001,1003,100+i,20,90,10000+i*10,56
        FROM generate_series(1,1125) i""")
    db.execute("INSERT INTO raw.price_dates(price_id,price_date) SELECT id,loading_date FROM raw.prices")
    run_etl(date(2026,1,1),date(2027,1,1),date(2026,10,26))
    report=train_and_score(date(2026,7,26),date(2026,10,5),date(2026,10,26),tmp_path,iterations=3)
    assert report['metrics']['future_rows']==1100
    assert db.execute("SELECT count(*) FROM mart.ml_price_predictions").fetchone()[0]==1105
    assert db.execute("SELECT count(*) FROM mart.ml_price_predictions WHERE score_kind='future' AND actual_price_rub IS NOT NULL").fetchone()[0]==0
