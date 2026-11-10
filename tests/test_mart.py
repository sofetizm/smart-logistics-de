from datetime import date
import math
import pytest
from tests.test_etl import etl


def test_exact_quartiles_carriers_cv_and_calendar_changes(db,add):
    add(1,price=10000,loading_date="2025-10-10")
    add(2,price=15000,loading_date="2026-09-10")
    for id,price in enumerate([10000,20000,30000,40000],10):
        add(id,price=price,loading_date="2026-10-10",organization_id=1 if id<12 else 2,
            price_type=3 if id<12 else 1)
    etl()
    row=db.execute("""SELECT p25_trip,median_trip,p75_trip,p25_km,median_km,p75_km,
      trips_count,carriers_count,cv_rate,mom_pct,yoy_pct,reliability_level
      FROM mart.market_corridor WHERE month='2026-10-01'""").fetchone()
    assert row[:8]==(17500,25000,32500,175,250,325,4,1)
    assert row[8]==pytest.approx(math.sqrt(500000000/3)/25000)
    assert row[9]==pytest.approx((25000/15000-1)*100)
    assert row[10]==150
    assert row[11]=='LOW_DATA'


def test_missing_calendar_month_is_not_previous_available(db,add):
    add(1,loading_date="2026-08-10")
    add(2,loading_date="2026-10-10")
    etl()
    assert db.execute("SELECT mom_pct,yoy_pct,cv_rate FROM mart.market_corridor WHERE month='2026-10-01'").fetchone()==(None,None,None)


def test_reliability_freshness_and_carrier_role(db,add):
    for i in range(30):
        add(i+1,loading_date="2026-10-10",organization_id=i%5,price_type=3)
        add(i+31,loading_date="2026-08-10",organization_id=i%5,price_type=3)
    etl()
    assert db.execute("SELECT reliability_level FROM mart.market_corridor ORDER BY month").fetchall()==[('MEDIUM',),('HIGH',)]
    db.execute("UPDATE raw.prices SET price_type=1")
    etl()
    assert db.execute("SELECT max(carriers_count) FROM mart.market_corridor").fetchone()[0]==0
    assert db.execute("SELECT DISTINCT reliability_level FROM mart.market_corridor").fetchall()==[('MEDIUM',)]
