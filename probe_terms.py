#!/usr/bin/env python
"""
Read the actual terms documents of hosts we denylist, and record what they say.

Written because the aggregator denial rested on an assumption. Rule 4 says check
the terms; this checks them for the hosts the collector refuses to touch, so the
denial is evidence-based and auditable.
"""
import json, os, sys
from datetime import datetime, timezone
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hn.policy import Fetcher
from hn.terms import classify_terms_text

CANDIDATES = {
    # ILS / aggregator listing sites
    "apartments.com": ["https://www.apartments.com/terms-of-service/"],
    "apartmentguide.com": ["https://www.apartmentguide.com/terms-of-service/",
                           "https://www.apartmentguide.com/terms/"],
    "zillow.com": ["https://www.zillow.com/z/corp/terms/"],
    "realtor.com": ["https://www.realtor.com/terms-of-service"],
    "rent.com": ["https://www.rent.com/terms-of-service/", "https://www.rent.com/terms/"],
    "apartmentlist.com": ["https://www.apartmentlist.com/about/terms-of-service",
                          "https://www.apartmentlist.com/terms-of-service"],
    "trulia.com": ["https://www.trulia.com/terms/", "https://www.trulia.com/legal/terms/"],
    "hotpads.com": ["https://hotpads.com/legal/terms"],
    "zumper.com": ["https://www.zumper.com/terms-of-service", "https://www.zumper.com/legal/terms"],
    "forrent.com": ["https://www.forrent.com/terms-of-service"],
    # leasing-engine vendors
    "rentcafe.com": ["https://www.yardi.com/legal/terms-of-use/",
                     "https://www.yardi.com/legal/", "https://www.rentcafe.com/legal/"],
    "entrata.com": ["https://www.entrata.com/legal", "https://www.entrata.com/terms-of-use",
                    "https://www.entrata.com/legal/terms-of-use"],
    "realpage.com": ["https://www.realpage.com/legal/terms-of-use/",
                     "https://www.realpage.com/terms-of-use/"],
    "appfolio.com": ["https://www.appfolio.com/legal/terms-of-service",
                     "https://www.appfolio.com/terms-of-service"],
    "myresman.com": ["https://myresman.com/terms-conditions/", "https://www.myresman.com/legal/"],
    "prospectportal.com": ["https://prospectportal.com/terms/"],
}


def main():
    f = Fetcher(min_delay=3.0, log_path="logs/terms_probe.jsonl")
    out = []
    for host, urls in CANDIDATES.items():
        rec = {"host": host, "checked_at": datetime.now(timezone.utc).isoformat(),
               "terms_url": None, "http": None, "verdict": "NOT_RETRIEVED",
               "snippets": [], "automation_mentions": 0, "text_chars": 0}
        for u in urls:
            r = f.get_terms_document(u)
            rec["http"] = f"{r.outcome}{'/' + str(r.status) if r.status else ''}"
            if r.ok and len(r.text) > 1500:
                soup = BeautifulSoup(r.text, "lxml")
                for bad in soup(["script", "style", "noscript"]):
                    bad.decompose()
                body = soup.get_text(" ", strip=True)
                v, snips, n = classify_terms_text(body)
                rec.update({"terms_url": r.final_url or u, "verdict": v,
                            "snippets": snips, "automation_mentions": n,
                            "text_chars": len(body)})
                break
        out.append(rec)
        print(f"{host:22} {rec['verdict']:30} http={str(rec['http']):14} "
              f"chars={rec['text_chars']:7} mentions={rec['automation_mentions']}")
        for sn in rec["snippets"][:1]:
            if isinstance(sn, dict):
                print(f"    [{sn.get('term')}|{sn.get('scope')}] {sn.get('text','')[:150]}")
    json.dump(out, open("logs/denylist_terms_evidence.json", "w"), indent=1)
    print("\nwrote logs/denylist_terms_evidence.json")
    return out


if __name__ == "__main__":
    main()
