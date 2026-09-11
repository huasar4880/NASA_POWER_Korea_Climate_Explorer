"""Run the offline Stage14.5 review, or regenerate its saved technical report."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main() -> int:
    """Numerically unsupported specifications are review findings, not workflow failures."""
    from src.spatial_numerical.workflow import run_review,report_from_saved
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run',action='store_true')
    mode.add_argument('--report-only',action='store_true')
    args=parser.parse_args()
    if args.report_only:
        print('\n'.join(report_from_saved()))
    else:
        result=run_review(dry_run=args.dry_run)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
