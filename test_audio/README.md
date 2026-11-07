# test_audio

Drop labelled audio clips here, then run:

```bash
python run_pipeline_tests.py
```

Suggested naming so the printed table is easy to read (the filename is shown
as-is, the labels are just for you):

```
real_normal_01.wav         # real voice, ordinary chat  -> expect Low
real_scam_giftcard.wav     # real voice, scam words      -> expect Medium/High
cloned_normal_01.wav       # AI voice, ordinary chat     -> expect Medium
cloned_scam_arrest.wav     # AI voice, scam words         -> expect High
```

Supported: `.wav`, `.mp3`, `.m4a`, `.flac`, `.ogg`. Clips are read into memory
and never copied anywhere.
