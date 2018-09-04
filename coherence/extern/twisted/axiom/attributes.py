# -*- test-case-name: axiom.test.test_attributes,axiom.test.test_reference -*-

import os

from decimal import Decimal

from coherence.extern.twisted.epsilon import hotfix

hotfix.require('twisted', 'filepath_copyTo')

from zope.interface import implementer

from twisted.python import filepath
from twisted.python.deprecate import deprecated
from twisted.python.components import registerAdapter
from twisted.python.versions import Version

from coherence.extern.twisted.epsilon.extime import Time

from coherence.extern.twisted.axiom.slotmachine import Attribute as inmemory

from coherence.extern.twisted.axiom.errors import \
    NoCrossStoreReferences, BrokenReference

from coherence.extern.twisted.axiom.iaxiom import \
    IComparison, IOrdering, IColumn, IQuery

_NEEDS_FETCH = object()  # token indicating that a value was not found

__metaclass__ = type


class _ComparisonOperatorMuxer:
    """
    Collapse comparison operations into calls to a single method with varying
    arguments.
    """

    def compare(self, other, op):
        """
        Override this in a subclass.
        """
        raise NotImplementedError()

    def __eq__(self, other):
        return self.compare(other, '=')

    def __ne__(self, other):
        return self.compare(other, '!=')

    def __gt__(self, other):
        return self.compare(other, '>')

    def __lt__(self, other):
        return self.compare(other, '<')

    def __ge__(self, other):
        return self.compare(other, '>=')

    def __le__(self, other):
        return self.compare(other, '<=')


def compare(left, right, op):
    # interim: maybe we want objects later?  right now strings should be fine
    if IColumn.providedBy(right):
        return TwoAttributeComparison(left, op, right)
    elif right is None:
        if op == '=':
            negate = False
        elif op == '!=':
            negate = True
        else:
            raise TypeError(
                "None/NULL does not work with %s comparison" % (op,))
        return NullComparison(left, negate)
    else:
        # convert to constant usable in the database
        return AttributeValueComparison(left, op, right)


class _MatchingOperationMuxer:
    """
    Collapse string matching operations into calls to a single method with
    varying arguments.
    """

    def _like(self, negate, firstOther, *others):
        others = (firstOther,) + others
        likeParts = []

        allValues = True
        for other in others:
            if IColumn.providedBy(other):
                likeParts.append(LikeColumn(other))
                allValues = False
            elif other is None:
                # LIKE NULL is a silly condition, but it's allowed.
                likeParts.append(LikeNull())
                allValues = False
            else:
                likeParts.append(LikeValue(other))

        if allValues:
            likeParts = [LikeValue(''.join(others))]

        return LikeComparison(self, negate, likeParts)

    def like(self, *others):
        return self._like(False, *others)

    def notLike(self, *others):
        return self._like(True, *others)

    def startswith(self, other):
        return self._like(False, other, '%')

    def endswith(self, other):
        return self._like(False, '%', other)


_ASC = 'ASC'
_DESC = 'DESC'


class _OrderingMixin:
    """
    Provide the C{ascending} and C{descending} attributes to specify sort
    direction.
    """

    def _asc(self):
        return SimpleOrdering(self, _ASC)

    def _desc(self):
        return SimpleOrdering(self, _DESC)

    desc = descending = property(_desc)
    asc = ascending = property(_asc)


class _ContainableMixin:
    def oneOf(self, seq, negate=False):
        """
        Choose items whose attributes are in a fixed set.

        X.oneOf([1, 2, 3])

        Implemented with the SQL 'in' statement.
        """
        return SequenceComparison(self, seq, negate)

    def notOneOf(self, seq):
        return self.oneOf(seq, negate=True)


class Comparable(_ContainableMixin, _ComparisonOperatorMuxer,
                 _MatchingOperationMuxer, _OrderingMixin):
    """
    Helper for a thing that can be compared like an SQLAttribute (or is in fact
    an SQLAttribute).  Requires that 'self' have 'type' (Item-subclass) and
    'columnName' (str) attributes, as well as an 'infilter' method in the
    spirit of SQLAttribute, documented below.
    """

    # XXX TODO: improve error reporting

    def compare(self, other, sqlop):
        return compare(self, other, sqlop)


@implementer(IOrdering)
class SimpleOrdering:
    """
    Currently this class is mostly internal.  More documentation will follow as
    its interface is finalized.
    """

    # maybe this will be a useful public API, for the query something
    # something.

    isDescending = property(lambda self: self.direction == _DESC)
    isAscending = property(lambda self: self.direction == _ASC)

    def __init__(self, attribute, direction=''):
        self.attribute = attribute
        self.direction = direction

    def orderColumns(self):
        return [(self.attribute, self.direction)]

    def __repr__(self):
        return repr(self.attribute) + self.direction

    def __add__(self, other):
        if isinstance(other, SimpleOrdering):
            return CompoundOrdering([self, other])
        elif isinstance(other, (list, tuple)):
            return CompoundOrdering([self] + list(other))
        else:
            return NotImplemented

    def __radd__(self, other):
        if isinstance(other, SimpleOrdering):
            return CompoundOrdering([other, self])
        elif isinstance(other, (list, tuple)):
            return CompoundOrdering(list(other) + [self])
        else:
            return NotImplemented


@implementer(IOrdering)
class CompoundOrdering:
    """
    List of SimpleOrdering instances.
    """

    def __init__(self, seq):
        self.simpleOrderings = list(seq)

    def __repr__(self):
        return self.__class__.__name__ + '(' + repr(self.simpleOrderings) + ')'

    def __add__(self, other):
        """
        Just thinking about what might be useful from the perspective of
        introspecting on query objects... don't document this *too* thoroughly
        yet.
        """
        if isinstance(other, CompoundOrdering):
            return CompoundOrdering(
                self.simpleOrderings + other.simpleOrderings)
        elif isinstance(other, SimpleOrdering):
            return CompoundOrdering(self.simpleOrderings + [other])
        elif isinstance(other, (list, tuple)):
            return CompoundOrdering(self.simpleOrderings + list(other))
        else:
            return NotImplemented

    def __radd__(self, other):
        """
        Just thinking about what might be useful from the perspective of
        introspecting on query objects... don't document this *too* thoroughly
        yet.
        """
        if isinstance(other, CompoundOrdering):
            return CompoundOrdering(
                other.simpleOrderings + self.simpleOrderings)
        elif isinstance(other, SimpleOrdering):
            return CompoundOrdering([other] + self.simpleOrderings)
        elif isinstance(other, (list, tuple)):
            return CompoundOrdering(list(other) + self.simpleOrderings)
        else:
            return NotImplemented

    def orderColumns(self):
        x = []
        for o in self.simpleOrderings:
            x.extend(o.orderColumns())
        return x


@implementer(IOrdering)
class UnspecifiedOrdering:

    def __init__(self, null):
        pass

    def __add__(self, other):
        return IOrdering(other, NotImplemented)

    __radd__ = __add__

    def orderColumns(self):
        return []


registerAdapter(CompoundOrdering, list, IOrdering)
registerAdapter(CompoundOrdering, tuple, IOrdering)
registerAdapter(UnspecifiedOrdering, type(None), IOrdering)
registerAdapter(SimpleOrdering, Comparable, IOrdering)


def compoundIndex(*columns):
    for column in columns:
        column.compoundIndexes.append(columns)


@implementer(IColumn)
class SQLAttribute(inmemory, Comparable):
    """
    Abstract superclass of all attributes.

    _Not_ an attribute itself.

    @ivar indexed: A C{bool} indicating whether this attribute will be indexed
    in the database.

    @ivar default: The value used for this attribute, if no value is specified.
    """

    sqltype = None

    def __init__(self, doc='', indexed=False, default=None, allowNone=True,
                 defaultFactory=None):
        inmemory.__init__(self, doc)
        self.indexed = indexed
        self.compoundIndexes = []
        self.allowNone = allowNone
        self.default = default
        self.defaultFactory = defaultFactory
        if default is not None and defaultFactory is not None:
            raise ValueError("You may specify only one of default "
                             "or defaultFactory, not both")

    def computeDefault(self):
        if self.defaultFactory is not None:
            return self.defaultFactory()
        return self.default

    def reprFor(self, oself):
        return repr(self.__get__(oself))

    def getShortColumnName(self, store):
        return store.getShortColumnName(self)

    def getColumnName(self, store):
        return store.getColumnName(self)

    def prepareInsert(self, oself, store):
        """
        Override this method to do something to an item to prepare for its
        insertion into a database.
        """

    def coercer(self, value):
        """
        must return a value equivalent to the data being passed in for it to be
        considered valid for a value of this attribute.  for example, 'int' or
        'str'.
        """

        raise NotImplementedError()

    def infilter(self, pyval, oself, store):
        """
        used to convert a Python value to something that lives in the database;
        so called because it is called when objects go in to the database.  It
        takes a Python value and returns an SQL value.
        """
        raise NotImplementedError()

    def outfilter(self, dbval, oself):
        """
        used to convert an SQL value to something that lives in memory; so
        called because it is called when objects come out of the database.  It
        takes an SQL value and returns a Python value.
        """
        return dbval

    # requiredSlots must be called before it's run

    prefix = "_axiom_memory_"
    dbprefix = "_axiom_store_"

    def requiredSlots(self, modname, classname, attrname):
        self.modname = modname
        self.classname = classname
        self.attrname = attrname
        self.underlying = self.prefix + attrname
        self.dbunderlying = self.dbprefix + attrname
        yield self.underlying
        yield self.dbunderlying

    def fullyQualifiedName(self):
        return '.'.join([self.modname,
                         self.classname,
                         self.attrname])

    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, self.fullyQualifiedName())

    def type():
        def get(self):
            if self._type is None:
                from twisted.python.reflect import namedAny
                self._type = namedAny(self.modname + '.' + self.classname)
            return self._type

        return get,

    _type = None
    type = property(*type())

    def __get__(self, oself, cls=None):
        if cls is not None and oself is None:
            if self._type is not None:
                assert self._type == cls
            else:
                self._type = cls
            return self

        pyval = getattr(oself, self.underlying, _NEEDS_FETCH)
        if pyval is _NEEDS_FETCH:
            dbval = getattr(oself, self.dbunderlying, _NEEDS_FETCH)
            if dbval is _NEEDS_FETCH:
                # here is what *is* happening here:

                # SQL attributes are always loaded when an Item is created by
                # loading from the database, either via a query, a getItemByID
                # or an attribute access.  If an attribute is left un-set, that
                # means that the item it is on was just created, and we fill in
                # the default value.

                # Here is what *should be*, but *is not* happening here:

                # this condition ought to indicate that a value may exist in
                # the database, but it is not currently available in memory.
                # It would then query the database immediately, loading all
                # SQL-resident attributes related to this item to minimize the
                # number of queries run (e.g. rather than one per attribute)

                # this is a more desireable condition because it means that you
                # can create items "for free", so doing, for example,
                # self.bar.storeID is a much cheaper operation than doing
                # self.bar.baz.  This particular idiom is frequently used in
                # queries and so speeding it up to avoid having to do a
                # database hit unless you actually need an item's attributes
                # would be worthwhile.

                return self.default
            pyval = self.outfilter(dbval, oself)
            # An upgrader may have changed the value of this attribute.  If so,
            # return the new value, not the old one.
            if dbval != getattr(oself, self.dbunderlying):
                return self.__get__(oself, cls)
            # cache python value
            setattr(oself, self.underlying, pyval)
        return pyval

    def loaded(self, oself, dbval):
        """
        This method is invoked when the item is loaded from the database, and
        when a transaction is reverted which restores this attribute's value.

        @param oself: an instance of an item which has this attribute.

        @param dbval: the underlying database value which was retrieved.
        """
        setattr(oself, self.dbunderlying, dbval)
        delattr(oself, self.underlying)  # member_descriptors don't raise
        # attribute errors; what gives?  good
        # for us, I guess.

    def _convertPyval(self, oself, pyval):
        """
        Convert a Python value to a value suitable for inserting into the
        database.

        @param oself: The object on which this descriptor is an attribute.
        @param pyval: The value to be converted.
        @return: A value legal for this column in the database.
        """
        # convert to dbval later, I guess?
        if pyval is None and not self.allowNone:
            raise TypeError("attribute [%s.%s = %s()] must not be None" % (
                self.classname, self.attrname, self.__class__.__name__))

        return self.infilter(pyval, oself, oself.store)

    def __set__(self, oself, pyval):
        st = oself.store

        dbval = self._convertPyval(oself, pyval)
        oself.__dirty__[self.attrname] = self, dbval
        oself.touch()
        setattr(oself, self.underlying, pyval)
        setattr(oself, self.dbunderlying, dbval)
        if st is not None and st.autocommit:
            st._rejectChanges += 1
            try:
                oself.checkpoint()
            finally:
                st._rejectChanges -= 1


@implementer(IComparison)
class TwoAttributeComparison:

    def __init__(self, leftAttribute, operationString, rightAttribute):
        self.leftAttribute = leftAttribute
        self.operationString = operationString
        self.rightAttribute = rightAttribute

    def getQuery(self, store):
        sql = ('(%s %s %s)' % (self.leftAttribute.getColumnName(store),
                               self.operationString,
                               self.rightAttribute.getColumnName(store)))
        return sql

    def getInvolvedTables(self):
        tables = [self.leftAttribute.type]
        if self.leftAttribute.type is not self.rightAttribute.type:
            tables.append(self.rightAttribute.type)
        return tables

    def getArgs(self, store):
        return []

    def __repr__(self):
        return ' '.join((self.leftAttribute.fullyQualifiedName(),
                         self.operationString,
                         self.rightAttribute.fullyQualifiedName()))


@implementer(IComparison)
class AttributeValueComparison:

    def __init__(self, attribute, operationString, value):
        self.attribute = attribute
        self.operationString = operationString
        self.value = value

    def getQuery(self, store):
        return ('(%s %s ?)' % (self.attribute.getColumnName(store),
                               self.operationString))

    def getArgs(self, store):
        return [self.attribute.infilter(self.value, None, store)]

    def getInvolvedTables(self):
        return [self.attribute.type]

    def __repr__(self):
        return ' '.join((self.attribute.fullyQualifiedName(),
                         self.operationString,
                         repr(self.value)))


@implementer(IComparison)
class NullComparison:

    def __init__(self, attribute, negate=False):
        self.attribute = attribute
        self.negate = negate

    def getQuery(self, store):
        if self.negate:
            op = 'NOT'
        else:
            op = 'IS'
        return ('(%s %s NULL)' % (self.attribute.getColumnName(store),
                                  op))

    def getArgs(self, store):
        return []

    def getInvolvedTables(self):
        return [self.attribute.type]


class LikeFragment:
    def getLikeArgs(self):
        return []

    def getLikeQuery(self, st):
        raise NotImplementedError()

    def getLikeTables(self):
        return []


class LikeNull(LikeFragment):
    def getLikeQuery(self, st):
        return "NULL"


class LikeValue(LikeFragment):
    def __init__(self, value):
        self.value = value

    def getLikeQuery(self, st):
        return "?"

    def getLikeArgs(self):
        return [self.value]


class LikeColumn(LikeFragment):
    def __init__(self, attribute):
        self.attribute = attribute

    def getLikeQuery(self, st):
        return self.attribute.getColumnName(st)

    def getLikeTables(self):
        return [self.attribute.type]


@implementer(IComparison)
class LikeComparison:
    # Not AggregateComparison or AttributeValueComparison because there is a
    # different, optimized syntax for 'or'.  WTF is wrong with you, SQL??

    def __init__(self, attribute, negate, likeParts):
        self.negate = negate
        self.attribute = attribute
        self.likeParts = likeParts

    def getInvolvedTables(self):
        tables = [self.attribute.type]
        for lf in self.likeParts:
            tables.extend([
                t for t in lf.getLikeTables() if t not in tables])
        return tables

    def getQuery(self, store):
        if self.negate:
            op = 'NOT LIKE'
        else:
            op = 'LIKE'
        sqlParts = [lf.getLikeQuery(store) for lf in self.likeParts]
        sql = '(%s %s (%s))' % (self.attribute.getColumnName(store),
                                op, ' || '.join(sqlParts))
        return sql

    def getArgs(self, store):
        l = []
        for lf in self.likeParts:
            for pyval in lf.getLikeArgs():
                l.append(
                    self.attribute.infilter(
                        pyval, None, store))
        return l


@implementer(IComparison)
class AggregateComparison:
    """
    Abstract base class for compound comparisons that aggregate other
    comparisons - currently only used for AND and OR comparisons.
    """

    operator = None

    def __init__(self, *conditions):
        self.conditions = conditions
        if self.operator is None:
            raise NotImplementedError('%s cannot be used; you want AND or OR.'
                                      % self.__class__.__name__)
        if not conditions:
            raise ValueError('%s condition requires at least one argument'
                             % self.operator)

    def getQuery(self, store):
        oper = ' %s ' % self.operator
        return '(%s)' % oper.join(
            [condition.getQuery(store) for condition in self.conditions])

    def getArgs(self, store):
        args = []
        for cond in self.conditions:
            args += cond.getArgs(store)
        return args

    def getInvolvedTables(self):
        tables = []
        for cond in self.conditions:
            tables.extend([
                t for t in cond.getInvolvedTables() if t not in tables])
        return tables

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__,
                           ', '.join(map(repr, self.conditions)))


@implementer(IComparison)
class SequenceComparison:

    def __init__(self, attribute, container, negate):
        self.attribute = attribute
        self.container = container
        self.negate = negate

        if IColumn.providedBy(container):
            self.containerClause = self._columnContainer
            self.getArgs = self._columnArgs
        elif IQuery.providedBy(container):
            self.containerClause = self._queryContainer
            self.getArgs = self._queryArgs
        else:
            self.containerClause = self._sequenceContainer
            self.getArgs = self._sequenceArgs

    def _columnContainer(self, store):
        """
        Return the fully qualified name of the column being examined so as
        to push all of the containment testing into the database.
        """
        return self.container.getColumnName(store)

    def _columnArgs(self, store):
        """
        The IColumn form of this has no arguments, just a column name
        specified in the SQL, specified by _columnContainer.
        """
        return []

    _subselectSQL = None
    _subselectArgs = None

    def _queryContainer(self, store):
        """
        Generate and cache the subselect SQL and its arguments.  Return the
        subselect SQL.
        """
        if self._subselectSQL is None:
            sql, args = self.container._sqlAndArgs('SELECT',
                                                   self.container._queryTarget)
            self._subselectSQL, self._subselectArgs = sql, args
        return self._subselectSQL

    def _queryArgs(self, store):
        """
        Make sure subselect arguments have been generated and then return
        them.
        """
        self._queryContainer(store)
        return self._subselectArgs

    _sequence = None

    def _sequenceContainer(self, store):
        """
        Smash whatever we got into a list and save the result in case we are
        executed multiple times.  This keeps us from tripping up over
        generators and the like.
        """
        if self._sequence is None:
            self._sequence = list(self.container)
            self._clause = ', '.join(['?'] * len(self._sequence))
        return self._clause

    def _sequenceArgs(self, store):
        """
        Filter each element of the data using the attribute type being
        tested for containment and hand back the resulting list.
        """
        self._sequenceContainer(store)  # Force _sequence to be valid
        return [self.attribute.infilter(pyval, None, store) for pyval in
                self._sequence]

    # IComparison - getArgs is assigned as an instance attribute
    def getQuery(self, store):
        return '%s %sIN (%s)' % (
            self.attribute.getColumnName(store),
            self.negate and 'NOT ' or '',
            self.containerClause(store))

    def getInvolvedTables(self):
        return [self.attribute.type]


class AND(AggregateComparison):
    """
    Combine 2 L{IComparison}s such that this is true when both are true.
    """
    operator = 'AND'


class OR(AggregateComparison):
    """
    Combine 2 L{IComparison}s such that this is true when either is true.
    """
    operator = 'OR'


@implementer(IComparison)
class TableOrderComparisonWrapper(object):
    """
    Wrap any other L{IComparison} and override its L{getInvolvedTables} method
    to specify the same tables but in an explicitly specified order.
    """

    tables = None
    comparison = None

    def __init__(self, tables, comparison):
        assert set(tables) == set(comparison.getInvolvedTables())

        self.tables = tables
        self.comparison = comparison

    def getInvolvedTables(self):
        return self.tables

    def getQuery(self, store):
        return self.comparison.getQuery(store)

    def getArgs(self, store):
        return self.comparison.getArgs(store)


class boolean(SQLAttribute):
    sqltype = 'BOOLEAN'

    def infilter(self, pyval, oself, store):
        if pyval is None:
            return None
        if pyval is True:
            return 1
        elif pyval is False:
            return 0
        else:
            raise TypeError(
                "attribute [%s.%s = boolean()] must be True or False; not %r" %
                (self.classname, self.attrname, type(pyval).__name__,))

    def outfilter(self, dbval, oself):
        if dbval == 1:
            return True
        elif dbval == 0:
            return False
        elif self.allowNone and dbval is None:
            return None
        else:
            raise ValueError(
                "attribute [%s.%s = boolean()] "
                "must have a database value of 1 or 0; not %r" %
                (self.classname, self.attrname, dbval))


LARGEST_POSITIVE = (2 ** 63) - 1
LARGEST_NEGATIVE = -(2 ** 63)


class ConstraintError(TypeError):
    """A type constraint was violated.
    """

    def __init__(self,
                 attributeObj,
                 requiredTypes,
                 providedValue):
        self.attributeObj = attributeObj
        self.requiredTypes = requiredTypes
        self.providedValue = providedValue
        TypeError.__init__(self,
                           "attribute [%s.%s = %s()] must be "
                           "(%s); not %r" %
                           (attributeObj.classname,
                            attributeObj.attrname,
                            attributeObj.__class__.__name__,
                            requiredTypes,
                            type(providedValue).__name__))


def requireType(attributeObj, value, typerepr, *types):
    if not isinstance(value, types):
        raise ConstraintError(attributeObj,
                              typerepr,
                              value)


inttyperepr = "integer between %r and %r" % (
LARGEST_NEGATIVE, LARGEST_POSITIVE)


class integer(SQLAttribute):
    sqltype = 'INTEGER'

    def infilter(self, pyval, oself, store):
        if pyval is None:
            return None
        requireType(self, pyval, inttyperepr, int, int)
        if not LARGEST_NEGATIVE <= pyval <= LARGEST_POSITIVE:
            raise ConstraintError(
                self, inttyperepr, pyval)
        return pyval


class bytes(SQLAttribute):
    """
    Attribute representing a sequence of bytes; this is represented in memory
    as a Python 'str'.
    """

    sqltype = 'BLOB'

    def infilter(self, pyval, oself, store):
        if pyval is None:
            return None
        if isinstance(pyval, str):
            raise ConstraintError(self, "str or other byte buffer", pyval)
        return memoryview(pyval)

    def outfilter(self, dbval, oself):
        if dbval is None:
            return None
        return str(dbval)

    @deprecated(Version("Axiom", 0, 7, 5))
    def like(self, *others):
        return super(SQLAttribute, self).like(*others)

    @deprecated(Version("Axiom", 0, 7, 5))
    def notLike(self, *others):
        return super(SQLAttribute, self).notLike(*others)

    @deprecated(Version("Axiom", 0, 7, 5))
    def startswith(self, other):
        return super(SQLAttribute, self).startswith(other)

    @deprecated(Version("Axiom", 0, 7, 5))
    def endswith(self, other):
        return super(SQLAttribute, self).endswith(other)


class InvalidPathError(ValueError):
    """
    A path that could not be used with the database was attempted to be used
    with the database.
    """


class text(SQLAttribute):
    """
    Attribute representing a sequence of characters; this is represented in
    memory as a Python 'unicode'.
    """

    def __init__(self, caseSensitive=False, **kw):
        SQLAttribute.__init__(self, **kw)
        if caseSensitive:
            self.sqltype = 'TEXT'
        else:
            self.sqltype = 'TEXT COLLATE NOCASE'
        self.caseSensitive = caseSensitive

    def infilter(self, pyval, oself, store):
        if pyval is None:
            return None
        if not isinstance(pyval, str) or '\0' in pyval:
            raise ConstraintError(
                self, "unicode string without NULL bytes", pyval)
        return pyval

    def outfilter(self, dbval, oself):
        return dbval


class textlist(text):
    delimiter = '\u001f'

    # Once upon a time, textlist encoded the list in such a way that caused []
    # to be indistinguishable from [u'']. This value is now used as a
    # placeholder at the head of the list, to avoid this problem in a way that
    # is almost completely backwards-compatible with older databases.
    guard = '\u0002'

    def outfilter(self, dbval, oself):
        unicodeString = super(textlist, self).outfilter(dbval, oself)
        if unicodeString is None:
            return None
        val = unicodeString.split(self.delimiter)
        if val[:1] == [self.guard]:
            del val[:1]
        return val

    def infilter(self, pyval, oself, store):
        if pyval is None:
            return None
        for innerVal in pyval:
            assert self.delimiter not in innerVal and self.guard not in innerVal
        result = self.delimiter.join([self.guard] + list(pyval))
        return super(textlist, self).infilter(result, oself, store)


class path(text):
    """
    Attribute representing a pathname in the filesystem.  If 'relative=True',
    the default, the representative pathname object must be somewhere inside
    the store, and will migrate with the store.

    I expect L{twisted.python.filepath.FilePath} or compatible objects as my
    values.
    """

    def __init__(self, relative=True, **kw):
        text.__init__(self, **kw)
        self.relative = True

    def prepareInsert(self, oself, store):
        """
        Prepare for insertion into the database by making the dbunderlying
        attribute of the item a relative pathname with respect to the store
        rather than an absolute pathname.
        """
        if self.relative:
            fspath = self.__get__(oself)
            oself.__dirty__[self.attrname] = self, self.infilter(fspath, oself,
                                                                 store)

    def infilter(self, pyval, oself, store):
        if pyval is None:
            return None
        mypath = str(pyval.path)
        if store is None:
            store = oself.store
        if store is None:
            return None
        if self.relative:
            # XXX add some more filepath APIs to
            # make this kind of checking easier.
            storepath = os.path.normpath(store.filesdir.path)
            mysegs = mypath.split(os.sep)
            storesegs = storepath.split(os.sep)
            if len(mysegs) <= len(storesegs) or mysegs[
                                                :len(storesegs)] != storesegs:
                raise InvalidPathError('%s not in %s' % (mypath, storepath))
            # In the database we use '/' to separate paths for portability.
            # This databaes could have relative paths created on Windows, then
            # be moved to Linux for deployment, and what *was* the native
            # os.sep (backslash) will not be friendly to Linux's filesystem.
            # However, this is only for relative paths, since absolute or UNC
            # pathnames on a Windows system are inherently unportable and it's
            # not reasonable to calculate relative paths outside the store.
            p = '/'.join(mysegs[len(storesegs):])
        else:
            p = mypath  # we already know it's absolute, it came from a
            # filepath.
        return super(path, self).infilter(p, oself, store)

    def outfilter(self, dbval, oself):
        if dbval is None:
            return None
        if self.relative:
            fp = oself.store.filesdir
            for segment in dbval.split('/'):
                fp = fp.child(segment)
        else:
            fp = filepath.FilePath(dbval)
        return fp


MICRO = 1000000.


class timestamp(integer):
    """
    An in-database representation of date and time.

    To make formatting as easy as possible, this is represented in Python as an
    instance of L{epsilon.extime.Time}; see its documentation for more details.
    """

    def infilter(self, pyval, oself, store):
        if pyval is None:
            return None
        return integer.infilter(self,
                                int(pyval.asPOSIXTimestamp() * MICRO), oself,
                                store)

    def outfilter(self, dbval, oself):
        if dbval is None:
            return None
        return Time.fromPOSIXTimestamp(dbval / MICRO)


_cascadingDeletes = {}
_disallows = {}


class reference(integer):
    NULLIFY = object()
    DISALLOW = object()
    CASCADE = object()

    def __init__(self, doc='', indexed=True, allowNone=True, reftype=None,
                 whenDeleted=NULLIFY):
        integer.__init__(self, doc, indexed, None, allowNone)
        assert whenDeleted in (reference.NULLIFY,
                               reference.CASCADE,
                               reference.DISALLOW), (
            "whenDeleted must be one of: "
            "reference.NULLIFY, reference.CASCADE, reference.DISALLOW")
        self.reftype = reftype
        self.whenDeleted = whenDeleted
        if whenDeleted is reference.CASCADE:
            # Note; this list is technically in a slightly inconsistent state
            # as things are being built.
            _cascadingDeletes.setdefault(reftype, []).append(self)
        if whenDeleted is reference.DISALLOW:
            _disallows.setdefault(reftype, []).append(self)

    def reprFor(self, oself):
        obj = getattr(oself, self.underlying, None)
        if obj is not None:
            if obj.storeID is not None:
                return 'reference(%d)' % (obj.storeID,)
            else:
                return 'reference(unstored@%d)' % (id(obj),)
        sid = getattr(oself, self.dbunderlying, None)
        if sid is None:
            return 'None'
        return 'reference(%d)' % (sid,)

    def __get__(self, oself, cls=None):
        """
        Override L{integer.__get__} to verify that the value to be returned is
        currently a valid item in the same store, and to make sure that legacy
        items are upgraded if they happen to have been cached.
        """
        rv = super(reference, self).__get__(oself, cls)
        if rv is self:
            # If it's an attr lookup on the class, just do that.
            return self
        if rv is None:
            return rv
        if not rv._currentlyValidAsReferentFor(oself.store):
            # Make sure it's currently valid, i.e. it's not going to be deleted
            # this transaction or it hasn't been deleted.

            # XXX TODO: drop cached in-memory referent if it's been deleted /
            # no longer valid.
            assert self.whenDeleted is reference.NULLIFY, (
                "not sure what to do if not...")
            return None
        # If the current cached value is a legacy item, we discard it in order
        # to force another fetch from the database. However, if *this item* is
        # also a legacy item, then the item referred to may have been created
        # in an upgrader and not have been stored yet, so we shouldn't discard
        # it.
        if rv.__legacy__ and not oself.__legacy__:
            delattr(oself, self.underlying)
            return super(reference, self).__get__(oself, cls)
        return rv

    def prepareInsert(self, oself, store):
        oitem = super(reference, self).__get__(oself)  # bypass NULLIFY
        if oitem is not None and oitem.store is not store:
            raise NoCrossStoreReferences(
                "Trying to insert item: %r into store: %r, "
                "but it has a reference to other item: .%s=%r "
                "in another store: %r" % (
                    oself, store,
                    self.attrname, oitem,
                    oitem.store))

    def infilter(self, pyval, oself, store):
        if pyval is None:
            return None
        if oself is None:
            return pyval.storeID
        if oself.store is None:
            return pyval.storeID
        if oself.store != pyval.store:
            raise NoCrossStoreReferences(
                "You can't establish references to items in other stores.")

        return integer.infilter(self, pyval.storeID, oself, store)

    def outfilter(self, dbval, oself):
        if dbval is None:
            return None

        referee = oself.store.getItemByID(dbval, default=None,
                                          autoUpgrade=not oself.__legacy__)
        if referee is None and self.whenDeleted is not reference.NULLIFY:

            # If referee merely changed to another valid referent,
            # SQLAttribute.__get__ will notice that what we returned is
            # inconsistent and try again.  However, it doesn't know about the
            # BrokenReference that is raised if the old referee is no longer a
            # valid referent.  Check to see if the dbunderlying is still the
            # same as the dbval passed in.  If it's different, we should try to
            # load the value again.  Only if it is unchanged will we raise the
            # BrokenReference.  It would be better if all of this
            # change-detection logic were in one place, but I can't figure out
            # how to do that. -exarkun
            if dbval != getattr(oself, self.dbunderlying):
                return self.__get__(oself, None)

            raise BrokenReference(
                'Reference to storeID %r is broken' % (dbval,))
        return referee


class ieee754_double(SQLAttribute):
    """
    From the SQLite documentation::

        Each value stored in an SQLite database (or manipulated by the
        database engine) has one of the following storage classes: (...)
        REAL. The value is a floating point value, stored as an 8-byte IEEE
        floating point number.

    This attribute type implements IEEE754 double-precision binary
    floating-point storage.  Some people call this 'float', and think it is
    somehow related to numbers.  This assumption can be misleading when working
    with certain types of data.

    This attribute name has an unweildy name on purpose.  You should be aware
    of the caveats related to binary floating point math before using this
    type.  It is particularly ill-advised to use it to store values
    representing large amounts of currency as rounding errors may be
    significant enough to introduce accounting discrepancies.

    Certain edge-cases are not handled properly.  For example, INF and NAN are
    considered by SQLite to be equal to everything, rather than the Python
    interpretation where INF is equal only to itself and greater than
    everything, and NAN is equal to nothing, not even itself.
    """

    sqltype = 'REAL'

    def infilter(self, pyval, oself, store):
        if pyval is None:
            return None
        requireType(self, pyval, 'float', float)
        return pyval

    def outfilter(self, dbval, oself):
        return dbval


class AbstractFixedPointDecimal(integer):
    """
    Attribute representing a number with a specified number of decimal
    places.

    This is stored in SQLite as a binary integer multiplied by M{10**N}
    where C{N} is the number of decimal places required by Python. 
    Therefore, in-database multiplication, division, or queries which
    compare to integers or fixedpointdecimals with a different number of
    decimal places, will not work.  Also, you cannot store, or sum to, fixed
    point decimals greater than M{(2**63)/(10**N)}.

    While L{ieee754_double} is handy for representing various floating-point
    numbers, such as scientific measurements, this class (and the associated
    Python decimal class) is more appropriate for arithmetic on sums of money.

    For more information on Python's U{Decimal
    class<http://www.python.org/doc/current/lib/module-decimal.html>} and on
    general U{computerized Decimal math in
    general<http://www2.hursley.ibm.com/decimal/decarith.html>}.

    This is currently a private helper superclass because we cannot store
    additional metadata about column types; maybe we should fix that.

    @cvar decimalPlaces: the number of points of decimal precision allowed by
    the storage and retrieval of this class.  *Points beyond this number
    will be silently truncated to values passed into the database*, so be
    sure to select a value appropriate to your application!
    """

    def __init__(self, **kw):
        integer.__init__(self, **kw)

    def infilter(self, pyval, oself, store):
        if pyval is None:
            return None
        if isinstance(pyval, int):
            pyval = Decimal(pyval)
        if isinstance(pyval, Decimal):
            # Python < 2.5.2 compatibility:
            # Use to_integral instead of to_integral_value.
            dbval = int((pyval * 10 ** self.decimalPlaces).to_integral())
            return super(AbstractFixedPointDecimal, self).infilter(
                dbval, oself, store)
        else:
            raise TypeError(
                "attribute [%s.%s = AbstractFixedPointDecimal(...)] must be "
                "Decimal instance; not %r" % (
                    self.classname, self.attrname, type(pyval).__name__))

    def outfilter(self, dbval, oself):
        if dbval is None:
            return None
        return Decimal(dbval) / 10 ** self.decimalPlaces

    def compare(self, other, sqlop):
        if isinstance(other, Comparable):
            if isinstance(other, AbstractFixedPointDecimal):
                if other.decimalPlaces == self.decimalPlaces:
                    # fall through to default behavior at bottom
                    pass
                else:
                    raise TypeError(
                        "Can't compare Decimals of varying precisions: "
                        "(%s.%s %s %s.%s)" % (
                            self.classname, self.attrname,
                            sqlop,
                            other.classname, other.attrname
                        ))
            else:
                raise TypeError(
                    "Can't compare Decimals to other things: "
                    "(%s.%s %s %s.%s)" % (
                        self.classname, self.attrname,
                        sqlop,
                        other.classname, other.attrname
                    ))
        return super(AbstractFixedPointDecimal, self).compare(other, sqlop)


class point1decimal(AbstractFixedPointDecimal):
    decimalPlaces = 1


class point2decimal(AbstractFixedPointDecimal):
    decimalPlaces = 2


class point3decimal(AbstractFixedPointDecimal):
    decimalPlaces = 3


class point4decimal(AbstractFixedPointDecimal):
    decimalPlaces = 4


class point5decimal(AbstractFixedPointDecimal):
    decimalPlaces = 5


class point6decimal(AbstractFixedPointDecimal):
    decimalPlaces = 6


class point7decimal(AbstractFixedPointDecimal):
    decimalPlaces = 7


class point8decimal(AbstractFixedPointDecimal):
    decimalPlaces = 8


class point9decimal(AbstractFixedPointDecimal):
    decimalPlaces = 9


class point10decimal(AbstractFixedPointDecimal):
    decimalPlaces = 10


class money(point4decimal):
    """
    I am a 4-point precision fixed-point decimal number column type; suggested
    for representing a quantity of money.

    (This does not, however, include features such as currency.)
    """
