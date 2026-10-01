import gzip
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import run_weekly


class WeeklyImportTests(unittest.TestCase):
    def test_uploads_gzipped_full_snapshot_after_collection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            sample = b'{"property_name":"Example"}\n'
            (root / "data/listings.jsonl").write_bytes(sample)

            response = Mock()
            response.json.return_value = {"status": "stored", "listings": 1, "collected_through": "2026-10-01"}

            def inspect_upload(url, *, data, headers, timeout):
                self.assertEqual(url, "http://backend.railway.internal:8080/internal/rental-listings")
                self.assertEqual(gzip.decompress(data.read()), sample)
                self.assertEqual(headers["Authorization"], "Bearer secret")
                self.assertEqual(timeout, 180)
                return response

            with patch.object(run_weekly, "ROOT", root), patch.dict(
                "os.environ", {"RENTAL_IMPORT_HOST": "backend.railway.internal", "RENTAL_IMPORT_TOKEN": "secret"}
            ), patch.object(run_weekly.subprocess, "run") as collect, patch.object(
                run_weekly.requests, "post", side_effect=inspect_upload
            ):
                run_weekly.main()

            collect.assert_called_once_with([sys.executable, "run_daily.py"], cwd=root, check=True)


if __name__ == "__main__":
    unittest.main()
