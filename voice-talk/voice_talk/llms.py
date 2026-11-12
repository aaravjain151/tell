"""Local LLM servers: any OpenAI-compatible endpoint on loopback (LM Studio, Ollama, llama.cpp, vLLM, Jan, or a custom URL).

Servers are discovered at runtime (GET /v1/models) and the model is picked by name or, if none is named, the first chat
model the server offers. Only loopback URLs are accepted, so nothing here can reach a remote host.
"""
from __future__ import annotations

from typing import Callable, Iterable

from .translate import BACKENDS, ensure_loopback


def chat_model_ids(ids: Iterable[str]) -> list[str]:
    """Model ids that can chat: embedding models are filtered out."""
    return [i for i in ids if "embed" not in i.lower()]


def list_models(base_url: str, timeout: float = 1.0) -> list[str]:
    """Ids the server at base_url offers. Raises if it is unreachable."""
    from openai import OpenAI

    client = OpenAI(base_url=ensure_loopback(base_url), api_key="local", timeout=timeout, max_retries=0)
    return [m.id for m in client.models.list()]


def discover(backends: dict[str, dict] | None = None, lister: Callable[..., list[str]] = list_models) -> list[dict]:
    """One row per configured server: {id, label, base_url, reachable, models, error}."""
    out = []
    for bid, cfg in (backends if backends is not None else BACKENDS).items():
        row = {"id": bid, "label": cfg.get("label", bid), "base_url": cfg["base_url"],
               "reachable": False, "models": [], "error": None}
        try:
            row["models"] = chat_model_ids(lister(cfg["base_url"]))
            row["reachable"] = True
        except Exception as e:
            row["error"] = str(e)
        out.append(row)
    return out


def register_custom(base_url: str, model: str | None = None) -> None:
    """Add (or replace) the 'custom' server: any other OpenAI-compatible endpoint, loopback only."""
    BACKENDS["custom"] = {"label": "Custom endpoint", "base_url": ensure_loopback(base_url), "model": model}
