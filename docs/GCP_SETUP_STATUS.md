# GCP preparation status

Verified 2026-10-08. Project `kidspark-499901` (number `347292804255`),
region `us-central1`. This is the Jacobs project, not the earlier personal project.

## Applied and verified

Created the dedicated runtime identity
`kidspark-standalone@kidspark-499901.iam.gserviceaccount.com`.
It has these project roles:

- Vertex AI User (`roles/aiplatform.user`).
- Cloud SQL Client (`roles/cloudsql.client`).
- Logs Writer (`roles/logging.logWriter`).

It also has **read-only**, bucket-scoped Storage Object Viewer access to
`gs://kidspark-data-processed`. No corpus objects were changed. No service-account
key was generated. The APIs needed for Vertex, Cloud Run, Cloud SQL, Storage,
Secret Manager and Artifact Registry were already enabled.

The existing `kidspark` Cloud Run service at
<https://kidspark-2msfnwk43a-uc.a.run.app> was not redeployed or reconfigured.
No shared database writes or billing changes were made.

## Blocked by billing

The project reports `billingEnabled: false`; the linked billing account reports
closed. These operations were attempted but rejected by GCP:

- Create the private `gs://kidspark-499901-standalone-artifacts` bucket.
- Grant the new identity access to the existing `hyper3d-api-key` and
  `kidspark-db-url` secrets.

These resources/permissions must not be treated as ready. A billing owner must
restore billing or link an active authorized billing account. No new Gemini API
key is necessary when the app uses its service identity in Cloud Run and Google
Application Default Credentials locally.

## Prepared for the next pass

`tools/gcp/prepare-standalone.ps1` repeats the scoped preparation after billing is
restored. It stops on failure and will not change billing, deploy the app, or write
the curriculum database. Review the account parameter before running it:

```powershell
.\tools\gcp\prepare-standalone.ps1 -Account <authorized-project-account>
```

The script's operations were exercised individually where billing permitted;
the complete script has not succeeded end to end. It grants write access only
to the new application artifact bucket, never the processed curriculum bucket.

## Still needed before hosted release

1. Enable/verify shared-data backups and a restore procedure before database
   changes. Backups were disabled at the earlier inspection.
2. Create a separate application database and restricted database user, with its
   own Secret Manager connection secret. Do not use the curriculum database for
   writable lesson/session tables.
3. Run the additive application schema migration with
   `PYTHONPATH=backend;.` and `python -m runtime.migrate`. PostgreSQL startup now
   requires the migration; local SQLite is bootstrapped automatically.
4. Configure the new Cloud Run web service and worker job, scoped worker execution
   permission, application DB access and private artifact bucket. The web process
   currently reconciles jobs in the background: hosted recovery requires CPU
   allocation that continues between requests, a minimum running instance, or a
   separate scheduled reconciler. Request-only CPU with scale-to-zero is not enough.
5. Verify real GCS upload/download between distinct executions and PostgreSQL
   concurrency/recovery. Local fake-storage and SQLite tests do not prove these.
6. Configure preview/production settings, GitHub identity federation, release
   branch/workflow, secret mounts, rollback and monitoring. No deployment branch
   or GitHub deployment credentials have been created by this preparation.
7. Resolve the remaining planner inventory/step-image blockers, validate live
   provider/corpus access, and complete hosted acceptance.

Local end-to-end testing does not require the new Cloud Run service or artifact
bucket. See [the local test runbook](LOCAL_END_TO_END.md).
