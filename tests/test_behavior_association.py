import numpy as np
import pytest
from sklearn.metrics import roc_auc_score

from analysis.behavior_association import auc_from_bins, bootstrap_interval, verdict


def test_the_auc_from_bins_is_the_auc_of_the_rows_it_counts_ties_included():
    rng = np.random.default_rng(1)
    y = rng.random(2000) < 0.1
    score = np.rint(np.where(y, rng.normal(0.6, 0.3, 2000), rng.normal(0.5, 0.3, 2000)).clip(0, 1) * 10).astype(int)  # many ties
    pos, neg = np.bincount(score[y], minlength=11), np.bincount(score[~y], minlength=11)
    assert auc_from_bins(pos, neg) == pytest.approx(roc_auc_score(y, score))


def test_the_interval_brackets_the_estimate_and_a_coin_includes_one_half():
    rng = np.random.default_rng(2)
    pos, neg = np.bincount(rng.integers(0, 1001, 3000), minlength=1001), np.bincount(rng.integers(0, 1001, 50000), minlength=1001)
    lo, hi = bootstrap_interval(pos, neg, np.random.default_rng(0))
    assert lo < auc_from_bins(pos, neg) < hi and lo < 0.5 < hi


@pytest.mark.parametrize("lower, point, says", [
    (0.50, 0.52, "No detectable association"), (0.55, 0.9, "No detectable association"),
    (0.56, 0.60, "Weak association"), (0.58, 0.70, "Association with a synthetic label"),
    (0.62, 0.64, "Association with a synthetic label"),
])
def test_the_wording_follows_the_gates_fixed_in_the_contract(lower, point, says):
    assert verdict(lower, point).startswith(says)
