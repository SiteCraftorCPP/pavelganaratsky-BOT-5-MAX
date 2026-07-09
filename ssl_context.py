from __future__ import annotations

import os
import ssl
from pathlib import Path

import certifi

_PROJECT_ROOT = Path(__file__).resolve().parent
_RUSSIAN_CA_BUNDLE = _PROJECT_ROOT / "certs" / "russian_trusted_bundle.pem"


def build_max_ssl_verify() -> bool | str | ssl.SSLContext:
    """Параметр verify для httpx: certifi + сертификаты НУЦ Минцифры."""
    raw = (os.getenv("MAX_SSL_VERIFY") or "1").strip()
    lowered = raw.lower()
    if lowered in ("0", "false", "no"):
        return False
    if lowered not in ("1", "true", "yes"):
        custom = Path(raw)
        if custom.is_file():
            return str(custom.resolve())

    ctx = ssl.create_default_context(cafile=certifi.where())
    if _RUSSIAN_CA_BUNDLE.is_file():
        ctx.load_verify_locations(cafile=str(_RUSSIAN_CA_BUNDLE))
    return ctx
