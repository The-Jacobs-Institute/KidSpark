# KidSpark

KidSpark helps teachers turn a story into a hands-on lesson: discuss learning
goals, review a proposed model, check a kit-constrained build, and prepare a
teacher lesson plan, activity guide, and slide companion.

This repository is the standalone modernization for The Jacobs Institute. It is
**under development, not a production replacement yet**. The previous BrickSmart
checkout and deployed service have not been changed. Work is on
`modernization/standalone`; cloud deployment and a deployment branch follow the
remaining readiness checks in [migration status](docs/MIGRATION_STATUS.md).

## Current architecture

```text
Teacher's browser
    React / TypeScript
          |
    same-origin /api/v1
          |
    FastAPI -- anonymous, private lesson sessions
          |                  |
    planning agents     durable job records
          |                  |
    Vertex Gemini       isolated Python workers
          |                  |
    retrieval           Rodin / Bang -> voxelization -> validated planner
          |                  |
    corpus PostgreSQL   classroom PDF renderer
    + pgvector               |
    (separate DB)       session-scoped local artifacts
```

The local runtime stores lesson and job state in SQLite. The corpus database is
separate; the teacher workflow must not initialize or overwrite curriculum data.
Future Cloud Run instances will need a shared application PostgreSQL database
and durable artifact transport. Local filesystem storage is **not** sufficient
for separate Cloud Run workers or multiple web instances.

## Repository map

| Directory | Responsibility |
| --- | --- |
| `ui/` | React teacher workflow, review controls, progress, downloads |
| `backend/api/` | HTTP contracts, session authorization, workflow boundaries |
| `backend/runtime/` | Session persistence, transactions, isolated worker execution |
| `backend/agents/` | Story analysis, teacher coaching, planning state, orchestration |
| `backend/llm/` | Vertex generation and primary/fallback routing |
| `backend/build3d/` | Rodin/Bang integration, physicalization, documents |
| `backend/bricksmart/` | Retained validated physical-build engine |
| `backend/bricksmart_inventory/` | Inventory and feasibility rules |
| `retrieval/` | Query embeddings, corpus lookup, ranking, evidence assembly |
| `ingestion/` | Curriculum loading and preprocessing; separate operator workflow |
| `shared/` | Corpus configuration, database models, logging contracts |
| `block_catalog/`, `config/inventory/` | Authoritative parts and kit definitions |
| `model_store/`, `model_registry/` | Canonical regression models and contracts |
| `tests/`, `backend/tests/` | Standalone, domain, planner, PDF regression tests |
| `tools/verification/` | Build-equivalence reporting |

The internal `bricksmart` Python package remains a dependency of the physical
planner. Keeping that package does not preserve the old product's UI or session
server. Streamlit and the old combined frontend are not part of this app.

## Local setup

Use Python 3.11+ and Node.js 22. Run from the repository root. A dedicated Python
environment avoids conflicts with globally installed scientific libraries.

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
Set-Location ui
npm ci
npm run build
Set-Location ..
$env:PYTHONPATH = "backend;."
.\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8012
```

Open <http://127.0.0.1:8012>. The FastAPI process serves the built UI and the API
on one origin. Keep the terminal running. Choose a different port if it is already
in use. The new app does not need to stop the previous app on port 8501.

For frontend development, run `npm run dev` inside `ui/` in a second terminal.
The Vite proxy targets the API on port 8012. Rebuild `ui/dist` when using the
single-origin built version.

### Configuration and credentials

`.env.example` contains configuration names and safe placeholders only. Put local
values in the ignored root `.env`, never in a tracked file. Environment variables
provided by the host take precedence. No OpenAI key is required by this workflow.

| Variable | Purpose |
| --- | --- |
| `GCP_PROJECT_ID` | Intended project: `kidspark-499901` |
| `GEMINI_PRIMARY_MODEL`, `GEMINI_FALLBACK_MODEL` | Configured generation model IDs; live availability still requires verification |
| `VERTEX_GENERATION_LOCATION` | Configured generation endpoint location |
| `VERTEX_EMBEDDING_LOCATION`, `EMBED_MODEL`, `EMBED_DIM` | Query/corpus embedding configuration; model and dimensions must agree |
| `HYPER3D_API_KEY` | Authorized Rodin/Bang access |
| `POSTGRESQL_DATABASE_URL` | Existing curriculum corpus connection, not the application database |
| `KIDSPARK_APP_DATABASE_URL` | Writable application state; local default is `sqlite:///work/kidspark.sqlite` |
| `KIDSPARK_WORKER_MODE` | `local` launches isolated processes; `disabled` is for tests |
| `KIDSPARK_RAG_ENABLED` | Controls curriculum lookup; unavailable evidence is disclosed, not fabricated |
| `KIDSPARK_COOKIE_SECURE` | False for local HTTP; must be true behind production HTTPS |

Vertex uses Application Default Credentials when `GEMINI_API_KEY` is absent.
An authorized project member can establish local ADC using
`gcloud auth application-default login`, then set its quota project to
`kidspark-499901`. A CLI account selection alone is not the same as ADC.
The optional existing Vertex API-key route remains supported for compatibility.
Do not distribute service-account private keys as a development shortcut.

For corpus access, use the approved Cloud SQL connection method and database
credentials. Ingestion has additional dependencies in `ingestion/requirements.txt`;
install them only for ingestion work. Do not run ingestion or schema changes
against the shared corpus merely to start the teacher app.

### Local validation without paid services

There is an explicit fixture server for exercising navigation, persistence,
approval transitions, revision, rendering, and downloads without external calls:

```powershell
$env:PYTHONPATH = "backend;."
.\.venv\Scripts\python.exe -m uvicorn fixture_server:app --app-dir tests/standalone --host 127.0.0.1 --port 8013
```

Open <http://127.0.0.1:8013>. Paste a short bridge story, choose a first-grade,
40-minute static bridge lesson, then complete the six stages. This harness
substitutes external analysis/generation boundaries with known data. It uses the
real API, session store, job transitions, and PDF renderer, with a separate database
at `work/browser-fixtures.sqlite`. The UI and PDFs are visibly labeled fixtures.

**These are not approved classroom instructions.** A successful fixture flow does
not prove Gemini availability, live retrieval relevance, Hyper3D behavior, or the
physical feasibility of a newly generated model. The harness is excluded from
the deployment image.

## Tests

```powershell
$env:PYTHONPATH = "backend;."
.\.venv\Scripts\python.exe -m pytest backend/tests tests -q
Set-Location ui
npm run build
npm audit --omit=dev --audit-level=high
```

Tests cover teacher planning, inventory and planner regressions, provider routing,
PDF layout, session isolation, optimistic concurrency, transactional dispatch,
duplicate submission, and file access boundaries. PyMuPDF is a required development
dependency so PDF checks do not silently skip in CI. The reference OBJ files are
checksum-verified and are not subject to Git line-ending conversion.

CI validates Python tests and the UI build. It does not deploy. Refer to
[local validation evidence](docs/LOCAL_VALIDATION.md) for what was actually tested
and what remains unverified.

## Workflow and safety boundaries

1. Upload or paste a story. Empty input is rejected; provider failure preserves
   the story draft instead of substituting a sample story.
2. Discuss the lesson. Confirm the required classroom and build choices.
3. Generate and review the model preview.
4. Review segmentation and kit-constrained build validation.
5. Review the validated instruction sequence. Missing or failed validation cannot
   be approved as a valid build.
6. Generate and download the three classroom documents; complete after review.

Revising a model clears its downstream results. Polling caches are keyed by job
identity so an older build cannot be presented as a newly generated result.
Submitted jobs and session changes commit together; dispatch happens only after
commit. A job's worker claim is atomic, preventing duplicate execution of the same
queued job. Heartbeats and bounded reconciliation recover eligible interrupted
work; saved provider responses are reused. Ambiguous paid submissions stop for
operator review instead of being blindly repeated. Teachers can stop eligible jobs,
resume saved work, and revise documents without regenerating the model.

Lessons use an opaque HttpOnly browser cookie. A different browser cannot read a
lesson just by knowing its ID. This is anonymous session isolation, not user-account
authentication: losing the cookie loses access. Keep the same browser and lesson
URL to return. The local app persists sessions across server restarts.

## Cloud migration status

The intended destination remains project `kidspark-499901` in `us-central1`.
The existing `kidspark` Cloud Run service, corpus database, and data buckets have
not been replaced or reconfigured by this local implementation.

Billing was reported disabled during the current verification. Per the project
decision, restoring billing and testing live endpoints are post-implementation
steps. Existing configured model names are not a claim of current entitlement.

Before deploying this standalone app:

- Verify implemented artifact transport and recovery across real cloud executions.
- Configure durable reconciliation scheduling and worker invocation permissions.
- Provision the isolated application database, run migrations and verify backups.
- Resolve physical-planner blockers and validate review/refinement with live outputs.
- Configure deployment identities, Secret Manager bindings, preview/production
  settings, release workflow, and rollback. Do not reuse a personal account's keys.
- Verify actual generation, corpus lookup, geometry processing, and PDF contents
  end to end on the hosted service after billing is restored.

The Dockerfile is a starting point with explicit copy rules and a non-root user;
it is not evidence that the hosted system is ready. Never deploy the local SQLite
and filesystem configuration as a multi-instance service.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Planning service unavailable | ADC/key, actual model entitlement, project billing; the draft remains saved |
| Curriculum references unavailable | Corpus DB reachability, credentials, exact grade filter, embedding metadata |
| Job stays queued | Local worker logs under `work/logs`, Python environment and dispatch status |
| Job interrupted while running | Eligible jobs recover from checkpoints; ambiguous submissions need operator review |
| Build needs revision | Piece and segment constraints plus strict inventory/connection checks; do not bypass approval |
| Lesson not found in another browser | Expected cookie-based isolation; use the original browser |
| Files cannot be downloaded | File must exist beneath that lesson's scoped job directory |
| UI does not reflect changes | Rebuild `ui/dist`, restart the backend when Python code changed, reload the browser |

Secrets, generated lesson files, local databases, and logs are ignored by Git.
Do not attach them to public issues without redaction. Retention, access control,
abuse limits, and production observability remain explicit readiness tasks.

See [local end-to-end instructions](docs/LOCAL_END_TO_END.md) for the private-env
launcher and live readiness checks, and [GCP setup status](docs/GCP_SETUP_STATUS.md)
for permissions applied versus resources still blocked by billing.
