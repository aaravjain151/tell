"""Fetch Pellav2 at the pinned revision and verify it (exec'd by tools/models/prefetch.py; also runnable alone).

Downloads the 2.3 GB head weights and the backbone's small config.json only. Refuses to keep a file whose SHA-256
differs from the pinned value.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    sys.path.insert(0, str(ROOT / "services" / "api"))
    from huggingface_hub import hf_hub_download
    from tell.signals import pella
    p = hf_hub_download(pella.REPO, pella.FILENAME, revision=pella.REVISION)
    if not pella.verify(Path(p)):
        raise RuntimeError(f"{p} does not match the pinned SHA-256; delete it and retry")
    cfg = Path(hf_hub_download(pella.BACKBONE, "config.json", revision=pella.BACKBONE_REVISION))
    if pella._sha256(cfg) != pella.BACKBONE_CONFIG_SHA256:
        raise RuntimeError(f"{cfg} does not match the pinned SHA-256; delete it and retry")
    print("Pellav2 cached and verified:", p)


if __name__ == "__main__":
    main()
