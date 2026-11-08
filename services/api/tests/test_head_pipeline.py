"""The neural-head evaluation helpers (finetune/head_train_eval.py): metrics and sample weights. No audio, no models."""
import sys
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("sklearn")
pytest.importorskip("torch")
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from finetune import head_train_eval as h  # noqa: E402


def test_metrics_perfect_and_chance():
    y = np.array([0] * 50 + [1] * 50)
    r = h.roc_metrics(y, np.r_[np.linspace(0, 0.4, 50), np.linspace(0.6, 1, 50)])
    assert r["auc"] == 1.0 and r["eer"] == 0.0 and r["tpr_at_fpr5"] == 1.0 and r["fpr_at_0.5"] == 0.0
    assert (r["n_real"], r["n_fake"]) == (50, 50)
    rng = np.random.default_rng(0)
    c = h.roc_metrics(np.r_[np.zeros(2000), np.ones(2000)].astype(int), rng.random(4000))
    assert abs(c["auc"] - 0.5) < 0.05 and abs(c["eer"] - 0.5) < 0.05


def test_metrics_single_class_has_no_auc():
    r = h.roc_metrics(np.ones(5, int), np.linspace(0, 1, 5))
    assert "auc" not in r and r["n_fake"] == 5


def test_weights_balance_classes_and_generators():
    label = np.array([0] * 100 + [1] * 10 + [1] * 90)
    gen = np.array(["human"] * 100 + ["gradium"] * 10 + ["qwen"] * 90)
    spk = np.array(["a"] * 50 + ["b"] * 50 + ["g"] * 10 + ["q"] * 90)
    w = h.weights_for(label, gen, spk)
    assert abs(w[label == 0].sum() - w[label == 1].sum()) < 1e-6
    # the small generator is up-weighted per window relative to the large one, but not to equal totals (sqrt balance)
    assert w[gen == "gradium"][0] > w[gen == "qwen"][0]
    assert w[gen == "gradium"].sum() < w[gen == "qwen"].sum()


def test_head_shapes_and_size():
    torch = pytest.importorskip("torch")
    m = h.build_head(25, 1024, "mlp", True)
    assert sum(p.numel() for p in m.parameters()) == 262426
    out = m(torch.zeros(3, 25, 1024), torch.ones(3, 25, 1024))
    assert out.shape == (3,)
    assert sum(p.numel() for p in h.build_head(25, 1024, "linear", False).parameters()) == 25 + 1024 + 1


def test_speaker_folds_are_disjoint_and_cover_all():
    meta = [{"speaker": f"s{i % 17}", "owner": "0"} for i in range(200)] + [{"speaker": "owner", "owner": "1"}]
    f = h.folds_for(meta)
    assert f["owner"] == -1
    assert {f[f"s{i}"] for i in range(17)} == set(range(h.K_FOLDS))


def test_new_human_groups_get_their_own_held_out_folds():
    """--extra-humans: the old speakers keep the 2026-11-07 fold assignment; each new speaker group is a separate fold."""
    old = [{"speaker": f"s{i % 17}", "owner": "0", "split": "dev-clean"} for i in range(200)] + [{"speaker": "owner", "owner": "1"}]
    new = [{"speaker": g, "owner": "0", "split": "humans_new"} for g in ("new_neu", "new_hunt", "new_neu")]
    f_old, f_new = h.folds_for(old), h.folds_for(old + new)
    assert all(f_old[f"s{i}"] == f_new[f"s{i}"] for i in range(17))
    assert {f_new["new_hunt"], f_new["new_neu"]} == {h.K_FOLDS, h.K_FOLDS + 1}
