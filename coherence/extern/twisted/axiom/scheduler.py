# -*- test-case-name: axiom.test.test_scheduler -*-

"""
Timed event scheduling for Axiom databases.

With this module, applications can schedule an L{Item} to have its C{run} method
called at a particular point in the future.  This call will happen even if the
process which initially schedules it exits and the database is later re-opened
by another process (of course, if the scheduled time comes and goes while no
process is using the database, then the call will be delayed until some process
opens the database and starts its services).

This module contains two implementations of the L{axiom.iaxiom.IScheduler}
interface, one for site stores and one for sub-stores.  Items can only be
scheduled using an L{IScheduler} implementations from the store containing the
item.  This means a typical way to schedule an item to be run is::

    IScheduler(item.store).schedule(item, when)

The scheduler service can also be retrieved from the site store's service
collection by name::

    IServiceCollection(siteStore).getServiceNamed(SITE_SCHEDULER)
"""

import warnings

from zope.interface import implements

from twisted.internet import reactor

from twisted.application.service import IService, Service
from twisted.python import log, failure

from coherence.extern.twisted.epsilon.extime import Time

from coherence.extern.twisted.axiom.iaxiom import IScheduler
from coherence.extern.twisted.axiom.item import Item, declareLegacyItem
from coherence.extern.twisted.axiom.attributes import AND, timestamp, reference, integer, inmemory, bytes
from coherence.extern.twisted.axiom.dependency import uninstallFrom
from coherence.extern.twisted.axiom.upgrade import registerUpgrader
from coherence.extern.twisted.axiom.substore import SubStore

VERBOSE = False

SITE_SCHEDULER = "Site Scheduler"


class TimedEventFailureLog(Item):
    typeName = 'timed_event_failure_log'
    schemaVersion = 1

    desiredTime = timestamp()
    actualTime = timestamp()

    runnable = reference()
    traceback = bytes()


class TimedEvent(Item):
    typeName = 'timed_event'
    schemaVersion = 1

    time = timestamp(indexed=True)
    runnable = reference()

    running = inmemory(doc='True if this event is currently running.')

    def activate(self):
        self.running = False

    def _rescheduleFromRun(self, newTime):
        """
        Schedule this event to be run at the indicated time, or if the
        indicated time is None, delete this event.
        """
        if newTime is None:
            self.deleteFromStore()
        else:
            self.time = newTime

    def invokeRunnable(self):
        """
        Run my runnable, and reschedule or delete myself based on its result.
        Must be run in a transaction.
        """
        runnable = self.runnable
        if runnable is None:
            self.deleteFromStore()
        else:
            try:
                self.running = True
                newTime = runnable.run()
            finally:
                self.running = False
            self._rescheduleFromRun(newTime)

    def handleError(self, now, failureObj):
        """ An error occurred running my runnable.  Check my runnable for an
        error-handling method called 'timedEventErrorHandler' that will take
        the given failure as an argument, and execute that if available:
        otherwise, create a TimedEventFailureLog with information about what
        happened to this event.

        Must be run in a transaction.
        """
        errorHandler = getattr(self.runnable, 'timedEventErrorHandler', None)
        if errorHandler is not None:
            self._rescheduleFromRun(errorHandler(self, failureObj))
        else:
            self._defaultErrorHandler(now, failureObj)

    def _defaultErrorHandler(self, now, failureObj):
        TimedEventFailureLog(store=self.store,
                             desiredTime=self.time,
                             actualTime=now,
                             runnable=self.runnable,
                             traceback=failureObj.getTraceback())
        self.deleteFromStore()


class _WackyControlFlow(Exception):
    def __init__(self, eventObject, failureObject):
        Exception.__init__(self, "User code failed during timed event")
        self.eventObject = eventObject
        self.failureObject = failureObject


MAX_WORK_PER_TICK = 10


class SchedulerMixin:
    def _oneTick(self, now):
        theEvent = self._getNextEvent(now)
        if theEvent is None:
            return False
        try:
            theEvent.invokeRunnable()
        except:
            raise _WackyControlFlow(theEvent, failure.Failure())
        self.lastEventAt = now
        return True

    def _getNextEvent(self, now):
        # o/` gonna party like it's 1984 o/`
        theEventL = list(self.store.query(TimedEvent,
                                          TimedEvent.time <= now,
                                          sort=TimedEvent.time.ascending,
                                          limit=1))
        if theEventL:
            return theEventL[0]

    def tick(self):
        now = self.now()
        self.nextEventAt = None
        workBeingDone = True
        workUnitsPerformed = 0
        errors = 0
        while workBeingDone and workUnitsPerformed < MAX_WORK_PER_TICK:
            try:
                workBeingDone = self.store.transact(self._oneTick, now)
            except _WackyControlFlow as wcf:
                self.store.transact(wcf.eventObject.handleError, now, wcf.failureObject)
                log.err(wcf.failureObject)
                errors += 1
                workBeingDone = True
            if workBeingDone:
                workUnitsPerformed += 1
        x = list(self.store.query(TimedEvent, sort=TimedEvent.time.ascending, limit=1))
        if x:
            self._transientSchedule(x[0].time, now)
        if errors or VERBOSE:
            log.msg("The scheduler ran %(eventCount)s events%(errors)s." % dict(
                    eventCount=workUnitsPerformed,
                    errors=(errors and (" (with %d errors)" % (errors,))) or ''))

    def schedule(self, runnable, when):
        TimedEvent(store=self.store, time=when, runnable=runnable)
        self._transientSchedule(when, self.now())

    def reschedule(self, runnable, fromWhen, toWhen):
        for evt in self.store.query(TimedEvent,
                                    AND(TimedEvent.time == fromWhen,
                                        TimedEvent.runnable == runnable)):
            evt.time = toWhen
            self._transientSchedule(toWhen, self.now())
            break
        else:
            raise ValueError("%r is not scheduled to run at %r" % (runnable, fromWhen))

    def unscheduleFirst(self, runnable):
        """
        Remove from given item from the schedule.

        If runnable is scheduled to run multiple times, only the temporally first
        is removed.
        """
        for evt in self.store.query(TimedEvent, TimedEvent.runnable == runnable, sort=TimedEvent.time.ascending):
            evt.deleteFromStore()
            break

    def unscheduleAll(self, runnable):
        for evt in self.store.query(TimedEvent, TimedEvent.runnable == runnable):
            evt.deleteFromStore()

    def scheduledTimes(self, runnable):
        """
        Return an iterable of the times at which the given item is scheduled to
        run.
        """
        events = self.store.query(
            TimedEvent, TimedEvent.runnable == runnable)
        return (event.time for event in events if not event.running)


_EPSILON = 1e-20      # A very small amount of time.


class _SiteScheduler(SchedulerMixin, Service, object):
    """
    Adapter from a site store to L{IScheduler}.
    """
    implements(IScheduler)

    timer = None
    callLater = reactor.callLater
    now = Time

    def __init__(self, store):
        self.store = store
        self.setName(SITE_SCHEDULER)

    def startService(self):
        """
        Start calling persistent timed events whose time has come.
        """
        super(_SiteScheduler, self).startService()
        self._transientSchedule(self.now(), self.now())

    def stopService(self):
        """
        Stop calling persistent timed events.
        """
        super(_SiteScheduler, self).stopService()
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None

    def tick(self):
        self.timer = None
        return super(_SiteScheduler, self).tick()

    def _transientSchedule(self, when, now):
        """
        If the service is currently running, schedule a tick to happen no
        later than C{when}.

        @param when: The time at which to tick.
        @type when: L{epsilon.extime.Time}

        @param now: The current time.
        @type now: L{epsilon.extime.Time}
        """
        if not self.running:
            return
        if self.timer is not None:
            if self.timer.getTime() < when.asPOSIXTimestamp():
                return
            self.timer.cancel()
        delay = when.asPOSIXTimestamp() - now.asPOSIXTimestamp()

        # reactor.callLater allows only positive delay values.  The scheduler
        # may want to have scheduled things in the past and that's OK, since we
        # are dealing with Time() instances it's impossible to predict what
        # they are relative to the current time from user code anyway.
        delay = max(_EPSILON, delay)
        self.timer = self.callLater(delay, self.tick)
        self.nextEventAt = when


class _UserScheduler(SchedulerMixin, Service, object):
    """
    Adapter from a non-site store to L{IScheduler}.
    """
    implements(IScheduler)

    def __init__(self, store):
        self.store = store

    def now(self):
        """
        Report the current time, as reported by the parent's scheduler.
        """
        return IScheduler(self.store.parent).now()

    def _transientSchedule(self, when, now):
        """
        If this service's store is attached to its parent, ask the parent to
        schedule this substore to tick at the given time.

        @param when: The time at which to tick.
        @type when: L{epsilon.extime.Time}

        @param now: Present for signature compatibility with
            L{_SiteScheduler._transientSchedule}, but ignored otherwise.
        """
        if self.store.parent is not None:
            subStore = self.store.parent.getItemByID(self.store.idInParent)
            hook = self.store.parent.findOrCreate(
                _SubSchedulerParentHook,
                subStore=subStore)
            hook._schedule(when)

    def migrateDown(self):
        """
        Remove the components in the site store for this SubScheduler.
        """
        subStore = self.store.parent.getItemByID(self.store.idInParent)
        ssph = self.store.parent.findUnique(
            _SubSchedulerParentHook,
            _SubSchedulerParentHook.subStore == subStore,
            default=None)
        if ssph is not None:
            te = self.store.parent.findUnique(TimedEvent,
                                              TimedEvent.runnable == ssph,
                                              default=None)
            if te is not None:
                te.deleteFromStore()
            ssph.deleteFromStore()

    def migrateUp(self):
        """
        Recreate the hooks in the site store to trigger this SubScheduler.
        """
        te = self.store.findFirst(TimedEvent, sort=TimedEvent.time.descending)
        if te is not None:
            self._transientSchedule(te.time, None)


class _SchedulerCompatMixin(object):
    """
    Backwards compatibility helper for L{Scheduler} and L{SubScheduler}.

    This mixin provides all the attributes from L{IScheduler}, but provides
    them by adapting the L{Store} the item is in to L{IScheduler} and
    getting them from the resulting object.  Primarily in support of test
    code, it also supports rebinding those attributes by rebinding them on
    the L{IScheduler} powerup.

    @see: L{IScheduler}
    """
    implements(IScheduler)

    def forwardToReal(name):
        def get(self):
            return getattr(IScheduler(self.store), name)
        def set(self, value):
            setattr(IScheduler(self.store), name, value)
        return property(get, set)

    now = forwardToReal("now")
    tick = forwardToReal("tick")
    schedule = forwardToReal("schedule")
    reschedule = forwardToReal("reschedule")
    unschedule = forwardToReal("unschedule")
    unscheduleAll = forwardToReal("unscheduleAll")
    scheduledTimes = forwardToReal("scheduledTimes")

    def activate(self):
        """
        Whenever L{Scheduler} or L{SubScheduler} is created, either newly or
        when loaded from a database, emit a deprecation warning referring
        people to L{IScheduler}.
        """
        # This is unfortunate.  Perhaps it is the best thing which works (it is
        # the first I found). -exarkun
        if '_axiom_memory_dummy' in vars(self):
            stacklevel = 7
        else:
            stacklevel = 5
        warnings.warn(
            self.__class__.__name__ + " is deprecated since Axiom 0.5.32.  "
            "Just adapt stores to IScheduler.",
            category=PendingDeprecationWarning,
            stacklevel=stacklevel)


class Scheduler(Item, _SchedulerCompatMixin):
    """
    Track and execute persistent timed events for a I{site} store.

    This is deprecated and present only for backwards compatibility.  Adapt
    the store to L{IScheduler} instead.
    """
    implements(IService)

    typeName = 'axiom_scheduler'
    schemaVersion = 2

    dummy = integer()

    def activate(self):
        _SchedulerCompatMixin.activate(self)

    def setServiceParent(self, parent):
        """
        L{Scheduler} is no longer an L{IService}, but still provides this
        method as a no-op in case an instance which was still an L{IService}
        powerup is loaded (in which case it will be used like a service
        once).
        """


declareLegacyItem(
    Scheduler.typeName, 1,
    dict(eventsRun=integer(default=0),
         lastEventAt=timestamp(),
         nextEventAt=timestamp()))


def scheduler1to2(old):
    new = old.upgradeVersion(Scheduler.typeName, 1, 2)
    new.store.powerDown(new, IService)
    new.store.powerDown(new, IScheduler)
    return new


registerUpgrader(scheduler1to2, Scheduler.typeName, 1, 2)


class _SubSchedulerParentHook(Item):
    schemaVersion = 4
    typeName = 'axiom_subscheduler_parent_hook'

    subStore = reference(
        doc="""
        The L{SubStore} for which this scheduling hook exists.
        """, reftype=SubStore)

    def run(self):
        """
        Tick our C{subStore}'s L{SubScheduler}.
        """
        IScheduler(self.subStore).tick()

    def _schedule(self, when):
        """
        Ensure that this hook is scheduled to run at or before C{when}.
        """
        sched = IScheduler(self.store)
        for scheduledAt in sched.scheduledTimes(self):
            if when < scheduledAt:
                sched.reschedule(self, scheduledAt, when)
            break
        else:
            sched.schedule(self, when)


def upgradeParentHook1to2(oldHook):
    """
    Add the scheduler attribute to the given L{_SubSchedulerParentHook}.
    """
    newHook = oldHook.upgradeVersion(
        oldHook.typeName, 1, 2,
        loginAccount=oldHook.loginAccount,
        scheduledAt=oldHook.scheduledAt,
        scheduler=oldHook.store.findFirst(Scheduler))
    return newHook


registerUpgrader(upgradeParentHook1to2, _SubSchedulerParentHook.typeName, 1, 2)

declareLegacyItem(
    _SubSchedulerParentHook.typeName, 2,
    dict(loginAccount=reference(),
         scheduledAt=timestamp(default=None),
         scheduler=reference()))


def upgradeParentHook2to3(old):
    """
    Copy the C{loginAccount} attribute, but drop the others.
    """
    return old.upgradeVersion(
        old.typeName, 2, 3,
        loginAccount=old.loginAccount)


registerUpgrader(upgradeParentHook2to3, _SubSchedulerParentHook.typeName, 2, 3)

declareLegacyItem(
    _SubSchedulerParentHook.typeName, 3,
    dict(loginAccount=reference(),
         scheduler=reference()))


def upgradeParentHook3to4(old):
    """
    Copy C{loginAccount} to C{subStore} and remove the installation marker.
    """
    new = old.upgradeVersion(
        old.typeName, 3, 4, subStore=old.loginAccount)
    uninstallFrom(new, new.store)
    return new


registerUpgrader(upgradeParentHook3to4, _SubSchedulerParentHook.typeName, 3, 4)


class SubScheduler(Item, _SchedulerCompatMixin):
    """
    Track and execute persistent timed events for a substore.

    This is deprecated and present only for backwards compatibility.  Adapt
    the store to L{IScheduler} instead.
    """
    schemaVersion = 2
    typeName = 'axiom_subscheduler'

    dummy = integer()

    def activate(self):
        _SchedulerCompatMixin.activate(self)


def subscheduler1to2(old):
    new = old.upgradeVersion(SubScheduler.typeName, 1, 2)
    try:
        new.store.powerDown(new, IScheduler)
    except ValueError:
        # Someone might have created a SubScheduler but failed to power it
        # up.  Fine.
        pass
    return new


registerUpgrader(subscheduler1to2, SubScheduler.typeName, 1, 2)
