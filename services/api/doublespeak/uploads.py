"""Keep uploaded audio in memory. Caller audio must never be written to disk (decision D-004).

Starlette parses multipart uploads into a SpooledTemporaryFile that rolls over to a real temp file on disk once it
exceeds `MultiPartParser.spool_max_size` (1 MiB by default), which a 10 s stereo recording easily does. Raising the
threshold above our largest allowed upload keeps every upload in RAM. The API's own size cap bounds memory use.
"""
from __future__ import annotations

from starlette.formparsers import MultiPartParser

from .limits import max_upload_bytes   # one tolerant parser for DOUBLESPEAK_MAX_UPLOAD_MB


def keep_uploads_in_memory() -> int:
    cap = max_upload_bytes() + (2 << 20)   # largest upload + slack
    MultiPartParser.spool_max_size = max(MultiPartParser.spool_max_size, cap)
    return MultiPartParser.spool_max_size
