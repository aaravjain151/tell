from . import offline_guard as _offline_guard

_offline_guard.apply_from_env()   # must happen before transformers / huggingface_hub are imported anywhere
