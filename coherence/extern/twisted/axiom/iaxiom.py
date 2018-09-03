
from zope.interface import Interface, Attribute


class IStatEvent(Interface):
    """
    Marker for a log message that is useful as a statistic.

    Log messages with 'interface' set to this class will be made available to
    external observers.  This is useful for tracking the rate of events such as
    page views.
    """


class IAtomicFile(Interface):
    def __init__(tempname, destdir):
        """Create a new atomic file.

        The file will exist temporarily at C{tempname} and be relocated to
        C{destdir} when it is closed.
        """

    def tell():
        """Return the current offset into the file, in bytes.
        """

    def write(bytes):
        """Write some bytes to this file.
        """

    def close(callback):
        """Close this file.  Move it to its final location.

        @param callback: A no-argument callable which will be invoked
        when this file is ready to be moved to its final location.  It
        must return the segment of the path relative to per-user
        storage of the owner of this file.  Alternatively, a string
        with semantics the same as those previously described for the
        return value of the callable.

        @rtype: C{axiom.store.StoreRelativePath}
        @return: A Deferred which fires with the full path to the file
        when it has been closed, or which fails if there is some error
        closing the file.
        """

    def abort():
        """Give up on this file.  Discard its contents.
        """


class IAxiomaticCommand(Interface):
    """
    Subcommand for 'axiomatic' and 'tell-axiom' command line programs.

    Should subclass twisted.python.usage.Options and provide a command to run.

    '.parent' attribute will be set to an object with a getStore method.
    """

    name = Attribute("""
    """)

    description = Attribute("""
    """)



class IBeneficiary(Interface):
    """
    Interface to adapt to when looking for an appropriate application-level
    object to install powerups on.
    """

    def powerUp(implementor, interface):
        """ Install a powerup on this object.  There is not necessarily any inverse
        powerupsFor on a beneficiary, although there may be; installations may
        be forwarded to a different implementation object, or deferred.
        """


class IPowerupIndirector(Interface):
    """
    Implement this interface if you want to change what is returned from
    powerupsFor for a particular interface.
    """

    def indirect(interface):
        """
        When an item which implements IPowerupIndirector is returned from a
        powerupsFor query, this method will be called on it to give it the
        opportunity to return something other than itself from powerupsFor.

        @param interface: the interface passed to powerupsFor
        @type interface: L{zope.interface.Interface}
        """


class IScheduler(Interface):
    """
    An interface for scheduling tasks.  Quite often the store will be adaptable
    to this; in any Mantissa application, for example; so it is reasonable to
    assume that it is if your application needs to schedule timed events or
    queue tasks.
    """
    def schedule(runnable, when):
        """
        @param runnable: any Item with a 'run' method.

        @param when: a Time instance describing when the runnable's run()
        method will be called.  See extime.Time's documentation for more
        details.
        """



class IQuery(Interface):
    """
    An object that represents a query that can be performed against a database.
    """

    limit = Attribute(
        """
        An integer representing the maximum number of rows to be returned from
        this query, or None, if the query is unlimited.
        """)

    store = Attribute(
        """
        The Axiom store that this query will return results from.
        """)

    def __iter__():
        """
        Retrieve an iterator for the results of this query.

        The query is performed whenever this is called.
        """

    def count():
        """
        Return the number of results in this query.

        NOTE: In most cases, this will have to load all of the rows in this
        query.  It is therefore very slow and should generally be considered
        discouraged.  Call with caution!
        """

    def cloneQuery(limit):
        """
        Create a similar-but-not-identical copy of this query with certain
        attributes changed.

        (Currently this only supports the manipulation of the "limit"
        parameter, but it is the intent that with a richer query-introspection
        interface, this signature could be expanded to support many different
        attributes.)

        @param limit: an integer, representing the maximum number of rows that
        this query should return.

        @return: an L{IQuery} provider with the new limit.
        """



class IColumn(Interface):
    """
    An object that represents a column in the database.
    """

    def getShortColumnName(store):
        """
        @rtype: C{str}
        @return: Just the name of this column.
        """

    def getColumnName(store):
        """
        @rtype: C{str}

        @return: The fully qualified name of this object as a column within the
        database, eg, C{"main_database.some_table.[this_column]"}.
        """

    def fullyQualifiedName():
        """
        @rtype: C{str}

        @return: The fully qualfied name of this object as an attribute in
        Python code, eg, C{myproject.mymodule.MyClass.myAttribute}.  If this
        attribute is represented by an actual Python code object, it will be a
        dot-separated sequence of Python identifiers; otherwise, it will
        contain invalid identifier characters other than '.'.
        """

    def __get__(row):
        """
        @param row: an item that has this column.
        @type row: L{axiom.item.Item}

        @return: The value of the column described by this object, for the given
        row.

        @rtype: depends on the underlying type of the column.
        """


class IOrdering(Interface):
    """
    An object suitable for passing to the 'sort' argument of a query method.
    """

    def orderColumns():
        """
        Return a list of two-tuples of IColumn providers and either C{'ASC'} or
        C{'DESC'} defining this ordering.
        """



class IComparison(Interface):
    """
    An object that represents an in-database comparison.  A predicate that may
    apply to certain items in a store.  Passed as an argument to
    attributes.AND, .OR, and Store.query(...)
    """

    def getInvolvedTables():
        """
        Return a sequence of L{Item} subclasses which are referenced by this
        comparison.  A class may appear at most once.
        """

    def getQuery(store):
        """
        Return an SQL string with ?-style bind parameter syntax thingies.
        """

    def getArgs(store):
        """
        Return a sequence of arguments suitable for use to satisfy the bind
        parameters in the result of L{getQuery}.
        """


class IReliableListener(Interface):
    """
    Receives notification of the existence of Items of a particular type.

    {IReliableListener} providers are given to
    L{IBatchProcessor.addReliableListener} and will then have L{processItem}
    called with items handled by that processor.
    """

    def processItem(item):
        """
        Callback notifying this listener of the existence of the given item.
        """

    def suspend():
        """
        Invoked when notification for this listener is being temporarily
        suspended.

        This should clean up any ephemeral resources held by this listener and
        generally prepare to not do anything for a while.
        """

    def resume():
        """
        Invoked when notification for this listener is being resumed.

        Any actions taken by L{suspend} may be reversed by this method.
        """


LOCAL, REMOTE = list(range(2))
class IBatchProcessor(Interface):
    def addReliableListener(listener, style=LOCAL):
        """
        Add the given Item to the set which will be notified of Items
        available for processing.

        Note: Each Item is processed synchronously.  Adding too many
        listeners to a single batch processor will cause the L{step}
        method to block while it sends notification to each listener.

        @type listener: L{IReliableListener}
        @param listener: The item to which listened-for items will be passed
        for processing.
        """

    def removeReliableListener(listener):
        """
        Remove a previously added listener.
        """

    def getReliableListeners():
        """
        Return an iterable of the listeners which have been added to
        this batch processor.
        """



class IBatchService(Interface):
    """
    Object which allows minimal communication with L{IReliableListener}
    providers which are running remotely (that is, with the L{REMOTE} style).
    """

    def start():
        """
        Start the remote batch process if it has not yet been started, otherwise
        do nothing.
        """

    def suspend(storeID):
        """
        @type storeID: C{int}
        @param storeID: The storeID of the listener to suspend.

        @rtype: L{twisted.internet.defer.Deferred}
        @return: A Deferred which fires when the listener has been suspended.
        """

    def resume(storeID):
        """
        @type storeID: C{int}
        @param storeID: The storeID of the listener to resume.

        @rtype: L{twisted.internet.defer.Deferred}
        @return: A Deferred which fires when the listener has been resumed.
        """


class IVersion(Interface):
    """
    Object with version information for a package that creates Axiom
    items, most likely a L{twisted.python.versions.Version}. Used to
    track which versions of a package have been used to load a store.
    """
    package = Attribute("""
    Name of a Python package.
    """)
    major = Attribute("""
    Major version number.
    """)
    minor = Attribute("""
    Minor version number.
    """)
    micro = Attribute("""
    Micro version number.
    """)
