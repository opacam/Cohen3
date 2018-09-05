from twisted.internet.defer import Deferred
from twisted.python.failure import Failure


class PendingEvent(object):
    def __init__(self):
        self.listeners = []

    def deferred(self):
        d = Deferred()
        self.listeners.append(d)
        return d

    def callback(self, result):
        lis = self.listeners
        self.listeners = []
        for d in lis:
            d.callback(result)

    def errback(self, result=None):
        if result is None:
            result = Failure()
        lis = self.listeners
        self.listeners = []
        for d in lis:
            d.errback(result)
