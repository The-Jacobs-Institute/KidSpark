"""Explicit, additive application migration. Never migrates the curriculum DB."""
import config  # Load the root .env before constructing the application engine.
from runtime import store

if __name__ == "__main__":
    import os
    if os.getenv("POSTGRESQL_DATABASE_URL") and os.getenv("POSTGRESQL_DATABASE_URL") == os.getenv("KIDSPARK_APP_DATABASE_URL"):
        raise SystemExit("Use a separate application database, not the curriculum database.")
    store.migrate()
    print("Application schema v1 is ready. No curriculum tables were modified.")
