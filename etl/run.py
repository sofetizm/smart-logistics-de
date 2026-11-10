import argparse
from datetime import date, timedelta
import os
import subprocess
import time

from etl.db import connect, connection_kwargs, initialize, ROOT, log
from etl.pipeline import run_etl


def bootstrap():
    args = connection_kwargs()
    env = os.environ.copy()
    if password := args.pop("password", None):
        env["PGPASSWORD"] = password
    command = ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-v", "n_prices=" + os.getenv("N_PRICES", "300000")]
    if "conninfo" in args:
        command += ["--dbname", args["conninfo"]]
    else:
        for key, flag in [("host","-h"),("port","-p"),("user","-U"),("dbname","-d")]:
            if key in args:
                command += [flag, str(args[key])]
    command += ["-f", str(ROOT / "sql" / "bootstrap.psql")]
    try:
        subprocess.run(command, env=env, check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Source bootstrap failed, psql exit code {exc.returncode}") from None
    with connect() as conn:
        initialize(conn)
    log("initialized")


def full_bounds():
    with connect() as conn:
        low, high = conn.execute("""SELECT min(loading_date),max(loading_date) FROM (
          SELECT loading_date FROM raw.prices UNION ALL SELECT loading_date FROM core.prices
          UNION ALL SELECT loading_date FROM core.dq_quarantine_prices) d""").fetchone()
    if low is None:
        raise ValueError("Empty source")
    return low, high + timedelta(days=1)


def main():
    p = argparse.ArgumentParser(description="Обработка данных и прогнозирование тарифов")
    p.add_argument("command", choices=["all","init","etl","ml","verify"])
    p.add_argument("--start-date", type=date.fromisoformat)
    p.add_argument("--end-date", type=date.fromisoformat, help="exclusive end")
    p.add_argument("--as-of", type=date.fromisoformat, default=os.getenv("AS_OF","2026-10-26"))
    p.add_argument("--train-start", type=date.fromisoformat, default=os.getenv("TRAIN_START","2026-07-26"))
    p.add_argument("--test-start", type=date.fromisoformat, default=os.getenv("TEST_START","2026-10-05"))
    p.add_argument("--artifact-dir", default=str(ROOT / "artifacts"))
    a = p.parse_args()
    if (a.start_date is None) != (a.end_date is None):
        p.error("Supply both --start-date and --end-date")
    interval = int(os.getenv("RUN_INTERVAL_SECONDS","0")) if a.command=="all" else 0
    if interval < 0:
        p.error("RUN_INTERVAL_SECONDS cannot be negative")
    while True:
        if a.command in ("init","all"):
            bootstrap()
        if a.command in ("etl","all"):
            start, end = (a.start_date,a.end_date) if a.start_date else full_bounds()
            run_etl(start,end,a.as_of)
        if a.command in ("ml","all"):
            from ml.train import train_and_score
            train_and_score(a.train_start,a.test_start,a.as_of,a.artifact_dir)
        if a.command in ("verify","all"):
            from etl.verify import verify
            verify(a.as_of)
        if not interval:
            break
        log("waiting_for_next_run", seconds=interval)
        time.sleep(interval)


if __name__ == "__main__":
    main()
