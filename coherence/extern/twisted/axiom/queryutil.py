# -*- test-case-name: axiom.test.test_queryutil -*-

import operator

from coherence.extern.twisted.axiom.attributes import AND, OR


def contains(startAttribute,
             endAttribute,
             value):
    """
    Return an L{axiom.iaxiom.IComparison} (an object that can be
    passed as the 'comparison' argument to Store.query/.sum/.count)
    which will constrain a query against 2 attributes for ranges which
    contain the given argument.  The range is half-open.
    """
    return AND(
        startAttribute <= value,
        value < endAttribute)


def overlapping(startAttribute,  # X
                endAttribute,  # Y
                startValue,  # A
                endValue,  # B
                ):
    """
    Return an L{axiom.iaxiom.IComparison} (an object that can be passed as the
    'comparison' argument to Store.query/.sum/.count) which will constrain a
    query against 2 attributes for ranges which overlap with the given
    arguments.

    For a database with Items of class O which represent values in this
    configuration::

              X                   Y
             (a)                 (b)
              |-------------------|
        (c)      (d)
         |--------|          (e)      (f)
                              |--------|

     (g) (h)
      |---|                            (i)    (j)
                                        |------|

     (k)                                   (l)
      |-------------------------------------|

             (a)                           (l)
              |-----------------------------|
        (c)                      (b)
         |------------------------|

        (c)  (a)
         |----|
                                 (b)       (l)
                                  |---------|

    The query::

        myStore.query(
            O,
            findOverlapping(O.X, O.Y,
                            a, b))

    Will return a generator of Items of class O which represent segments a-b,
    c-d, e-f, k-l, a-l, c-b, c-a and b-l, but NOT segments g-h or i-j.

    (NOTE: If you want to pass attributes of different classes for
    startAttribute and endAttribute, read the implementation of this method to
    discover the additional join clauses required.  This may be eliminated some
    day so for now, consider this method undefined over multiple classes.)

    In the database where this query is run, for an item N, all values of
    N.startAttribute must be less than N.endAttribute.

    startValue must be less than endValue.
    """
    assert startValue <= endValue

    return OR(
        AND(startAttribute >= startValue,
            startAttribute <= endValue),
        AND(endAttribute >= startValue,
            endAttribute <= endValue),
        AND(startAttribute <= startValue,
            endAttribute >= endValue)
    )


def _tupleCompare(tuple1, ineq, tuple2,
                  eq=lambda a, b: (a == b),
                  ander=AND,
                  orer=OR):
    """
    Compare two 'in-database tuples'.  Useful when sorting by a compound key
    and slicing into the middle of that query.
    """

    orholder = []
    for limit in range(len(tuple1)):
        eqconstraint = [
            eq(elem1, elem2) for elem1, elem2 in zip(tuple1, tuple2)[:limit]]
        ineqconstraint = ineq(tuple1[limit], tuple2[limit])
        orholder.append(ander(*(eqconstraint + [ineqconstraint])))
    return orer(*orholder)


def _tupleLessThan(tuple1, tuple2):
    return _tupleCompare(tuple1, operator.lt, tuple2)


def _tupleGreaterThan(tuple1, tuple2):
    return _tupleCompare(tuple1, operator.gt, tuple2)


class AttributeTuple(object):
    def __init__(self, *attributes):
        self.attributes = attributes

    def __iter__(self):
        return iter(self.attributes)

    def __eq__(self, other):
        if not isinstance(other, (AttributeTuple, tuple, list)):
            return NotImplemented
        return AND(*[
            myAttr == otherAttr
            for (myAttr, otherAttr)
            in zip(self, other)])

    def __ne__(self, other):
        if not isinstance(other, (AttributeTuple, tuple, list)):
            return NotImplemented
        return OR(*[
            myAttr != otherAttr
            for (myAttr, otherAttr)
            in zip(self, other)])

    def __gt__(self, other):
        if not isinstance(other, (AttributeTuple, tuple, list)):
            return NotImplemented
        return _tupleGreaterThan(tuple(iter(self)), other)

    def __lt__(self, other):
        if not isinstance(other, (AttributeTuple, tuple, list)):
            return NotImplemented
        return _tupleLessThan(tuple(iter(self)), other)

    def __ge__(self, other):
        if not isinstance(other, (AttributeTuple, tuple, list)):
            return NotImplemented
        return OR(self > other, self == other)

    def __le__(self, other):
        if not isinstance(other, (AttributeTuple, tuple, list)):
            return NotImplemented
        return OR(self < other, self == other)
