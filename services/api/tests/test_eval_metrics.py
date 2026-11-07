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


def test_auc_and_eer_perfect_and_chance():
    from eval.metrics import auc, eer
    assert auc([0.9, 0.8], [0.1, 0.2]) == 1.0 and eer([0.9, 0.8], [0.1, 0.2]) == 0.0
    assert auc([0.5, 0.5], [0.5, 0.5]) == 0.5
    assert auc([], [0.1]) is None and eer([0.9], []) is None


def test_loeo_threshold_comes_from_the_other_engines():
    from eval.metrics import loeo
    r = loeo({"a": [0.9, 0.8, 0.95], "b": [0.3, 0.2, 0.25]}, human_scores=[0.1, 0.4])
    assert r["b"]["threshold"] == 0.8 and r["b"]["tpr"] == 0.0 and r["b"]["fpr"] == 0.0   # b is missed when tuned on a
    assert r["a"]["tpr"] == 1.0 and r["a"]["fpr"] == 0.5                                  # tuned on b (thr .2): humans .4 flagged
