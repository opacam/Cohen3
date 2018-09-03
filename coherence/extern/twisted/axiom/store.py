# Copyright 2008 Divmod, Inc.  See LICENSE for details
# -*- test-case-name: axiom.test -*-

"""
This module holds the Axiom Store class and related classes, such as queries.
"""
from coherence.extern.twisted.epsilon import hotfix
hotfix.require('twisted', 'filepath_copyTo')

import time, os, itertools, warnings, sys, operator, weakref

from zope.interface import implementer

from twisted.python import log
from twisted.python.failure import Failure
from twisted.python import filepath
from twisted.internet import defer
from twisted.python.reflect import namedAny
from twisted.application.service import IService, IServiceCollection

from coherence.extern.twisted.epsilon.pending import PendingEvent
from coherence.extern.twisted.epsilon.cooperator import SchedulingService

from coherence.extern.twisted.axiom import _schema, attributes, upgrade, _fincache, iaxiom, errors
from coherence.extern.twisted.axiom import item
from coherence.extern.twisted.axiom._pysqlite2 import Connection

from coherence.extern.twisted.axiom.item import \
    _typeNameToMostRecentClass, declareLegacyItem, \
    _legacyTypes, Empowered, serviceSpecialCase, _StoreIDComparer

IN_MEMORY_DATABASE = ':memory:'

# The special storeID used to mark the store itself as the target of a
# reference.
STORE_SELF_ID = -1

tempCounter = itertools.count()

# A mapping from MetaItem instances to precomputed structures describing the
# indexes necessary for those MetaItems.  Avoiding recomputing this speeds up
# opening stores significantly.
_requiredTableIndexes = weakref.WeakKeyDictionary()

# A mapping from MetaItem instances to precomputed structures describing the
# known in-memory schema for those MetaItems.  Avoiding recomputing this speeds
# up opening stores significantly.
_inMemorySchemaCache = weakref.WeakKeyDictionary()


class NoEmptyItems(Exception):
    """You must define some attributes on every item.
    """


def _mkdirIfNotExists(dirname):
    if os.path.isdir(dirname):
        return False
    os.makedirs(dirname)
    return True


@implementer(iaxiom.IAtomicFile)
class AtomicFile():
    """I am a file which is moved from temporary to permanent storage when it
    is closed.

    After I'm closed, I will have a 'finalpath' property saying where I went.
    """

    def __init__(self, tempname, destpath):
        """
        Create an AtomicFile.  (Note: AtomicFiles can only be opened in
        write-binary mode.)

        @param tempname: The filename to open for temporary storage.

        @param destpath: The filename to move this file to when .close() is
        called.
        """
        self._destpath = destpath
        self.f = open(tempname, 'w+b')
        self.name = self.f.name
        self.finalpath = self.f.finalpath
        # super(AtomicFile, self).__init__(tempname, 'w+b')

    def close(self):
        """
        Close this file and commit it to its permanent location.

        @return: a Deferred which fires when the file has been moved (and
        backed up to tertiary storage, if necessary).
        """
        now = time.time()
        try:
            self.f.close(self)
            _mkdirIfNotExists(self._destpath.dirname())
            self.finalpath = self._destpath
            os.rename(self.name, self.finalpath.path)
            os.utime(self.finalpath.path, (now, now))
        except:
            return defer.fail()
        return defer.succeed(self.finalpath)

    def abort(self):
        os.unlink(self.name)


_noItem = object()              # tag for optional argument to getItemByID
                                # default


def storeServiceSpecialCase(st, pups):
    """
    Adapt a store to L{IServiceCollection}.

    @param st: The L{Store} to adapt.
    @param pups: A list of L{IServiceCollection} powerups on C{st}.

    @return: An L{IServiceCollection} which has all of C{pups} as children.
    """
    if st.parent is not None:
        # If for some bizarre reason we're starting a substore's service, let's
        # just assume that its parent is running its upgraders, rather than
        # risk starting the upgrader run twice. (XXX: it *IS* possible to
        # figure out whether we need to or not, I just doubt this will ever
        # even happen in practice -- fix here if it does)
        return serviceSpecialCase(st, pups)
    if st._axiom_service is not None:
        # not new, don't add twice.
        return st._axiom_service

    collection = serviceSpecialCase(st, pups)

    st._upgradeService.setServiceParent(collection)

    if st.dbdir is not None:
        from coherence.extern.twisted.axiom import batch
        batcher = batch.BatchProcessingControllerService(st)
        batcher.setServiceParent(collection)

    scheduler = iaxiom.IScheduler(st)
    # If it's an old database, we might get a SubScheduler instance.  It has no
    # setServiceParent method.
    setServiceParent = getattr(scheduler, 'setServiceParent', None)
    if setServiceParent is not None:
        setServiceParent(collection)

    return collection


def _typeIsTotallyUnknown(typename, version):
    return ((typename not in _typeNameToMostRecentClass)
            and ((typename, version) not in _legacyTypes))


@implementer(iaxiom.IQuery)
class BaseQuery:
    """
    This is the abstract base implementation of query logic shared between item
    and attribute queries.

    Note: as this is an abstract class, it doesn't *actually* implement IQuery,
    but all its subclasses must, so it is declared to.  Don't instantiate it
    directly.
    """
    # XXX: need a better convention for this sort of
    # abstract-but-provide-most-of-a-base-implementation thing. -glyph

    # How about not putting the implements(iaxiom.IQuery) here, but on
    # subclasses instead? -exarkun

    def __init__(self, store, tableClass,
                 comparison=None, limit=None,
                 offset=None, sort=None):
        """
        Create a generic object-oriented interface to SQL, used to implement
        Store.query.

        @param store: the store that this query is within.

        @param tableClass: a subclass of L{Item}.

        @param comparison: an implementor of L{iaxiom.IComparison}

        @param limit: an L{int} that limits the number of results that will be
        queried for, or None to indicate that all results should be returned.

        @param offset: an L{int} that specifies the offset within the query
        results to begin iterating from, or None to indicate that we should
        start at 0.

        @param sort: A sort order object.  Obtained by doing
        C{YourItemClass.yourAttribute.ascending} or C{.descending}.
        """

        self.store = store
        self.tableClass = tableClass
        self.comparison = comparison
        self.limit = limit
        self.offset = offset
        self.sort = iaxiom.IOrdering(sort)
        tables = self._involvedTables()
        self._computeFromClause(tables)


    _cloneAttributes = 'store tableClass comparison limit offset sort'.split()

    # IQuery
    def cloneQuery(self, limit=_noItem, sort=_noItem):
        clonekw = {}
        for attr in self._cloneAttributes:
            clonekw[attr] = getattr(self, attr)
        if limit is not _noItem:
            clonekw['limit'] = limit
        if sort is not _noItem:
            clonekw['sort'] = sort
        return self.__class__(**clonekw)


    def __repr__(self):
        return self.__class__.__name__ + '(' + ', '.join([
                repr(self.store),
                repr(self.tableClass),
                repr(self.comparison),
                repr(self.limit),
                repr(self.offset),
                repr(self.sort)]) + ')'


    def explain(self):
        """
        A debugging API, exposing SQLite's I{EXPLAIN} statement.

        While this is not a private method, you also probably don't have any
        use for it unless you understand U{SQLite
        opcodes<http://www.sqlite.org/opcode.html>} very well.

        Once you do, it can be handy to call this interactively to get a sense
        of the complexity of a query.

        @return: a list, the first element of which is a L{str} (the SQL
        statement which will be run), and the remainder of which is 3-tuples
        resulting from the I{EXPLAIN} of that statement.
        """
        return ([self._sqlAndArgs('SELECT', self._queryTarget)[0]] +
                self._runQuery('EXPLAIN SELECT', self._queryTarget))


    def _involvedTables(self):
        """
        Return a list of tables involved in this query,
        first checking that no required tables (those in
        the query target) have been omitted from the comparison.
        """
        # SQL and arguments
        if self.comparison is not None:
            tables = self.comparison.getInvolvedTables()
            self.args = self.comparison.getArgs(self.store)
        else:
            tables = [self.tableClass]
            self.args = []

        if self.tableClass not in tables:
            raise ValueError(
                "Comparison omits required reference to result type")

        return tables

    def _computeFromClause(self, tables):
        """
        Generate the SQL string which follows the "FROM" string and before the
        "WHERE" string in the final SQL statement.
        """
        tableAliases = []
        self.fromClauseParts = []
        for table in tables:
            # The indirect calls to store.getTableName() will create the tables
            # if needed. (XXX That's bad, actually.   They should get created
            # some other way if necessary.  -exarkun)
            tableName = table.getTableName(self.store)
            tableAlias = table.getTableAlias(self.store, tuple(tableAliases))
            if tableAlias is None:
                self.fromClauseParts.append(tableName)
            else:
                tableAliases.append(tableAlias)
                self.fromClauseParts.append('%s AS %s' % (tableName,
                                                          tableAlias))

        self.sortClauseParts = []
        for attr, direction in self.sort.orderColumns():
            assert direction in ('ASC', 'DESC'), "%r not in ASC,DESC" % (direction,)
            if attr.type not in tables:
                raise ValueError(
                    "Ordering references type excluded from comparison")
            self.sortClauseParts.append(
                '%s %s' % (attr.getColumnName(self.store), direction))


    def _sqlAndArgs(self, verb, subject):
        limitClause = []
        if self.limit is not None:
            # XXX LIMIT and OFFSET used to be using ?, but they started
            # generating syntax errors in places where generating the whole SQL
            # statement does not.  this smells like a bug in sqlite's parser to
            # me, but I don't know my SQL syntax standards well enough to be
            # sure -glyph
            if not isinstance(self.limit, int):
                raise TypeError("limit must be an integer: %r" % (self.limit,))
            limitClause.append('LIMIT')
            limitClause.append(str(self.limit))
            if self.offset is not None:
                if not isinstance(self.offset, int):
                    raise TypeError("offset must be an integer: %r" % (self.offset,))
                limitClause.append('OFFSET')
                limitClause.append(str(self.offset))
        else:
            assert self.offset is None, 'Offset specified without limit'

        sqlParts = [verb, subject]
        if self.fromClauseParts:
            sqlParts.extend(['FROM', ', '.join(self.fromClauseParts)])
        if self.comparison is not None:
            sqlParts.extend(['WHERE', self.comparison.getQuery(self.store)])
        if self.sortClauseParts:
            sqlParts.extend(['ORDER BY', ', '.join(self.sortClauseParts)])
        if limitClause:
            sqlParts.append(' '.join(limitClause))
        sqlstr = ' '.join(sqlParts)
        return (sqlstr, self.args)


    def _runQuery(self, verb, subject):
        # XXX ideally this should be creating an SQL cursor and iterating
        # through that so we don't have to load the whole query into memory,
        # but right now Store's interface to SQL is all through one cursor.
        # I'm not sure how to do this and preserve the chokepoint so that we
        # can do, e.g. transaction fallbacks.
        t = time.time()
        if not self.store.autocommit:
            self.store.checkpoint()
        sqlstr, sqlargs = self._sqlAndArgs(verb, subject)
        sqlResults = self.store.querySQL(sqlstr, sqlargs)
        cs = self.locateCallSite()
        log.msg(interface=iaxiom.IStatEvent,
                querySite=cs, queryTime=time.time() - t, querySQL=sqlstr)
        return sqlResults

    def locateCallSite(self):
        i = 3
        frame = sys._getframe(i)
        while frame.f_code.co_filename == __file__:
            #let's not get stuck in findOrCreate, etc
            i += 1
            frame = sys._getframe(i)
        return (frame.f_code.co_filename, frame.f_lineno)


    def _selectStuff(self, verb='SELECT'):
        """
        Return a generator which yields the massaged results of this query with
        a particular SQL verb.

        For an attribute query, massaged results are of the type of that
        attribute.  For an item query, they are items of the type the query is
        supposed to return.

        @param verb: a str containing the SQL verb to execute.  This really
        must be some variant of 'SELECT', the only two currently implemented
        being 'SELECT' and 'SELECT DISTINCT'.
        """
        sqlResults = self._runQuery(verb, self._queryTarget)
        for row in sqlResults:
            yield self._massageData(row)


    def _massageData(self, row):
        """
        Subclasses must override this method to 'massage' the data received
        from the database, converting it from data direct from the database
        into Python objects of the appropriate form.

        @param row: a tuple of some kind, representing an element of data
        returned from a call to sqlite.
        """
        raise NotImplementedError()


    def distinct(self):
        """
        Call this method if you want to avoid repeated results from a query.

        You can call this on either an attribute or item query.  For example,
        on an attribute query::

            X(store=s, value=1, name=u'foo')
            X(store=s, value=1, name=u'bar')
            X(store=s, value=2, name=u'baz')
            X(store=s, value=3, name=u'qux')
            list(s.query(X).getColumn('value'))
                => [1, 1, 2, 3]
            list(s.query(X).getColumn('value').distinct())
                => [1, 2, 3]

        You can also use distinct queries to eliminate duplicate results from
        joining two Item types together in a query, like so::

            x = X(store=s, value=1, name=u'hello')
            Y(store=s, other=x, ident=u'a')
            Y(store=s, other=x, ident=u'b')
            Y(store=s, other=x, ident=u'b+')
            list(s.query(X, AND(Y.other == X.storeID,
                                Y.ident.startswith(u'b'))))
                => [X(name=u'hello', value=1, storeID=1)@...,
                    X(name=u'hello', value=1, storeID=1)@...]
            list(s.query(X, AND(Y.other == X.storeID,
                                Y.ident.startswith(u'b'))).distinct())
                => [X(name=u'hello', value=1, storeID=1)@...]

        @return: an L{iaxiom.IQuery} provider whose values are distinct.
        """
        return _DistinctQuery(self)


    def __iter__(self):
        """
        Iterate the results of this query.
        """
        return self._selectStuff('SELECT')


    _selfiter = None
    def __next__(self):
        """
        This method is deprecated, a holdover from when queries were iterators,
        rather than iterables.

        @return: one element of massaged data.
        """
        if self._selfiter is None:
            warnings.warn(
                "Calling 'next' directly on a query is deprecated. "
                "Perhaps you want to use iter(query).next(), or something "
                "more expressive like store.findFirst or store.findOrCreate?",
                DeprecationWarning, stacklevel=2)
            self._selfiter = self.__iter__()
        return next(self._selfiter)



class _FakeItemForFilter:
    __legacy__ = False
    def __init__(self, store):
        self.store = store


def _isColumnUnique(col):
    """
    Determine if an IColumn provider is unique.

    @param col: an L{IColumn} provider
    @return: True if the IColumn provider is unique, False otherwise.
    """
    return isinstance(col, _StoreIDComparer)

class ItemQuery(BaseQuery):
    """
    This class is a query whose results will be Item instances.  This is the
    type always returned from L{Store.query}.
    """

    def __init__(self, *a, **k):
        """
        Create an ItemQuery.  This is typically done via L{Store.query}.
        """
        BaseQuery.__init__(self, *a, **k)
        self._queryTarget = (
            self.tableClass.storeID.getColumnName(self.store) + ', ' + (
                ', '.join(
                    [attrobj.getColumnName(self.store)
                     for name, attrobj in self.tableClass.getSchema()
                     ])))


    def paginate(self, pagesize=20):
        """
        Split up the work of gathering a result set into multiple smaller
        'pages', allowing very large queries to be iterated without blocking
        for long periods of time.

        While simply iterating C{paginate()} is very similar to iterating a
        query directly, using this method allows the work to obtain the results
        to be performed on demand, over a series of different transaction.

        @param pagesize: the number of results gather in each chunk of work.
        (This is mostly for testing paginate's implementation.)
        @type pagesize: L{int}

        @return: an iterable which yields all the results of this query.
        """

        sort = self.sort
        oc = list(sort.orderColumns())
        if not oc:
            # You can't have an unsorted pagination.
            sort = self.tableClass.storeID.ascending
            oc = list(sort.orderColumns())
        if len(oc) != 1:
            raise RuntimeError("%d-column sorts not supported yet with paginate" %(len(oc),))
        sortColumn = oc[0][0]
        if oc[0][1] == 'ASC':
            sortOp = operator.gt
        else:
            sortOp = operator.lt
        if _isColumnUnique(sortColumn):
            # This is the easy case.  There is never a tie to be broken, so we
            # can just remember our last value and yield from there.  Right now
            # this only happens when the column is a storeID, but hopefully in
            # the future we will have more of this.
            tiebreaker = None
        else:
            tiebreaker = self.tableClass.storeID

        tied = lambda a, b: (sortColumn.__get__(a) ==
                             sortColumn.__get__(b))
        def _AND(a, b):
            if a is None:
                return b
            return attributes.AND(a, b)

        results = list(self.store.query(self.tableClass, self.comparison,
                                        sort=sort, limit=pagesize + 1))
        while results:
            if len(results) == 1:
                # XXX TODO: reject 0 pagesize.  If the length of the result set
                # is 1, there's no next result to test for a tie with, so we
                # must be at the end, and we should just yield the result and finish.
                yield results[0]
                return
            for resultidx in range(len(results) - 1):
                # check for a tie.
                result = results[resultidx]
                nextResult = results[resultidx + 1]
                if tied(result, nextResult):
                    # Yield any ties first, in the appropriate order.
                    lastTieBreaker = tiebreaker.__get__(result)
                    # Note that this query is _NOT_ limited: currently large ties
                    # will generate arbitrarily large amounts of work.
                    trq = self.store.query(
                        self.tableClass,
                        _AND(self.comparison,
                             sortColumn == sortColumn.__get__(result)))
                    tiedResults = list(trq)
                    tiedResults.sort(key=lambda rslt: (sortColumn.__get__(result),
                                                       tiebreaker.__get__(result)))
                    for result in tiedResults:
                        yield result
                    # re-start the query here ('result' is set to the
                    # appropriate value by the inner loop)
                    break
                else:
                    yield result

            lastSortValue = sortColumn.__get__(result) # hooray namespace pollution
            results = list(self.store.query(
                    self.tableClass,
                    _AND(self.comparison,
                         sortOp(sortColumn,
                                sortColumn.__get__(result))),
                    sort=sort,
                    limit=pagesize + 1))

    def _massageData(self, row):
        """
        Convert a row into an Item instance by loading cached items or
        creating new ones based on query results.

        @param row: an n-tuple, where n is the number of columns specified by
        my item type.

        @return: an instance of the type specified by this query.
        """
        result = self.store._loadedItem(self.tableClass, row[0], row[1:])
        assert result.store is not None, "result %r has funky store" % (result,)
        return result


    def getColumn(self, attributeName, raw=False):
        """
        Get an L{iaxiom.IQuery} whose results will be values of a single
        attribute rather than an Item.

        @param attributeName: a L{str}, the name of a Python attribute, that
        describes a column on the Item subclass that this query was specified
        for.

        @return: an L{AttributeQuery} for the column described by the attribute
        named L{attributeName} on the item class that this query's results will
        be instances of.
        """
        # XXX: 'raw' is undocumented because I think it's completely unused,
        # and it's definitely untested.  It should probably be removed when
        # someone has the time. -glyph

        # Quotient POP3 server uses it.  Not that it shouldn't be removed.
        # ;) -exarkun
        attr = getattr(self.tableClass, attributeName)
        return AttributeQuery(self.store,
                              self.tableClass,
                              self.comparison,
                              self.limit,
                              self.offset,
                              self.sort,
                              attr,
                              raw)


    def count(self):
        rslt = self._runQuery(
            'SELECT',
            'COUNT(' + self.tableClass.storeID.getColumnName(self.store)
            + ')')
        assert len(rslt) == 1, 'more than one result: %r' % (rslt,)
        return rslt[0][0] or 0


    def deleteFromStore(self):
        """
        Delete all the Items which are found by this query.
        """
        if (self.limit is None and
            not isinstance(self.sort, attributes.UnspecifiedOrdering)):
            # The ORDER BY is pointless here, and SQLite complains about it.
            return self.cloneQuery(sort=None).deleteFromStore()

        #We can do this the fast way or the slow way.

        # If there's a 'deleted' callback on the Item type or 'deleteFromStore'
        # is overridden, we have to do it the slow way.
        deletedOverridden = (
            self.tableClass.deleted.__func__ is not item.Item.deleted.__func__)
        deleteFromStoreOverridden = (
            self.tableClass.deleteFromStore.__func__ is not
            item.Item.deleteFromStore.__func__)

        if deletedOverridden or deleteFromStoreOverridden:
            for it in self:
                it.deleteFromStore()
        else:

            # Find other item types whose instances need to be deleted
            # when items of the type in this query are deleted, and
            # remove them from the store.
            def itemsToDelete(attr):
                return attr.oneOf(self.getColumn("storeID"))

            if not item.allowDeletion(self.store, self.tableClass, itemsToDelete):
                raise errors.DeletionDisallowed(
                    'Cannot delete item; '
                    'has referents with whenDeleted == reference.DISALLOW')

            for it in item.dependentItems(self.store,
                                          self.tableClass, itemsToDelete):
                it.deleteFromStore()

            # actually run the DELETE for the items in this query.
            self._runQuery('DELETE', "")

class MultipleItemQuery(BaseQuery):
    """
    A query that returns tuples of Items from a join.
    """

    def __init__(self, *a, **k):
        """
        Create a MultipleItemQuery.  This is typically done via L{Store.query}.
        """
        BaseQuery.__init__(self, *a, **k)

        # Just in case it's some other kind of iterable.
        self.tableClass = tuple(self.tableClass)

        if len(self.tableClass) == 0:
            raise ValueError("Multiple item queries must have "
                             "at least one table class")

        targets = []

        # Later when we massage data out, we need to slice the row.
        # This records the slice lengths.
        self.schemaLengths = []

        # self.tableClass is a tuple of Item classes.
        for tableClass in self.tableClass:

            schema = tableClass.getSchema()

            # The extra 1 is oid
            self.schemaLengths.append(len(schema) + 1)

            targets.append(
                tableClass.storeID.getColumnName(self.store) + ', ' + (
                ', '.join(
                [attrobj.getColumnName(self.store)
                 for name, attrobj in schema
                 ])))

        self._queryTarget = ', '.join(targets)

    def _involvedTables(self):
        """
        Return a list of tables involved in this query,
        first checking that no required tables (those in
        the query target) have been omitted from the comparison.
        """
        # SQL and arguments
        if self.comparison is not None:
            tables = self.comparison.getInvolvedTables()
            self.args = self.comparison.getArgs(self.store)
        else:
            tables = list(self.tableClass)
            self.args = []

        for tableClass in self.tableClass:
            if tableClass not in tables:
                raise ValueError(
                    "Comparison omits required reference to result type %s"
                    % tableClass.typeName)

        return tables

    def _massageData(self, row):

        """
        Convert a row into a tuple of Item instances, by slicing it
        according to the number of columns for each instance, and then
        proceeding as for ItemQuery._massageData.

        @param row: an n-tuple, where n is the total number of columns
        specified by all the item types in this query.

        @return: a tuple of instances of the types specified by this query.
        """
        offset = 0
        resultBits = []

        for i, tableClass in enumerate(self.tableClass):
            numAttrs = self.schemaLengths[i]

            result = self.store._loadedItem(self.tableClass[i],
                                            row[offset],
                                            row[offset+1:offset+numAttrs])
            assert result.store is not None, "result %r has funky store" % (result,)
            resultBits.append(result)

            offset += numAttrs

        return tuple(resultBits)

    def count(self):
        """
        Count the number of distinct results of the wrapped query.

        @return: an L{int} representing the number of distinct results.
        """
        if not self.store.autocommit:
            self.store.checkpoint()
        target = ', '.join([
            tableClass.storeID.getColumnName(self.store)
            for tableClass in self.tableClass ])
        sql, args = self._sqlAndArgs('SELECT', target)
        sql = 'SELECT COUNT(*) FROM (' + sql + ')'
        result = self.store.querySQL(sql, args)
        assert len(result) == 1, 'more than one result: %r' % (result,)
        return result[0][0] or 0

    def distinct(self):
        """
        @return: an L{iaxiom.IQuery} provider whose values are distinct.
        """
        return _MultipleItemDistinctQuery(self)


@implementer(iaxiom.IQuery)
class _DistinctQuery(object):
    """
    A query for results excluding duplicates.

    Results from this query depend on the query it was initialized with.
    """

    def __init__(self, query):
        """
        Create a distinct query, based on another query.

        @param query: an instance of a L{BaseQuery} subclass.  Note: an IQuery
        provider is not sufficient, this class relies on implementation details
        of L{BaseQuery}.
        """
        self.query = query
        self.store = query.store
        self.limit = query.limit


    def cloneQuery(self, limit=_noItem, sort=_noItem):
        """
        Clone the original query which this distinct query wraps, and return a new
        wrapper around that clone.
        """
        newq = self.query.cloneQuery(limit=limit, sort=sort)
        return self.__class__(newq)


    def __iter__(self):
        """
        Iterate the distinct results of the wrapped query.

        @return: a generator which yields distinct values from its delegate
        query, whether they are items or attributes.
        """
        return self.query._selectStuff('SELECT DISTINCT')


    def count(self):
        """
        Count the number of distinct results of the wrapped query.

        @return: an L{int} representing the number of distinct results.
        """
        if not self.query.store.autocommit:
            self.query.store.checkpoint()
        sql, args = self.query._sqlAndArgs(
            'SELECT DISTINCT',
            self.query.tableClass.storeID.getColumnName(self.query.store))
        sql = 'SELECT COUNT(*) FROM (' + sql + ')'
        result = self.query.store.querySQL(sql, args)
        assert len(result) == 1, 'more than one result: %r' % (result,)
        return result[0][0] or 0


class _MultipleItemDistinctQuery(_DistinctQuery):
    """
    Distinct query based on a MultipleItemQuery.
    """

    def count(self):
        """
        Count the number of distinct results of the wrapped query.

        @return: an L{int} representing the number of distinct results.
        """
        if not self.query.store.autocommit:
            self.query.store.checkpoint()
        target = ', '.join([
            tableClass.storeID.getColumnName(self.query.store)
            for tableClass in self.query.tableClass ])
        sql, args = self.query._sqlAndArgs(
            'SELECT DISTINCT',
            target)
        sql = 'SELECT COUNT(*) FROM (' + sql + ')'
        result = self.query.store.querySQL(sql, args)
        assert len(result) == 1, 'more than one result: %r' % (result,)
        return result[0][0] or 0


_noDefault = object()


class AttributeQuery(BaseQuery):
    """
    A query for the value of a single attribute from an item class, so as to
    load only a single value rather than an instantiating an entire item when
    the value is all that is needed.
    """
    def __init__(self,
                 store,
                 tableClass,
                 comparison=None, limit=None,
                 offset=None, sort=None,
                 attribute=None,
                 raw=False):
        BaseQuery.__init__(self, store, tableClass,
                           comparison, limit,
                           offset, sort)
        self.attribute = attribute
        self.raw = raw
        self._queryTarget = attribute.getColumnName(self.store)

    _cloneAttributes = BaseQuery._cloneAttributes + 'attribute raw'.split()

    def _massageData(self, row):
        """
        Convert a raw database row to the type described by an attribute.  For
        example, convert a database integer into an L{extime.Time} instance for
        an L{attributes.timestamp} attribute.

        @param row: a 1-tuple, containing the in-database value from my
        attribute.

        @return: a value of the type described by my attribute.
        """
        if self.raw:
            return row[0]
        return self.attribute.outfilter(row[0], _FakeItemForFilter(self.store))

    def count(self):
        """
        @return: the number of non-None values of this attribute specified by this query.
        """
        rslt = self._runQuery('SELECT', 'COUNT(%s)' % (self._queryTarget,)) or [(0,)]
        assert len(rslt) == 1, 'more than one result: %r' % (rslt,)
        return rslt[0][0]

    def sum(self):
        """
        Return the sum of all the values returned by this query.  If no results
        are specified, return None.

        Note: for non-numeric column types the result of this method will be
        nonsensical.

        @return: a number or None.
        """
        res = self._runQuery('SELECT', 'SUM(%s)' % (self._queryTarget,)) or [(0,)]
        assert len(res) == 1, "more than one result: %r" % (res,)
        dbval = res[0][0] or 0
        return self.attribute.outfilter(dbval, _FakeItemForFilter(self.store))

    def average(self):
        """
        Return the average value (as defined by the AVG implementation in the
        database) of the values specified by this query.

        Note: for non-numeric column types the result of this method will be
        nonsensical.

        @return: a L{float} representing the 'average' value of this column.
        """
        rslt = self._runQuery('SELECT', 'AVG(%s)' % (self._queryTarget,)) or [(0,)]
        assert len(rslt) == 1, 'more than one result: %r' % (rslt,)
        return rslt[0][0]

    def max(self, default=_noDefault):
        return self._functionOnTarget('MAX', default)

    def min(self, default=_noDefault):
        return self._functionOnTarget('MIN', default)

    def _functionOnTarget(self, which, default):
        rslt = self._runQuery('SELECT', '%s(%s)' %
                              (which, self._queryTarget,)) or [(None,)]
        assert len(rslt) == 1, 'more than one result: %r' % (rslt,)
        dbval = rslt[0][0]
        if dbval is None:
            if default is _noDefault:
                raise ValueError('%s() on table with no items'%(which))
            else:
                return default
        return self.attribute.outfilter(dbval, _FakeItemForFilter(self.store))


def _storeBatchServiceSpecialCase(*args, **kwargs):
    """
    Trivial wrapper around L{batch.storeBatchServiceSpecialCase} to delay the
    import of axiom.batch, which imports the reactor, which we do not want as a
    side-effect of importing L{axiom.store} (as this would preclude selecting a
    reactor after importing this module; see #2864).
    """
    from coherence.extern.twisted.axiom import batch
    return batch.storeBatchServiceSpecialCase(*args, **kwargs)


def _schedulerServiceSpecialCase(empowered, pups):
    """
    This function creates (or returns a previously created) L{IScheduler}
    powerup.

    If L{IScheduler} powerups were found on C{empowered}, the first of those
    is given priority.  Otherwise, a site L{Store} or a user L{Store} will
    have any pre-existing L{IScheduler} powerup associated with them (on the
    hackish cache attribute C{_schedulerService}) returned, or a new one
    created if none exists already.
    """
    from coherence.extern.twisted.axiom.scheduler import _SiteScheduler, _UserScheduler

    # Give precedence to anything found in the store
    for pup in pups:
        return pup
    # If the empowered is a store, construct a scheduler for it.
    if isinstance(empowered, Store):
        if getattr(empowered, '_schedulerService', None) is None:
            if empowered.parent is None:
                sched = _SiteScheduler(empowered)
            else:
                sched = _UserScheduler(empowered)
            empowered._schedulerService = sched
        return empowered._schedulerService
    return None


def _diffSchema(diskSchema, memorySchema):
    """
    Format a schema mismatch for human consumption.

    @param diskSchema: The on-disk schema.

    @param memorySchema: The in-memory schema.

    @rtype: L{bytes}
    @return: A description of the schema differences.
    """
    diskSchema = set(diskSchema)
    memorySchema = set(memorySchema)
    diskOnly = diskSchema - memorySchema
    memoryOnly = memorySchema - diskSchema
    diff = []
    if diskOnly:
        diff.append('Only on disk:')
        diff.extend(list(map(repr, diskOnly)))
    if memoryOnly:
        diff.append('Only in memory:')
        diff.extend(list(map(repr, memoryOnly)))
    return '\n'.join(diff)


@implementer(iaxiom.IBeneficiary)
class Store(Empowered):
    """
    I am a database that Axiom Items can be stored in.

    Store an item in me by setting its 'store' attribute to be me.

    I can be created one of two ways::

        Store()                      # Create an in-memory database

        Store("/path/to/file.axiom") # create an on-disk database in the
                                     # directory /path/to/file.axiom

    @ivar typeToTableNameCache: a dictionary mapping Item subclass type objects
    to the fully-qualified sqlite table name where items of that type are
    stored.  This cache is generated from the saved schema metadata when this
    store is opened and updated when schema changes from other store objects
    (such as in other processes) are detected.

    @cvar __legacy__: an L{Item} may refer to a L{Store} via a L{reference},
    and this attribute tells the item reference system that the store itself is
    not an old version of an item; i.e. it does not need to have its upgraders
    invoked.

    @cvar storeID: an L{Item} may refer to a L{Store} via a L{reference}, and
    this attribute tells the item reference system that the L{Store} has a
    special ID that to use (which is never allocated to any item).
    """

    aggregateInterfaces = {
        IService: storeServiceSpecialCase,
        IServiceCollection: storeServiceSpecialCase,
        iaxiom.IBatchService: _storeBatchServiceSpecialCase,
        iaxiom.IScheduler: _schedulerServiceSpecialCase}

    transaction = None          # set of objects changed in the current transaction
    touched = None              # set of objects changed since the last checkpoint

    databaseName = 'main'       # can differ if database is attached to another
                                # database.

    dbdir = None # FilePath to the Axiom database directory, or None for
                 # in-memory Stores.
    filesdir = None # FilePath to the filesystem-storage subdirectory of the
                    # database directory, or None for in-memory Stores.

    store = property(lambda self: self) # I have a 'store' attribute because I
                                        # am 'stored' within myself; this is
                                        # also for references to use.


    # Counter indicating things are going on which disallows changes to the
    # database.  Callbacks dispatched to application code while this is
    # non-zero will reject database changes with a ChangeRejected exception.
    _rejectChanges = 0

    # The following method and attributes are the ad-hoc interface required as
    # targets of attributes.reference attributes.  (In other words, the store
    # is a little bit like a fake item.)  These should probably eventually be
    # on an interface somewhere, and be better named.

    def _currentlyValidAsReferentFor(self, store):
        """
        Check to see if this store is currently valid as a target of a
        reference from an item in the given L{Store}.  This is true iff the
        given L{Store} is this L{Store}.

        @param store: the store that the referring item is present in.

        @type store: L{Store}
        """
        if store is self:
            return True
        else:
            return False

    __legacy__ = False

    storeID = STORE_SELF_ID

    def __init__(self, dbdir=None, filesdir=None, debug=False, parent=None, idInParent=None):
        """
        Create a store.

        @param dbdir: A L{FilePath} to (or name of) an existing Axiom directory, or
        directory that does not exist yet which will be created as this Store
        is instantiated.  If unspecified, this database will be kept in memory.

        @param filesdir: A L{FilePath} to (or name of) a directory to keep files in for in-memory
        stores. An exception will be raised if both this attribute and C{dbdir}
        are specified.

        @param debug: set to True if this Store should print out every SQL
        statement it sends to SQLite.

        @param parent: (internal) If this is opened using an
        L{axiom.substore.Substore}, a reference to its parent.

        @param idInParent: (internal) If this is opened using an
        L{axiom.substore.Substore}, the storeID of the item within its parent
        which opened it.

        @raises: C{ValueError} if both C{dbdir} and C{filesdir} are specified.
        """
        if parent is not None or idInParent is not None:
            assert parent is not None
            assert idInParent is not None
        self.parent = parent
        self.idInParent = idInParent
        self.debug = debug
        self.autocommit = True
        self.queryTimes = []
        self.execTimes = []

        self._inMemoryPowerups = {}

        self._attachedChildren = {} # database name => child store object

        self.statementCache = {} # non-normalized => normalized qmark SQL
                                 # statements

        self.activeTables = {}  # tables which have had items added/removed
                                # this run

        self.objectCache = _fincache.FinalizingCache()

        self.tableQueries = {}  # map typename: query string w/ storeID
                                # parameter.  a typename is a persistent
                                # database handle for what we'll call a 'FQPN',
                                # i.e. arg to namedAny.

        self.typenameAndVersionToID = {} # map database-persistent typename and
                                         # version to an oid in the types table

        self.typeToInsertSQLCache = {}
        self.typeToSelectSQLCache = {}
        self.typeToDeleteSQLCache = {}

        self.typeToTableNameCache = {}
        self.attrToColumnNameCache = {}

        self._upgradeManager = upgrade._StoreUpgrade(self)

        self._axiom_service = None

        if self.parent is None:
            self._upgradeService = SchedulingService()
        else:
            # Substores should hook into their parent, since they shouldn't
            # expect to have their own substore service started.
            self._upgradeService = self.parent._upgradeService

        # OK!  Everything that can be set up without touching the filesystem
        # has been done.  Let's get ready to open the actual database...

        _initialOpenFailure = None
        if dbdir is None:
            self._initdb(IN_MEMORY_DATABASE)
            self._initSchema()
            self._memorySubstores = []
            if filesdir is not None:
                if not isinstance(filesdir, filepath.FilePath):
                    filesdir = filepath.FilePath(filesdir)
                self.filesdir = filesdir
                if not self.filesdir.isdir():
                    self.filesdir.makedirs()
                    self.filesdir.child("temp").createDirectory()
        else:
            if filesdir is not None:
                raise ValueError("Only one of dbdir and filesdir"
                                 " may be specified")
            if not isinstance(dbdir, filepath.FilePath):
                dbdir = filepath.FilePath(dbdir)
                # required subdirs: files, temp, run
                # datafile: db.sqlite
            self.dbdir = dbdir
            self.filesdir = self.dbdir.child('files')

            if not dbdir.isdir():
                tempdbdir = dbdir.temporarySibling()
                tempdbdir.makedirs() # maaaaaaaybe this is a bad idea, we
                                     # probably shouldn't be doing this
                                     # automatically.
                for child in ('files', 'temp', 'run'):
                    tempdbdir.child(child).createDirectory()
                self._initdb(tempdbdir.child('db.sqlite').path)
                self._initSchema()
                self.close(_report=False)
                try:
                    tempdbdir.moveTo(dbdir)
                except:
                    _initialOpenFailure = Failure()

            try:
                self._initdb(dbdir.child('db.sqlite').path)
            except:
                if _initialOpenFailure is not None:
                    log.msg("Failed to initialize axiom database."
                            "  Possible cause of error: ")
                    log.err(_initialOpenFailure)
                raise

        self.transact(self._startup)

        # _startup may have found some things which we must now upgrade.
        if self._upgradeManager.upgradesPending:
            # Automatically upgrade when possible.
            self._upgradeComplete = PendingEvent()
            d = self._upgradeService.addIterator(self._upgradeManager.upgradeEverything())
            def logUpgradeFailure(aFailure):
                if aFailure.check(errors.ItemUpgradeError):
                    log.err(aFailure.value.originalFailure, 'Item upgrade error')
                log.err(aFailure, "upgrading %r failed" % (self,))
                return aFailure
            d.addErrback(logUpgradeFailure)
            def finishHim(resultOrFailure):
                self._upgradeComplete.callback(resultOrFailure)
                self._upgradeComplete = None
            d.addBoth(finishHim)
        else:
            self._upgradeComplete = None

        log.msg(
            interface=iaxiom.IStatEvent,
            store_opened=self.dbdir is not None and self.dbdir.path or '')

    _childCounter = 0

    def _attachChild(self, child):
        "attach a child database, returning an identifier for it"
        self._childCounter += 1
        databaseName = 'child_db_%d' % (self._childCounter,)
        self._attachedChildren[databaseName] = child
        # ATTACH DATABASE statements can't use bind paramaters, blech.
        self.executeSQL("ATTACH DATABASE '%s' AS %s" % (
                child.dbdir.child('db.sqlite').path,
                databaseName,))
        return databaseName

    attachedToParent = False

    def attachToParent(self):
        assert self.parent is not None, 'must have a parent to attach'
        assert self.transaction is None, "can't attach within a transaction"

        self.close()

        self.attachedToParent = True
        self.databaseName = self.parent._attachChild(self)
        self.connection = self.parent.connection
        self.cursor = self.parent.cursor

#     def detachFromParent(self):
#         pass

    def _initSchema(self):
        # No point in even attempting to transactionalize this:
        # every single statement is a CREATE TABLE or a CREATE
        # INDEX and those commit transactions silently anyway.
        for stmt in _schema.BASE_SCHEMA:
            self.executeSchemaSQL(stmt)

    def _startup(self):
        """
        Called during __init__.  Check consistency of schema in database with
        classes in memory.  Load all Python modules for stored items, and load
        version information for upgrader service to run later.
        """
        typesToCheck = []

        for oid, module, typename, version in self.querySchemaSQL(_schema.ALL_TYPES):
            if self.debug:
                print()
                print('SCHEMA:', oid, module, typename, version)
            if typename not in _typeNameToMostRecentClass:
                try:
                    namedAny(module)
                except ValueError as err:
                    raise ImportError('cannot find module ' + module, str(err))
            self.typenameAndVersionToID[typename, version] = oid

        # Can't call this until typenameAndVersionToID is populated, since this
        # depends on building a reverse map of that.
        persistedSchema = self._loadTypeSchema()

        # Now that we have persistedSchema, loop over everything again and
        # prepare old types.
        for (typename, version), typeID in self.typenameAndVersionToID.items():
            cls = _typeNameToMostRecentClass.get(typename)

            if cls is not None:
                if version != cls.schemaVersion:
                    typesToCheck.append(
                        self._prepareOldVersionOf(
                            typename, version, persistedSchema))
                else:
                    typesToCheck.append(cls)

        for cls in typesToCheck:
            self._checkTypeSchemaConsistency(cls, persistedSchema)

        # Schema is consistent!  Now, if I forgot to create any indexes last
        # time I saw this table, do it now...
        extantIndexes = self._loadExistingIndexes()
        for cls in typesToCheck:
            self._createIndexesFor(cls, extantIndexes)

        self._upgradeManager.checkUpgradePaths()

    def _loadExistingIndexes(self):
        """
        Return a C{set} of the SQL indexes which already exist in the
        underlying database.  It is important to load all of this information
        at once (as opposed to using many CREATE INDEX IF NOT EXISTS statements
        or many CREATE INDEX statements and handling the errors) to minimize
        the cost of opening a store.  Loading all the indexes at once is much
        faster than doing pretty much anything that involves doing something
        once per required index.
        """
        # Totally SQLite-specific: look up what indexes exist already in
        # sqlite_master so we can skip trying to create them (which can be
        # really slow).
        return set(
            name
            for (name,) in self.querySchemaSQL(
                "SELECT name FROM *DATABASE*.sqlite_master "
                "WHERE type = 'index'"))

    def _initdb(self, dbfname):
        self.connection = Connection.fromDatabaseName(dbfname)
        self.cursor = self.connection.cursor()

    def __repr__(self):
        dbdir = self.dbdir
        if self.dbdir is None:
            dbdir = '(in memory)'

        return "<Store {dbdir}@{id:#x}".format(dbdir=dbdir, id=id(self))

    def findOrCreate(self, userItemClass, __ifnew=None, **attrs):
        """
        Usage::

            s.findOrCreate(userItemClass [, function] [, x=1, y=2, ...])

        Example::

            class YourItemType(Item):
                a = integer()
                b = text()
                c = integer()

            def f(x):
                print x, \"-- it's new!\"
            s.findOrCreate(YourItemType, f, a=1, b=u'2')

        Search for an item with columns in the database that match the passed
        set of keyword arguments, returning the first match if one is found,
        creating one with the given attributes if not.  Takes an optional
        positional argument function to call on the new item if it is new.
        """
        andargs = []
        for k, v in attrs.items():
            col = getattr(userItemClass, k)
            andargs.append(col == v)

        if len(andargs) == 0:
            cond = []
        elif len(andargs) == 1:
            cond = [andargs[0]]
        else:
            cond = [attributes.AND(*andargs)]

        for result in self.query(userItemClass, *cond):
            return result
        newItem = userItemClass(store=self, **attrs)
        if __ifnew is not None:
            __ifnew(newItem)
        return newItem

    def newFilePath(self, *path):
        p = self.filesdir
        for subdir in path:
            p = p.child(subdir)
        return p

    def newTemporaryFilePath(self, *path):
        p = self.dbdir.child('temp')
        for subdir in path:
            p = p.child(subdir)
        return p

    def newFile(self, *path):
        """
        Open a new file somewhere in this Store's file area.

        @param path: a sequence of path segments.

        @return: an L{AtomicFile}.
        """
        assert len(path) > 0, "newFile requires a nonzero number of segments"
        if self.dbdir is None:
            if self.filesdir is None:
                raise RuntimeError("This in-memory store has no file directory")
            else:
                tmpbase = self.filesdir
        else:
            tmpbase = self.dbdir
        tmpname = tmpbase.child('temp').child(str(next(tempCounter)) + ".tmp")
        return AtomicFile(tmpname.path, self.newFilePath(*path))

    def newDirectory(self, *path):
        p = self.filesdir
        for subdir in path:
            p = p.child(subdir)
        return p

    def _loadTypeSchema(self):
        """
        Load all of the stored schema information for all types known by this
        store.  It's important to load everything all at once (rather than
        loading the schema for each type separately as it is needed) to keep
        store opening fast.  A single query with many results is much faster
        than many queries with a few results each.

        @return: A dict with two-tuples of item type name and schema version as
            keys and lists of five-tuples of attribute schema information for
            that type.  The elements of the five-tuple are::

              - a string giving the name of the Python attribute
              - a string giving the SQL type
              - a boolean indicating whether the attribute is indexed
              - the Python attribute type object (eg, axiom.attributes.integer)
              - a string giving documentation for the attribute
        """

        # Oops, need an index going the other way.  This only happens once per
        # store open, and it's based on data queried from the store, so there
        # doesn't seem to be any broader way to cache and re-use the result.
        # However, if we keyed the resulting dict on the database typeID rather
        # than (typeName, schemaVersion), we wouldn't need the information this
        # dict gives us.  That would mean changing the callers of this function
        # to use typeID instead of that tuple, which may be possible.  Probably
        # only represents a very tiny possible speedup.
        typeIDToNameAndVersion = {}
        for key, value in self.typenameAndVersionToID.items():
            typeIDToNameAndVersion[value] = key

        # Indexing attribute, ordering by it, and getting rid of row_offset
        # from the schema and the sorted() here doesn't seem to be any faster
        # than doing this.
        persistedSchema = sorted(self.querySchemaSQL(
            "SELECT attribute, type_id, sqltype, indexed, "
            "pythontype, docstring FROM *DATABASE*.axiom_attributes "))

        # This is trivially (but measurably!) faster than getattr(attributes,
        # pythontype).
        getAttribute = attributes.__dict__.__getitem__

        result = {}
        for (attribute, typeID, sqltype, indexed, pythontype,
             docstring) in persistedSchema:
            key = typeIDToNameAndVersion[typeID]
            if key not in result:
                result[key] = []
            result[key].append((
                    attribute, sqltype, indexed,
                    getAttribute(pythontype), docstring))
        return result

    def _checkTypeSchemaConsistency(self, actualType, onDiskSchema):
        """
        Called for all known types at database startup: make sure that what we
        know (in memory) about this type agrees with what is stored about this
        type in the database.

        @param actualType: A L{MetaItem} instance which is associated with a
            table in this store.  The schema it defines in memory will be
            checked against the schema known in the database to ensure they
            agree.

        @param onDiskSchema: A mapping from L{MetaItem} instances (such as
            C{actualType}) to the schema known in the database and associated
            with C{actualType}.

        @raise RuntimeError: if the schema defined by C{actualType} does not
            match the database-present schema given in C{onDiskSchema} or if
            C{onDiskSchema} contains a newer version of the schema associated
            with C{actualType} than C{actualType} represents.
        """
        # make sure that both the runtime and the database both know about this
        # type; if they don't both know, we can't check that their views are
        # consistent
        try:
            inMemorySchema = _inMemorySchemaCache[actualType]
        except KeyError:
            inMemorySchema = _inMemorySchemaCache[actualType] = [
                (storedAttribute.attrname, storedAttribute.sqltype)
                for (name, storedAttribute) in actualType.getSchema()]

        key = (actualType.typeName, actualType.schemaVersion)
        persistedSchema = [(storedAttribute[0], storedAttribute[1])
                           for storedAttribute in onDiskSchema[key]]
        if inMemorySchema != persistedSchema:
            raise RuntimeError(
                "Schema mismatch on already-loaded %r <%r> object version %d:\n%s" %
                (actualType, actualType.typeName, actualType.schemaVersion,
                 _diffSchema(persistedSchema, inMemorySchema)))

        if actualType.__legacy__:
            return

        if (key[0], key[1] + 1) in onDiskSchema:
            raise RuntimeError(
                "Memory version of %r is %d; database has newer" % (
                    actualType.typeName, key[1]))

    # finally find old versions of the data and prepare to upgrade it.
    def _prepareOldVersionOf(self, typename, version, persistedSchema):
        """
        Note that this database contains old versions of a particular type.
        Create the appropriate dummy item subclass and queue the type to be
        upgraded.

        @param typename: The I{typeName} associated with the schema for which
            to create a dummy item class.

        @param version: The I{schemaVersion} of the old version of the schema
            for which to create a dummy item class.

        @param persistedSchema: A mapping giving information about all schemas
            stored in the database, used to create the attributes of the dummy
            item class.
        """
        appropriateSchema = persistedSchema[typename, version]
        # create actual attribute objects
        dummyAttributes = {}
        for (attribute, sqlType, indexed, pythontype,
             docstring) in appropriateSchema:
            atr = pythontype(indexed=indexed, doc=docstring)
            dummyAttributes[attribute] = atr
        dummyBases = []
        oldType = declareLegacyItem(
            typename, version, dummyAttributes, dummyBases)
        self._upgradeManager.queueTypeUpgrade(oldType)
        return oldType

    def whenFullyUpgraded(self):
        """
        Return a Deferred which fires when this Store has been fully upgraded.
        """
        if self._upgradeComplete is not None:
            return self._upgradeComplete.deferred()
        else:
            return defer.succeed(None)

    def getOldVersionOf(self, typename, version):
        return _legacyTypes[typename, version]

        # grab the schema for that version
        # look up upgraders which push it forward

    def findUnique(self, tableClass, comparison=None, default=_noItem):
        """
        Find an Item in the database which should be unique.  If it is found,
        return it.  If it is not found, return 'default' if it was passed,
        otherwise raise L{errors.ItemNotFound}.  If more than one item is
        found, raise L{errors.DuplicateUniqueItem}.

        @param comparison: implementor of L{iaxiom.IComparison}.

        @param default: value to use if the item is not found.
        """
        results = list(self.query(tableClass, comparison, limit=2))
        lr = len(results)

        if lr == 0:
            if default is _noItem:
                raise errors.ItemNotFound(comparison)
            else:
                return default
        elif lr == 2:
            raise errors.DuplicateUniqueItem(comparison, results)
        elif lr == 1:
            return results[0]
        else:
            raise AssertionError("limit=2 database query returned 3+ results: ",
                                 comparison, results)

    def findFirst(self, tableClass, comparison=None,
                  offset=None, sort=None, default=None):
        """
        Usage::

            s.findFirst(tableClass [, query arguments except 'limit'])

        Example::

            class YourItemType(Item):
                a = integer()
                b = text()
                c = integer()
            ...
            it = s.findFirst(YourItemType,
                             AND(YourItemType.a == 1,
                                 YourItemType.b == u'2'),
                                 sort=YourItemType.c.descending)

        Search for an item with columns in the database that match the passed
        comparison, offset and sort, returning the first match if one is found,
        or the passed default (None if none is passed) if one is not found.
        """

        limit = 1
        for item in self.query(tableClass, comparison, limit, offset, sort):
            return item
        return default

    def query(self, tableClass, comparison=None,
              limit=None, offset=None, sort=None):
        """
        Return a generator of instances of C{tableClass},
        or tuples of instances if C{tableClass} is a
        tuple of classes.

        Examples::

            fastCars = s.query(Vehicle,
                axiom.attributes.AND(
                    Vehicle.wheels == 4,
                    Vehicle.maxKPH > 200),
                limit=100,
                sort=Vehicle.maxKPH.descending)

            quotesByClient = s.query( (Client, Quote),
                axiom.attributes.AND(
                    Client.active == True,
                    Quote.client == Client.storeID,
                    Quote.created >= someDate),
                limit=10,
                sort=(Client.name.ascending,
                      Quote.created.descending))

        @param tableClass: a subclass of Item to look for instances of,
        or a tuple of subclasses.

        @param comparison: a provider of L{IComparison}, or None, to match
        all items available in the store. If tableClass is a tuple, then
        the comparison must refer to all Item subclasses in that tuple,
        and specify the relationships between them.

        @param limit: an int to limit the total length of the results, or None
        for all available results.

        @param offset: an int to specify a starting point within the available
        results, or None to start at 0.

        @param sort: an L{ISort}, something that comes from an SQLAttribute's
        'ascending' or 'descending' attribute.

        @return: an L{ItemQuery} object, which is an iterable of Items or
        tuples of Items, according to tableClass.
        """
        if isinstance(tableClass, tuple):
            queryClass = MultipleItemQuery
        else:
            queryClass = ItemQuery

        return queryClass(self, tableClass, comparison, limit, offset, sort)

    def sum(self, summableAttribute, *a, **k):
        args = (self, summableAttribute.type) + a
        return AttributeQuery(attribute=summableAttribute,
                              *args, **k).sum()
    def count(self, *a, **k):
        return self.query(*a, **k).count()

    def batchInsert(self, itemType, itemAttributes, dataRows):
        """
        Create multiple items in the store without loading
        corresponding Python objects into memory.

        the items' C{stored} callback will not be called.

        Example::

            myData = [(37, u"Fred",  u"Wichita"),
                      (28, u"Jim",   u"Fresno"),
                      (43, u"Betty", u"Dubuque")]
            myStore.batchInsert(FooItem,
                                [FooItem.age, FooItem.name, FooItem.city],
                                myData)

        @param itemType: an Item subclass to create instances of.

        @param itemAttributes: an iterable of attributes on the Item subclass.

        @param dataRows: an iterable of iterables, each the same
        length as C{itemAttributes} and containing data corresponding
        to each attribute in it.

        @return: None.
        """
        class FakeItem:
            pass
        _NEEDS_DEFAULT = object() # token for lookup failure
        fakeOSelf = FakeItem()
        fakeOSelf.store = self
        sql = itemType._baseInsertSQL(self)
        indices = {}
        schema = [attr for (name, attr) in itemType.getSchema()]
        for i, attr in enumerate(itemAttributes):
            indices[attr] = i
        for row in dataRows:
            oid = self.store.executeSchemaSQL(
                _schema.CREATE_OBJECT, [self.store.getTypeID(itemType)])
            insertArgs = [oid]
            for attr in schema:
                i = indices.get(attr, _NEEDS_DEFAULT)
                if i is _NEEDS_DEFAULT:
                    pyval = attr.default
                else:
                    pyval = row[i]
                dbval = attr._convertPyval(fakeOSelf, pyval)
                insertArgs.append(dbval)
            self.executeSQL(sql, insertArgs)

    def _loadedItem(self, itemClass, storeID, attrs):
        try:
            result = self.objectCache.get(storeID)
            # XXX do checks on consistency between attrs and DB object, maybe?
        except KeyError:
            result = itemClass.existingInStore(self, storeID, attrs)
            if not result.__legacy__:
                self.objectCache.cache(storeID, result)
        return result

    def changed(self, item):
        """
        An item in this store was changed.  Add it to the current transaction's
        list of changed items, if a transaction is currently underway, or raise
        an exception if this L{Store} is currently in a state which does not
        allow changes.
        """
        if self._rejectChanges:
            raise errors.ChangeRejected()
        if self.transaction is not None:
            self.transaction.add(item)
            self.touched.add(item)

    def checkpoint(self):
        self._rejectChanges += 1
        try:
            for item in self.touched:
                # XXX: it should be possible here, using various clever hacks, to
                # automatically optimize functionally identical statements into
                # executemany.
                item.checkpoint()
            self.touched.clear()
        finally:
            self._rejectChanges -= 1

    executedThisTransaction = None
    tablesCreatedThisTransaction = None

    def transact(self, f, *a, **k):
        """
        Execute C{f(*a, **k)} in the context of a database transaction.

        Any changes made to this L{Store} by C{f} will be committed when C{f}
        returns.  If C{f} raises an exception, those changes will be reverted
        instead.

        If a transaction is already in progress (in this thread - ie, if a
        frame executing L{Store.transact} is already on the call stack), this
        will B{not} start a nested transaction.  Changes will not be committed
        until the existing transaction completes, and an exception raised by
        C{f} will not revert changes made by C{f}.  You probably don't want to
        ever call this if another transaction is in progress.

        @return: Whatever C{f(*a, **kw)} returns.
        @raise: Whatever C{f(*a, **kw)} raises, or a database exception.
        """
        if self.transaction is not None:
            return f(*a, **k)
        if self.attachedToParent:
            return self.parent.transact(f, *a, **k)
        try:
            self._begin()
            try:
                result = f(*a, **k)
                self.checkpoint()
            except:
                exc = Failure()
                try:
                    self.revert()
                except:
                    log.err(exc)
                    raise
                raise
            else:
                self._commit()
            return result
        finally:
            self._cleanupTxnState()

    # The following three methods are necessary...
    # - in PySQLite: because PySQLite has some buggy transaction handling which
    #   makes it impossible to issue explicit BEGIN statements - which we
    #   _need_ to do to provide guarantees for read/write transactions.

    def _begin(self):
        if self.debug:
            print('<'*10, 'BEGIN', '>'*10)
        self.cursor.execute("BEGIN IMMEDIATE TRANSACTION")
        self._setupTxnState()

    def _setupTxnState(self):
        self.executedThisTransaction = []
        self.tablesCreatedThisTransaction = []
        if self.attachedToParent:
            self.transaction = self.parent.transaction
            self.touched = self.parent.touched
        else:
            self.transaction = set()
            self.touched = set()
        self.autocommit = False
        for sub in list(self._attachedChildren.values()):
            sub._setupTxnState()

    def _commit(self):
        if self.debug:
            print('*'*10, 'COMMIT', '*'*10)
        # self.connection.commit()
        self.cursor.execute("COMMIT")
        log.msg(interface=iaxiom.IStatEvent, stat_commits=1)
        self._postCommitHook()


    def _postCommitHook(self):
        self._rejectChanges += 1
        try:
            for committed in self.transaction:
                committed.committed()
        finally:
            self._rejectChanges -= 1

    def _rollback(self):
        if self.debug:
            print('>'*10, 'ROLLBACK', '<'*10)
        # self.connection.rollback()
        self.cursor.execute("ROLLBACK")
        log.msg(interface=iaxiom.IStatEvent, stat_rollbacks=1)

    def revert(self):
        self._rollback()
        self._inMemoryRollback()

    def _inMemoryRollback(self):
        self._rejectChanges += 1
        try:
            for item in self.transaction:
                item.revert()
        finally:
            self._rejectChanges -= 1
        self.transaction.clear()
        for tableClass in self.tablesCreatedThisTransaction:
            del self.typenameAndVersionToID[tableClass.typeName,
                                            tableClass.schemaVersion]
            # Clear all cache related to this table
            for cache in (self.typeToInsertSQLCache,
                          self.typeToDeleteSQLCache,
                          self.typeToSelectSQLCache,
                          self.typeToTableNameCache) :
                if tableClass in cache:
                    del cache[tableClass]
            if tableClass.storeID in self.attrToColumnNameCache:
                del self.attrToColumnNameCache[tableClass.storeID]
            for name, attr in tableClass.getSchema():
                if attr in self.attrToColumnNameCache:
                    del self.attrToColumnNameCache[attr]

        for sub in list(self._attachedChildren.values()):
            sub._inMemoryRollback()

    def _cleanupTxnState(self):
        self.autocommit = True
        self.transaction = None
        self.touched = None
        self.executedThisTransaction = None
        self.tablesCreatedThisTransaction = []
        for sub in list(self._attachedChildren.values()):
            sub._cleanupTxnState()

    def close(self, _report=True):
        self.cursor.close()
        self.connection.close()
        self.cursor = self.connection = None
        if self.debug and _report:
            if not self.queryTimes:
                print('no queries')
            else:
                print('query:', self.avgms(self.queryTimes))
            if not self.execTimes:
                print('no execs')
            else:
                print('exec:', self.avgms(self.execTimes))

    def avgms(self, l):
        return 'count: %d avg: %dus' % (len(l),
                                        int( (sum(l)/len(l)) * 1000000.),)

    def _indexNameOf(self, tableClass, attrname):
        """
        Return the unqualified (ie, no database name) name of the given
        attribute of the given table.

        @type tableClass: L{MetaItem}
        @param tableClass: The Python class associated with a table in the
            database.

        @param attrname: A sequence of the names of the columns of the
            indicated table which will be included in the named index.

        @return: A C{str} giving the name of the index which will index the
            given attributes of the given table.
        """
        return "axiomidx_%s_v%d_%s" % (tableClass.typeName,
                                       tableClass.schemaVersion,
                                       '_'.join(attrname))

    def _tableNameFor(self, typename, version):
        return "%s.item_%s_v%d" % (self.databaseName, typename, version)


    def getTableName(self, tableClass):
        """
        Retrieve the fully qualified name of the table holding items
        of a particular class in this store.  If the table does not
        exist in the database, it will be created as a side-effect.

        @param tableClass: an Item subclass

        @raises axiom.errors.ItemClassesOnly: if an object other than a
            subclass of Item is passed.

        @return: a string
        """
        if not (isinstance(tableClass, type) and issubclass(tableClass, item.Item)):
            raise errors.ItemClassesOnly("Only subclasses of Item have table names.")

        if tableClass not in self.typeToTableNameCache:
            self.typeToTableNameCache[tableClass] = self._tableNameFor(tableClass.typeName, tableClass.schemaVersion)
            # make sure the table exists
            self.getTypeID(tableClass)
        return self.typeToTableNameCache[tableClass]

    def getShortColumnName(self, attribute):
        """
        Retreive the column name for a particular attribute in this
        store.  The attribute must be bound to an Item subclass (its
        type must be valid). If the underlying table does not exist in
        the database, it will be created as a side-effect.

        @param tableClass: an Item subclass

        @return: a string

        XXX: The current implementation does not really match the
        description, which is actually more restrictive. But it will
        be true soon, so I guess it is ok for now.  The reason is
        that this method is used during table creation.
        """
        if isinstance(attribute, _StoreIDComparer):
            return 'oid'
        return '[' + attribute.attrname + ']'

    def getColumnName(self, attribute):
        """
        Retreive the fully qualified column name for a particular
        attribute in this store.  The attribute must be bound to an
        Item subclass (its type must be valid). If the underlying
        table does not exist in the database, it will be created as a
        side-effect.

        @param tableClass: an Item subclass

        @return: a string
        """
        if attribute not in self.attrToColumnNameCache:
            self.attrToColumnNameCache[attribute] = '.'.join(
                (self.getTableName(attribute.type),
                 self.getShortColumnName(attribute)))
        return self.attrToColumnNameCache[attribute]

    def getTypeID(self, tableClass):
        """
        Retrieve the typeID associated with a particular table in the
        in-database schema for this Store.  A typeID is an opaque integer
        representing the Item subclass, and the associated table in this
        Store's SQLite database.

        @param tableClass: a subclass of Item

        @return: an integer
        """
        key = (tableClass.typeName,
               tableClass.schemaVersion)
        if key in self.typenameAndVersionToID:
            return self.typenameAndVersionToID[key]
        return self.transact(self._maybeCreateTable, tableClass, key)

    def _maybeCreateTable(self, tableClass, key):
        """
        A type ID has been requested for an Item subclass whose table was not
        present when this Store was opened.  Attempt to create the table, and
        if that fails because another Store object (perhaps in another process)
        has created the table, re-read the schema.  When that's done, return
        the typeID.

        This method is internal to the implementation of getTypeID.  It must be
        run in a transaction.

        @param tableClass: an Item subclass
        @param key: a 2-tuple of the tableClass's typeName and schemaVersion

        @return: a typeID for the table; a new one if no table exists, or the
        existing one if the table was created by another Store object
        referencing this database.
        """
        sqlstr = []
        sqlarg = []

        # needs to be calculated including version
        tableName = self._tableNameFor(tableClass.typeName,
                                       tableClass.schemaVersion)

        sqlstr.append("CREATE TABLE %s (" % tableName)

        for nam, atr in tableClass.getSchema():
            # it's a stored attribute
            sqlarg.append("\n%s %s" %
                          (atr.getShortColumnName(self), atr.sqltype))

        if len(sqlarg) == 0:
            # XXX should be raised way earlier, in the class definition or something
            raise NoEmptyItems("%r did not define any attributes" % (tableClass,))

        sqlstr.append(', '.join(sqlarg))
        sqlstr.append(')')

        try:
            self.createSQL(''.join(sqlstr))
        except errors.TableAlreadyExists:
            # Although we don't have a memory of this table from the last time
            # we called "_startup()", another process has updated the schema
            # since then.
            self._startup()
            return self.typenameAndVersionToID[key]

        typeID = self.executeSchemaSQL(_schema.CREATE_TYPE,
                                       [tableClass.typeName,
                                        tableClass.__module__,
                                        tableClass.schemaVersion])

        self.typenameAndVersionToID[key] = typeID

        if self.tablesCreatedThisTransaction is not None:
            self.tablesCreatedThisTransaction.append(tableClass)

        # If the new type is a legacy type (not the current version), we need
        # to queue it for upgrade to ensure that if we are in the middle of an
        # upgrade, legacy items of this version get upgraded.
        cls = _typeNameToMostRecentClass.get(tableClass.typeName)
        if cls is not None and tableClass.schemaVersion != cls.schemaVersion:
            self._upgradeManager.queueTypeUpgrade(tableClass)

        # We can pass () for extantIndexes here because since the table didn't
        # exist for tableClass, none of its indexes could have either.
        # Whatever checks _createIndexesFor will make would give the same
        # result against the actual set of existing indexes as they will
        # against ().
        self._createIndexesFor(tableClass, ())

        for n, (name, storedAttribute) in enumerate(tableClass.getSchema()):
            self.executeSchemaSQL(
                _schema.ADD_SCHEMA_ATTRIBUTE,
                [typeID, n, storedAttribute.indexed, storedAttribute.sqltype,
                 storedAttribute.allowNone, storedAttribute.attrname,
                 storedAttribute.doc, storedAttribute.__class__.__name__])
            # XXX probably need something better for pythontype eventually,
            # when we figure out a good way to do user-defined attributes or we
            # start parameterizing references.

        return typeID

    def _createIndexesFor(self, tableClass, extantIndexes):
        """
        Create any indexes which don't exist and are required by the schema
        defined by C{tableClass}.

        @param tableClass: A L{MetaItem} instance which may define a schema
            which includes indexes.

        @param extantIndexes: A container (anything which can be the right-hand
            argument to the C{in} operator) which contains the unqualified
            names of all indexes which already exist in the underlying database
            and do not need to be created.
        """
        try:
            indexes = _requiredTableIndexes[tableClass]
        except KeyError:
            indexes = set()
            for nam, atr in tableClass.getSchema():
                if atr.indexed:
                    indexes.add(((atr.getShortColumnName(self),), (atr.attrname,)))
                for compound in atr.compoundIndexes:
                    indexes.add((tuple(inatr.getShortColumnName(self) for inatr in compound),
                                 tuple(inatr.attrname for inatr in compound)))
            _requiredTableIndexes[tableClass] = indexes

        # _ZOMFG_ SQL is such a piece of _shit_: you can't fully qualify the
        # table name in CREATE INDEX statements because the _INDEX_ is fully
        # qualified!

        indexColumnPrefix = '.'.join(self.getTableName(tableClass).split(".")[1:])

        for (indexColumns, indexAttrs) in indexes:
            nameOfIndex = self._indexNameOf(tableClass, indexAttrs)
            if nameOfIndex in extantIndexes:
                continue
            csql = 'CREATE INDEX %s.%s ON %s(%s)' % (
                self.databaseName, nameOfIndex, indexColumnPrefix,
                ', '.join(indexColumns))
            self.createSQL(csql)

    def getTableQuery(self, typename, version):
        if (typename, version) not in self.tableQueries:
            query = 'SELECT * FROM %s WHERE oid = ?' % (
                self._tableNameFor(typename, version), )
            self.tableQueries[typename, version] = query
        return self.tableQueries[typename, version]

    def getItemByID(self, storeID, default=_noItem, autoUpgrade=True):
        """
        Retrieve an item by its storeID, and return it.

        Note: most of the failure modes of this method are catastrophic and
        should not be handled by application code.  The only one that
        application programmers should be concerned with is KeyError.  They are
        listed for educational purposes.

        @param storeID: an L{int} which refers to the store.

        @param default: if passed, return this value rather than raising in the
        case where no Item is found.

        @raise TypeError: if storeID is not an integer.

        @raise UnknownItemType: if the storeID refers to an item row in the
        database, but the corresponding type information is not available to
        Python.

        @raise RuntimeError: if the found item's class version is higher than
        the current application is aware of.  (In other words, if you have
        upgraded a database to a new schema and then attempt to open it with a
        previous version of the code.)

        @raise KeyError: if no item corresponded to the given storeID.

        @return: an Item, or the given default, if it was passed and no row
        corresponding to the given storeID can be located in the database.
        """

        if not isinstance(storeID, int):
            raise TypeError("storeID *must* be an int or long, not %r" % (
                    type(storeID).__name__,))
        if storeID == STORE_SELF_ID:
            return self
        try:
            return self.objectCache.get(storeID)
        except KeyError:
            pass
        log.msg(interface=iaxiom.IStatEvent, stat_cache_misses=1, key=storeID)
        results = self.querySchemaSQL(_schema.TYPEOF_QUERY, [storeID])
        assert (len(results) in [1, 0]),\
            "Database panic: more than one result for TYPEOF!"
        if results:
            typename, module, version = results[0]
            # for the moment we're going to assume no inheritance
            attrs = self.querySQL(self.getTableQuery(typename, version),
                                  [storeID])
            if len(attrs) != 1:
                if default is _noItem:
                    raise errors.ItemNotFound("No results for known-to-be-good object")
                return default
            attrs = attrs[0]
            useMostRecent = False
            moreRecentAvailable = False

            # The schema may have changed since the last time I saw the
            # database.  Let's look to see if this is suspiciously broken...

            if _typeIsTotallyUnknown(typename, version):
                # Another process may have created it - let's re-up the schema
                # and see what we get.
                self._startup()

                # OK, all the modules have been loaded now, everything
                # verified.
                if _typeIsTotallyUnknown(typename, version):

                    # If there is STILL no inkling of it anywhere, we are
                    # almost certainly boned.  Let's tell the user in a
                    # structured way, at least.
                    raise errors.UnknownItemType(
                        "cannot load unknown schema/version pair: %r %r - id: %r" %
                        (typename, version, storeID))

            if typename in _typeNameToMostRecentClass:
                moreRecentAvailable = True
                mostRecent = _typeNameToMostRecentClass[typename]

                if mostRecent.schemaVersion < version:
                    raise RuntimeError("%s:%d - was found in the database and most recent %s is %d" %
                                       (typename, version, typename, mostRecent.schemaVersion))
                if mostRecent.schemaVersion == version:
                    useMostRecent = True
            if useMostRecent:
                T = mostRecent
            else:
                T = self.getOldVersionOf(typename, version)
            x = T.existingInStore(self, storeID, attrs)
            if moreRecentAvailable and (not useMostRecent) and autoUpgrade:
                # upgradeVersion will do caching as necessary, we don't have to
                # cache here.  (It must, so that app code can safely call
                # upgradeVersion and get a consistent object out of it.)
                x = self.transact(self._upgradeManager.upgradeItem, x)
            elif not x.__legacy__:
                # We loaded the most recent version of an object
                self.objectCache.cache(storeID, x)
            return x
        if default is _noItem:
            raise KeyError(storeID)
        return default

    def querySchemaSQL(self, sql, args=()):
        sql = sql.replace("*DATABASE*", self.databaseName)
        return self.querySQL(sql, args)

    def querySQL(self, sql, args=()):
        """For use with SELECT (or SELECT-like PRAGMA) statements.
        """
        if self.debug:
            result = timeinto(self.queryTimes, self._queryandfetch, sql, args)
        else:
            result = self._queryandfetch(sql, args)
        return result

    def _queryandfetch(self, sql, args):
        if self.debug:
            print('**', sql, '--', ', '.join(map(str, args)))
        self.cursor.execute(sql, args)
        before = time.time()
        result = list(self.cursor)
        after = time.time()
        if after - before > 2.0:
            log.msg('Extremely long list(cursor): %s' % (after - before,))
            log.msg(sql)
            # import traceback; traceback.print_stack()
        if self.debug:
            print('  lastrow:', self.cursor.lastRowID())
            print('  result:', result)
        return result

    def createSQL(self, sql, args=()):
        """
        For use with auto-committing statements such as CREATE TABLE or CREATE
        INDEX.
        """
        before = time.time()
        self._execSQL(sql, args)
        after = time.time()
        if after - before > 2.0:
            log.msg('Extremely long CREATE: %s' % (after - before,))
            log.msg(sql)
            # import traceback; traceback.print_stack()

    def _execSQL(self, sql, args):
        if self.debug:
            rows = timeinto(self.execTimes, self._queryandfetch, sql, args)
        else:
            rows = self._queryandfetch(sql, args)
        assert not rows
        return sql

    def executeSchemaSQL(self, sql, args=()):
        sql = sql.replace("*DATABASE*", self.databaseName)
        return self.executeSQL(sql, args)

    def executeSQL(self, sql, args=()):
        """
        For use with UPDATE or INSERT statements.
        """
        sql = self._execSQL(sql, args)
        result = self.cursor.lastRowID()
        if self.executedThisTransaction is not None:
            self.executedThisTransaction.append((result, sql, args))
        return result

# This isn't actually useful any more.  It turns out that the pysqlite
# documentation is confusingly worded; it's perfectly possible to create tables
# within transactions, but PySQLite's automatic transaction management (which
# we turn off) breaks that.  However, a function very much like it will be
# useful for doing nested transactions without support from the database
# itself, so I'm keeping it here commented out as an example.

#     def _reexecute(self):
#         assert self.executedThisTransaction is not None
#         self._begin()
#         for resultLastTime, sql, args in self.executedThisTransaction:
#             self._execSQL(sql, args)
#             resultThisTime = self.cursor.lastRowID()
#             if resultLastTime != resultThisTime:
#                 raise errors.TableCreationConcurrencyError(
#                     "Expected to get %s as a result "
#                     "of %r:%r, got %s" % (
#                         resultLastTime,
#                         sql, args,
#                         resultThisTime))


def timeinto(l, f, *a, **k):
    then = time.time()
    try:
        return f(*a, **k)
    finally:
        now = time.time()
        elapsed = now - then
        l.append(elapsed)

queryTimes = []
execTimes = []
