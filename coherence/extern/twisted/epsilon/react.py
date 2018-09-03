# -*- test-case-name: epsilon.test.test_react -*-
# Copyright (c) 2008 Divmod.  See LICENSE for details.

"""
Utilities for running the reactor for a while.
"""

from twisted.python.log import err


def react(reactor, main, argv):
    """
    Call C{main} and run the reactor until the L{Deferred} it returns fires.

    @param reactor: An unstarted L{IReactorCore} provider which will be run and
        later stopped.

    @param main: A callable which returns a L{Deferred}.  It should take as
        many arguments as there are elements in the list C{argv}.

    @param argv: A list of arguments to pass to C{main}.

    @return: C{None}
    """
    stopping = []
    reactor.addSystemEventTrigger('before', 'shutdown', stopping.append, True)
    finished = main(reactor, *argv)
    finished.addErrback(err, "main function encountered error")
    def cbFinish(ignored):
        if not stopping:
            reactor.callWhenRunning(reactor.stop)
    finished.addCallback(cbFinish)
    reactor.run()


