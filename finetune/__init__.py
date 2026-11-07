"""Fine-tuning pipeline for the pellav2 deepfake detector.

Trains only pellav2's layer-weighting vector and linear head (backbone frozen)
to improve detection of Qwen3-TTS voices. See README.md for the full flow.
"""
