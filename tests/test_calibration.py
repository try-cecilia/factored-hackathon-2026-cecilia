import numpy as np

from eval.calibration import EDGES, reliability


def test_ece_is_zero_when_bins_are_honest_and_the_gap_when_they_are_not():
    p = np.array([0.05] * 20 + [0.9] * 10)
    honest = np.array([True] + [False] * 19 + [True] * 9 + [False])  # 1/20 = 0.05 and 9/10 = 0.9
    assert reliability(p, honest, EDGES)[1] < 1e-9
    always_wrong = np.array([True] * 20 + [False] * 10)  # observed 1.0 at 0.05 and 0.0 at 0.9
    assert abs(reliability(p, always_wrong, EDGES)[1] - ((20 * 0.95 + 10 * 0.9) / 30)) < 1e-9
