"""Isolated execution with heartbeat, fencing, checkpoints and artifact transfer."""
import logging
import sys
import threading

import config  # Load .env in isolated workers before initializing the database.
from sqlalchemy import update
from runtime import artifacts, checkpoints, recovery, store

logger = logging.getLogger(__name__)


class LeaseLost(RuntimeError):
    """Cancellation or another worker fenced this execution."""


def execute(job_id):
    store.initialize()
    row = recovery.claim(job_id)
    if row is None:
        return
    job = dict(row["snapshot"])
    lease = job["lease"]
    stop = threading.Event()

    def owned():
        return (store.jobs.c.id == job_id) & (store.jobs.c.status == "running") & (
            store.jobs.c.snapshot["lease"].as_string() == lease)

    def persist():
        with store.engine.begin() as connection:
            result = connection.execute(update(store.jobs).where(owned()).values(
                status=job["status"], snapshot=job, updated_at=store.now()))
            if result.rowcount != 1:
                raise LeaseLost()

    def heartbeat():
        while not stop.wait(20):
            try:
                with store.engine.begin() as connection:
                    result = connection.execute(update(store.jobs).where(owned()).values(updated_at=store.now()))
                    if result.rowcount != 1:
                        return
            except Exception:
                logger.exception("Heartbeat failed for %s", job_id)

    def progress(stage, percent, message):
        job.update(status="running", stage=stage, progress=percent, message=message)
        job["events"] = (job["events"] + [{"at": store.now(), "stage": stage, "message": message}])[-30:]
        persist()

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        from build3d.pipeline import create_document_bundle, create_rodin_preview, create_segments_and_build_plan
        directory = artifacts.ROOT / row["session_id"] / job_id
        directory.mkdir(parents=True, exist_ok=True)
        progress("Starting", 1, "Preparing your lesson")
        payload = artifacts.materialize(row["payload"], row["session_id"])
        with checkpoints.for_job(job_id, lease):
            if row["kind"] == "model":
                result = create_rodin_preview(payload["context"], directory, progress)
            elif row["kind"] == "segments":
                result = create_segments_and_build_plan(payload["context"], payload["rodin_task_uuid"],
                                                        payload["rodin_files"], directory, progress)
                result["source_model_task_uuid"] = payload["rodin_task_uuid"]
            elif row["kind"] == "documents":
                result = create_document_bundle(payload["story_text"], payload["context"],
                                                payload["build_plan"], directory, progress)
            else:
                raise ValueError("Unknown job type")
        progress("Saving results", 99, "Saving your lesson files")
        result = artifacts.publish(result, directory, row["session_id"])
        job.update(status="complete", stage="Complete", progress=100, result=result,
                   message="Ready for review")
        persist()
    except LeaseLost:
        logger.info("Worker stopped after cancellation or lease loss: %s", job_id)
    except Exception as exc:
        logger.exception("Job %s failed", job_id)
        uncertain = isinstance(exc, checkpoints.UncertainSubmission)
        job.update(status="error", stage="Needs attention", error="recovery_required" if uncertain else "processing_failed",
                   message="The previous provider request needs an operator check before retrying." if uncertain else
                   "Processing could not finish. Your lesson and previous results are saved.")
        try:
            persist()
        except LeaseLost:
            pass
    finally:
        stop.set()
        thread.join(timeout=2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    execute(sys.argv[1])
