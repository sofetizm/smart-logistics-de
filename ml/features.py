import numpy as np
import pandas as pd

CATEGORICAL = ["origin_region", "destination_region", "origin_city", "destination_city",
               "body_group", "weight_category", "volume_category"]
NUMERIC = ["distance", "total_weight", "total_volume", "origin_latitude", "origin_longitude",
           "destination_latitude", "destination_longitude", "year", "month_sin", "month_cos",
           "dow_sin", "dow_cos", "doy_sin", "doy_cos"]
FEATURES = CATEGORICAL + NUMERIC


def build_features(rows: pd.DataFrame) -> pd.DataFrame:
    dates = pd.to_datetime(rows["loading_date"])
    x = rows[CATEGORICAL + NUMERIC[:7]].copy()
    x["year"] = dates.dt.year
    for name, t, period in [("month", dates.dt.month - 1, 12),
                             ("dow", dates.dt.dayofweek, 7),
                             ("doy", dates.dt.dayofyear - 1, 365.25)]:
        x[name + "_sin"] = np.sin(2 * np.pi * t / period)
        x[name + "_cos"] = np.cos(2 * np.pi * t / period)
    for col in CATEGORICAL:
        x[col] = x[col].fillna("UNKNOWN").astype(str)
    for col in NUMERIC:
        x[col] = pd.to_numeric(x[col], errors="coerce").replace([np.inf, -np.inf], np.nan)
    return x[FEATURES]


def split_masks(rows, train_start, test_start, as_of):
    dates = pd.to_datetime(rows["loading_date"])
    train = (dates >= pd.Timestamp(train_start)) & (dates < pd.Timestamp(test_start))
    test = (dates >= pd.Timestamp(test_start)) & (dates <= pd.Timestamp(as_of))
    future = dates > pd.Timestamp(as_of)
    return train, test, future
