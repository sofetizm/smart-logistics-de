from datetime import date
from etl.db import connect, initialize, sql_file, log, LOCK_ID, execute_script


def run_etl(start_date: date, end_date: date, as_of: date):
    if start_date >= end_date:
        raise ValueError("start_date must be before exclusive end_date")
    params = dict(start_date=start_date, end_date=end_date, as_of=as_of)
    with connect() as conn:
        conn.autocommit = True
        conn.execute("SELECT pg_advisory_lock(%s)", (LOCK_ID,))
        with conn.transaction():
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            initialize(conn)
            execute_script(conn, "010_etl.sql", params)
            read = conn.execute("SELECT count(*) FROM staged").fetchone()[0]
            rejected = conn.execute("SELECT count(*) FROM staged WHERE cardinality(reasons)>0").fetchone()[0]
            execute_script(conn, "020_market_corridor.sql", {"as_of": as_of})
            cells = conn.execute("SELECT count(*) FROM mart.market_corridor").fetchone()[0]
            reasons = dict(conn.execute("SELECT reason,count(*) FROM staged,unnest(reasons) reason GROUP BY reason").fetchall())
            conn.execute("""INSERT INTO ops.etl_runs(start_date,end_date,rows_read,rows_loaded,rows_quarantined,mart_rows)
                            VALUES(%s,%s,%s,%s,%s,%s)""",
                         (start_date,end_date,read,read-rejected,rejected,cells))
        result = dict(rows_read=read, rows_loaded=read-rejected, rows_quarantined=rejected,
                      mart_rows=cells, reasons=reasons)
        log("etl_complete", **params, **result)
        return result
