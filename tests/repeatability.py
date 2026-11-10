import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import tempfile
from etl.db import connect, log
from etl.run import full_bounds
from etl.pipeline import run_etl
from etl.verify import verify
from ml.train import train_and_score


def fingerprint():
    result = {}
    with connect() as conn:
        for table,excluded in [("core.cities",[]),("core.prices",[]),("core.price_bodies",[]),("core.price_dates",[]),
                               ("core.dq_quarantine_prices",[]),("mart.market_corridor",[]),
                               ("mart.ml_price_predictions",["scored_at"])]:
            query = f"SELECT to_jsonb(t)-%s::text[] FROM {table} t ORDER BY 1"
            cur=conn.execute(query,(excluded,))
            digest=hashlib.sha256()
            count=0
            for (row,) in cur:
                digest.update(json.dumps(row,sort_keys=True,separators=(',',':')).encode())
                count+=1
            result[table] = dict(rows=count,sha256=digest.hexdigest())
    return result


def main():
    p=argparse.ArgumentParser(description="Проверка повторяемости полного прогона")
    p.add_argument("--output",default="artifacts/repeatability.json")
    a=p.parse_args()
    with connect() as conn:
        row=conn.execute("""SELECT train_start,test_start,as_of,parameters FROM mart.ml_models
          ORDER BY trained_at DESC LIMIT 1""").fetchone()
    if not row:
        raise ValueError("Run all first")
    train_start,test_start,as_of,parameters=row
    before=fingerprint()
    start,end=full_bounds()
    run_etl(start,end,as_of)
    with tempfile.TemporaryDirectory() as directory:
        train_and_score(train_start,test_start,as_of,directory,iterations=parameters["iterations"])
    after=fingerprint()
    checks=verify(as_of)
    report=dict(unchanged=before==after,before=before,after=after,verification=checks)
    Path(a.output).write_text(json.dumps(report,indent=2,ensure_ascii=False))
    log("repeatability",unchanged=report["unchanged"])
    if before!=after:
        raise AssertionError("Business data changed on repeated full run")


if __name__=="__main__":
    main()
