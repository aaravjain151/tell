# SESSION_LOG

| when | domain | tool | event |
|---|---|---|---|
| 2026-11-07 13:30 | pm | claude | init: brief, tokens, repo scaffold, backend MVP (17 tests, eval 0.98/1.00), web prototype |
| 2026-11-07 14:20 | backend | claude | session start |
| 2026-11-07 14:23 | backend | - | T-011 STT verified: audio-only /analyze (wav+webm) -> transcript_source=local_whisper, egress 0; ffmpeg+faster-whisper+onnxruntime installed. Human still to record a real mic clip. Next: T-010 anti-spoof; ollama server not running (ollama serve). |
| 2026-11-07 14:32 | backend | - | T-010: picked garystafford/wav2vec2-deepfake-voice-detector via HF_SPOOF_MODEL (0.35s/10s CPU, id2label logged on load); whole-word label matching + tests; make test 20 pass, eval PASS with voter on. Accuracy on Gradium clips unmeasured until GRADIUM_API_KEY set (T-012). |
