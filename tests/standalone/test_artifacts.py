"""Portable private artifacts, tested without credentials or GCS writes."""
from pathlib import Path
import pytest
from runtime import artifacts


class MemoryBucket:
    def __init__(self):
        self.objects = {}

    def blob(self, key):
        objects = self.objects
        class Blob:
            def upload_from_filename(self, filename, **kwargs):
                objects[key] = Path(filename).read_bytes()
            def upload_from_string(self, value, **kwargs):
                objects[key] = value.encode()
            def download_to_filename(self, filename, **kwargs):
                Path(filename).write_bytes(objects[key])
            def download_as_text(self):
                return objects[key].decode()
        return Blob()


@pytest.fixture
def storage(monkeypatch, tmp_path):
    target = MemoryBucket()
    monkeypatch.setenv("KIDSPARK_ARTIFACT_BUCKET", "private-test")
    monkeypatch.setattr(artifacts, "bucket", lambda: target)
    monkeypatch.setattr(artifacts, "ROOT", tmp_path / "worker-one")
    return target


def test_publish_and_restore_on_fresh_worker_includes_sidecars(storage, monkeypatch, tmp_path):
    directory = artifacts.ROOT / "lesson-one" / "job-one"
    directory.mkdir(parents=True)
    mesh = directory / "model.obj"
    mesh.write_text("mtllib model.mtl\n")
    (directory / "model.mtl").write_text("newmtl blue\n")
    (directory / "rodin_submit.json").write_text('{"subscription_key":"not-public"}')
    result = artifacts.publish({"files": [str(mesh)]}, directory, "lesson-one")
    assert result["files"][0] == "gs://private-test/sessions/lesson-one/job-one/model.obj"
    assert not any(k.endswith("rodin_submit.json") for k in storage.objects)
    monkeypatch.setattr(artifacts, "ROOT", tmp_path / "worker-two")
    restored = artifacts.materialize(result, "lesson-one")
    assert Path(restored["files"][0]).read_text() == "mtllib model.mtl\n"
    assert Path(restored["files"][0]).with_suffix(".mtl").is_file()


@pytest.mark.parametrize("uri", [
    "gs://other-bucket/sessions/lesson-one/job-one/model.obj",
    "gs://private-test/sessions/another-lesson/job-one/model.obj",
    "gs://private-test/sessions/lesson-one/job-one/../../secret.pdf",
    "gs://private-test/sessions/lesson-one/job-one/C:/secret.pdf",
    "gs://private-test/sessions/lesson-one/job-one/..\\secret.pdf",
])
def test_reject_cross_lesson_and_path_traversal(storage, uri):
    with pytest.raises(ValueError):
        artifacts.download(uri, "lesson-one")


def test_previous_job_image_references_remain_portable(storage):
    previous = artifacts.ROOT / "lesson-one" / "job-one" / "build.png"
    previous.parent.mkdir(parents=True)
    previous.write_bytes(b"test")
    directory = artifacts.ROOT / "lesson-one" / "job-two"
    directory.mkdir()
    result = artifacts.publish({"image": str(previous)}, directory, "lesson-one")
    assert result["image"] == "gs://private-test/sessions/lesson-one/job-one/build.png"
