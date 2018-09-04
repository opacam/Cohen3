# -*- test-case-name: epsilon.test.test_remember -*-

"""
This module implements a utility for managing the lifecycle of attributes
related to a particular object.
"""

from coherence.extern.twisted.epsilon.structlike import record


class remembered(record('creationFunction')):
    """
    This descriptor decorator is applied to a function to create an attribute
    which will be created on-demand, but remembered for the lifetime of the
    instance to which it is attached.  Subsequent accesses of the attribute
    will return the remembered value.

    @ivar creationFunction: the decorated function, to be called to create the
        value.  This should be a 1-argument callable, that takes only a 'self'
        parameter, like a method.
    """

    value = None

    def __get__(self, oself, type):
        """
        Retrieve the value if already cached, otherwise, call the
        C{creationFunction} to create it.
        """
        remembername = "_remembered_" + self.creationFunction.__name__
        rememberedval = oself.__dict__.get(remembername, None)
        if rememberedval is not None:
            return rememberedval
        rememberme = self.creationFunction(oself)
        oself.__dict__[remembername] = rememberme
        return rememberme


__all__ = ['remembered']
