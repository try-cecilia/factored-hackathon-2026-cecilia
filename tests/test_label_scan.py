import numpy as np
import pandas as pd

from analysis.label_scan import scan


def test_scan_finds_a_lookup_and_a_shuffled_label_stays_at_chance():
    rng = np.random.default_rng(0)
    n = 4000
    df = pd.DataFrame({"key": rng.integers(0, 2, n), "noise": rng.normal(size=n)})
    r = scan(df, pd.Series(df["key"] == 1), ["key", "noise"])
    assert r["all"] > 0.99 and r["one"][0][1] == "key" and r["one"][0][0] > 0.99
    assert r["permuted_max"] < 0.56
    r = scan(df, pd.Series(rng.integers(0, 2, n) == 1), ["key", "noise"])  # a label with no relation to any column
    assert r["all"] < 0.56
