"""Common functionalities for testing, shared between tests and other test utility modules."""

from collections import OrderedDict
from typing import Any
from urllib.parse import urljoin

import yaml
from pydantic import AnyUrl, FilePath
from urllib3 import BaseHTTPResponse, request

from trolldb.config.config import AppConfig


def make_test_app_config(subscriber_address: FilePath | None = None) -> dict:
    """Makes the app configuration when used in testing.

    Args:
        subscriber_address:
            The address of the subscriber if it is of type ``FilePath``. Otherwise, if it is ``None`` the ``subscriber``
            config will be an empty dictionary.

    Returns:
        A dictionary which resembles an object of type :obj:`AppConfig`.
    """
    app_config = dict(
        api_server=dict(
            url="http://localhost:8080"
        ),
        database=dict(
            main_database_name="mock_database",
            main_collection_name="mock_collection",
            url="mongodb://localhost:28017",
            timeout=1000
        ),
        subscriber=dict(
            nameserver=False,
            addresses=[f"ipc://{subscriber_address}/in.ipc"] if subscriber_address is not None else [""],
            port=3000
        )
    )

    return app_config


test_app_config = AppConfig(**make_test_app_config())
"""The app configs for testing purposes assuming an empty configuration for the subscriber."""


def create_config_file(config_path: FilePath) -> FilePath:
    """Creates a config file for tests."""
    config_file = config_path / "config.yaml"
    with open(config_file, "w") as f:
        yaml.safe_dump(make_test_app_config(config_path), f)
    return config_file


def http_get(route: str = "", root: AnyUrl = test_app_config.api_server.url) -> BaseHTTPResponse:
    """An auxiliary function to make a GET request using :func:`urllib.request`.

    Args:
        route:
            The desired route (excluding the root URL) which can include a query string as well.
        root (Optional, default :obj:`test_app_config.api_server.url`):
            The root to which the given route will be added to make the complete URL.

    Returns:
        The response from the GET request.
    """
    return request("GET", urljoin(root.unicode_string(), route))


def assert_equal(test: Any, expected: Any, ordered: bool = False, silent: bool = False) -> bool:
    """An auxiliary function to assert the equality of two objects using the ``==`` operator.

    Examples:
      - If ``ordered=False`` and the input is a list or a tuple, it will be first converted to a set
        so that the order of items therein does not affect the assertion outcome.
      - If ``ordered=True`` and the input is a dictionary, it will be first converted to an ``OrderedDict``.

    Note:
        The rationale behind choosing ``ordered=False`` as the default behaviour is that this function is often used
        in combination with API calls and/or querying the database. In such cases, the order of items which are returned
        often does not matter. In addition, if the order really matters, one might as well simply use the built-in
        ``assert`` statement.

    Note:
        Dictionaries by default are unordered objects.

    Warning:
        For the purpose of this function, the concept of ordered vs unordered only applies to lists, tuples, and
        dictionaries. An object of any other type is assumed as-is, i.e. the default behaviour of Python applies.
        For example, conceptually, two strings can be converted to two sets of characters and then be compared with
        each other. However, this is not what we do for strings.

    Args:
        test:
            The object to be tested.
        expected:
            The object to test against.
        ordered (Optional, default ``False``):
            A flag to determine whether the order of items matters in case of a list, a tuple, or a dictionary.
        silent (Optional, default ``False``):
            A flag to determine whether the assertion should be silent, i.e. simply return the result as a boolean or
            it should raise an ``AssertionError``.

    Raises:
        AssertionError:
            If the ``test`` and ``expected`` are not equal and ``silent=False``.
    """

    def _ordered(obj: Any) -> Any:
        """An auxiliary function to convert an object to ordered depending on its type and the ``ordered`` flag."""
        match obj:
            case list() | tuple():
                return set(obj) if not ordered else obj
            case dict():
                return OrderedDict(obj) if ordered else obj
            case _:
                return obj

    if _ordered(test) == _ordered(expected):
        return True

    if silent:
        return False

    raise AssertionError(f"{test} and {expected} are not equal. The flag `ordered` is set to `{ordered}`.")


def compare_by_operator_name(operator: str, left: Any, right: Any) -> Any:
    """Compares two operands given the binary operator name in a string format.

    Args:
        operator:
            Any of ``["$gte", "$gt", "$lte", "$lt", "$eq"]``.
            These match the MongoDB comparison operators described
            `here <https://www.mongodb.com/docs/v6.2/reference/operator/aggregation/#comparison-expression-operators>`_.
        left:
            The left operand
        right:
            The right operand

    Returns:
        The result of the comparison operation, i.e. ``<left> <operator> <right>``.

    Raises:
         ValueError:
            If the operator name is not valid.
    """
    match operator:
        case "$gte":
            return left >= right
        case "$gt":
            return left > right
        case "$lte":
            return left <= right
        case "$lt":
            return left < right
        case "$eq":
            return left == right
        case _:
            raise ValueError(f"Unknown operator: {operator}")


def collections_exists(test_collection_names: list[str], expected_collection_name: list[str]) -> bool:
    """Checks if the test and expected list of collection names match."""
    return assert_equal(test_collection_names, expected_collection_name, silent=True)


def document_ids_are_correct(test_ids: list[str], expected_ids: list[str]) -> bool:
    """Checks if the test (retrieved from the API) and expected list of (document) ids match."""
    return assert_equal(test_ids, expected_ids, silent=True)
