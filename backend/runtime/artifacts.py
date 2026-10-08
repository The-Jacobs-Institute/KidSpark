"""Session-scoped artifact transport with private, portable GCS references.

Local runs need no bucket. Cloud workers publish the full job directory (OBJ/MTL
sidecars included) and a relative-path manifest before exposing a completed job.
"""
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2] / "work" / "build_jobs"


def bucket_name():
    return os.getenv("KIDSPARK_ARTIFACT_BUCKET", "").strip()


def bucket():
    from google.cloud import storage
    return storage.Client().bucket(bucket_name())


def walk(value, transform):
    if isinstance(value, dict):
        return {k: walk(v, transform) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [walk(v, transform) for v in value]
    return transform(value) if isinstance(value, str) else value


def object_key(uri, session_id):
    parsed = urlsplit(uri)
    key = parsed.path.lstrip("/")
    parts = key.split("/")
    if (parsed.scheme != "gs" or parsed.netloc != bucket_name() or parsed.query or parsed.fragment
            or len(parts) < 4 or parts[:2] != ["sessions", session_id]
            or any(p in {"", ".", ".."} or "\\" in p or ":" in p for p in parts)):
        raise ValueError("Artifact is outside this lesson")
    return key


def publish(result, directory, session_id):
    if not bucket_name():
        return result
    directory = directory.resolve()
    prefix = f"sessions/{session_id}/{directory.name}/"
    target = bucket()
    mapping = {}
    entries = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(directory).as_posix()
        # Provider subscription tokens stay in the database checkpoints, not downloads.
        if relative.endswith(("rodin_submit.json", "bang_submit.json")):
            continue
        key = prefix + relative
        target.blob(key).upload_from_filename(str(path), timeout=120)
        mapping[str(path)] = f"gs://{bucket_name()}/{key}"
        entries.append(relative)
    target.blob(prefix + "_manifest.json").upload_from_string(json.dumps(entries), content_type="application/json")
    def portable(value):
        if value in mapping:
            return mapping[value]
        # References to input images from earlier jobs must remain portable too.
        try:
            path = Path(value)
            if path.is_absolute() and path.resolve().is_relative_to((ROOT / session_id).resolve()) and path.is_file():
                key = path.resolve().relative_to(ROOT.resolve()).as_posix()
                return f"gs://{bucket_name()}/sessions/{key}"
        except (OSError, ValueError):
            pass
        return value
    return walk(result, portable)


def download(uri, session_id):
    key = object_key(uri, session_id)
    relative = PurePosixPath(key).relative_to("sessions")
    target = (ROOT / Path(str(relative))).resolve()
    if not target.is_relative_to((ROOT / session_id).resolve()):
        raise ValueError("Invalid artifact path")
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=target.parent)
        os.close(fd)
        try:
            bucket().blob(key).download_to_filename(temporary, timeout=120)
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return str(target)


def materialize(payload, session_id):
    """Restore each referenced job, including sidecars, on a fresh worker."""
    restored = set()
    def restore(value):
        if not value.startswith("gs://"):
            return value
        key = object_key(value, session_id)
        prefix = "/".join(key.split("/")[:3]) + "/"
        if prefix not in restored:
            entries = json.loads(bucket().blob(prefix + "_manifest.json").download_as_text())
            if not isinstance(entries, list) or len(entries) > 10000:
                raise ValueError("Invalid artifact manifest")
            for entry in entries:
                download(f"gs://{bucket_name()}/{prefix}{entry}", session_id)
            restored.add(prefix)
        return download(value, session_id)
    return walk(payload, restore)
