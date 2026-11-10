from datetime import date
import pytest
from etl.pipeline import run_etl

AS_OF = date(2026,10,26)


def etl():
    return run_etl(date(2023,1,1),date(2028,1,1),AS_OF)


@pytest.mark.parametrize("weight,expected",[(0.44,"OTH"),(0.45,"L5T"),(2.45,"5T"),(4.95,"10T"),
                                           (9.95,"FTL"),(29.95,"G20T"),(30,"G20T")])
def test_weight_rounding(db,weight,expected):
    assert db.execute("SELECT core.weight_cat(%s)",(weight,)).fetchone()[0]==expected


@pytest.mark.parametrize("change,reason",[
 ({"price":0},"INVALID_PRICE"),({"price":-1},"INVALID_PRICE"),({"price":1000},"RUB_PRICE_TOO_LOW"),
 ({"distance":0},"INVALID_DISTANCE"),({"distance":-3},"INVALID_DISTANCE"),
 ({"total_weight":-0.1},"INVALID_WEIGHT"),({"total_volume":-1},"INVALID_VOLUME"),
 ({"loading_city_gcid":9999},"UNKNOWN_ORIGIN"),({"unloading_city_gcid":9999},"UNKNOWN_DESTINATION"),
 ({"currency_code":"840","nearest_rate_date":None},"MISSING_FX_RATE"),
 ({"currency_code":"978","nearest_rate_date":"2026-09-02"},"MISSING_FX_RATE"),
 ({"currency_code":"123"},"UNSUPPORTED_CURRENCY"),({"price":float('nan')},"INVALID_PRICE")])
def test_quarantine(db,add,change,reason):
    add(1,**change)
    result=etl()
    assert result["rows_quarantined"]==1
    assert reason in db.execute("SELECT reason_codes FROM core.dq_quarantine_prices").fetchone()[0]
    assert db.execute("SELECT count(*) FROM core.prices").fetchone()[0]==0


def test_fx_uses_saved_date_not_loading_date(db,add):
    add(1,price=500,currency_code="840",loading_date="2026-10-10")
    etl()
    assert float(db.execute("SELECT price_rub FROM core.prices").fetchone()[0])==45000


def test_dimension_and_body_dedup_month_expansion(db,add):
    add(1,bodies=[56,57,61,15],months=["2026-09-10","2026-09-20","2026-10-10","2026-11-10"])
    add(2,body_type=None,total_volume=0)
    etl()
    assert db.execute("SELECT source_id,region FROM core.cities WHERE gc_id=1003").fetchone()==(2,'Республика Татарстан')
    assert db.execute("SELECT count(*) FROM core.price_bodies WHERE price_id=1").fetchone()[0]==2
    cards=db.execute("SELECT month,body_group,trips_count FROM mart.market_corridor WHERE body_group='Тент' ORDER BY month").fetchall()
    assert cards==[(date(2026,9,1),'Тент',1),(date(2026,10,1),'Тент',1)]
    assert db.execute("SELECT body_group FROM core.price_bodies WHERE price_id=2").fetchone()[0]=='Не указан'
    assert db.execute("SELECT volume_category FROM core.prices WHERE price_id=2").fetchone()[0]=='OTH'


def test_same_city_valid_and_outlier_auction_complex_excluded(db,add):
    add(1,unloading_city_gcid=1001)
    add(2,outlier_mark=True)
    add(3,price_type=6,is_fact=False)
    add(4,complex=True)
    etl()
    assert db.execute("SELECT count(*) FROM core.prices").fetchone()[0]==4
    assert db.execute("SELECT sum(trips_count) FROM mart.market_corridor").fetchone()[0]==1


def snapshot(db):
    return [db.execute("SELECT * FROM "+table+" ORDER BY 1,2").fetchall()
            for table in ["core.prices","core.price_bodies","core.price_dates","core.dq_quarantine_prices","mart.market_corridor"]]


def test_repeat_corrections_deletion_and_moved_date(db,add):
    add(1)
    add(2,price=0)
    etl()
    original=snapshot(db)
    etl()
    assert snapshot(db)==original
    db.execute("UPDATE raw.prices SET price=0 WHERE id=1")
    db.execute("UPDATE raw.prices SET price=12000 WHERE id=2")
    etl()
    assert db.execute("SELECT price_id FROM core.prices").fetchall()==[(2,)]
    db.execute("UPDATE raw.prices SET loading_date='2026-11-01' WHERE id=2")
    run_etl(date(2026,9,1),date(2026,10,1),AS_OF)
    assert db.execute("SELECT loading_date FROM core.prices WHERE price_id=2").fetchone()[0]==date(2026,11,1)
    db.execute("DELETE FROM raw.prices WHERE id=2")
    run_etl(date(2026,11,1),date(2026,12,1),AS_OF)
    assert db.execute("SELECT count(*) FROM core.prices").fetchone()[0]==0


def test_atomic_rollback(db,add,monkeypatch):
    import etl.pipeline as pipeline
    add(1)
    etl()
    before=snapshot(db)
    db.execute("UPDATE raw.prices SET price=55555")
    real_execute=pipeline.execute_script
    def fail_on_mart(conn,name,params=None):
        if name=="020_market_corridor.sql":
            raise RuntimeError("injected refresh failure")
        return real_execute(conn,name,params)
    monkeypatch.setattr(pipeline,"execute_script",fail_on_mart)
    with pytest.raises(RuntimeError):
        etl()
    assert snapshot(db)==before


@pytest.mark.parametrize("volume,expected",[(0,"OTH"),(120,"FTL"),(120.01,"OTH")])
def test_volume_boundaries(db,add,volume,expected):
    add(1,total_volume=volume,volume_category=None,weight_category=None,total_weight=9.95)
    etl()
    assert db.execute("SELECT volume_category,weight_category FROM core.prices").fetchone()==(expected,'FTL')


def test_conflicting_fx_rates_are_quarantined(db,add):
    db.execute("INSERT INTO raw.exchange_rates(num_code,value,setting_date) VALUES('840',95,'2026-09-01')")
    add(1,currency_code='840')
    etl()
    assert 'AMBIGUOUS_FX_RATE' in db.execute("SELECT reason_codes FROM core.dq_quarantine_prices").fetchone()[0]
