"""Stage 1 — discover, download (with caching), and extract the BIS CBPOL bulk CSV.

Public entry point: ``fetch(data_dir, force=False) -> Provenance``.

Caching notes (verified against the live endpoint):
- ``Content-Length`` is stable, but ``ETag``/``Last-Modified`` vary between requests because
  the file is served from replicated backends. So freshness is decided by matching the remote
  ``Content-Length`` *and* re-checking the local file's recorded SHA-256 — not by trusting ETag.
- ``--force`` bypasses the cache entirely.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

BULK_URL = "https://data.bis.org/static/bulk/WS_CBPOL_csv_flat.zip"
DATAFLOW_URL = (
    "https://stats.bis.org/api/v2/structure/dataflow/BIS/WS_CBPOL?detail=full"
)
ZIP_NAME = "WS_CBPOL_csv_flat.zip"
META_NAME = "WS_CBPOL_csv_flat.meta.json"

DEFAULT_TIMEOUT = 60
_CHUNK = 1 << 16  # 64 KiB


@dataclass
class RemoteMeta:
    """Metadata advertised by the server for the file we're about to download."""

    content_length: int | None
    last_modified: str | None
    etag: str | None


@dataclass
class Provenance:
    """Recorded source-of-truth for a fetched copy (written as a sidecar JSON)."""

    dataflow_id: str
    dataflow_name: str | None
    version: str | None
    source_url: str
    last_modified: str | None
    etag: str | None
    content_length: int | None
    sha256: str
    downloaded_at: str
    zip_path: str
    csv_path: str


# --------------------------------------------------------------------------- #
# Discovery / metadata
# --------------------------------------------------------------------------- #
def remote_metadata(
    url: str = BULK_URL, *, timeout: int = DEFAULT_TIMEOUT
) -> RemoteMeta:
    """HEAD the bulk file and return its size / validators (to check against a local copy)."""
    resp = requests.head(url, timeout=timeout, allow_redirects=True)
    resp.raise_for_status()
    cl = resp.headers.get("Content-Length")
    return RemoteMeta(
        content_length=int(cl) if cl and cl.isdigit() else None,
        last_modified=resp.headers.get("Last-Modified"),
        etag=resp.headers.get("ETag"),
    )


def confirm_dataflow(
    url: str = DATAFLOW_URL, *, timeout: int = DEFAULT_TIMEOUT
) -> dict:
    """Confirm via the BIS SDMX structure API that we're targeting the right dataset.

    Returns ``{id, name, version, agency}``. Used for provenance and a sanity check.
    """
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    flow = resp.json()["data"]["dataflows"][0]
    name = flow.get("name")
    if isinstance(name, dict):  # some SDMX responses localise the name
        name = name.get("en") or next(iter(name.values()), None)
    return {
        "id": flow["id"],
        "name": name,
        "version": flow.get("version"),
        "agency": flow.get("agencyID"),
    }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_meta(meta_path: Path) -> dict | None:
    try:
        return json.loads(meta_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _cache_is_fresh(zip_path: Path, meta: dict | None, remote: RemoteMeta) -> bool:
    """Cache hit = file present, size matches remote, and the file still matches its checksum."""
    if meta is None or not zip_path.exists():
        return False
    if (
        remote.content_length is not None
        and meta.get("content_length") != remote.content_length
    ):
        return False
    recorded = meta.get("sha256")
    return bool(recorded) and _sha256(zip_path) == recorded


def _download(url: str, dest: Path, *, timeout: int, expected_size: int | None) -> None:
    """Stream the download to a temp file, verify size, then atomically move into place."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=dest.parent, suffix=".part")
    tmp = Path(tmp_name)
    try:
        with requests.get(url, stream=True, timeout=timeout) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length", 0)) or expected_size or 0
            with os.fdopen(fd, "wb") as out:
                for chunk in resp.iter_content(_CHUNK):
                    out.write(chunk)
        if total and tmp.stat().st_size != total:
            raise OSError(f"incomplete download: {tmp.stat().st_size} of {total} bytes")
        os.replace(tmp, dest)  # atomic on the same filesystem
    finally:
        if tmp.exists():
            tmp.unlink()


def _extract_csv(zip_path: Path, dest_dir: Path) -> Path:
    """Extract the (single) CSV member from the archive and return its path."""
    with zipfile.ZipFile(zip_path) as zf:
        members = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not members:
            raise ValueError(f"no CSV member found in {zip_path}")
        member = members[0]
        zf.extract(member, dest_dir)
    return dest_dir / member


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #
def fetch(
    data_dir: str | os.PathLike = "data", *, force: bool = False, verify: bool = True
) -> Provenance:
    """Download + cache + extract the CBPOL bulk CSV. Returns provenance for the report.

    Skips the download when a valid cached copy exists (unless ``force``).
    """
    data_dir = Path(data_dir)
    zip_path = data_dir / ZIP_NAME
    meta_path = data_dir / META_NAME

    flow = (
        confirm_dataflow()
        if verify
        else {"id": "WS_CBPOL", "name": None, "version": "1.0", "agency": "BIS"}
    )
    remote = remote_metadata()
    cached = _load_meta(meta_path)

    if not force and _cache_is_fresh(zip_path, cached, remote):
        csv_path = Path(cached["csv_path"])
        if not csv_path.exists():
            csv_path = _extract_csv(zip_path, data_dir)
        fields = {f for f in Provenance.__dataclass_fields__}
        return Provenance(**{k: cached.get(k) for k in fields})

    _download(
        BULK_URL, zip_path, timeout=DEFAULT_TIMEOUT, expected_size=remote.content_length
    )
    sha = _sha256(zip_path)
    csv_path = _extract_csv(zip_path, data_dir)

    prov = Provenance(
        dataflow_id=flow["id"],
        dataflow_name=flow["name"],
        version=flow["version"],
        source_url=BULK_URL,
        last_modified=remote.last_modified,
        etag=remote.etag,
        content_length=remote.content_length,
        sha256=sha,
        downloaded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        zip_path=str(zip_path),
        csv_path=str(csv_path),
    )
    meta_path.write_text(json.dumps(asdict(prov), indent=2))
    return prov
