# -*- test-case-name: epsilon.test.test_structlike -*-

"""
This module implements convenience objects for classes which have initializers
and repr()s that describe a fixed set of attributes.
"""

from twisted.python import context

_NOT_SPECIFIED = object()


class _RecursiveReprer(object):
    """
    This object maintains state so that repr()s can tell when they are
    recursing and not do so.
    """

    def __init__(self):
        self.active = {}

    def recursiveRepr(self, stuff, thunk=repr):
        """
        Recursive repr().
        """
        ID = id(stuff)
        if ID in self.active:
            return '%s(...)' % (stuff.__class__.__name__,)
        else:
            try:
                self.active[ID] = stuff
                return thunk(stuff)
            finally:
                del self.active[ID]


def _contextualize(contextFactory, contextReceiver):
    """
    Invoke a callable with an argument derived from the current execution
    context (L{twisted.python.context}), or automatically created if none is
    yet present in the current context.

    This function, with a better name and documentation, should probably be
    somewhere in L{twisted.python.context}.  Calling context.get() and
    context.call() individually is perilous because you always have to handle
    the case where the value you're looking for isn't present; this idiom
    forces you to supply some behavior for that case.

    @param contextFactory: An object which is both a 0-arg callable and
    hashable; used to look up the value in the context, set the value in the
    context, and create the value (by being called).

    @param contextReceiver: A function that receives the value created or
    identified by contextFactory.  It is a 1-arg callable object, called with
    the result of calling the contextFactory, or retrieving the contextFactory
    from the context.
    """
    value = context.get(contextFactory, _NOT_SPECIFIED)
    if value is not _NOT_SPECIFIED:
        return contextReceiver(value)
    else:
        return context.call({contextFactory: contextFactory()},
                            _contextualize, contextFactory, contextReceiver)


class StructBehavior(object):
    __names__ = []
    __defaults__ = []

    def __init__(self, *args, **kw):
        super(StructBehavior, self).__init__()

        # Turn all the args into kwargs
        if len(args) > len(self.__names__):
            raise TypeError(
                "Got %d positional arguments but expected no more than %d" %
                (len(args), len(self.__names__)))

        for n, v in zip(self.__names__, args):
            if n in kw:
                raise TypeError("Got multiple values for argument " + n)
            kw[n] = v

        # Fill in defaults
        for n, v in zip(self.__names__[::-1], self.__defaults__[::-1]):
            if n not in kw:
                kw[n] = v

        for n in self.__names__:
            if n not in kw:
                raise TypeError('Specify a value for %r' % (n,))
            setattr(self, n, kw.pop(n))

        if kw:
            raise TypeError('Got unexpected arguments: ' + ', '.join(kw))

    def __repr__(self):
        """
        Generate a string representation.
        """

        def doit(rr):
            def _recordrepr(self2):
                """
                Internal implementation of repr() for this record.
                """
                return '%s(%s)' % (
                    self.__class__.__name__,
                    ', '.join(["%s=%s" %
                               (n, repr(getattr(self, n, None)))
                               for n in self.__names__]))

            return rr.recursiveRepr(self, _recordrepr)

        return _contextualize(_RecursiveReprer, doit)


def record(*a, **kw):
    """
    Are you tired of typing class declarations that look like this::

        class StuffInfo:
            def __init__(self, a=None, b=None, c=None, d=None, e=None,
                         f=None, g=None, h=None, i=None, j=None):
                self.a = a
                self.b = b
                self.c = c
                self.d = d
                # ...

    Epsilon can help!  That's right - for a limited time only, this function
    returns a class which provides a shortcut.  The above can be simplified
    to::

        StuffInfo = record(a=None, b=None, c=None, d=None, e=None,
                           f=None, g=None, h=None, i=None, j=None)

    if the arguments are required, rather than having defaults, it could be
    even shorter::

        StuffInfo = record('a b c d e f g h i j')

    Put more formally: C{record} optionally takes one positional argument, a
    L{str} representing attribute names as whitespace-separated identifiers; it
    also takes an arbitrary number of keyword arguments, which map attribute
    names to their default values.  If no positional argument is provided, the
    names of attributes will be inferred from the names of the defaults
    instead.
    """
    if len(a) == 1:
        attributeNames = a[0].split()
    elif len(a) == 0:
        if not kw:
            raise TypeError("Attempted to define a record with no attributes.")
        attributeNames = list(kw.keys())
        attributeNames.sort()
    else:
        raise TypeError(
            "record must be called with zero or one positional arguments")

    # Work like Python: allow defaults specified backwards from the end
    defaults = []
    for attributeName in attributeNames:
        default = kw.pop(attributeName, _NOT_SPECIFIED)
        if defaults:
            if default is _NOT_SPECIFIED:
                raise TypeError(
                    "You must specify default values like in Python; "
                    "backwards from the end of the argument list, "
                    "with no gaps")
            else:
                defaults.append(default)
        elif default is not _NOT_SPECIFIED:
            defaults.append(default)
        else:
            # This space left intentionally blank.
            pass
    if kw:
        raise TypeError("The following defaults did not apply: %r" % (kw,))

    return type('Record<%s>' % (' '.join(attributeNames),),
                (StructBehavior,),
                dict(__names__=attributeNames,
                     __defaults__=defaults))
