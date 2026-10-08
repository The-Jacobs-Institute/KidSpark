# Local validation record

Date: 2026-10-08. Repository: `The-Jacobs-Institute/KidSpark`.
Branch: `modernization/standalone`. Scope: standalone migration implementation,
not production acceptance. Existing BrickSmart deployment was left unchanged.

## Automated coverage

Run from the repository root with `backend` and the root on `PYTHONPATH`:

```text
python -m pytest backend/tests tests -q --tb=short
npm run build  (inside ui)
npm audit --omit=dev --audit-level=high  (inside ui)
```

Latest result: **201 passed, one dependency deprecation warning**, in 23.28 seconds. No tests
were skipped or deselected. The complete Python suite includes domain behavior, kit inventory, planner
regressions, model checksums, document layout, and standalone API persistence.
The UI build performs TypeScript checking. The dependency audit reported no
production JavaScript vulnerabilities at the time of this pass.

New regressions cover:

- Browser-cookie session isolation and reconnecting with the same cookie.
- Rejected cross-site mutations, empty stories, and out-of-order confirmation.
- Preserved story draft when the generation provider is unavailable.
- File-path traversal rejection and another browser's denied artifact access.
- Atomic session/job transactions, rollback, and post-commit dispatch.
- Deterministic job submissions and a worker claiming a queued job only once.
- Dispatch failure preserving durable queued intent.
- Optimistic concurrency rejecting stale writes.
- Revised piece/region constraints persisting while old downstream results clear.
- Missing validation or instruction sequence preventing approval.
- Canonical regression model checksums surviving cross-platform checkouts.
- Activity heading variants, optional section omission, and static-build wording.

The latest full suite ran in a newly created Python 3.13 `.venv` installed from
`requirements-dev.txt`. `pip check` reported no broken requirements. Starlette's
test client emits one warning about a future switch from httpx to httpx2; this
does not fail tests. Python 3.11 and remote CI remain unverified.

Additional tests cover completed provider checkpoint reuse, uncertain submissions,
lease fencing, legacy-job recovery refusal, queue capacity, cancellation, bounded
resume, fresh-worker artifact restoration, GCS path ownership, document revision
approval resets, and mandatory connection review tied to the current build.

## Browser verification

The embedded browser exercised the explicitly labeled fixture server on port
8013. The fixture substitutes external provider boundaries; the FastAPI routes,
orchestrator, database transactions, job state, and PDF renderer are real.

| Check | Observed result |
| --- | --- |
| Story upload | Story title and planning ideas appeared |
| Teacher planning | Required fields populated and confirmation enabled |
| Static movement | Displayed `Fully static`, not `Not decided yet` |
| Model preview | Preview image loaded and approval advanced the stage |
| Build review | Test result clearly labeled `Test fixture only` |
| Instructions | Instruction text rendered before approval |
| Model revision | Returned to preview and required a new build review |
| Revision persistence | 24 pieces and 3 regions survived browser reload |
| Documents | Three distinct download links appeared |
| Downloads | Lesson plan, activity guide, and slide companion downloaded |
| Completion | Lesson complete state appeared; downloads remained available |
| Server restart | Existing lesson remained accessible in the same browser |
| Document-only revision | New bundle job and PDF paths; model/build retained |
| Revised bundle approval | Waited for generation, then completion survived reload |

Desktop screenshots and PDF page renders are saved locally under
`work/validation/`, intentionally outside Git. The updated completion screen was
visually inspected at 390 x 844 and reported no horizontal overflow. This is not
a full mobile acceptance run across all six stages.

## PDF inspection

All nine pages from the revised fixture bundle were rendered with Poppler and
visually inspected: one teacher-plan page, two activity pages, six widescreen
slide pages. Text and images were present; no clipping or overlapping text was
observed. All three PDFs contained the bridge fixture image. Fixtures are marked
as unvalidated and are not classroom instructions.

The test input is deliberately short. It verifies rendering and transport, not
pedagogical depth, faithful illustration of a real generated model, or quality
equivalence to the source curriculum. Those require a live, teacher-reviewed run.
The newest downloaded bundle (lesson plan 8, activity guide 6, slide companion 7)
was also rendered with Poppler and all nine pages inspected. Text and the bridge
fixture image were present without clipping. The deliberately short fixture has
large empty areas; it is not evidence of publication-quality generated content.

## Fixes found during validation

1. A nested SQLite savepoint could leave an orphan job after an outer rollback.
   Native conflict-safe insert now keeps the job inside the request transaction.
2. The instructions screen showed images but not its validated step text.
3. Download links all inherited the internal label `pdf_path`.
4. Revision polling could briefly request the deleted old stage; job identities
   now distinguish cached results and replaced stages are not force-refetched.
5. Refreshed constraint controls showed defaults rather than saved limits.
6. Activity PDFs emitted empty section headings and assumed a moving component.
7. An equivalent `Learn and Explore` heading was not recognized by the activity
   layout. It now accepts the equivalent section name without losing its text.
8. Two reference OBJ files had Windows line endings inconsistent with their
   manifests. Their canonical bytes and Git attributes are now protected.
9. The selective port omitted the build-equivalence utility and retained a wheel
   packaging assertion. The utility is restored and container exclusions tested.
10. Block planning still used a sample catalog/fallback. It now reads the actual
    CSV catalog and reports provider unavailability rather than inventing a build.

## Deferred or not validated

- Billing restoration and actual configured Gemini model entitlement/location.
- Live corpus access, embedding coverage, retrieval relevance, and grade values.
- A new live Rodin/Bang model, physical validation, and all its instruction images.
- Cross-instance GCS artifacts, Cloud Run workers, quotas, and interrupted-job recovery.
- PostgreSQL migration execution, shared-data backups/restore, and disaster recovery.
- Container execution, hosted end-to-end tests, remote CI, and deployment rollback.
- Live connector/document refinement quality and full mobile visual review.

Docker Desktop initially failed to start because its temporary analytics socket
was inaccessible. Its runtime folder was preserved under a backup name, and Docker
successfully recreated it on restart. The Linux engine now responds. Application
container build/run validation remains outstanding; engine startup alone is not
a container acceptance test.

The live preflight authenticated against Hyper3D's balance endpoint without
generating a model. Both Gemini probes failed during ADC token refresh, before
model availability could be assessed. The corpus query failed to connect; there
was no local listener on its configured proxy port 5555. Billing also remains
disabled. The new local live launcher starts successfully on 8014, with live mode
reported by its health endpoint; this is startup evidence, not a live end-to-end pass.

See [migration status](MIGRATION_STATUS.md) for implementation work that must be
completed before deployment. Local green tests do not waive any of these items.
