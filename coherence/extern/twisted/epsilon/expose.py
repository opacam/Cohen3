# Copright 2008 Divmod, Inc.  See LICENSE file for details.
# -*- test-case-name: epsilon.test.test_expose -*-

"""
This module provides L{Exposer}, a utility for creating decorators that expose
methods on types for a particular purpose.

The typical usage of this module is for an infrastructure layer (usually one
that allows methods to be invoked from the network, directly or indirectly) to
provide an explicit API for exposing those methods securely.

For example, a sketch of a finger protocol implementation which could use this
to expose the results of certain methods as finger results::

    # tx_finger.py
    fingermethod = Exposer("This object exposes finger methods.")
    ...
    class FingerProtocol(Protocol):
        def __init__(self, fingerModel):
            self.model = fingerModel
        ...
        def fingerQuestionReceived(self, whichUser):
            try:
                method = fingermethod.get(self.model, whichUser)
            except MethodNotExposed:
                method = lambda : "Unknown user"
            return method()

    # myfingerserver.py
    from tx_finger import fingermethod
    ...
    class MyFingerModel(object):
        @fingermethod.expose("bob")
        def someMethod(self):
            return "Bob is great."

Assuming lots of protocol code to hook everything together, this would then
allow you to use MyFingerModel and 'finger bob' to get the message 'Bob is
great.'
"""

import inspect

from types import FunctionType


class MethodNotExposed(Exception):
    """
    The requested method was not exposed for the purpose requested.  More
    specifically, L{Exposer.get} was used to retrieve a key from an object
    which does not expose that key with that exposer.
    """


class NameRequired(Exception):
    """
    L{Exposer.expose} was used to decorate a non-function object without having
    a key explicitly specified.
    """


class Exposer(object):
    """
    This is an object that can expose and retrieve methods on classes.

    @ivar _exposed: a dict mapping exposed keys to exposed function objects.
    """

    def __init__(self, doc):
        """
        Create an exposer.
        """
        self.__doc__ = doc
        self._exposed = {}

    def expose(self, key=None):
        """
        Expose the decorated method for this L{Exposer} with the given key.  A
        method which is exposed will be able to be retrieved by this
        L{Exposer}'s C{get} method with that key.  If no key is provided, the
        key is the method name of the exposed method.

        Use like so::

            class MyClass:
                @someExposer.expose()
                def foo(): ...

        or::

            class MyClass:
                @someExposer.expose('foo')
                def unrelatedMethodName(): ...

        @param key: a hashable object, used by L{Exposer.get} to look up the
        decorated method later.  If None, the key is the exposed method's name.

        @return: a 1-argument callable which records its input as exposed, then
        returns it.
        """
        def decorator(function):
            rkey = key
            if rkey is None:
                if isinstance(function, FunctionType):
                    rkey = function.__name__
                else:
                    raise NameRequired()
            if rkey not in self._exposed:
                self._exposed[rkey] = []
            self._exposed[rkey].append(function)
            return function
        return decorator

    def get(self, obj, key):
        """
        Retrieve 'key' from an instance of a class which previously exposed it.

        @param key: a hashable object, previously passed to L{Exposer.expose}.

        @return: the object which was exposed with the given name on obj's key.

        @raise MethodNotExposed: when the key in question was not exposed with
        this exposer.
        """
        if key not in self._exposed:
            raise MethodNotExposed()
        rightFuncs = self._exposed[key]
        T = obj.__class__
        seen = {}
        for subT in inspect.getmro(T):
            for name, value in list(subT.__dict__.items()):
                for rightFunc in rightFuncs:
                    if value is rightFunc:
                        if name in seen:
                            raise MethodNotExposed()
                        return value.__get__(obj, T)
                seen[name] = True
        raise MethodNotExposed()
