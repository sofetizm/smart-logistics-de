from datetime import date
import numpy as np
import pandas as pd
from ml.features import build_features, split_masks, CATEGORICAL, NUMERIC, FEATURES


def frame(dates):
    x = pd.DataFrame({c:["a"]*len(dates) for c in CATEGORICAL})
    for c in NUMERIC[:7]:
        x[c] = 1.0
    x["loading_date"] = dates
    return x


def test_fixed_boundaries():
    rows = frame(["2026-07-25","2026-07-26","2026-10-04","2026-10-05","2026-10-26","2026-10-27"])
    train,test,future = split_masks(rows,date(2026,7,26),date(2026,10,5),date(2026,10,26))
    assert train.tolist()==[False,True,True,False,False,False]
    assert test.tolist()==[False,False,False,True,True,False]
    assert future.tolist()==[False,False,False,False,False,True]
    assert not (train & test).any()


def test_target_columns_cannot_change_features():
    rows = frame(["2026-12-31","2027-01-01"])
    rows["price_rub"] = [100,1e9]
    rows["profit"] = rows["price_rub"]
    rows["price_group_id"] = rows["price_rub"]
    rows["outlier_mark"] = True
    x = build_features(rows)
    rows["price_rub"] = 7
    rows["profit"] = 18
    rows["price_group_id"] = 12
    rows["outlier_mark"] = False
    pd.testing.assert_frame_equal(x,build_features(rows))
    assert x.columns.tolist()==FEATURES
    assert np.isclose(x.loc[0,"dow_sin"]**2+x.loc[0,"dow_cos"]**2,1)
    assert abs(x.loc[0,"doy_sin"]-x.loc[1,"doy_sin"])<0.03


def test_missing_numeric_and_categories():
    rows = frame(["2026-10-05"])
    rows.loc[0,"origin_region"] = None
    rows.loc[0,"origin_latitude"] = np.inf
    x = build_features(rows)
    assert x.loc[0,"origin_region"]=="UNKNOWN"
    assert np.isnan(x.loc[0,"origin_latitude"])
