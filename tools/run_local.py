"""Launch the standalone app locally, with isolated session storage and files."""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--port", type=int, default=8014)
    parser.add_argument("--vertex-adc", action="store_true", help="Use local Google ADC instead of a Gemini API key")
    args = parser.parse_args()
    env_file = args.env_file.resolve()
    if not env_file.is_file():
        parser.error("Private environment file not found. Configure .env or supply --env-file.")
    os.chdir(ROOT)
    from dotenv import load_dotenv
    load_dotenv(env_file)
    if os.getenv("K_SERVICE") or os.getenv("CLOUD_RUN_JOB"):
        parser.error("This launcher is for a developer workstation, not Cloud Run.")
    if os.getenv("GCP_PROJECT_ID", "kidspark-499901") != "kidspark-499901":
        parser.error("Use the Jacobs project kidspark-499901 for this migration.")
    os.environ.update(
        KIDSPARK_APP_DATABASE_URL="sqlite:///work/kidspark-local.sqlite",
        KIDSPARK_ARTIFACT_BUCKET="",
        KIDSPARK_WORKER_MODE="local",
        KIDSPARK_COOKIE_SECURE="false",
        KIDSPARK_OFFLINE_MODE="false",
    )
    if args.vertex_adc:
        os.environ["GEMINI_API_KEY"] = ""
    paths = [str(ROOT / "backend"), str(ROOT)]
    sys.path[:0] = paths
    os.environ["PYTHONPATH"] = os.pathsep.join(paths)
    if not (ROOT / "ui/dist/index.html").is_file():
        parser.error("Build the UI first: npm ci and npm run build inside ui/.")
    import uvicorn
    print(f"Live-provider local app: http://127.0.0.1:{args.port}/. External generation may incur charges.")
    print("Sessions and generated files stay in this checkout; no deployment or corpus migration is performed.")
    uvicorn.run("api.main:app", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
