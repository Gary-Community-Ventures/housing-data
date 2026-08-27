#!/usr/bin/env python
"""
Re-audit hosts previously classified SILENT.

The prohibition classifier missed the most common drafting style: a "You agree
not to:" stem followed by bullets. Every SILENT verdict produced before that fix
is therefore unreliable and has to be re-checked against the actual document.
Any host that now reads PROHIBITS is dropped and its rows removed.
"""
import json, os, sys, threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hn.policy import Fetcher
from hn.terms import classify_terms_text

LOCK = threading.Lock()


def main(workers=10):
    prior = {}
    for line in open("logs/terms_audit.jsonl"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        prior[r["site"]] = r
    # Re-check everything we have a document for, not just SILENT: the stem and
    # scope fixes can move a verdict in either direction.
    targets = [r for r in prior.values() if r.get("terms_url")]
    print(f"re-checking {len(targets)} hosts previously scored SILENT\n")

    results, done = [], [0]

    def work(chunk):
        f = Fetcher(min_delay=3.0, log_path="logs/terms_reaudit_fetch.jsonl")
        for rec in chunk:
            out = {"site": rec["site"], "terms_url": rec["terms_url"],
                   "prior_verdict": "SILENT", "new_verdict": "UNREADABLE",
                   "snippets": [], "checked_at": datetime.now(timezone.utc).isoformat()}
            try:
                r = f.get(rec["terms_url"])
                if r.ok and len(r.text) > 1200:
                    soup = BeautifulSoup(r.text, "lxml")
                    for b in soup(["script", "style", "noscript"]):
                        b.decompose()
                    v, snips, n = classify_terms_text(soup.get_text(" ", strip=True))
                    out.update({"new_verdict": v, "snippets": snips,
                                "automation_mentions": n})
                else:
                    out["detail"] = f"{r.outcome} {r.detail}"[:120]
            except Exception as e:
                out["detail"] = f"{type(e).__name__}"
            with LOCK:
                results.append(out)
                done[0] += 1
                flag = "  <-- NOW PROHIBITS" if out["new_verdict"] == "PROHIBITS" else ""
                print(f"[{done[0]}/{len(targets)}] {out['site'][:44]:46} "
                      f"{out['new_verdict']}{flag}", flush=True)

    shards = [targets[i::workers] for i in range(workers)]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, shards))

    json.dump(results, open("logs/terms_reaudit.json", "w"), indent=1)
    c = Counter(r["new_verdict"] for r in results)
    print("\n" + "=" * 56)
    print("re-audit outcome:", dict(c))
    newly = [r for r in results if r["new_verdict"] == "PROHIBITS"]
    print(f"newly prohibiting hosts: {len(newly)}")
    for r in newly:
        print(f"  {r['site']}")
        for sn in r["snippets"][:1]:
            txt = sn["text"] if isinstance(sn, dict) else str(sn)
            term = sn.get("term", "?") if isinstance(sn, dict) else "?"
            print(f"     [{term}] {txt[:180]}")
    return results


if __name__ == "__main__":
    main()
