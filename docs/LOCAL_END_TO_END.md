# Local end-to-end test runbook

## What is ready now

The standalone React/FastAPI app can be tested locally with saved test fixtures.
The fixture server at <http://127.0.0.1:8013/> deliberately replaces AI, retrieval
and 3D-provider responses. It exercises real browser navigation, session storage,
document revision and PDF generation/download, but it does **not** demonstrate
live model quality, retrieval relevance or physical build validity.

The isolated `.venv` is installed and the UI is built on the current workstation.
No production deployment is needed to run a real-provider local test. All local
session data and generated files can stay under this repository's ignored `work/`
directory. The original BrickSmart app is not used as the frontend or backend.

## Requirements for the real-provider run

| Requirement | Current state / next check |
| --- | --- |
| Jacobs project billing | Disabled; billing owner must restore it |
| Google credentials | Found, but token refresh failed in the live probe; renew ADC login |
| Generation models | Both probes stopped at credential refresh; entitlement and location remain unverified |
| Hyper3D | Authenticated balance endpoint succeeded; confirm credits are sufficient for generation |
| Reference corpus | Connection is localhost:5555/kidspark; no proxy listener was running and DB probe failed |
| Corpus vectors | Confirm populated nodes with `gemini-embedding-001`, 3072 dimensions and exact stored grade values |
| New application storage | Local SQLite and files are sufficient; separate from the reference corpus |
| Physical planner | Inventory-ledger and step-image issues remain acceptance blockers for real generated builds |

Do not paste credentials into chat or check them into Git. The tracked
`.env.example` lists configuration names without secrets. On the current
workstation, the existing ignored `C:\Users\asggm\BrickSmart\example.env` can
be supplied explicitly without copying its keys into the new repository.
For another workstation, obtain authorized secret values through the project's
secure process and place them in an ignored `.env`.

## 1. Verify local dependencies

From `C:\Users\asggm\KidSpark`:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe tools/local_preflight.py --env-file C:\Users\asggm\BrickSmart\example.env
```

The configuration-only preflight intentionally exits nonzero because live
dependencies have not been tested. It prints status, not credentials. On a new
checkout, install `requirements-dev.txt` into a virtual environment and run
`npm ci` then `npm run build` in `ui/` first.

## 2. Restore and verify cloud access

After billing restoration, use the authorized Jacobs-project account for local
Application Default Credentials. A `gcloud` CLI login alone is not an ADC login:

```powershell
gcloud auth application-default login
gcloud auth application-default set-quota-project kidspark-499901
```

If the corpus connection points to localhost, keep a Cloud SQL Auth Proxy running
for `kidspark-499901:us-central1:kidspark-db`. Its port must match the private
connection URL (the team's earlier configuration used `5555`). The proxy requires
Cloud SQL Client permission; the PostgreSQL user also needs database read access.
Do not expose the proxy port publicly. Do not load or migrate shared corpus tables
as part of this application test.

```powershell
cloud-sql-proxy kidspark-499901:us-central1:kidspark-db --address 127.0.0.1 --port 5555
```

Run live preflight; it makes small billable model requests, checks Hyper3D's
balance endpoint without generating a model, and reads corpus metadata:

```powershell
.\.venv\Scripts\python.exe tools/local_preflight.py --env-file C:\Users\asggm\BrickSmart\example.env --live
```

Use one of the exact grade values reported by the database to verify retrieval:

```powershell
.\.venv\Scripts\python.exe tools/local_preflight.py --env-file C:\Users\asggm\BrickSmart\example.env --live --grade "<exact grade_band>"
```

Both configured generation models and the retrieval probe should pass. Model
names in configuration are not proof of availability. If either is unavailable,
select a supported model and test the primary/fallback policy before proceeding.
An empty corpus or incompatible embedding metadata requires a separate ingestion
repair, not bypassing retrieval checks or replacing shared data without review.

## 3. Start the live-provider local app

Use a free port (8014 by default). The launcher explicitly isolates application
sessions in local SQLite, disables cloud artifact writes, and launches local
workers. `--vertex-adc` makes generation use the same project-based authentication
checked by the preflight, instead of any older Gemini API key in the env file.

```powershell
.\.venv\Scripts\python.exe tools/run_local.py --env-file C:\Users\asggm\BrickSmart\example.env --vertex-adc --port 8014
```

Open <http://127.0.0.1:8014/>. Unlike port 8013, this run calls real providers and
can incur charges. Keep the terminal and corpus proxy running. Do not run the
fixture server to assess real generation or physical correctness.

This launcher was smoke-tested on port 8014: the app started and `/api/v1/health`
reported live mode. That health response confirms configuration/startup only,
not successful provider authentication. The local app is running, but cannot yet
complete real generation until the blockers above are resolved.

## 4. Acceptance checklist

1. Paste a short story or upload a story PDF. Verify the extracted story and title.
2. Confirm grade, classroom time, grouping, kit constraints and movement choice.
   Check curriculum evidence is actually returned, not just a graceful no-RAG fallback.
3. Generate and approve the preview. Confirm the intended object and moving parts.
4. Let segmentation, voxelization and bounded correction finish. Confirm both
   piece and region limits, inventory feasibility and actual validation status.
   Review any moving-part connection notes. Never approve an unvalidated result.
5. Inspect every build step for a usable instruction and the correct image. Missing
   step images or inventory inconsistencies are failures, even if a summary looks valid.
6. Generate and download all three PDFs. Compare the story, grade, materials,
   model images and build sequence across the teacher plan, activity and slides.
7. Request a document-only revision. Verify it creates a new bundle without
   regenerating the model; approve only after the revised files are ready.
8. Reload in the same browser and confirm the saved lesson and downloads remain.

Recovery is bounded (three worker attempts by default). Completed provider
responses are checkpointed; ambiguous submissions are stopped for operator review
instead of being blindly re-billed. A Stop action cannot cancel work already
accepted by an external provider. Local process recovery is unit-tested; fault
injection against paid providers and Cloud Run remains a later acceptance step.

## Evidence and limitations

See [local validation](LOCAL_VALIDATION.md), [migration status](MIGRATION_STATUS.md)
and [GCP setup](GCP_SETUP_STATUS.md). Local fixture success is useful but is not a
claim that the real-provider end-to-end path is ready for classroom use.
