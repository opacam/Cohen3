
from twisted.python import failure
from twisted.internet import  defer

def getResult(self):
    if isinstance(self.result, failure.Failure):
        self.result.raiseException()
    return self.result


def _deferGenerator(g, deferred=None):
    """
    See L{waitForDeferred}.
    """
    result = None
    while 1:
        if deferred is None:
            deferred = defer.Deferred()
        try:
            result = next(g)
        except StopIteration:
            deferred.callback(result)
            return deferred
        except:
            deferred.errback()
            return deferred

        # Deferred.callback(Deferred) raises an error; we catch this case
        # early here and give a nicer error message to the user in case
        # they yield a Deferred. Perhaps eventually these semantics may
        # change.
        if isinstance(result, defer.Deferred):
            return defer.fail(TypeError("Yield waitForDeferred(d), not d!"))

        if isinstance(result, defer.waitForDeferred):
            waiting = [True, None]
            # Pass vars in so they don't get changed going around the loop
            def gotResult(r, waiting=waiting, result=result):
                result.result = r
                if waiting[0]:
                    waiting[0] = False
                    waiting[1] = r
                else:
                    _deferGenerator(g, deferred)
            result.d.addBoth(gotResult)
            if waiting[0]:
                # Haven't called back yet, set flag so that we get reinvoked
                # and return from the loop
                waiting[0] = False
                return deferred
            result = None # waiting[1]


def install():
    getResult.__module__ = 'twisted.internet.defer'
    defer.waitForDeferred.getResult = getResult

    _deferGenerator.__module__ = 'twisted.internet.defer'
    defer._deferGenerator = _deferGenerator
