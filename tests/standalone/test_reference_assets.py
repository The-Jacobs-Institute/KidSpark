"""Regression assets are portable, canonical data rather than user uploads."""
from hashlib import sha256
import json
from pathlib import Path


def test_packaged_model_checksums_match_manifests():
    root = Path(__file__).resolve().parents[2] / "model_store"
    for name in ("bird-base", "airplane-tripo"):
        manifest = json.loads((root / "manifests" / f"{name}.json").read_text())
        data = (root / manifest["object_path"]).read_bytes()
        assert len(data) == manifest["size_bytes"]
        assert sha256(data).hexdigest() == manifest["sha256"]
