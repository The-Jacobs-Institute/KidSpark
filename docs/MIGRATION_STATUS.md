# Standalone migration status

The application is being modernized on `modernization/standalone`. This is not
yet a production release. The original BrickSmart checkout and Cloud Run service
are unchanged.

## Implemented

- Selective import of Python agents, 3D processing, planner, catalog, and tests.
- React/TypeScript interface replacing the Streamlit dependency.
- Separate top-level retrieval and ingestion packages with shared corpus contracts.
- Model/dimension filtering and composite identities in vector retrieval.
- Durable anonymous lesson records with optimistic concurrency checks.
- Same-origin mutation protection and cross-browser session isolation.
- Durable job records, deterministic submission identities, and isolated workers.
- Transactional session/job submission with dispatch only after commit.
- Instruction-sequence review, named PDF downloads, and persistent revision limits.
- Model revision clears downstream results and caches use the new job identity.
- Explicit test harness exercising the full local browser flow without paid APIs.
- Full local backend/planner suite and frontend build; see `LOCAL_VALIDATION.md`.
- Strict rejection of absent build validation and empty story uploads.
- Explicit build-context exclusions for local credentials.
- Heartbeats, stale-job reconciliation, bounded recovery, cancellation and queue limits.
- Checkpointed provider responses; ambiguous submissions require operator review.
- Private GCS artifact manifests and fresh-worker restoration, tested with fake storage.
- Additive application database schema v1 and explicit PostgreSQL migration entry point.
- Document-only revisions with fresh approval and job-scoped connector review.
- Isolated Python environment, 201 passing tests, responsive completion-screen check.
- Dedicated GCP runtime identity and scoped permissions; see `GCP_SETUP_STATUS.md`.

## Required before deployment

- Verify recovery with PostgreSQL, separate Cloud Run executions and durable GCS storage.
- Provide always-on/scheduled reconciliation, worker execution IAM and capacity settings.
- Remove obsolete domain entry points and unused historical sample constants.
- Resolve planner inventory and validated-step image blockers.
- Validate refinement, connector review and recovery against real provider outputs.
- Separate preview/production configuration, application database provisioning,
  backup verification, Terraform, GitHub OIDC, and release workflows.
- Full corpus/provider verification, hosted live workflow, generated-content quality,
  final physical instruction image review, and rollback.

## Baseline

Source checkout: `yujia-l/BrickSmart`, commit `7af6ab0` plus reviewed local changes.
Destination: `The-Jacobs-Institute/KidSpark`; license preserved, README updated for the standalone app.
Existing project: `kidspark-499901`, service `kidspark`, SQL instance `kidspark-db`.
Existing corpus buckets are reused, not copied or modified during code migration.

Database backups were disabled at inspection. Enabling protection is a prerequisite
for any shared-data changes. Corpus SQL/GCS access must remain separate from
the new application's writable session data.

## Deferred billing check

The project reported `billingEnabled: false`; live Gemini calls reported
`BILLING_DISABLED`. The user explicitly requested continuing local implementation
and making billing/live verification a post-implementation step. No billing
settings or existing Cloud Run services were changed. A new runtime identity and
scoped read/provider permissions were added; existing corpus data was not changed.
Storage creation and secret access grants were blocked by billing.

Local fixtures verify workflow behavior only. They must never be counted as live
AI, retrieval relevance, or new-model physical validation evidence.
