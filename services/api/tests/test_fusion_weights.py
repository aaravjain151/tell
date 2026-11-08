"""Fusion weights live in thresholds.py / signals; the scorer formula must not drift (re-weighting is data, not logic)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tell import scorer, thresholds as T  # noqa: E402
from tell.signals import neural, pella  # noqa: E402
from tell.types import Tell  # noqa: E402


def test_weights_come_from_the_documented_places():
    assert T.THRESHOLDS_VERSION == "2026-11-08.2"           # .2 few_pauses voter; .1 learned_tells + breath 0 + Pellav2 all windows
    assert T.ACOUSTIC_SHARE == 0.8 and T.P_AI_THRESHOLD == 0.60
    assert pella.W_PELLA == 4.0 and neural.W_HF == 0.7
    # the Tell a voter emits carries the module weight (fusion reads it from the Tell, nowhere else)
    assert pella._na("x").weight == pella.W_PELLA


def test_hf_stays_a_small_but_nonzero_vote_and_pella_is_not_everything():
    assert 0 < neural.W_HF < pella.W_PELLA
    others = sum(T.ACOUSTIC_WEIGHTS.values())
    assert pella.W_PELLA / (pella.W_PELLA + neural.W_HF + others) < 0.5   # behavioural tells keep a majority of the acoustic vote


def test_formula_unchanged_on_a_synthetic_tell_list():
    ac = [Tell("pause_regularity", "acoustic", 0.9, 1.0, ""), Tell("neural_pella", "acoustic", 1.0, pella.W_PELLA, ""),
          Tell("neural_hf", "acoustic", 0.2, neural.W_HF, ""), Tell("off", "acoustic", 1.0, 9.0, "", applicable=False)]
    sc = [Tell("llm_isms", "script", 0.5, 1.0, ""), Tell("zero_weight", "script", 1.0, 0.0, "")]
    a = (0.9 * 1.0 + 1.0 * 4.0 + 0.2 * 0.7) / (1.0 + 4.0 + 0.7)
    want = T.ACOUSTIC_SHARE * a + (1 - T.ACOUSTIC_SHARE) * 0.5
    assert abs(scorer.fuse(ac, sc, [], disclosed_ai=False).p_ai - want) < 1e-9
    assert abs(scorer.fuse(ac, [], [], disclosed_ai=False).p_ai - a) < 1e-9           # one family only -> used alone
    assert abs(scorer.fuse([], sc, [], disclosed_ai=False).p_ai - 0.5) < 1e-9
    assert scorer.fuse(ac, sc, [], disclosed_ai=False).thresholds_version == T.THRESHOLDS_VERSION


def test_wild_markdown_table_counts_at_the_shipping_threshold():
    from eval.run_eval import wild_markdown
    rows = {"clean": [{"label": "ai", "engine": "e1", "p_ai": 0.7}, {"label": "ai", "engine": "e2", "p_ai": 0.3},
                      {"label": "human", "engine": "other", "p_ai": 0.1}, {"label": "human", "engine": "other", "p_ai": 0.65}]}
    md = wild_markdown(rows, 0.6, "v")
    assert "| clean | all AI | 2 | 2 |" in md and "| 1/2 | 1/2 |" in md
    assert "| clean | e1 | 1 | 2 |" in md and "thresholds_version `v`" in md
