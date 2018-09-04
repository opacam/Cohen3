# -*- test-case-name: axiom.test.test_pysqlite2 -*-

"""
PySQLite2 Connection and Cursor wrappers.

These provide a uniform interface on top of PySQLite2 for Axiom, particularly
including error handling behavior and exception types.
"""

import sys
import time

try:
    # Prefer the third-party module, as it is easier to update, and so may
    # be newer or otherwise better.
    from pysqlite2 import dbapi2
except ImportError:
    # But fall back to the stdlib module if we're on Python 2.6 or newer,
    # because it should work too.  Don't do this for Python 2.5 because
    # there are critical, data-destroying bugs in that version.
    if sys.version_info >= (2, 6):
        import sqlite3 as dbapi2
    else:
        raise

from twisted.python import log

from coherence.extern.twisted.axiom import errors, iaxiom


class Connection(object):
    """
    Wrapper for an SQLite3 C{Connection} object.

    @type closed: L{bool}
    @ivar closed: Has this cursor been closed?
    """

    def __init__(self, connection, timeout=None):
        self._connection = connection
        self._timeout = timeout
        self.closed = False

    def fromDatabaseName(cls, dbFilename, timeout=None, isolationLevel=None):
        return cls(dbapi2.connect(dbFilename, timeout=0,
                                  isolation_level=isolationLevel))

    fromDatabaseName = classmethod(fromDatabaseName)

    def cursor(self):
        return Cursor(self, self._timeout)

    def identifySQLError(self, sql, args, e):
        """
        Identify an appropriate SQL error object for the given message for the
        supported versions of sqlite.

        @return: an SQLError
        """
        message = e.args[0]
        if message.startswith("table") and message.endswith("already exists"):
            return errors.TableAlreadyExists(sql, args, e)
        return errors.SQLError(sql, args, e)

    def close(self):
        """
        Close the underlying connection.
        """
        self._connection.close()
        self.closed = True


class Cursor(object):
    """
    Wrapper for an SQLite3 C{Cursor} object.

    @type closed: L{bool}
    @ivar closed: Has this cursor been closed?
    """

    def __init__(self, connection, timeout):
        self._connection = connection
        self._cursor = connection._connection.cursor()
        self.timeout = timeout
        self.closed = False

    def __iter__(self):
        return iter(self._cursor)

    def time(self):
        """
        Return the current wallclock time as a float representing seconds
        from an fixed but arbitrary point.
        """
        return time.time()

    def sleep(self, seconds):
        """
        Block for the given number of seconds.

        @type seconds: C{float}
        """
        time.sleep(seconds)

    def execute(self, sql, args=()):
        try:
            try:
                blockedTime = 0.0
                t = self.time()
                try:
                    # SQLite3 uses something like exponential backoff when
                    # trying to acquire a database lock.  This means that even
                    # for very long timeouts, it may only attempt to acquire
                    # the lock a handful of times.  Another process which is
                    # executing frequent, short-lived transactions may acquire
                    # and release the lock many times between any two attempts
                    # by this one to acquire it.  If this process gets unlucky
                    # just a few times, this execute may fail to acquire the
                    # lock within the specified timeout.

                    # Since attempting to acquire the lock is a fairly cheap
                    # operation, we take another route.  SQLite3 is always told
                    # to use a timeout of 0 - ie, acquire it on the first try
                    # or fail instantly.  We will keep doing this, ten times a
                    # second, until the actual timeout expires.

                    # What would be really fantastic is a notification
                    # mechanism for information about the state of the lock
                    # changing.  Of course this clearly insane, no one has ever
                    # managed to invent a tool for communicating one bit of
                    # information between multiple processes.
                    while 1:
                        try:
                            return self._cursor.execute(sql, args)
                        except dbapi2.OperationalError as e:
                            if e.args[0] == 'database is locked':
                                now = self.time()
                                if self.timeout is not None:
                                    if (now - t) > self.timeout:
                                        raise errors.TimeoutError(sql,
                                                                  self.timeout,
                                                                  e)
                                self.sleep(0.1)
                                blockedTime = self.time() - t
                            else:
                                raise
                finally:
                    txntime = self.time() - t
                    if txntime - blockedTime > 2.0:
                        log.msg('Extremely long execute: %s' % (
                        txntime - blockedTime,))
                        log.msg(sql)
                        # import traceback; traceback.print_stack()
                    log.msg(interface=iaxiom.IStatEvent,
                            stat_cursor_execute_time=txntime,
                            stat_cursor_blocked_time=blockedTime)
            except dbapi2.OperationalError as e:
                if e.args[0] == 'database schema has changed':
                    return self._cursor.execute(sql, args)
                raise
        except (dbapi2.ProgrammingError,
                dbapi2.InterfaceError,
                dbapi2.OperationalError) as e:
            raise self._connection.identifySQLError(sql, args, e)

    def lastRowID(self):
        return self._cursor.lastrowid

    def close(self):
        """
        Close the underlying cursor.
        """
        self._cursor.close()
        self.closed = True


# Export some names from the underlying module.
sqlite_version_info = dbapi2.sqlite_version_info
OperationalError = dbapi2.OperationalError

__all__ = [
    'OperationalError',
    'Connection',
    'sqlite_version_info',
]
