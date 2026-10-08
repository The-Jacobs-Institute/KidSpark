"""Same-origin public application with private anonymous teacher sessions."""
from contextlib import asynccontextmanager
import asyncio
from hashlib import sha256
from pathlib import Path
import logging
import os
import secrets
import uuid

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agents import orchestrator as workflow
from ingestion.story_upload import extract_story_text
from llm.vertex_gemini import GeminiGenerationError, provider_configured
from models.schemas import SessionState
from runtime import store
from runtime.context import bind_session

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    store.initialize()
    async def reconcile_jobs():
        from runtime.recovery import reconcile
        while True:
            try:
                await asyncio.to_thread(reconcile)
            except Exception:
                logger.exception("Background job reconciliation failed")
            await asyncio.sleep(30)
    task = asyncio.create_task(reconcile_jobs())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="KidSpark", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def session_boundary(request: Request, call_next):
    # A same-origin custom header prevents cross-site form submissions without
    # exposing session credentials to frontend JavaScript.
    if request.url.path.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("X-KidSpark-Request") != "1":
            return JSONResponse({"detail": "Invalid request origin"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "Invalid request origin"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(GeminiGenerationError)
async def provider_error(request, error):
    logger.error("Generation unavailable: %s", type(error).__name__)
    return JSONResponse({"detail": "The planning service is unavailable. Your lesson is saved; try again shortly."}, status_code=503)


def owner(request: Request) -> str:
    value = request.cookies.get("kidspark_session")
    if not value:
        raise HTTPException(404, "Lesson not found")
    return sha256(value.encode()).hexdigest()


def load(request, session_id):
    identity = owner(request)
    row = store.load_session(session_id, identity)
    if not row:
        raise HTTPException(404, "Lesson not found")
    return identity, row, SessionState.model_validate(row["state"])


def save(identity, row, state):
    if not store.save_session(state.session_id, identity, row["revision"], state.model_dump(mode="json")):
        raise HTTPException(409, "This lesson changed in another tab. Refresh before continuing.")


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "service": "kidspark", "generation_configured": provider_configured(),
            "validation_mode": os.getenv("KIDSPARK_VALIDATION_MODE", "live")}


@app.post("/api/v1/sessions", status_code=201)
def create_session(request: Request, response: Response):
    credential = request.cookies.get("kidspark_session") or secrets.token_urlsafe(32)
    response.set_cookie("kidspark_session", credential, httponly=True,
                        secure=os.getenv("KIDSPARK_COOKIE_SECURE", "false").lower() == "true",
                        samesite="strict", max_age=30 * 86400)
    state = SessionState(session_id=str(uuid.uuid4()))
    store.insert_session(state.model_dump(mode="json"), sha256(credential.encode()).hexdigest())
    return state.model_dump()


@app.get("/api/v1/sessions/{session_id}")
def session_detail(session_id: str, request: Request):
    _, row, state = load(request, session_id)
    return {**state.model_dump(), "revision": row["revision"]}


@app.post("/api/v1/sessions/{session_id}/upload")
async def upload(session_id: str, request: Request, text: str = Form(""), file: UploadFile | None = File(None)):
    identity, row, state = load(request, session_id)
    if state.phase.value != "story_upload":
        raise HTTPException(409, "Start a new lesson to change the story.")
    if file:
        data = await file.read(20 * 1024 * 1024 + 1)
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, "Please choose a file smaller than 20 MB.")
        try:
            text = extract_story_text(file.filename or "story.pdf", data)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    if not text.strip() or len(text) > 100000:
        raise HTTPException(422, "Enter a story between 1 and 100,000 characters.")
    state.storybook_text = text.strip()
    save(identity, row, state)
    identity, row, state = load(request, session_id)
    if not provider_configured():
        raise GeminiGenerationError("Generation not configured")
    with bind_session(state):
        await workflow.run_storybook_analysis(session_id, text.strip())
    save(identity, row, state)
    return state.model_dump()


class Message(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


@app.post("/api/v1/sessions/{session_id}/message")
async def message(session_id: str, request: Request, body: Message):
    identity, row, state = load(request, session_id)
    if state.phase.value != "lesson_planning":
        raise HTTPException(409, "This lesson is not in the planning stage.")
    if not provider_configured():
        raise GeminiGenerationError("Generation not configured")
    with bind_session(state):
        await workflow.route_message(session_id, body.message)
    save(identity, row, state)
    return state.model_dump()


@app.post("/api/v1/sessions/{session_id}/confirm-planning")
async def confirm_planning(session_id: str, request: Request):
    identity, row, state = load(request, session_id)
    if state.phase.value != "lesson_planning" or not state.planning_state.get("required_complete"):
        raise HTTPException(409, "Complete the lesson details before confirming.")
    with bind_session(state):
        await workflow.confirm_teacher_planning(session_id)
    save(identity, row, state)
    return state.model_dump()


class ModelRefinement(BaseModel):
    refinement: str = Field(min_length=1, max_length=3000)
    max_validated_blocks: int = Field(default=28, ge=8, le=64)
    max_semantic_segments: int = Field(default=4, ge=1, le=8)


@app.post("/api/v1/sessions/{session_id}/model-preview/refine")
def refine_model(session_id: str, request: Request, body: ModelRefinement):
    identity, row, state = load(request, session_id)
    if state.phase.value not in {"model_preview", "segments_connectors", "build_plan"}:
        raise HTTPException(409, "Confirm lesson planning before revising the model.")
    from models.schemas import SessionPhase
    try:
        with store.unit_of_work(), bind_session(state):
            context = dict((state.model_preview_result or {}).get("context") or workflow.build_seed_context(state))
            context["rodin_prompt"] = str(context.get("rodin_prompt", "")) + " Teacher revision: " + body.refinement
            context["build_constraints"] = {**context.get("build_constraints", {}),
                "max_validated_blocks": body.max_validated_blocks,
                "max_semantic_segments": body.max_semantic_segments}
            state.phase = SessionPhase.model_preview
            state.model_preview_result = None
            result = workflow.start_session_model_preview(session_id, context_override=context)
            save(identity, row, state)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return result


@app.post("/api/v1/sessions/{session_id}/jobs/{job_id}/cancel")
def cancel_job(session_id: str, job_id: str, request: Request):
    load(request, session_id)
    from runtime.recovery import cancel
    try:
        return cancel(job_id, session_id)
    except ValueError as exc:
        raise HTTPException(404, "Job not found") from exc


@app.post("/api/v1/sessions/{session_id}/jobs/{job_id}/resume")
def resume_job(session_id: str, job_id: str, request: Request):
    _, _, state = load(request, session_id)
    current = {"model_preview": state.model_preview_job_id, "segments_connectors": state.segment_job_id,
               "build_plan": state.segment_job_id, "lesson_bundle": state.document_job_id}.get(state.phase.value)
    if job_id != current:
        raise HTTPException(409, "This job is not part of the current lesson stage.")
    from runtime.recovery import resume
    try:
        return resume(job_id, session_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


class RevisionNotes(BaseModel):
    notes: str = Field(min_length=1, max_length=3000)


@app.post("/api/v1/sessions/{session_id}/documents/refine")
def refine_documents(session_id: str, request: Request, body: RevisionNotes):
    identity, row, state = load(request, session_id)
    if state.phase.value not in {"lesson_bundle", "complete"}:
        raise HTTPException(409, "Approve the build before revising classroom materials.")
    from build3d.jobs import start_document_job
    from models.schemas import SessionPhase
    try:
        with store.unit_of_work(), bind_session(state):
            workflow._require_validated_build_result(state.build_result)
            previous = workflow.get_session_documents(session_id)
            if not previous or previous.get("status") != "complete":
                raise ValueError("Finish the current document bundle before requesting a revision.")
            context = dict(state.build_result.get("context") or workflow.build_seed_context(state))
            state.document_revision += 1
            context["document_revision"] = state.document_revision
            context["teacher_document_revision"] = body.notes
            context["previous_lesson_package"] = (previous.get("result") or {}).get("lesson_package", {})
            context["connector_review_notes"] = state.connector_review.get("notes", "")
            result = start_document_job(state.storybook_text, context, state.build_result["build_plan"], session_id)
            state.document_history = (state.document_history + [{"job_id": previous["job_id"], "result": previous["result"]}])[-5:]
            state.document_job_id = result["job_id"]
            state.document_result = None
            state.phase = SessionPhase.lesson_bundle
            save(identity, row, state)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return result


@app.post("/api/v1/sessions/{session_id}/connectors/review")
def review_connectors(session_id: str, request: Request, body: RevisionNotes):
    identity, row, state = load(request, session_id)
    if state.phase.value != "segments_connectors":
        raise HTTPException(409, "Connections can be reviewed during the build assessment.")
    with bind_session(state):
        current = workflow.get_session_segments(session_id)
    if not current or current.get("status") != "complete":
        raise HTTPException(409, "Wait for the build assessment to finish.")
    state.connector_review = {"job_id": state.segment_job_id, "notes": body.notes, "reviewed_at": store.now()}
    save(identity, row, state)
    return state.model_dump()


@app.post("/api/v1/sessions/{session_id}/{stage}")
def stage_action(session_id: str, stage: str, request: Request):
    identity, row, state = load(request, session_id)
    actions = {
        "model-preview": ({"model_preview"}, workflow.start_session_model_preview),
        "confirm-model": ({"model_preview"}, workflow.confirm_session_model),
        "segments": ({"segments_connectors"}, workflow.start_session_segments),
        "confirm-segments": ({"segments_connectors"}, workflow.confirm_session_segments),
        "confirm-build-plan": ({"build_plan"}, workflow.confirm_session_build_plan),
        "documents": ({"lesson_bundle"}, workflow.start_session_documents),
        "confirm-documents": ({"lesson_bundle"}, workflow.confirm_session_documents),
    }
    if stage not in actions:
        raise HTTPException(404, "Unknown action")
    phases, action = actions[stage]
    if state.phase.value not in phases:
        raise HTTPException(409, "Finish the current lesson stage first.")
    if stage == "confirm-build-plan":
        plan = (state.build_result or {}).get("build_plan", {})
        validation = plan.get("validated_planner") or plan.get("notebook_outputs", {}).get("validated_planner", {})
        if not validation.get("instruction_steps"):
            raise HTTPException(409, "The validated instruction sequence is missing. Please revise the build.")
    try:
        with store.unit_of_work():
            with bind_session(state):
                result = action(session_id)
            save(identity, row, state)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return result


@app.get("/api/v1/sessions/{session_id}/artifact")
def artifact(session_id: str, path: str, request: Request):
    _, _, state = load(request, session_id)
    root = Path(__file__).resolve().parents[2] / "work" / "build_jobs" / session_id
    allowed = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".glb", ".obj"}
    if path.startswith("gs://"):
        if Path(path).suffix.lower() not in allowed:
            raise HTTPException(404, "Artifact not found")
        from runtime import artifacts
        try:
            path = artifacts.download(path, session_id)
        except ValueError as exc:
            raise HTTPException(404, "Artifact not found") from exc
        except Exception as exc:
            logger.warning("Artifact storage unavailable: %s", type(exc).__name__)
            raise HTTPException(503, "Saved file storage is temporarily unavailable. Please try again.") from exc
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(root.resolve()) or resolved.suffix.lower() not in allowed or not resolved.is_file():
        raise HTTPException(404, "Artifact not found")
    return FileResponse(resolved, filename=resolved.name if resolved.suffix == ".pdf" else None)


@app.get("/api/v1/sessions/{session_id}/{stage}")
def poll_stage(session_id: str, stage: str, request: Request):
    identity, row, state = load(request, session_id)
    actions = {"model-preview": workflow.get_session_model_preview,
               "segments": workflow.get_session_segments, "documents": workflow.get_session_documents}
    if stage not in actions:
        raise HTTPException(404, "Unknown stage")
    with bind_session(state):
        result = actions[stage](session_id)
    if not result:
        raise HTTPException(404, "No job for this stage")
    if state.model_dump(mode="json") != row["state"]:
        save(identity, row, state)
    return result


dist = Path(__file__).resolve().parents[2] / "ui" / "dist"
if dist.is_dir():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        return FileResponse(dist / "index.html")
