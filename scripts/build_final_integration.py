"""Build the final fact-bound research package from existing caches, with HTTP blocked."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main() -> int:
    """Publish new final artifacts, not old analysis results or API data."""
    from src.final_integration.workflow import build,publication_inventory,security_scan
    result=build(ROOT)
    publication_inventory(ROOT);scan=security_scan(ROOT)
    print(json.dumps({'facts':result['fact_count'],'provenance_verified':result['verified'],
        'report':result['report'],'NASA_API_calls':result['NASA_API_calls'],'KMA_API_calls':result['KMA_API_calls'],
        'security_safe':scan['safe'],'status':'GENERATED; full QA is a separate gate'},ensure_ascii=False,indent=2))
    return 0 if scan['safe'] else 1


if __name__=='__main__':
    raise SystemExit(main())
