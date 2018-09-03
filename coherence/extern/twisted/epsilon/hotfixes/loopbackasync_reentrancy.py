
"""
Fix from Twisted r23970
"""

from twisted.internet.task import deferLater
from twisted.protocols.loopback import _loopbackAsyncBody

def _loopbackAsyncContinue(ignored, server, serverToClient, client, clientToServer):
    # Clear the Deferred from each message queue, since it has already fired
    # and cannot be used again.
    clientToServer._notificationDeferred = serverToClient._notificationDeferred = None

    # Schedule some more byte-pushing to happen.  This isn't done
    # synchronously because no actual transport can re-enter dataReceived as
    # a result of calling write, and doing this synchronously could result  
    # in that.
    from twisted.internet import reactor
    return deferLater(
        reactor, 0,   
        _loopbackAsyncBody, server, serverToClient, client, clientToServer)


def install():
    from twisted.protocols import loopback
    loopback._loopbackAsyncContinue = _loopbackAsyncContinue
