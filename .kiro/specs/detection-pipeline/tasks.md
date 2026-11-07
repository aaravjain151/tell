# Detection Pipeline - Implementation Plan

- [ ] 1. Add pipeline config knobs
  - Add window/hop seconds, silence RMS threshold, risk weights and level
    thresholds, scam rule weights, and contacts to `config.py`.
  - _Requirements: 2.2, 2.3, 5.1, 5.3, 5.4, 5.5_

- [ ] 2. Implement `load_audio`
  - 16 kHz mono float32 via librosa, peak-normalise with zero-peak guard.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [ ] 3. Implement the voice checker with rolling windows
  - Reuse pellav2 preprocessing; 4 s window / 2 s hop; skip silent windows;
    return mean + per-window scores.
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [ ] 4. Implement the scam checker
  - Ollama JSON path (temp 0) returning `{risk, reasons}`; regex rule engine;
    fuse with regex-as-safety-net.
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [ ] 5. Implement fusion, levels, result dataclass and caching
  - `0.4*voice + 0.6*scam`, floor-to-0.9 rule, level thresholds; `PipelineResult`;
    load each model once via a cached singleton.
  - _Requirements: 3.1, 3.2, 3.3, 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3_

- [ ] 6. Implement `secure_store.py` with tests
  - AES-256-GCM, 96-bit nonce per record, key in keychain; `save_alert`,
    `load_alerts`, `wipe_all`; record holds only timestamp/level/reasons; tests
    prove the file is unreadable without the key.
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ] 7. Implement `net_monitor.py` + Streamlit panel + config.toml
  - Outbound count ignoring loopback; green/red panel refreshing ~2 s; disable
    Streamlit usage stats.
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

- [ ] 8. Build the demo `app.py`
  - Upload/record, colored full-width alert, plain reasons, contact button,
    per-window chart, always-visible net panel, large high-contrast styling.
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_

- [ ] 9. Implement `download_models.py` and `run_pipeline_tests.py`
  - Online model fetch + README ollama step; batch scorer printing a per-file
    table of voice/scam/level.
  - _Requirements: 10.1, 10.2_
