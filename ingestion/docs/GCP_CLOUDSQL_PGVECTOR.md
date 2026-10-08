# Curriculum database operations

This is an operator workflow, separate from starting the teacher application.
Do not initialize, reload, or migrate the shared curriculum database as part of
local UI testing. Confirm database backups and the intended target before writes.

## Current migration target

- GCP project: `kidspark-499901`.
- Existing SQL connection name: `kidspark-499901:us-central1:kidspark-db`.
- Existing raw bucket: `kidspark-project-data`.
- Existing processed bucket: `kidspark-data-processed`.
- Processed prefix: `Knowledge_chunks`.

These identify the existing environment, not new resources created by this
repository. Billing was disabled during the local validation pass. Schema state,
row counts, model coverage, and backup/restore readiness must be reverified before
live ingestion or deployment. In particular, backups were disabled at inspection.

## Code map

| Module | Responsibility |
| --- | --- |
| `shared/corpus_settings.py` | Environment configuration and URL assembly |
| `shared/corpus_models.py` | Curriculum ORM tables |
| `shared/corpus_database.py` | Connections and schema initialization helpers |
| `ingestion/app/services/ingest.py` | Load processed bundles, enrich, embed, persist |
| `retrieval/repository.py` | Existing corpus persistence and lookup helpers |
| `retrieval/embeddings.py` | Vertex query/document embedding |
| `retrieval/engine.py` | Retrieval orchestration |
| `retrieval/provider.py` | Bounded teacher-workflow integration |

Some persistence helpers remain in `retrieval/repository.py` during the port;
moving write-only helpers into ingestion remains a separation-of-concerns task.
The application state store in `backend/runtime/store.py` is a different database
contract and must not share curriculum schema initialization logic.

## Local connection

Use your authorized GCP identity and the approved Cloud SQL connection method.
For a local Cloud SQL Auth Proxy, point it at the connection name above and a free
local port. Obtain database credentials through the team's approved secret access.
Do not put passwords in command-line arguments, screenshots, or committed files.

Set the following in an ignored root `.env` or process environment:

```dotenv
GCP_PROJECT_ID=kidspark-499901
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5555
POSTGRES_DB=kidspark
POSTGRES_USER=kidspark_app
POSTGRES_PASSWORD=
GCS_BUCKET_NAME=kidspark-project-data
GCS_PROCESSED_BUCKET=kidspark-data-processed
KNOWLEDGE_PREFIX=Knowledge_chunks
EMBED_MODEL=gemini-embedding-001
EMBED_DIM=3072
VERTEX_EMBEDDING_LOCATION=us-central1
```

The blank password is intentional. Alternatively set `POSTGRESQL_DATABASE_URL`
to the approved SQLAlchemy psycopg connection URI. URL components must be encoded;
the settings class handles that when constructing a URI from separate fields.
Do not use a Vertex API key as a database password. ADC authorizes GCP APIs and
proxy access; database authentication is a separate layer.

## Before any write

1. Confirm project, instance, database, backups, restore procedure, and permissions.
2. Verify `vector` is installed and inspect the curriculum tables against
   `shared/corpus_models.py`.
3. Check distinct `grade_band`, `embedding_model`, and `embedding_dimensions`
   values. Do not combine vectors from incompatible models or dimensions.
4. Count populated embeddings and inspect source lineage and stable image URIs.
5. Test against a disposable database and a small processed bundle first.
6. Review generated schema changes before applying them to shared data.

The legacy `create_all_tables()` helper performs DDL, including extension/table
setup. It is not a substitute for versioned, reviewed production migrations.

## Isolated ingestion environment

Install `ingestion/requirements.txt` in an ingestion-specific environment. It
includes the heavier Docling and ranking dependencies not required for
the teacher UI. Run modules from the repository root with `backend` and the root
on `PYTHONPATH`.

```powershell
$env:PYTHONPATH = "backend;."
python -m ingestion.app.services.ingest --help
```

Review the available flags before loading or backfilling. A `--no-embed` load
still writes data; it is not a read-only connectivity test. Existing corpus
re-embedding and any selective visual embedding are deferred until billing,
permissions, image availability, and the target database are verified.

For teacher retrieval contracts and fallback behavior, see
[runtime retrieval](../../retrieval/README.md). No OpenAI key is used for the
standalone Gemini generation or embedding paths.
