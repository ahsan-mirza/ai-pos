import sys

import uvicorn

from app.core.config import get_settings


def serve() -> None:
    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.api_host, port=settings.api_port)


def main() -> None:
    if sys.platform == "win32":
        # uvicorn's reloader restarts its worker with CTRL_C_EVENT, which Windows delivers to every process on the
        # console, so pnpm and the node wrapper exit on the first reload. watchfiles terminates only the worker.
        from watchfiles import PythonFilter, run_process

        run_process("app", target=serve, watch_filter=PythonFilter())
        return
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
        reload_dirs=["app"],
    )


if __name__ == "__main__":
    main()
