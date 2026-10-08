"""Read-only local/live readiness checks. Never prints credentials or changes GCP.

Default checks configuration only. --live makes small paid Vertex requests,
checks Hyper3D balance, and queries corpus metadata/retrieval without writing it.
"""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--grade", help="Exact grade_band from the corpus; required for live retrieval test")
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(args.env_file)
    import config
    report = []
    def record(name, ready, detail):
        report.append({"check": name, "status": "pass" if ready else "pending", "detail": detail})

    record("project", config.GCP_PROJECT_ID == "kidspark-499901", config.GCP_PROJECT_ID)
    record("frontend", (ROOT / "ui/dist/index.html").is_file(), "Run npm ci and npm run build in ui/.")
    record("Hyper3D configuration", bool(config.HYPER3D_API_KEY), "An authorized Hyper3D key and provider credits are required.")
    record("corpus configuration", bool(os.getenv("POSTGRESQL_DATABASE_URL")), "Requires a populated pgvector database and reachable connection/proxy.")
    try:
        import google.auth
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        record("Google ADC", True, "Credentials found; permissions and billing are not yet verified.")
    except Exception as exc:
        record("Google ADC", False, f"{type(exc).__name__}; run gcloud auth application-default login.")
    if not args.live:
        report.append({"check": "live dependencies", "status": "not_tested", "detail": "Use --live --grade <exact corpus grade> after billing is restored."})
    else:
        from google import genai
        from google.genai import types
        for model in dict.fromkeys([config.GEMINI_PRIMARY_MODEL, config.GEMINI_FALLBACK_MODEL]):
            try:
                with genai.Client(vertexai=True, project=config.GCP_PROJECT_ID,
                        location=config.VERTEX_GENERATION_LOCATION,
                        http_options=types.HttpOptions(timeout=20000)) as client:
                    response = client.models.generate_content(model=model, contents="Reply with OK only.",
                        config=types.GenerateContentConfig(max_output_tokens=32, temperature=0))
                record(model, bool(response.text), f"Endpoint: {config.VERTEX_GENERATION_LOCATION}")
            except Exception as exc:
                record(model, False, f"{type(exc).__name__}; check billing, model availability, IAM and quota.")
        try:
            from build3d.rodin_client import check_balance
            check_balance()
            record("Hyper3D service", True, "Authenticated balance endpoint; no model was generated. Confirm enough credits before a full run.")
        except Exception as exc:
            record("Hyper3D service", False, type(exc).__name__)
        try:
            from sqlalchemy import create_engine, text
            url = os.environ["POSTGRESQL_DATABASE_URL"]
            engine = create_engine(url, connect_args={"connect_timeout": 8})
            try:
                with engine.connect() as connection:
                    connection.execute(text("SET TRANSACTION READ ONLY"))
                    connection.execute(text("SET LOCAL statement_timeout = '15s'"))
                    extension = connection.execute(text("SELECT extversion FROM pg_extension WHERE extname='vector'")).scalar()
                    record("pgvector", bool(extension), extension or "Extension missing")
                    rows = connection.execute(text("SELECT grade_band, count(*) AS nodes, count(embedding) AS embedded FROM pdf_node GROUP BY grade_band")).mappings().all()
                    record("corpus grades", bool(rows), [dict(row) for row in rows])
                    matching = connection.execute(text("SELECT count(*) FROM pdf_node WHERE embedding IS NOT NULL AND embedding_model=:model AND embedding_dimensions=:dimensions"),
                        {"model": os.getenv("EMBED_MODEL", "gemini-embedding-001"), "dimensions": int(os.getenv("EMBED_DIM", "3072"))}).scalar()
                    record("matching embeddings", bool(matching), {"nodes": matching})
            finally:
                engine.dispose()
        except Exception as exc:
            record("corpus database", False, f"{type(exc).__name__}; verify the proxy, credentials, schema and populated corpus.")
        if args.grade:
            try:
                from retrieval.engine import templated_retrieve
                from shared.corpus_database import DBUtil
                from shared.corpus_settings import settings
                database = DBUtil(settings)
                try:
                    result = templated_retrieve("Build and test a stable bridge with a partner", args.grade, rerank=False, dbu=database)
                finally:
                    database.engine.dispose()
                record("live retrieval", bool(result.get("seeds")), {"grade": args.grade, "seed_count": len(result.get("seeds", []))})
            except Exception as exc:
                record("live retrieval", False, f"{type(exc).__name__}; check exact grade, matching vectors and Vertex embedding access.")
        else:
            record("live retrieval", False, "Run again with --grade using an exact value listed in corpus grades.")
    print(json.dumps(report, indent=2))
    return 0 if all(item["status"] == "pass" for item in report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
