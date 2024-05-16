"""The module which defines the base functionalities for errors that will be raised when using the package or the API.

This module only includes the generic utilities using which each module should define its own error responses
specifically. See :obj:`trolldb.database.errors` as an example on how to achieve this.
"""

from collections import OrderedDict
from sys import exit
from typing import Literal, Self

from fastapi import Response
from fastapi.responses import PlainTextResponse
from loguru import logger

StatusCode = int
"""An alias for the built-in ``int`` type, which is used for HTTP status codes."""


def _listify(item: str | list[str]) -> list[str]:
    """Encloses the given (single) string in a list or returns the same input as-is in case of a list of strings.

    Args:
        item:
            The item that needs to be converted to a list.

    Returns:
          If the input is itself a list of strings the same list is returned as-is, otherwise, the given input
          string is enclosed in ``[]`` and returned.

    Example:
        .. code-block:: python

            # The following evaluate to ``True``
            __listify("test") == ["test"]
            __listify(["a", "b"]) = ["a", "b"]
            __listify([]) == []
    """
    return item if isinstance(item, list) else [item]


def _stringify(item: str | list[str], delimiter: str) -> str:
    """Makes a single string out of the item(s) by delimiting them with ``delimiter``.

    Args:
        item:
            A string or list of strings to be delimited.
        delimiter:
            A string as delimiter.

    Returns:
        The same input string, or in case of a list of items, a single string delimited by ``delimiter``.
    """
    return delimiter.join(_listify(item))


class ResponseError(Exception):
    """The base class for all error responses.

    This is a derivative of the ``Exception`` class and therefore can be used directly in ``raise`` statements.

    Attributes:
        __dict (:obj:`OrderedDict[StatusCode, str]`):
            An ordered dictionary in which the keys are (HTTP) status codes and the values are the corresponding
            messages.
    """

    descriptor_delimiter: str = " |OR| "
    """A delimiter to divide the message part of several error responses which have been combined into a single one.

    This will be shown in textual format for the response descriptors of the Fast API routes.

    Example:
        .. code-block:: python

            error_a = ResponseError({400: "Bad Request"})
            error_b = ResponseError({404: "Not Found"})
            errors = error_a | error_b

            # When used in a FastAPI response descriptor, the following string will be generated for ``errors``
            "Bad Request |OR| Not Found"
    """

    DefaultResponseClass: Response = PlainTextResponse
    """The default type of the response which will be returned when an error occurs.

    This must be a valid member (class) of ``fastapi.responses``.
    """

    def __init__(self, args_dict: OrderedDict[StatusCode, str | list[str]] | dict) -> None:
        """Initializes the error object given a dictionary of error (HTTP) codes (keys) and messages (values).

        Note:
            The order of items will be preserved as we use an ordered dictionary to store the items internally.

        Example:
            .. code-block:: python

                # The following are all valid error objects
                error_a = ResponseError({400: "Bad Request"})
                error_b = ResponseError({404: "Not Found"})
                errors = error_a | error_b
                errors_a_or_b = ResponseError({400: "Bad Request", 404: "Not Found"})
        """
        self.__dict: OrderedDict = OrderedDict(args_dict)
        self.extra_information: dict | None = None

    def __or__(self, other: Self):
        """Implements the bitwise `or` (``|``) which combines the error objects into a single error response.

        Args:
            other:
                Another error response of the same base type to combine with.

        Returns:
            A new error response which includes the combined error response. In case of different (HTTP) status codes,
            the returned response includes the ``{<status-code>: <message>}`` pairs for both ``self`` and the ``other``.
            In case of the same status codes, the messages will be stored in a list.

        Example:
            .. code-block:: python

                error_a = ResponseError({400: "Bad Request"})
                error_b = ResponseError({404: "Not Found"})
                error_c = ResponseError({400: "Still Bad Request"})

                errors_combined = error_a | error_b | error_c

                # which is equivalent to the following
                errors_combined_literal = ResponseError({
                    400: ["Bad Request", "Still Bad Request"],
                    404: "Not Found"
                }
        """
        buff = OrderedDict(self.__dict)
        for key, msg in other.__dict.items():
            self_msg = buff.get(key, None)
            buff[key] = _listify(self_msg) if self_msg else []
            buff[key].extend(_listify(msg))
        return ResponseError(buff)

    def __retrieve_one_from_some(
            self,
            status_code: StatusCode | None = None) -> (StatusCode, str):
        """Retrieves a single tuple of ``(<status-code>, <message>)`` from the internal dictionary ``self.__dict``.

        Args:
            status_code (Optional, default: ``None``):
                The status code to retrieve from the internal dictionary. In case of ``None``, the internal dictionary
                must include only a single entry which will be returned.

        Returns:
            The tuple of ``(<status-code>, <message>)``.

        Raises:
            ValueError:
                In case of ambiguity, i.e. there are multiple items in the internal dictionary and the
                ``status_code`` is ``None``.

            KeyError:
                When the given ``status_code`` cannot be found.
        """
        match status_code, len(self.__dict):
            # Ambiguity, several items in the dictionary but the status code has not been given
            case None, n if n > 1:
                raise ValueError("In case of multiple response status codes, the status code must be specified.")

            # The status code has been specified
            case StatusCode(), n if n >= 1:
                if status_code in self.__dict.keys():
                    return status_code, self.__dict[status_code]
                raise KeyError(f"Status code {status_code} cannot be found.")

            # The status code has not been given and there is only a single item in the dictionary
            case _, 1:
                return [(k, v) for k, v in self.__dict.items()][0]

            # The internal dictionary is empty and the status code is None.
            case _:
                return 500, "Generic Response Error"

    def get_error_details(
            self,
            extra_information: dict | None = None,
            status_code: int | None = None) -> (StatusCode, str):
        """Gets the details of the error response.

        Args:
            extra_information (Optional, default ``None``):
                Some more information to be added in the message string.
            status_code (Optional, default ``None``):
                The status to retrieve. This is useful when there are several error items in the internal dictionary.
                In case of ``None``, the internal dictionary must include a single entry, otherwise an error is raised.

        Returns:
            A tuple, in which the first element is the status code and the second element is a single string message.
        """
        status_code, msg = self.__retrieve_one_from_some(status_code)
        return status_code, msg + (f" :=> {extra_information}" if extra_information else "")

    def log_as_warning(
            self,
            extra_information: dict | None = None,
            status_code: int | None = None):
        """Same as :func:`~ResponseError.get_error_details` but logs the error as a warning and returns ``None``."""
        msg, _ = self.get_error_details(extra_information, status_code)
        logger.warning(msg)

    def sys_exit_log(
            self,
            exit_code: int = -1,
            extra_information: dict | None = None,
            status_code: int | None = None) -> None:
        """Same as :func:`~ResponseError.get_error_details` but logs the error and calls the ``sys.exit``.

        This is supposed to be done in case of non-recoverable errors, e.g. database issues.

        The arguments are the same as :func:`~ResponseError.get_error_details` with the addition of ``exit_code``
        which is optional and is set to ``-1`` by default.

        Returns:
            Does not return anything, but logs the error and exits the program.
        """
        msg, _ = self.get_error_details(extra_information, status_code)
        logger.error(msg)
        exit(exit_code)

    @property
    def fastapi_descriptor(self) -> dict[StatusCode, dict[Literal["description"], str]]:
        """Gets the FastAPI descriptor (dictionary) of the error items stored in :obj:`~ResponseError.__dict`.

        Example:
             .. code-block:: python

            error_a = ResponseError({400: "Bad Request"})
            error_b = ResponseError({404: "Not Found"})
            error_c = ResponseError({400: "Still Bad Request"})

            errors_combined = error_a | error_b | error_c
            errors_combined.fastapi_descriptor == {
                400: {"description": "Bad Request |OR| Still Bad Request"},
                404: {"description": "Not Found"}
            }
        """
        return {
            status: {Literal["description"]: _stringify(msg, self.descriptor_delimiter)}
            for status, msg in self.__dict.items()
        }


class ResponsesErrorGroup:
    """A class which groups related errors.

    This provides a base class from which actual error groups are derived. The attributes of this class are all static.

    See :obj:`trolldb.database.errors` as an example on how to achieve this.
    """

    @classmethod
    def fields(cls) -> dict[str, ResponseError]:
        """Retrieves a dictionary of all errors which are members of the class."""
        return {k: v for k, v in cls.__dict__.items() if isinstance(v, ResponseError)}

    @classmethod
    def union(cls) -> ResponseError:
        """Gets the union of all member errors in the group.

        This utilizes the bitwise `or` ``|`` functionality of :obj:`ResponseError`.
        """
        buff = None
        for v in cls.fields().values():
            if buff is None:
                buff = v
            else:
                buff |= v
        return buff
