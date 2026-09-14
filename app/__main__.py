from __future__ import annotations

import argparse
import asyncio

from . import collector, reports


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app", description="CSE Live collector + server")
    parser.add_argument("--collector-only", action="store_true", help="run only the collector, no web server")
    parser.add_argument("--server-only", action="store_true", help="run only the web server, no collector")
    parser.add_argument(
        "--once", action="store_true", help="run a single collector poll cycle then exit (implies --collector-only)"
    )
    parser.add_argument("--report", action="store_true", help="print a DB summary and exit")
    parser.add_argument("--host", default="127.0.0.1", help="server bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="server port (default 8000)")
    args = parser.parse_args()

    if args.report:
        reports.print_report()
        return

    if args.collector_only and args.server_only:
        parser.error("--collector-only and --server-only are mutually exclusive")

    try:
        if args.once:
            asyncio.run(collector.run(once=True))
        elif args.collector_only:
            asyncio.run(collector.run())
        elif args.server_only:
            asyncio.run(_serve_only(args.host, args.port))
        else:
            asyncio.run(_run_both(args.host, args.port))
    except KeyboardInterrupt:
        pass


async def _serve_only(host: str, port: int) -> None:
    import uvicorn

    from .config import load_config
    from .server import create_app

    app = create_app(load_config())
    uv_config = uvicorn.Config(app, host=host, port=port, log_level="info")
    await uvicorn.Server(uv_config).serve()


async def _run_both(host: str, port: int) -> None:
    """python -m app with no flags: one process runs the collector and the
    web server together, per CLAUDE.md ("python -m app must start everything")."""
    import uvicorn

    from .config import load_config
    from .server import create_app

    app = create_app(load_config())
    uv_config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(uv_config)

    collector_task = asyncio.create_task(collector.run(), name="collector")
    server_task = asyncio.create_task(server.serve(), name="server")

    done, pending = await asyncio.wait({collector_task, server_task}, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    for task in done:
        exc = task.exception()
        if exc is not None:
            raise exc


if __name__ == "__main__":
    main()
