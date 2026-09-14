from __future__ import annotations

import argparse
import asyncio

from . import collector, reports


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m app", description="CSE Live collector (writes to Supabase Postgres)"
    )
    parser.add_argument("--once", action="store_true", help="run a single poll cycle then exit")
    parser.add_argument("--report", action="store_true", help="print a DB summary and exit")
    args = parser.parse_args()

    try:
        if args.report:
            asyncio.run(reports.print_report())
        else:
            asyncio.run(collector.run(once=args.once))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
