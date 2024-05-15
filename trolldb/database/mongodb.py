"""
The module which handles database CRUD operations for MongoDB. It is based on
`PyMongo <https://github.com/mongodb/mongo-python-driver>`_ and `motor <https://github.com/mongodb/motor>`_.
"""

import errno
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Coroutine, TypeVar

from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorDatabase,
    AsyncIOMotorCollection,
    AsyncIOMotorCommandCursor,
    AsyncIOMotorCursor
)
from pydantic import validate_call, BaseModel
from pymongo.collection import _DocumentType
from pymongo.errors import (
    ConnectionFailure,
    ServerSelectionTimeoutError)

from trolldb.config.config import DatabaseConfig
from trolldb.database.errors import Collections, Databases, Client
from trolldb.errors.errors import ResponseError

T = TypeVar("T")
CoroutineLike = Coroutine[Any, Any, T]
CoroutineDocument = CoroutineLike[_DocumentType | None]
CoroutineStrList = CoroutineLike[list[str]]


class DatabaseName(BaseModel):
    name: str | None


class CollectionName(BaseModel):
    name: str | None


async def get_id(doc: CoroutineDocument) -> str:
    """
    Retrieves the ID of a document as a simple flat string.

    Note:
        The rationale behind this method is as follows. In MongoDB, each document has a unique ID which is of type
        :class:`~bson.objectid.ObjectId`. This is not suitable for purposes when a simple string is needed, hence
        the need for this method.

    Args:
        doc:
            A MongoDB document in the coroutine form. This could be e.g. the result of applying the standard
            ``find_one`` method from MongoDB on a collection given a ``filter``.

    Returns:
        The ID of a document as a simple string. For example, when applied on a document with
        ``_id: ObjectId('000000000000000000000000')``, the method returns ``'000000000000000000000000'``.
    """
    return str((await doc)["_id"])


async def get_ids(docs: AsyncIOMotorCommandCursor | AsyncIOMotorCursor) -> list[str]:
    """
    Similar to :func:`~MongoDB.get_id` but for a list of documents.

    Args:
        docs:
            A list of MongoDB documents as :obj:`~AsyncIOMotorCommandCursor` or :obj:`~AsyncIOMotorCursor`.
            This could be e.g. the result of applying the standard ``aggregate`` method from MongoDB on a
            collection given a ``pipeline``.

    Returns:
        The list of all IDs, each as a simple string.
    """
    return [str(doc["_id"]) async for doc in docs]


class MongoDB:
    """
    A wrapper class around the `motor async driver <https://www.mongodb.com/docs/drivers/motor/>`_ for Mongo DB with
    convenience methods tailored to our specific needs. As such, the :func:`~MongoDB.initialize()`` method returns a
    coroutine which needs to be awaited.

    Note:
        This class is not meant to be instantiated! That's why all the methods in this class are decorated with
        ``@classmethods``. This choice has been made to guarantee optimal performance, i.e. for each running process
        there must be only a single motor client to handle all database operations. Having different clients which are
        constantly opened/closed degrades the performance. The expected usage is that we open a client in the beginning
        of the program and keep it open until the program finishes. It is okay to reopen/close the client for testing
        purposes when isolation is needed.

    Note:
        The main difference between this wrapper class and the original motor driver class is that we attempt to access
        the database and collections during the initialization to see if we succeed or fail. This is contrary to the
        behaviour of the motor driver which simply creates a client object and does not attempt to access the database
        until some time later when an actual operation is performed on the database. This behaviour is not desired for
        us, we would like to fail early!
    """

    __client: AsyncIOMotorClient | None = None
    __database_config: DatabaseConfig | None = None
    __main_collection: AsyncIOMotorCollection = None
    __main_database: AsyncIOMotorDatabase = None

    default_database_names = ["admin", "config", "local"]
    """
    MongoDB creates these databases by default for self usage.
    """

    @classmethod
    async def initialize(cls, database_config: DatabaseConfig):
        """
        Initializes the motor client. Note that this method has to be awaited!

        Args:
            database_config:
                 A named tuple which includes the database configurations.

        Raises ``SystemExit(errno.EIO)``:

            - If connection is not established (``ConnectionFailure``)

            - If the attempt times out (``ServerSelectionTimeoutError``)

            - If one attempts reinitializing the class with new (different) database configurations without calling
            :func:`~close()` first.

            - If the state is not consistent, i.e. the client is closed or ``None`` but the internal database
            configurations still exist and are different from the new ones which have been just provided.


        Raises ``SystemExit(errno.ENODATA)``:
            If either ``database_config.main_database`` or ``database_config.main_collection`` does not exist.

        Returns:
            On success ``None``.
        """

        if cls.__database_config:
            if database_config == cls.__database_config:
                if cls.__client:
                    return Client.AlreadyOpenError.log_as_warning()
                Client.InconsistencyError.sys_exit_log(errno.EIO)
            else:
                Client.ReinitializeConfigError.sys_exit_log(errno.EIO)

        # This only makes the reference and does not establish an actual connection until the first attempt is made
        # to access the database.
        cls.__client = AsyncIOMotorClient(
            database_config.url.unicode_string(),
            serverSelectionTimeoutMS=database_config.timeout)

        __database_names = []
        try:
            # Here we attempt to access the database
            __database_names = await cls.__client.list_database_names()
        except (ConnectionFailure, ServerSelectionTimeoutError):
            Client.ConnectionError.sys_exit_log(
                errno.EIO, {"url": database_config.url.unicode_string()}
            )

        err_extra_information = {"database_name": database_config.main_database_name}

        if database_config.main_database_name not in __database_names:
            Databases.NotFoundError.sys_exit_log(errno.ENODATA, err_extra_information)
        cls.__main_database = cls.__client.get_database(database_config.main_database_name)

        err_extra_information |= {"collection_name": database_config.main_collection_name}

        if database_config.main_collection_name not in await cls.__main_database.list_collection_names():
            Collections.NotFoundError.sys_exit_log(errno.ENODATA, err_extra_information)

        cls.__main_collection = cls.__main_database.get_collection(database_config.main_collection_name)

    @classmethod
    def close(cls) -> None:
        """
        Closes the motor client.
        """
        if cls.__client:
            cls.__database_config = None
            return cls.__client.close()
        Client.CloseNotAllowedError.sys_exit_log(errno.EIO)

    @classmethod
    def list_database_names(cls) -> CoroutineStrList:
        return cls.__client.list_database_names()

    @classmethod
    def main_collection(cls) -> AsyncIOMotorCollection:
        """
        A convenience method to get the main collection.

        Returns:
            The main collection which resides inside the main database.
            Equivalent to ``MongoDB.client()[<main_database_name>][<main_collection_name>]``.
        """
        return cls.__main_collection

    @classmethod
    def main_database(cls) -> AsyncIOMotorDatabase:
        """
        A convenience method to get the main database.

        Returns:
            The main database which includes the main collection, which in turn includes the desired documents.
            Equivalent to ``MongoDB.client()[<main_database_name>]``.
        """
        return cls.__main_database

    @classmethod
    async def get_collection(
            cls,
            database_name: str,
            collection_name: str) -> AsyncIOMotorCollection | ResponseError:
        """
        Gets the collection object given its name and the database name in which it resides.

        Args:
            database_name:
                The name of the parent database which includes the collection.
            collection_name:
                The name of the collection which resides inside the parent database labelled by ``database_name``.

        Raises:
            ``ValidationError``:
                If input args are invalid according to the pydantic.

             ``KeyError``:
                If the database name exists, but it does not include any collection with the given name.

            ``TypeError``:
                If only one of the database or collection names are ``None``.

            ``_``:
                This method relies on :func:`get_database` to check for the existence of the database which can raise
                exceptions. Check its documentation for more information.

        Returns:
            The database object. In case of ``None`` for both the database name and collection name, the main collection
            will be returned.
        """

        database_name = DatabaseName(name=database_name).name
        collection_name = CollectionName(name=collection_name).name

        match database_name, collection_name:
            case None, None:
                return cls.main_collection()

            case str(), str():
                db = await cls.get_database(database_name)
                if collection_name in await db.list_collection_names():
                    return db[collection_name]
                raise Collections.NotFoundError
            case _:
                raise Collections.WrongTypeError

    @classmethod
    async def get_database(cls, database_name: str) -> AsyncIOMotorDatabase | ResponseError:
        """
        Gets the database object given its name.

        Args:
            database_name:
                The name of the database to retrieve.
        Raises:
             ``KeyError``:
                If the database name does not exist in the list of database names.

        Returns:
            The database object.
        """
        database_name = DatabaseName(name=database_name).name

        match database_name:
            case None:
                return cls.main_database()
            case _ if database_name in await cls.list_database_names():
                return cls.__client[database_name]
            case _:
                raise Databases.NotFoundError


@asynccontextmanager
@validate_call
async def mongodb_context(database_config: DatabaseConfig) -> AsyncGenerator:
    """
    An asynchronous context manager to connect to the MongoDB client.
    It can be either used in production or in testing environments.

    Args:
        database_config:
            The configuration of the database.
    """
    try:
        await MongoDB.initialize(database_config)
        yield
    finally:
        MongoDB.close()
