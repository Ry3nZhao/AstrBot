"""Content-addressed media cache: ``gateway://<sha256>``.

Inbound media the gateway only has locally (a file path, ``base64://``, a
``data:`` URI) is copied here so the backend can fetch it later; remote
``http(s)`` URLs are passed through untouched. Outbound uploads land here too.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import mimetypes
import os
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from .protocol import GATEWAY_MEDIA_SCHEME, Media

MAX_MEDIA_BYTES = 200 * 1024 * 1024

_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"%PDF-", "application/pdf"),
    (b"#!AMR", "audio/amr"),
    (b"\x02#!SILK", "audio/silk"),
    (b"#!SILK", "audio/silk"),
    (b"OggS", "audio/ogg"),
    (b"ID3", "audio/mpeg"),
)


def sniff_mime(data: bytes, name: str | None = None) -> str | None:
    for magic, mime in _MAGIC:
        if data.startswith(magic):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:8] == b"ftyp":
        return "video/mp4"
    if name:
        guessed, _ = mimetypes.guess_type(name)
        if guessed:
            return guessed
    return None


def is_remote(ref: str | None) -> bool:
    return bool(ref) and ref.startswith(("http://", "https://"))


def name_from_ref(ref: str | None) -> str | None:
    """A file name worth keeping from a reference (NapCat's ``file`` is often
    just ``ABCD.jpg``)."""
    if not ref or ref.startswith(("base64://", "data:")):
        return None
    if "://" in ref:
        path = unquote(urlparse(ref).path)
        base = os.path.basename(path)
        return base or None
    return os.path.basename(ref) or None


class MediaStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def path_of(self, sha256: str) -> Path | None:
        if len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
            return None
        path = self.root / sha256
        return path if path.is_file() else None

    def meta_of(self, sha256: str) -> dict:
        try:
            return json.loads((self.root / f"{sha256}.json").read_text("utf-8"))
        except (OSError, ValueError):
            return {}

    def put(
        self, data: bytes, *, name: str | None = None, mime: str | None = None
    ) -> Media:
        """Store bytes and describe them as ``gateway://<sha256>`` media."""
        if len(data) > MAX_MEDIA_BYTES:
            raise ValueError(f"media larger than {MAX_MEDIA_BYTES} bytes")
        self._ensure()
        digest = hashlib.sha256(data).hexdigest()
        path = self.root / digest
        if not path.exists():
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, path)
        else:
            os.utime(path)  # referenced again: keep it past the next cleanup
        mime = mime or sniff_mime(data, name)
        meta = {"mime": mime, "name": name, "stored_at": time.time()}
        (self.root / f"{digest}.json").write_text(
            json.dumps(meta, ensure_ascii=False), "utf-8"
        )
        return Media(
            url=GATEWAY_MEDIA_SCHEME + digest,
            mime=mime,
            name=name,
            size=len(data),
            sha256=digest,
        )

    def read_ref(self, ref: str) -> tuple[bytes, str | None] | None:
        """Bytes behind a local reference, with the mime type if the reference
        says. ``None`` when it is not local or cannot be read."""
        try:
            if ref.startswith(GATEWAY_MEDIA_SCHEME):
                sha = ref[len(GATEWAY_MEDIA_SCHEME) :]
                path = self.path_of(sha)
                if path is None:
                    return None
                return path.read_bytes(), self.meta_of(sha).get("mime")
            if ref.startswith("base64://"):
                return base64.b64decode(ref[len("base64://") :], validate=False), None
            if ref.startswith("data:") and ";base64," in ref:
                head, payload = ref[len("data:") :].split(";base64,", 1)
                return base64.b64decode(payload, validate=False), head or None
            if ref.startswith("file://"):
                path = Path(unquote(urlparse(ref).path))
            elif os.path.isabs(ref):
                path = Path(ref)
            else:
                return None
            if not path.is_file() or path.stat().st_size > MAX_MEDIA_BYTES:
                return None
            return path.read_bytes(), None
        except (OSError, ValueError, binascii.Error):
            return None

    def ingest(self, candidates: list[str | None], name: str | None = None) -> Media:
        """Describe media from the references an adapter gave: the first remote
        URL if any, else the first local reference copied into the cache, else
        media without a URL (announced but unavailable)."""
        refs = [c for c in candidates if isinstance(c, str) and c]
        name = name or next((n for n in (name_from_ref(r) for r in refs) if n), None)
        for ref in refs:
            if is_remote(ref):
                return Media(url=ref, name=name)
        for ref in refs:
            got = self.read_ref(ref)
            if got is not None:
                data, mime = got
                return self.put(data, name=name, mime=mime)
        return Media(name=name)

    def cleanup(self, max_age_days: float, now: float | None = None) -> int:
        """Delete cached media older than ``max_age_days``; returns how many."""
        if not self.root.is_dir():
            return 0
        cutoff = (now or time.time()) - max_age_days * 86400
        removed = 0
        for path in self.root.iterdir():
            if path.suffix or len(path.name) != 64:
                continue
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    (self.root / f"{path.name}.json").unlink(missing_ok=True)
                    removed += 1
            except OSError:
                continue
        return removed
