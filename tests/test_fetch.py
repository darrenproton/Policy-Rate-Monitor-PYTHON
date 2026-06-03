"""Fetch tests: pure helpers + the cache/download orchestration (network mocked)."""
from __future__ import annotations

import hashlib
import json
import zipfile

import pytest

from bis_prates import fetch as F


def test_sha256(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"hello")
    assert F._sha256(p) == hashlib.sha256(b"hello").hexdigest()


def test_extract_csv(tmp_path):
    z = tmp_path / "a.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("data.csv", "a,b\n1,2\n")
    out = F._extract_csv(z, tmp_path)
    assert out.name == "data.csv" and out.exists()


def test_extract_csv_raises_without_csv(tmp_path):
    z = tmp_path / "a.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("readme.txt", "hi")
    with pytest.raises(ValueError):
        F._extract_csv(z, tmp_path)


def test_load_provenance_roundtrip(tmp_path):
    (tmp_path / F.META_NAME).write_text(json.dumps({"sha256": "x"}))
    assert F.load_provenance(tmp_path)["sha256"] == "x"
    assert F.load_provenance(tmp_path / "missing") is None


def test_cache_is_fresh(tmp_path):
    zip_path = tmp_path / F.ZIP_NAME
    zip_path.write_bytes(b"data")
    sha = F._sha256(zip_path)
    remote = F.RemoteMeta(content_length=4, last_modified=None, etag=None)
    assert F._cache_is_fresh(zip_path, {"content_length": 4, "sha256": sha}, remote) is True
    assert F._cache_is_fresh(zip_path, {"content_length": 99, "sha256": sha}, remote) is False
    assert F._cache_is_fresh(zip_path, None, remote) is False


def _stub_network(monkeypatch, content_length=None):
    monkeypatch.setattr(
        F, "confirm_dataflow",
        lambda *a, **k: {"id": "WS_CBPOL", "name": "X", "version": "1.0", "agency": "BIS"},
    )
    monkeypatch.setattr(
        F, "remote_metadata",
        lambda *a, **k: F.RemoteMeta(content_length=content_length, last_modified="lm", etag="e"),
    )


def test_fetch_downloads_when_missing(tmp_path, monkeypatch):
    _stub_network(monkeypatch)

    def fake_download(url, dest, *, timeout, expected_size):
        with zipfile.ZipFile(dest, "w") as zf:
            zf.writestr("WS_CBPOL_csv_flat.csv", "a\n1\n")

    monkeypatch.setattr(F, "_download", fake_download)
    prov = F.fetch(tmp_path, force=True)
    assert (tmp_path / "WS_CBPOL_csv_flat.csv").exists()
    assert (tmp_path / F.META_NAME).exists()
    assert prov.dataflow_name == "X" and prov.dataflow_id == "WS_CBPOL"


def test_fetch_uses_cache(tmp_path, monkeypatch):
    # Seed a valid cache, then assert fetch() returns it without downloading.
    zip_path = tmp_path / F.ZIP_NAME
    zip_path.write_bytes(b"data")
    csv_path = tmp_path / "WS_CBPOL_csv_flat.csv"
    csv_path.write_text("x")
    sha = F._sha256(zip_path)
    (tmp_path / F.META_NAME).write_text(
        json.dumps(
            {
                "dataflow_id": "WS_CBPOL", "dataflow_name": "X", "version": "1.0",
                "source_url": "u", "last_modified": "lm", "etag": "e", "content_length": 4,
                "sha256": sha, "downloaded_at": "t",
                "zip_path": str(zip_path), "csv_path": str(csv_path),
            }
        )
    )
    _stub_network(monkeypatch, content_length=4)

    def boom(*a, **k):
        raise AssertionError("download must not run on a cache hit")

    monkeypatch.setattr(F, "_download", boom)
    prov = F.fetch(tmp_path, force=False)
    assert prov.sha256 == sha
