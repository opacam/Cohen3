# -*- test-case-name: axiom.test -*-

from twisted.cred.error import UnauthorizedLogin


class TimeoutError(Exception):
    """
    A low-level SQL operation timed out.

    @ivar statement: The SQL statement which timed out.
    @ivar timeout: The timeout, in seconds, which was exceeded.
    @ivar underlying: The backend exception which signaled this, or None.
    """
    def __init__(self, statement, timeout, underlying):
        Exception.__init__(self, statement, timeout, underlying)
        self.statement = statement
        self.timeout = timeout
        self.underlying = underlying


class BadCredentials(UnauthorizedLogin):
    pass


class NoSuchUser(UnauthorizedLogin):
    pass


class MissingDomainPart(NoSuchUser):
    """
    Raised when a login is attempted with a username which consists of only
    a local part.  For example, "testuser" instead of "testuser@example.com".
    """


class DuplicateUser(Exception):
    pass


class CannotOpenStore(RuntimeError):
    """
    There is a problem such that the store cannot be opened.
    """


class NoUpgradePathAvailable(CannotOpenStore):
    """
    No upgrade path is available, so the store cannot be opened.
    """


class NoCrossStoreReferences(AttributeError):
    """
    References are not allowed between items within different Stores.
    """


class SQLError(RuntimeError):
    """
    Axiom internally generated some bad SQL.
    """
    def __init__(self, sql, args, underlying):
        RuntimeError.__init__(self, sql, args, underlying)
        self.sql, self.args, self.underlying = self.args

    def __str__(self):
        return "<SQLError: %r(%r) caused %s: %s>" % (
            self.sql, self.args,
            self.underlying.__class__, self.underlying)


class TableAlreadyExists(SQLError):
    """
    Axiom internally created a table at the same time as another database.
    (User code should not need to catch this exception.)
    """


class UnknownItemType(Exception):
    """
    Can't load an item: it's of a type that I don't see anywhere in Python.
    """


class SQLWarning(Warning):
    """
    Axiom internally generated some CREATE TABLE SQL that ... probably wasn't bad
    """


class TableCreationConcurrencyError(RuntimeError):
    """
    Woah, this is really bad.  If you can get this please tell us how.
    """


class DuplicateUniqueItem(KeyError):
    """
    Found 2 or more of an item which is supposed to be unique.
    """


class ItemNotFound(KeyError):
    """
    Did not find even 1 of an item which was supposed to exist.
    """


class ItemClassesOnly(TypeError):
    """
    An object was passed to a method that wasn't a subclass of Item.
    """


class ChangeRejected(Exception):
    """
    Raised when an attempt is made to change the database at a time when
    database changes are disallowed for reasons of consistency.

    This is raised when an application-level callback (for example, committed)
    attempts to change database state.
    """


class DependencyError(Exception):
    """
    Raised when an item can't be installed or uninstalled.
    """


class DeletionDisallowed(ValueError):
    """
    Raised when an attempt is made to delete an item that is referred to by
    reference attributes with whenDeleted == DISALLOW.
    """


class DataIntegrityError(RuntimeError):
    """
    Data integrity seems to have been lost.
    """


class BrokenReference(DataIntegrityError):
    """
    A reference to a nonexistent item was detected when this should be
    impossible.
    """


class UpgraderRecursion(RuntimeError):
    """
    Upgraders are not allowed to recurse.
    """


class ItemUpgradeError(RuntimeError):
    """
    Attempting to upgrade an Item resulted in an error.

    @ivar originalFailure: The failure that caused the item upgrade to fail
    @ivar storeID: Store ID of the item that failed to upgrade
    @ivar oldType: The type of the item being upgraded
    @ivar newType: The type the item should've been upgraded to
    """
    def __init__(self, originalFailure, storeID, oldType, newType):
        RuntimeError.__init__(self, originalFailure, storeID, oldType, newType)
        self.originalFailure = originalFailure
        self.storeID = storeID
        self.oldType = oldType
        self.newType = newType


class UnsatisfiedRequirement(AttributeError):
    """
    A requirement described by a L{axiom.dependency.requiresFromSite} was not
    satisfied by the database, and could not be satisfied automatically at
    runtime by a default factory.
    """
