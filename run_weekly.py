"""Collect a complete rental snapshot and publish it to the housing screener."""

import gzip
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parent


def main() -> None:
    host = os.environ["RENTAL_IMPORT_HOST"].strip()
    token = os.environ["RENTAL_IMPORT_TOKEN"]
    if not host or not token:
        raise ValueError("Rental import host and token must be configured")

    subprocess.run([sys.executable, "run_daily.py"], cwd=ROOT, check=True)

    source = ROOT / "data/listings.jsonl"
    if not source.is_file() or not source.stat().st_size:
        raise ValueError("Collection produced no rental listings")

    with tempfile.TemporaryFile() as compressed:
        with gzip.GzipFile(fileobj=compressed, mode="wb") as zipped:
            with source.open("rb") as listings:
                for chunk in iter(lambda: listings.read(1024 * 1024), b""):
                    zipped.write(chunk)
        compressed.seek(0)
        response = requests.post(
            f"http://{host}:8080/internal/rental-listings",
            data=compressed,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/gzip"},
            timeout=180,
        )

    response.raise_for_status()
    result = response.json()
    if result["status"] != "stored":
        raise ValueError(f"Rental import was not updated: {result['status']}")
    print(f"Imported {result['listings']} rental listings through {result['collected_through']}")


if __name__ == "__main__":
    main()
