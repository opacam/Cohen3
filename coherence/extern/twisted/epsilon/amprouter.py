# -*- test-case-name: epsilon.test.test_amprouter -*-
# Copyright (c) 2008 Divmod.  See LICENSE for details.

"""
This module provides an implementation of I{Routes}, a system for multiplexing
multiple L{IBoxReceiver}/I{IBoxSender} pairs over a single L{AMP} connection.
"""

from itertools import count

from zope.interface import implementer

from twisted.protocols.amp import IBoxReceiver, IBoxSender

from coherence.extern.twisted.epsilon.structlike import record

__metaclass__ = type

_ROUTE = '_route'
_unspecified = object()


class RouteNotConnected(Exception):
    """
    An attempt was made to send AMP boxes through a L{Route} which is not yet
    connected to anything.
    """


@implementer(IBoxSender)
class Route(record('router receiver localRouteName remoteRouteName',
                   remoteRouteName=_unspecified)):
    """
    Wrap up a route name and a box sender to transparently add the route name
    to boxes sent through this box sender.

    @ivar router: The L{Router} which created this route.  This will be used
        for route tear down and for its L{IBoxSender}, to send boxes.

    @ivar receiver: The receiver which will be started with this object as its
        sender.

    @type localRouteName: C{unicode}
    @ivar localRouteName: The name of this route as known by the other side of
        the AMP connection.  AMP boxes with this route are expected to be
        routed to this object.

    @type remoteRouteName: C{unicode} or L{NoneType}
    @ivar remoteRouteName: The name of the route which will be added to all
        boxes sent to this sender.  If C{None}, no route will be added.
    """

    def connectTo(self, remoteRouteName):
        """
        Set the name of the route which will be added to outgoing boxes.
        """
        self.remoteRouteName = remoteRouteName
        # This route must not be started before its router is started.  If
        # sender is None, then the router is not started.  When the router is
        # started, it will start this route.
        if self.router._sender is not None:
            self.start()


    def unbind(self):
        """
        Remove the association between this route and its router.
        """
        del self.router._routes[self.localRouteName]


    def start(self):
        """
        Associate this object with a receiver as its L{IBoxSender}.
        """
        self.receiver.startReceivingBoxes(self)


    def stop(self, reason):
        """
        Shut down the underlying receiver.
        """
        self.receiver.stopReceivingBoxes(reason)


    def sendBox(self, box):
        """
        Add the route and send the box.
        """
        if self.remoteRouteName is _unspecified:
            raise RouteNotConnected()
        if self.remoteRouteName is not None:
            box[_ROUTE] = self.remoteRouteName.encode('ascii')
        self.router._sender.sendBox(box)


    def unhandledError(self, failure):
        """
        Pass failures through to the wrapped L{IBoxSender} without
        modification.
        """
        self.router._sender.unhandledError(failure)


@implementer(IBoxReceiver)
class Router:
    """
    An L{IBoxReceiver} implementation which demultiplexes boxes from an AMP
    connection being used with zero, one, or more routes.

    @ivar _sender: An L{IBoxSender} provider which is used to allow
        L{IBoxReceiver}s added to this router to send boxes.

    @ivar _unstarted: A C{dict} similar to C{_routes} set before
        C{startReceivingBoxes} is called and containing all routes which have
        been added but not yet started.  These are started and moved to the
        C{_routes} dict when the router is started.

    @ivar _routes: A C{dict} mapping local route identifiers to
        L{IBoxReceivers} associated with them.  This is only initialized after
        C{startReceivingBoxes} is called.

    @ivar _routeCounter: A L{itertools.count} instance used to generate unique
        identifiers for routes in this router.
    """

    _routes = None
    _sender = None

    def __init__(self):
        self._routeCounter = count()
        self._unstarted = {}


    def createRouteIdentifier(self):
        """
        Return a route identifier which is not yet associated with a route on
        this dispatcher.

        @rtype: C{unicode}
        """
        return str(next(self._routeCounter))


    def bindRoute(self, receiver, routeName=_unspecified):
        """
        Create a new route to associate the given route name with the given
        receiver.

        @type routeName: C{unicode} or L{NoneType}
        @param routeName: The identifier for the newly created route.  If
            C{None}, boxes with no route in them will be delivered to this
            receiver.

        @rtype: L{Route}
        """
        if routeName is _unspecified:
            routeName = self.createRouteIdentifier()
        # self._sender may yet be None; if so, this route goes into _unstarted
        # and will have its sender set correctly in startReceivingBoxes below.
        route = Route(self, receiver, routeName)
        mapping = self._routes
        if mapping is None:
            mapping = self._unstarted
        mapping[routeName] = route
        return route


    def startReceivingBoxes(self, sender):
        """
        Initialize route tracking objects.
        """
        self._sender = sender
        for routeName, route in self._unstarted.items():
            # Any route which has been bound but which does not yet have a
            # remote route name should not yet be started.  These will be
            # started in Route.connectTo.
            if route.remoteRouteName is not _unspecified:
                route.start()
        self._routes = self._unstarted
        self._unstarted = None


    def ampBoxReceived(self, box):
        """
        Dispatch the given box to the L{IBoxReceiver} associated with the route
        indicated by the box, or handle it directly if there is no route.
        """
        route = box.pop(_ROUTE, None)
        self._routes[route].receiver.ampBoxReceived(box)


    def stopReceivingBoxes(self, reason):
        """
        Stop all the L{IBoxReceiver}s which have been added to this router.
        """
        for routeName, route in self._routes.items():
            route.stop(reason)
        self._routes = None



__all__ = ['Router', 'Route']
