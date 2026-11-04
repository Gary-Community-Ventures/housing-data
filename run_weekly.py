"""Import the latest published GitHub rental snapshot without running collectors."""

import os
import tempfile
from datetime import datetime, timedelta, timezone

import requests


REPOSITORY = "Gary-Community-Ventures/housing-data"
MAX_SNAPSHOT_BYTES = 25 * 1024 * 1024


def main() -> None:
    host = os.environ["RENTAL_IMPORT_HOST"].strip()
    token = os.environ["RENTAL_IMPORT_TOKEN"]
    if not host or not token:
        raise ValueError("Rental import host and token must be configured")

    release_response = requests.get(
        f"https://api.github.com/repos/{REPOSITORY}/releases/latest",
        timeout=30,
    )
    release_response.raise_for_status()
    release = release_response.json()
    if not release["tag_name"].startswith("rental-snapshot-"):
        raise ValueError("Latest release is not a rental snapshot")
    published_at = datetime.fromisoformat(release["published_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) - published_at > timedelta(days=10):
        raise ValueError("Latest rental snapshot is more than 10 days old")
    asset = next(
        asset for asset in release["assets"]
        if asset["name"] == "rental-listings.jsonl.gz"
    )
    download_url = asset["browser_download_url"]
    if not download_url.startswith(f"https://github.com/{REPOSITORY}/releases/download/"):
        raise ValueError("Snapshot download URL is outside the expected repository")
    if not 0 < asset["size"] <= MAX_SNAPSHOT_BYTES:
        raise ValueError("Snapshot has an invalid compressed size")

    with tempfile.TemporaryFile() as compressed:
        with requests.get(download_url, stream=True, timeout=60) as download:
            download.raise_for_status()
            size = 0
            for chunk in download.iter_content(chunk_size=1024 * 1024):
                size += len(chunk)
                if size > MAX_SNAPSHOT_BYTES:
                    raise ValueError("Snapshot exceeds the compressed size limit")
                compressed.write(chunk)
        if size != asset["size"]:
            raise ValueError("Snapshot download size does not match the published asset")
        compressed.seek(0)
        response = requests.post(
            f"http://{host}:8080/internal/rental-listings",
            data=compressed,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/gzip"},
            timeout=180,
        )

    if not response.ok:
        raise RuntimeError(
            f"Rental import failed (HTTP {response.status_code}): {response.text[:8000]}"
        )
    result = response.json()
    if result["status"] == "skipped_older":
        print("Backend already has this snapshot or a newer one")
        return
    if result["status"] != "stored":
        raise ValueError(f"Rental import was not updated: {result['status']}")
    print(f"Imported {result['listings']} rental listings through {result['collected_through']}")


if __name__ == "__main__":
    main()
