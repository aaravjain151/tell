#!/usr/bin/env python3
"""Build design/tokens.json and verify WCAG contrast for every text/surface pair.

Run: python3 design/build_tokens.py   (prints ratios; exits 1 if any small-text pair < 4.5)
Edit the hex values below, re-run, commit tokens.json.
"""
import json
import sys
from pathlib import Path


def lum(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))

    def ch(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return round((hi + 0.05) / (lo + 0.05), 2)


signal = {  # teal-cyan: "a clear signal in the noise"
    "50": "#e6fbf9", "100": "#c2f4ef", "200": "#8fe8e0", "300": "#55d6cc", "400": "#22bfb4",
    "500": "#0ea39a", "600": "#0b857e", "700": "#0a6a65", "800": "#0b5450", "900": "#0a4341",
}
neutral = {  # cool slate
    "50": "#f6f8f9", "100": "#eceff2", "200": "#d9dee3", "300": "#b9c2ca", "400": "#8e9aa5",
    "500": "#67737e", "600": "#4f5a64", "700": "#3c4650", "800": "#262d35", "900": "#141a20",
    "950": "#0b0f13",
}
status = {
    "human": {"light": "#1b7f3b", "dark": "#5fd48a"},
    "ai_disclosed": {"light": "#8a5a00", "dark": "#f0b64a"},
    "ai_undisclosed": {"light": "#b3470e", "dark": "#ff9a5c"},
    "scam": {"light": "#b41e2c", "dark": "#ff6b7a"},
    "unsure": {"light": "#4f5a64", "dark": "#b9c2ca"},
}

light = {
    "bg": neutral["50"], "surface": "#ffffff", "surface_alt": neutral["100"],
    "text": neutral["900"], "text_muted": neutral["600"], "border": neutral["200"],
    "primary": signal["600"], "primary_text": "#ffffff", "primary_hover": signal["700"],
    "status": {k: v["light"] for k, v in status.items()},
}
dark = {
    "bg": neutral["950"], "surface": neutral["900"], "surface_alt": neutral["800"],
    "text": neutral["50"], "text_muted": neutral["300"], "border": neutral["700"],
    "primary": signal["400"], "primary_text": neutral["950"], "primary_hover": signal["300"],
    "status": {k: v["dark"] for k, v in status.items()},
}

pairs = []
for name, t in (("light", light), ("dark", dark)):
    pairs += [
        (f"{name}: text on bg", t["text"], t["bg"], 4.5),
        (f"{name}: text on surface", t["text"], t["surface"], 4.5),
        (f"{name}: text_muted on surface", t["text_muted"], t["surface"], 4.5),
        (f"{name}: primary_text on primary (button)", t["primary_text"], t["primary"], 4.5),
        (f"{name}: primary as link on surface", t["primary"], t["surface"], 4.5),
    ]
    for k, v in t["status"].items():
        pairs.append((f"{name}: status.{k} text on surface", v, t["surface"], 4.5))

tokens = {
    "name": "Doublespeak",
    "palette": {"signal": signal, "neutral": neutral},
    "themes": {"light": light, "dark": dark},
    "type": {
        "family_display": "'Bricolage Grotesque', 'IBM Plex Sans', system-ui, sans-serif",
        "family_body": "'IBM Plex Sans', system-ui, -apple-system, sans-serif",
        "family_mono": "'IBM Plex Mono', ui-monospace, SFMono-Regular, monospace",
        "scale": {"xs": 12, "sm": 14, "md": 16, "lg": 20, "xl": 28, "2xl": 40, "3xl": 56},
        "line_height": {"tight": 1.1, "normal": 1.5},
    },
    "spacing": {"1": 4, "2": 8, "3": 12, "4": 16, "6": 24, "8": 32, "12": 48, "16": 64},
    "radius": {"sm": 6, "md": 10, "lg": 16, "pill": 999},
    "motion": {"fast": "120ms", "base": "200ms", "slow": "400ms", "ease": "cubic-bezier(.2,.8,.2,1)"},
    "contrast": {},
}

failed = False
for label, fg, bg, need in pairs:
    r = contrast(fg, bg)
    ok = r >= need
    failed |= not ok
    tokens["contrast"][label] = {"fg": fg, "bg": bg, "ratio": r, "pass": ok}
    print(f"{'PASS' if ok else 'FAIL'} {r:5.2f}  {label}  ({fg} on {bg})")

Path(__file__).with_name("tokens.json").write_text(json.dumps(tokens, indent=2) + "\n")
print("wrote design/tokens.json")
sys.exit(1 if failed else 0)
