"""Training pipeline for Tell's two models.

Part A (pellav2-finetune/): voice model - real vs AI-generated speech.
Part B (scam-text):          transcript model - scam vs not-scam.
Part C (engine.py in doublespeak/): wires both trained models into the app.

Downloads run once, online. Training and inference are fully offline after.
See DATA_SOURCES.md for every dataset and its licence.
"""
