#!/usr/bin/env python3
"""Startup script to run the trading agent API server.

The trading agent now runs as a background task within the API process,
ensuring that instrumentation data is shared between the agent and API.
"""

import os
import subprocess
import sys


def run_db_init():
    """Run database initialization (migrations + seeding)."""
    print("=" * 50, flush=True)
    print("Running database initialization...", flush=True)
    print("=" * 50, flush=True)

    result = subprocess.run(
        [sys.executable, "scripts/init_db.py"],
        stdout=sys.stdout,
        stderr=sys.stderr,
    )

    if result.returncode != 0:
        print(f"WARNING: Database init exited with code {result.returncode}", flush=True)
        print("Continuing with startup anyway...", flush=True)
    else:
        print("Database initialization complete!", flush=True)


def main():
    # Run database migrations first
    run_db_init()

    port = os.environ.get("PORT", "8080")

    print("=" * 50, flush=True)
    print(f"Starting Trading Agent API on port {port}...", flush=True)
    print("Trading agent runs as background task in API process", flush=True)
    print("=" * 50, flush=True)

    # Start the API server (trading agent starts automatically via lifespan)
    api_process = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "agent.api.main:app",
            "--host", "0.0.0.0",
            "--port", port,
        ],
        stdout=sys.stdout,
        stderr=sys.stderr,
    )

    # Wait for the API process to exit
    try:
        api_process.wait()
    except KeyboardInterrupt:
        print("Received interrupt, shutting down...", flush=True)
    finally:
        api_process.terminate()
        api_process.wait()
        print("Shutdown complete", flush=True)


if __name__ == "__main__":
    main()
