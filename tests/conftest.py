import os
from datetime import date
import psycopg
import pytest
from etl.db import initialize, ROOT, connection_kwargs


@pytest.fixture
def db(monkeypatch):
    url = os.getenv("TEST_DATABASE_URL")
    if not url and os.getenv("TEST_DB_ENABLED")=="1":
        url = psycopg.conninfo.make_conninfo(**connection_kwargs())
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a dedicated *_test database for integration tests")
    conn = psycopg.connect(url, autocommit=True)
    if not conn.info.dbname.endswith("_test"):
        conn.close()
        pytest.fail("Integration tests require a database name ending in _test")
    monkeypatch.setenv("DATABASE_URL", url)
    conn.execute("DROP SCHEMA IF EXISTS mart CASCADE; DROP SCHEMA IF EXISTS core CASCADE; "
                 "DROP SCHEMA IF EXISTS ops CASCADE; DROP SCHEMA IF EXISTS raw CASCADE; CREATE SCHEMA raw")
    conn.execute("SET search_path TO raw,public")
    conn.execute((ROOT/"sql/source/schema.sql").read_text())
    initialize(conn)
    conn.execute("""INSERT INTO raw.cities(id,gc_id,name,full_name_local,full_name_gc,latitude,longitude) VALUES
       (1,1001,'Москва','Москва, г. Москва','Москва',55.75,37.61),
       (2,1003,'Казань','Казань, Республика Татарстан','Казань',55.79,49.10),
       (42,1003,'Казань','Казань г, Татарстан','Казань',0,0)""")
    conn.execute("""INSERT INTO raw.body_types(id,name,"id_from_1C",std_id) VALUES
     (56,'Тент',56,56),(57,'Тент бок',57,56),(61,'Тент все',61,56),
     (4,'Реф',4,4),(46,'Реф мульт',46,4),(15,'Борт',15,15),(1,'Борт',1,15)""")
    conn.execute("""INSERT INTO raw.exchange_rates(num_code,value,setting_date) VALUES
     ('840',90,'2026-09-01'),('840',99,'2026-10-01'),('978',100,'2026-09-01')""")
    conn.close()

    class Result:
        def __init__(self, rows):
            self.rows = rows
        def fetchone(self):
            return self.rows[0] if self.rows else None
        def fetchall(self):
            return self.rows

    class Database:
        def execute(self, query, params=None):
            with psycopg.connect(url, autocommit=True) as session:
                cur = session.execute(query, params)
                return Result(cur.fetchall() if cur.description else [])
    yield Database()


@pytest.fixture
def add(db):
    def insert(id, **values):
        p = dict(id=id,created_at="2026-09-02",loading_date="2026-09-10",loading_city_gcid=1001,
                 unloading_city_gcid=1003,distance=100,total_weight=20,total_volume=100,
                 body_type=56,price=10000,currency_code="643",organization_id=id,
                 price_type=3,is_fact=True,nearest_rate_date="2026-09-01",outlier_mark=False,complex=False)
        months = values.pop("months", None)
        bodies = values.pop("bodies", None)
        p.update(values)
        from psycopg import sql
        db.execute(sql.SQL("INSERT INTO raw.prices ({}) VALUES ({})").format(
            sql.SQL(',').join(map(sql.Identifier,p)),sql.SQL(',').join(sql.Placeholder() for _ in p)),list(p.values()))
        for dt in months or [p["loading_date"]]:
            db.execute("INSERT INTO raw.price_dates(price_id,price_date) VALUES(%s,%s)",(id,dt))
        if bodies:
            for body in bodies:
                db.execute("INSERT INTO raw.price_body_types(price_id,body_type_id) VALUES(%s,%s)",(id,body))
    return insert
