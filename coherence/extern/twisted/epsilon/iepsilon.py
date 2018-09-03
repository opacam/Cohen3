# Copyright (c) 2008 Divmod.  See LICENSE for details.

"""
Epsilon interfaces.
"""
from zope.interface import Attribute

from twisted.cred.credentials import ICredentials


class IOneTimePad(ICredentials):
    """
    A type of opaque credential for authenticating users, which can be used
    only a single time.

    This interface should also be responsible for authenticating.  See #2784.
    """
    padValue = Attribute(
        """
        C{str} giving the value of the one-time pad.  The value will be
        compared by a L{twisted.cred.checkers.ICredentialsChecker} (e.g.
        L{epsilon.ampauth.OneTimePadChecker}) against all valid one-time pads.
        If there is a match, login will be successful and the pad will be
        invalidated (further attempts to use it will fail).
        """)
