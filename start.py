#!/usr/bin/env python3
"""Startup script to run both trading agent and API server."""

import os
import subprocess
import sys


def main():
    port = os.environ.get("PORT", "8080")

    # Start the trading agent in the background
    agent_process = subprocess.Popen(
        [sys.executable, "-m", "agent.main"],
        stdout=sys.stdout,
        stderr=sys.stderr,
    )

    # Start the API server (this blocks)
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

    # Wait for either process to exit
    try:
        agent_process.wait()
        api_process.wait()
    except KeyboardInterrupt:
        agent_process.terminate()
        api_process.terminate()
        agent_process.wait()
        api_process.wait()


if __name__ == "__main__":
    main()
