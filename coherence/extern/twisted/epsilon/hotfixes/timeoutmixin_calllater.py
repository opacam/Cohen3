from twisted.internet import reactor


class TimeoutMixin:
    """Mixin for protocols which wish to timeout connections

    @cvar timeOut: The number of seconds after which to timeout the connection.
    """
    timeOut = None

    __timeoutCall = None

    def callLater(self, period, func):
        return reactor.callLater(period, func)

    def resetTimeout(self):
        """Reset the timeout count down"""
        if self.__timeoutCall is not None and self.timeOut is not None:
            self.__timeoutCall.reset(self.timeOut)

    def setTimeout(self, period):
        """Change the timeout period

        @type period: C{int} or C{NoneType}
        @param period: The period, in seconds, to change the timeout to, or
        C{None} to disable the timeout.
        """
        prev = self.timeOut
        self.timeOut = period

        if self.__timeoutCall is not None:
            if period is None:
                self.__timeoutCall.cancel()
                self.__timeoutCall = None
            else:
                self.__timeoutCall.reset(period)
        elif period is not None:
            self.__timeoutCall = self.callLater(period, self.__timedOut)

        return prev

    def __timedOut(self):
        self.__timeoutCall = None
        self.timeoutConnection()

    def timeoutConnection(self):
        """Called when the connection times out.
        Override to define behavior other than dropping the connection.
        """
        self.transport.loseConnection()


def install():
    global TimeoutMixin

    from twisted.protocols import policies
    policies.TimeoutMixin.__dict__ = TimeoutMixin.__dict__
    policies.TimeoutMixin.__dict__['module'] = 'twisted.protocols.policies'
    TimeoutMixin = policies.TimeoutMixin
