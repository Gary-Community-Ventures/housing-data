#!/bin/bash
# Wait for any in-flight pipeline stage, then run the operator-sitemap
# enumeration, collect what it finds, and rebuild every report.
set -u
cd /Users/tlillis/git/housing-data
PY=./.venv/bin/python

echo "=== waiting for in-flight pipeline ==="
while pgrep -f "rerun_subset|hn.cleanup|hn.validate|hn.normalize" >/dev/null; do sleep 10; done

echo; echo "=== normalize current data ==="
$PY -m hn.cleanup   2>&1 | tail -4
$PY -m hn.validate  2>&1 | grep -E "^validated|^==" 
$PY -m hn.normalize 2>&1 | tail -14

echo; echo "=== enumerate operator sitemaps ==="
$PY enum_operators.py 2>&1 | tail -45

echo; echo "=== collect newly enumerated properties ==="
if [ -s data/candidates_operator_sitemaps.json ]; then
  $PY run_collect.py --workers 12 --delay 3 --only candidates_operator_sitemaps 2>&1 | tail -12
fi

echo; echo "=== re-normalize with the new rows ==="
$PY -m hn.cleanup   2>&1 | tail -3
$PY -m hn.validate  2>&1 | grep -E "^validated|^=="
$PY -m hn.normalize 2>&1 | tail -14

echo; echo "=== rebuild reports ==="
$PY -m hn.report 2>&1 | tail -40
$PY -m hn.report_md
$PY tests/test_reference.py 2>&1 | tail -2
$PY tests/test_normalize.py 2>&1 | tail -2
echo "=== FINISH PASS COMPLETE ==="
