"""
Fix from Twisted r20480.
"""
from functools import cmp_to_key

from twisted.internet import base
from twisted.internet.task import Clock


def callLater(self, when, what, *a, **kw):
    """
    Copied from twisted.internet.task.Clock, r20480.  Fixes the bug
    where the wrong DelayedCall would sometimes be returned.
    """
    dc = base.DelayedCall(self.seconds() + when,
                          what, a, kw,
                          self.calls.remove,
                          lambda c: None,
                          self.seconds)
    self.calls.append(dc)
    self.calls.sort(key=lambda x, y: cmp_to_key(x.getTime(), y.getTime()))
    return dc


def clockIsBroken():
    """
    Returns whether twisted.internet.task.Clock has the bug that
    returns the wrong DelayedCall or not.
    """
    clock = Clock()
    dc1 = clock.callLater(10, lambda: None)
    dc2 = clock.callLater(1, lambda: None)
    if dc1 is dc2:
        return True
    else:
        return False


def install():
    """
    Insert the fixed callLater method.
    """
    Clock.callLater = callLater
