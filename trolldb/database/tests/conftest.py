"""Pytest config for database tests.

This module provides fixtures for running a Mongo DB instance in test mode and filling the database with test data.
"""

import pytest
import pytest_asyncio

from trolldb.database.mongodb import mongodb_context
from trolldb.test_utils.common import test_app_config
from trolldb.test_utils.mongodb_database import TestDatabase
from trolldb.test_utils.mongodb_instance import mongodb_instance_server_process_context


@pytest.fixture(scope="session")
def _run_mongodb_server_instance():
    """Runs the MongoDB instance in test mode using a context manager.

    It is run once for all tests in this test suite.
    """
    with mongodb_instance_server_process_context():
        yield


@pytest_asyncio.fixture()
async def mongodb_fixture(_run_mongodb_server_instance):
    """Fills the database with test data and then runs the mongodb client using a context manager."""
    TestDatabase.prepare()
    async with mongodb_context(test_app_config.database):
        yield
