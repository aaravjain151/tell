import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval.metrics import fpr_at_tpr  # noqa: E402


def test_perfect_separation():
    assert fpr_at_tpr([0.9, 0.8, 0.95], [0.1, 0.2]) == (0.0, 0.8)


def test_overlap_counts_humans_above_threshold():
    ai = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.05]   # 90% TPR needs the 9th highest = 0.1
    fpr, thr = fpr_at_tpr(ai, [0.05, 0.1, 0.5, 0.95])
    assert thr == 0.1 and fpr == 0.75


def test_empty_class_is_undefined():
    assert fpr_at_tpr([], [0.1]) == (None, None)
    assert fpr_at_tpr([0.9], []) == (None, None)
