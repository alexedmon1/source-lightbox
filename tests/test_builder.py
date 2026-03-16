"""Tests for builder module."""

import json
from pathlib import Path

import pytest

from source_lightbox.builder import build
from source_lightbox.config import BuildConfig, SourceInput


@pytest.fixture
def mock_results(tmp_path):
    """Create a minimal results directory for build testing."""
    fig_dir = tmp_path / "results" / "figures" / "resting" / "psd"
    fig_dir.mkdir(parents=True)

    # Create a real small PNG (1x1 pixel)
    import struct
    import zlib

    def make_png():
        sig = b"\x89PNG\r\n\x1a\n"
        ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF
        ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)
        raw = zlib.compress(b"\x00\xff\x00\x00")
        idat_crc = zlib.crc32(b"IDAT" + raw) & 0xFFFFFFFF
        idat = struct.pack(">I", len(raw)) + b"IDAT" + raw + struct.pack(">I", idat_crc)
        iend_crc = zlib.crc32(b"IEND") & 0xFFFFFFFF
        iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)
        return sig + ihdr + idat + iend

    png_data = make_png()
    (fig_dir / "psd_global.png").write_bytes(png_data)

    tbl_dir = tmp_path / "results" / "tables" / "resting" / "psd"
    tbl_dir.mkdir(parents=True)
    (tbl_dir / "psd_omnibus.csv").write_text("group_a,group_b,p\n30mgkg,Vehicle,0.05\n")

    return tmp_path


def test_build_creates_gallery(mock_results, tmp_path):
    output = tmp_path / "gallery"
    config = BuildConfig(
        output_dir=output,
        title="Test Gallery",
        results=[SourceInput(path=mock_results / "results", label="Test")],
        thumb_workers=1,
    )
    result = build(config, verbose=False)

    assert result == output
    assert (output / "index.html").exists()
    assert (output / "data" / "manifest.json").exists()

    manifest = json.loads((output / "data" / "manifest.json").read_text())
    assert manifest["title"] == "Test Gallery"
    assert manifest["stats"]["total_figures"] == 1
    assert manifest["stats"]["total_tables"] == 1

    # Check figure was copied
    assert len(list((output / "figures").rglob("*.png"))) == 1

    # Check thumbnail was generated
    assert len(list((output / "figures" / "thumbs").rglob("*.jpg"))) == 1

    # Check table data is embedded inline in manifest
    tbl = manifest["paradigms"]["resting"]["psd"]["tables"]["Test"][0]
    assert tbl["filename"] == "psd_omnibus.csv"
    assert tbl["headers"] == ["group_a", "group_b", "p"]
    assert len(tbl["rows"]) == 1


def test_build_empty(tmp_path):
    output = tmp_path / "gallery"
    config = BuildConfig(output_dir=output, title="Empty Gallery")
    result = build(config, verbose=False)
    assert (output / "index.html").exists()
    manifest = json.loads((output / "data" / "manifest.json").read_text())
    assert manifest["stats"]["total_figures"] == 0
