"""The module which includes the main functionalities of the API package.

This is the main module which is supposed to be imported by the users of the package.

Note:
    The following applies to the :obj:`api` package and all its subpackages/modules.

    To avoid redundant documentation and inconsistencies, only non-FastAPI components are documented via the docstrings.
    For the documentation related to the FastAPI components, check out the auto-generated documentation by FastAPI.
    Assuming that the API server is running on `<http://localhost:8000>`_ (example) the auto-generated documentation can
    be accessed via either `<http://localhost:8000/redoc>`_ or  `<http://localhost:8000/docs>`_.

    Read more at `FastAPI automatics docs <https://fastapi.tiangolo.com/features/#automatic-docs>`_.
"""

import asyncio
import sys
import time
from contextlib import contextmanager
from multiprocessing import Process
from typing import Any, Generator, NoReturn

import uvicorn
from loguru import logger

from trolldb.api.fastapi_app import fastapi_app
from trolldb.config.config import AppConfig, Timeout
from trolldb.database.mongodb import mongodb_context


@logger.catch(onerror=lambda _: sys.exit(1))
def run_server(app_config: AppConfig) -> None:
    """Runs the API server with connection to the database.

    It runs the imported ``fastapi_app`` using `uvicorn <https://www.uvicorn.org/>`_ which is ASGI
    (Asynchronous Server Gateway Interface) compliant. This function runs the event loop using
    `asyncio <https://docs.python.org/3/library/asyncio.html>`_ and does not yield!

    Args:
        app_config:
            The configuration of the API server and the database.

    Example:
        .. code-block:: python

            from trolldb.api.api import run_server
            from trolldb.config.config import parse_config

            if __name__ == "__main__":
                run_server(parse_config("config.yaml"))
    """
    logger.info("Attempt to run the API server ...")

    async def _serve() -> NoReturn:
        """An auxiliary coroutine to be used in the asynchronous execution of the FastAPI application."""
        async with mongodb_context(app_config.database):
            logger.info("Attempt to start the uvicorn server ...")
            await uvicorn.Server(
                config=uvicorn.Config(
                    host=app_config.api_server.url.host,
                    port=app_config.api_server.url.port,
                    app=fastapi_app
                )
            ).serve()

    logger.info("Attempt to run the asyncio loop for the API server ...")
    asyncio.run(_serve())


@contextmanager
def api_server_process_context(config: AppConfig, startup_time: Timeout = 2) -> Generator[Process, Any, None]:
    """A synchronous context manager to run the API server in a separate process (non-blocking).

    It uses the `multiprocessing <https://docs.python.org/3/library/multiprocessing.html>`_ package. The main use case
    is envisaged to be in `TESTING` environments.

    Args:
        config:
            Same as ``config`` argument for :func:`run_server`.

        startup_time:
            The overall time in seconds that is expected for the server and the database connections to be established
            before actual requests can be sent to the server. For testing purposes ensure that this is sufficiently
            large so that the tests will not time out.
    """
    logger.info("Attempt to run the API server process in a context manager ...")
    process = Process(target=run_server, args=(config,))
    try:
        process.start()
        time.sleep(startup_time)
        yield process
    finally:
        logger.info("Attempt to terminate the API server process in the context manager ...")
        process.terminate()
        process.join()
        logger.info("The API server process has terminated successfully.")
