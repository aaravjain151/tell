from doublespeak import reasons



def test_voice_reason_never_contradicts_fused_score():
    from doublespeak.types import Tell
    hf = Tell("neural_hf", "acoustic", 0.96, 0.7, "x")
    low = Tell("neural_pella", "acoustic", 0.5, 4.0, "x")
    agree = reasons.build([hf, low], False, p_ai=0.8)
    split = reasons.build([hf, low], False, p_ai=0.42)
    assert reasons.VOICE in agree and reasons.VOICE_SPLIT not in agree
    assert reasons.VOICE_SPLIT in split and reasons.VOICE not in split
    assert reasons.build([hf], False)  == [reasons.VOICE]   # p_ai omitted keeps old behaviour
