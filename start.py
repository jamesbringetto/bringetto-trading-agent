#!/usr/bin/env python3
"""Startup script to run both trading agent and API server."""

import os
import subprocess
import sys
import time


def main():
    port = os.environ.get("PORT", "8080")

    print(f"Starting API server on port {port}...", flush=True)

    # Start the API server FIRST so healthcheck can pass quickly
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

    # Give uvicorn a moment to start before launching the agent
    time.sleep(2)

    print("Starting trading agent...", flush=True)

    # Start the trading agent in the background
    agent_process = subprocess.Popen(
        [sys.executable, "-m", "agent.main"],
        stdout=sys.stdout,
        stderr=sys.stderr,
    )

    # Wait for either process to exit
    try:
        # Use poll() to check both processes
        while True:
            api_status = api_process.poll()
            agent_status = agent_process.poll()

            if api_status is not None:
                print(f"API server exited with code {api_status}", flush=True)
                break
            if agent_status is not None:
                print(f"Trading agent exited with code {agent_status}", flush=True)
                break

            time.sleep(1)
    except KeyboardInterrupt:
        print("Received interrupt, shutting down...", flush=True)
    finally:
        agent_process.terminate()
        api_process.terminate()
        agent_process.wait()
        api_process.wait()
        print("Shutdown complete", flush=True)


if __name__ == "__main__":
    main()
