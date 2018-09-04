# -*- test-case-name: axiom.test.test_batch -*-

"""
Utilities for performing repetitive tasks over potentially large sets
of data over an extended period of time.
"""

import datetime
import os
import sys
import weakref

from twisted.application import service
from twisted.internet import task, defer, reactor, error, protocol
from twisted.python import reflect, failure, log, procutils, util, runtime
from zope.interface import implements

from coherence.extern.twisted.axiom import iaxiom, errors as eaxiom, item, \
    attributes
from coherence.extern.twisted.axiom.dependency import installOn
from coherence.extern.twisted.axiom.scheduler import Scheduler, SubScheduler
from coherence.extern.twisted.axiom.upgrade import registerUpgrader, \
    registerDeletionUpgrader
from coherence.extern.twisted.epsilon import extime, process, cooperator, \
    modal, juice

VERBOSE = False

_processors = weakref.WeakValueDictionary()


class _NoWorkUnits(Exception):
    """
    Raised by a _ReliableListener's step() method to indicate it
    didn't do anything.
    """


class _ProcessingFailure(Exception):
    """
    Raised when processItem raises any exception.  This is never raised
    directly, but instances of the three subclasses are.
    """

    def __init__(self, reliableListener, workUnit, failure):
        Exception.__init__(self)
        self.reliableListener = reliableListener
        self.workUnit = workUnit
        self.failure = failure

        # Get rid of all references this failure is holding so that it doesn't
        # cause any crazy object leaks.  See also the comment in
        # BatchProcessingService.step's except suite.
        self.failure.cleanFailure()

    def mark(self):
        """
        Mark the unit of work as failed in the database and update the listener
        so as to skip it next time.
        """
        self.reliableListener.lastRun = extime.Time()
        BatchProcessingError(
            store=self.reliableListener.store,
            processor=self.reliableListener.processor,
            listener=self.reliableListener.listener,
            item=self.workUnit,
            error=self.failure.getErrorMessage())


class _ForwardProcessingFailure(_ProcessingFailure):
    """
    An error occurred in a reliable listener while processing items forward
    from the mark.
    """

    def mark(self):
        _ProcessingFailure.mark(self)
        self.reliableListener.forwardMark = self.workUnit.storeID


class _BackwardProcessingFailure(_ProcessingFailure):
    """
    An error occurred in a reliable listener while processing items backwards
    from the mark.
    """

    def mark(self):
        _ProcessingFailure.mark(self)
        self.reliableListener.backwardMark = self.workUnit.storeID


class _TrackedProcessingFailure(_ProcessingFailure):
    """
    An error occurred in a reliable listener while processing items specially
    added to the batch run.
    """


class BatchProcessingError(item.Item):
    processor = attributes.reference(doc="""
    The batch processor which owns this failure.
    """)

    listener = attributes.reference(doc="""
    The listener which caused this error.
    """)

    item = attributes.reference(doc="""
    The item which actually failed to be processed.
    """)

    error = attributes.bytes(doc="""
    The error message which was associated with this failure.
    """)


class _ReliableTracker(item.Item):
    """
    A tracking item for an out-of-sequence item which a reliable listener
    should be given to process.

    These are created when L{_ReliableListener.addItem} is called and the
    specified item is in the range of items which have already been processed.
    """

    processor = attributes.reference(doc="""
    The batch processor which owns this tracker.
    """)

    listener = attributes.reference(doc="""
    The listener which is responsible for this tracker's item.
    """)

    item = attributes.reference(doc="""
    The item which this is tracking.
    """)


class _ReliableListener(item.Item):
    processor = attributes.reference(doc="""
    The batch processor which owns this listener.
    """)

    listener = attributes.reference(doc="""
    The item which is actually the listener.
    """)

    backwardMark = attributes.integer(doc="""
    Store ID of the first Item after the next Item to be processed in
    the backwards direction.  Usually, the Store ID of the Item
    previously processed in the backwards direction.
    """)

    forwardMark = attributes.integer(doc="""
    Store ID of the first Item before the next Item to be processed in
    the forwards direction.  Usually, the Store ID of the Item
    previously processed in the forwards direction.
    """)

    lastRun = attributes.timestamp(doc="""
    Time indicating the last chance given to this listener to do some
    work.
    """)

    style = attributes.integer(doc="""
    Either L{iaxiom.LOCAL} or L{iaxiom.REMOTE}. Indicates where the
    batch processing should occur, in the main process or a
    subprocess.
    """)

    def __repr__(self):
        return '<ReliableListener %s %r #%r>' % ({iaxiom.REMOTE: 'remote',
                                                  iaxiom.LOCAL: 'local'}[
                                                     self.style],
                                                 self.listener,
                                                 self.storeID)

    def addItem(self, item):
        assert type(item) is self.processor.workUnitType, \
            "Adding work unit of type %r to listener for type %r" % (
                type(item), self.processor.workUnitType)
        if item.storeID >= self.backwardMark and item.storeID <= self.forwardMark:
            _ReliableTracker(store=self.store,
                             listener=self,
                             item=item)

    def _forwardWork(self, workUnitType):
        if VERBOSE:
            log.msg("%r looking forward from %r" % (self, self.forwardMark,))
        return self.store.query(
            workUnitType,
            workUnitType.storeID > self.forwardMark,
            sort=workUnitType.storeID.ascending,
            limit=2)

    def _backwardWork(self, workUnitType):
        if VERBOSE:
            log.msg("%r looking backward from %r" % (self, self.backwardMark,))
        if self.backwardMark == 0:
            return []
        return self.store.query(
            workUnitType,
            workUnitType.storeID < self.backwardMark,
            sort=workUnitType.storeID.descending,
            limit=2)

    def _extraWork(self):
        return self.store.query(_ReliableTracker,
                                _ReliableTracker.listener == self,
                                limit=2)

    def _doOneWork(self, workUnit, failureType):
        if VERBOSE:
            log.msg("Processing a unit of work: %r" % (workUnit,))
        try:
            self.listener.processItem(workUnit)
        except:
            f = failure.Failure()
            if VERBOSE:
                log.msg("Processing failed: %s" % (f.getErrorMessage(),))
                log.err(f)
            raise failureType(self, workUnit, f)

    def step(self):
        first = True
        for workTracker in self._extraWork():
            if first:
                first = False
            else:
                return True
            item = workTracker.item
            workTracker.deleteFromStore()
            self._doOneWork(item, _TrackedProcessingFailure)

        for workUnit in self._forwardWork(self.processor.workUnitType):
            if first:
                first = False
            else:
                return True
            self.forwardMark = workUnit.storeID
            self._doOneWork(workUnit, _ForwardProcessingFailure)

        for workUnit in self._backwardWork(self.processor.workUnitType):
            if first:
                first = False
            else:
                return True
            self.backwardMark = workUnit.storeID
            self._doOneWork(workUnit, _BackwardProcessingFailure)

        if first:
            raise _NoWorkUnits()
        if VERBOSE:
            log.msg("%r.step() returning False" % (self,))
        return False


class _BatchProcessorMixin:

    def step(self, style=iaxiom.LOCAL, skip=()):
        now = extime.Time()
        first = True

        for listener in self.store.query(_ReliableListener,
                                         attributes.AND(
                                             _ReliableListener.processor == self,
                                             _ReliableListener.style == style,
                                             _ReliableListener.listener.notOneOf(
                                                 skip)),
                                         sort=_ReliableListener.lastRun.ascending):
            if not first:
                if VERBOSE:
                    log.msg(
                        "Found more work to do, returning True from %r.step()" % (
                        self,))
                return True
            listener.lastRun = now
            try:
                if listener.step():
                    if VERBOSE:
                        log.msg(
                            "%r.step() reported more work to do, returning True from %r.step()" % (
                            listener, self))
                    return True
            except _NoWorkUnits:
                if VERBOSE:
                    log.msg("%r.step() reported no work units" % (listener,))
            else:
                first = False
        if VERBOSE:
            log.msg(
                "No listeners left with work, returning False from %r.step()" % (
                self,))
        return False

    def run(self):
        """
        Try to run one unit of work through one listener.  If there are more
        listeners or more work, reschedule this item to be run again in
        C{self.busyInterval} milliseconds, otherwise unschedule it.

        @rtype: L{extime.Time} or C{None}
        @return: The next time at which to run this item, used by the scheduler
        for automatically rescheduling, or None if there is no more work to do.
        """
        now = extime.Time()
        if self.step():
            self.scheduled = now + datetime.timedelta(
                milliseconds=self.busyInterval)
        else:
            self.scheduled = None
        return self.scheduled

    def timedEventErrorHandler(self, timedEvent, failureObj):
        failureObj.trap(_ProcessingFailure)
        log.msg("Batch processing failure")
        log.err(failureObj.value.failure)
        failureObj.value.mark()
        return extime.Time() + datetime.timedelta(
            milliseconds=self.busyInterval)

    def addReliableListener(self, listener, style=iaxiom.LOCAL):
        """
        Add the given Item to the set which will be notified of Items
        available for processing.

        Note: Each Item is processed synchronously.  Adding too many
        listeners to a single batch processor will cause the L{step}
        method to block while it sends notification to each listener.

        @param listener: An Item instance which provides a
        C{processItem} method.

        @return: An Item representing L{listener}'s persistent tracking state.
        """
        existing = self.store.findUnique(_ReliableListener,
                                         attributes.AND(
                                             _ReliableListener.processor == self,
                                             _ReliableListener.listener == listener),
                                         default=None)
        if existing is not None:
            return existing

        for work in self.store.query(self.workUnitType,
                                     sort=self.workUnitType.storeID.descending,
                                     limit=1):
            forwardMark = work.storeID
            backwardMark = work.storeID + 1
            break
        else:
            forwardMark = 0
            backwardMark = 0

        if self.scheduled is None:
            self.scheduled = extime.Time()
            iaxiom.IScheduler(self.store).schedule(self, self.scheduled)

        return _ReliableListener(store=self.store,
                                 processor=self,
                                 listener=listener,
                                 forwardMark=forwardMark,
                                 backwardMark=backwardMark,
                                 style=style)

    def removeReliableListener(self, listener):
        """
        Remove a previously added listener.
        """
        self.store.query(_ReliableListener,
                         attributes.AND(_ReliableListener.processor == self,
                                        _ReliableListener.listener == listener)).deleteFromStore()
        self.store.query(BatchProcessingError,
                         attributes.AND(BatchProcessingError.processor == self,
                                        BatchProcessingError.listener == listener)).deleteFromStore()

    def getReliableListeners(self):
        """
        Return an iterable of the listeners which have been added to
        this batch processor.
        """
        for rellist in self.store.query(_ReliableListener,
                                        _ReliableListener.processor == self):
            yield rellist.listener

    def getFailedItems(self):
        """
        Return an iterable of two-tuples of listeners which raised an
        exception from C{processItem} and the item which was passed as
        the argument to that method.
        """
        for failed in self.store.query(BatchProcessingError,
                                       BatchProcessingError.processor == self):
            yield (failed.listener, failed.item)

    def itemAdded(self):
        """
        Called to indicate that a new item of the type monitored by this batch
        processor is being added to the database.

        If this processor is not already scheduled to run, this will schedule
        it.  It will also start the batch process if it is not yet running and
        there are any registered remote listeners.
        """
        localCount = self.store.query(
            _ReliableListener,
            attributes.AND(_ReliableListener.processor == self,
                           _ReliableListener.style == iaxiom.LOCAL),
            limit=1).count()

        remoteCount = self.store.query(
            _ReliableListener,
            attributes.AND(_ReliableListener.processor == self,
                           _ReliableListener.style == iaxiom.REMOTE),
            limit=1).count()

        if localCount and self.scheduled is None:
            self.scheduled = extime.Time()
            iaxiom.IScheduler(self.store).schedule(self, self.scheduled)
        if remoteCount:
            batchService = iaxiom.IBatchService(self.store, None)
            if batchService is not None:
                batchService.start()


def upgradeProcessor1to2(oldProcessor):
    """
    Batch processors stopped polling at version 2, so they no longer needed the
    idleInterval attribute.  They also gained a scheduled attribute which
    tracks their interaction with the scheduler.  Since they stopped polling,
    we also set them up as a timed event here to make sure that they don't
    silently disappear, never to be seen again: running them with the scheduler
    gives them a chance to figure out what's up and set up whatever other state
    they need to continue to run.

    Since this introduces a new dependency of all batch processors on a powerup
    for the IScheduler, install a Scheduler or a SubScheduler if one is not
    already present.
    """
    newProcessor = oldProcessor.upgradeVersion(
        oldProcessor.typeName, 1, 2,
        busyInterval=oldProcessor.busyInterval)
    newProcessor.scheduled = extime.Time()

    s = newProcessor.store
    sch = iaxiom.IScheduler(s, None)
    if sch is None:
        if s.parent is None:
            # Only site stores have no parents.
            sch = Scheduler(store=s)
        else:
            # Substores get subschedulers.
            sch = SubScheduler(store=s)
        installOn(sch, s)

    # And set it up to run.
    sch.schedule(newProcessor, newProcessor.scheduled)
    return newProcessor


def processor(forType):
    """
    Create an Axiom Item type which is suitable to use as a batch processor for
    the given Axiom Item type.

    Processors created this way depend on a L{iaxiom.IScheduler} powerup on the
    on which store they are installed.

    @type forType: L{item.MetaItem}
    @param forType: The Axiom Item type for which to create a batch processor
    type.

    @rtype: L{item.MetaItem}

    @return: An Axiom Item type suitable for use as a batch processor.  If such
    a type previously existed, it will be returned.  Otherwise, a new type is
    created.
    """
    MILLI = 1000
    try:
        processor = _processors[forType]
    except KeyError:
        def __init__(self, *a, **kw):
            item.Item.__init__(self, *a, **kw)
            self.store.powerUp(self, iaxiom.IBatchProcessor)

        attrs = {
            '__name__': 'Batch_' + forType.__name__,

            '__module__': forType.__module__,

            '__init__': __init__,

            '__repr__': lambda self: '<Batch of %s #%d>' % (
            reflect.qual(self.workUnitType), self.storeID),

            'schemaVersion': 2,

            'workUnitType': forType,

            'scheduled': attributes.timestamp(doc="""
            The next time at which this processor is scheduled to run.
            """, default=None),

            # MAGIC NUMBERS AREN'T THEY WONDERFUL?
            'busyInterval': attributes.integer(doc="", default=MILLI / 10),
        }
        _processors[forType] = processor = item.MetaItem(
            attrs['__name__'],
            (item.Item, _BatchProcessorMixin),
            attrs)

        registerUpgrader(
            upgradeProcessor1to2,
            _processors[forType].typeName,
            1, 2)

    return processor


class ProcessUnavailable(Exception):
    """Indicates the process is not available to perform tasks.

    This is a transient error.  Calling code should handle it by
    arranging to do the work they planned on doing at a later time.
    """


class Shutdown(juice.Command):
    """
    Abandon, belay, cancel, cease, close, conclude, cut it out, desist,
    determine, discontinue, drop it, end, finish, finish up, give over, go
    amiss, go astray, go wrong, halt, have done with, hold, knock it off, lay
    off, leave off, miscarry, perorate, quit, refrain, relinquish, renounce,
    resolve, scrap, scratch, scrub, stay, stop, terminate, wind up.
    """
    commandName = "Shutdown"
    responseType = juice.QuitBox


def _childProcTerminated(self, err):
    self.mode = 'stopped'
    err = ProcessUnavailable(err)
    for d in self.waitingForProcess:
        d.errback(err)
    del self.waitingForProcess


class ProcessController(object, metaclass=modal.ModalType):
    """
    Stateful class which tracks a Juice connection to a child process.

    Communication occurs over stdin and stdout of the child process.  The
    process is launched and restarted as necessary.  Failures due to the child
    process terminating, either unilaterally of by request, are represented as
    a transient exception class,

    Mode is one of::

      - 'stopped'       (no process running or starting)
      - 'starting'      (process begun but not ready for requests)
      - 'ready'         (process ready for requests)
      - 'stopping'      (process being torn down)
      - 'waiting_ready' (process beginning but will be shut down
                         as soon as it starts up)

    Transitions are as follows::

       getProcess:
           stopped -> starting:
               launch process
               create/save in waitingForStartup/return Deferred
           starting -> starting:
               create/save/return Deferred
           ready -> ready:
                return saved process
           stopping:
                return failing Deferred indicating transient failure
           waiting_ready:
                return failing Deferred indicating transient failure

       stopProcess:
           stopped -> stopped:
               return succeeding Deferred
           starting -> waiting_ready:
               create Deferred, add transient failure errback handler, return
           ready -> stopping:
               call shutdown on process
               return Deferred which fires when shutdown is done

       childProcessCreated:
           starting -> ready:
               callback saved Deferreds
               clear saved Deferreds
           waiting_ready:
               errback saved Deferred indicating transient failure
               return _shutdownIndexerProcess()

       childProcessTerminated:
           starting -> stopped:
               errback saved Deferreds indicating transient failure
           waiting_ready -> stopped:
               errback saved Deferreds indicating transient failure
           ready -> stopped:
               drop reference to process object
           stopping -> stopped:
               Callback saved shutdown deferred

    @ivar process: A reference to the process object.  Set in every non-stopped
    mode.

    @ivar juice: A reference to the juice protocol.  Set in all modes.

    @ivar connector: A reference to the process protocol.  Set in every
    non-stopped mode.

    @ivar onProcessStartup: None or a no-argument callable which will
    be invoked whenever the connection is first established to a newly
    spawned child process.

    @ivar onProcessTermination: None or a no-argument callable which
    will be invoked whenever a Juice connection is lost, except in the
    case where process shutdown was explicitly requested via
    stopProcess().
    """

    initialMode = 'stopped'
    modeAttribute = 'mode'

    # A reference to the Twisted process object which corresponds to
    # the child process we have spawned.  Set to a non-None value in
    # every state except stopped.
    process = None

    # A reference to the process protocol object via which we
    # communicate with the process's stdin and stdout.  Set to a
    # non-None value in every state except stopped.
    connector = None

    def __init__(self, name, juice, tacPath,
                 onProcessStartup=None,
                 onProcessTermination=None,
                 logPath=None,
                 pidPath=None):
        self.name = name
        self.juice = juice
        self.tacPath = tacPath
        self.onProcessStartup = onProcessStartup
        self.onProcessTermination = onProcessTermination
        if logPath is None:
            logPath = name + '.log'
        if pidPath is None:
            pidPath = name + '.pid'
        self.logPath = logPath
        self.pidPath = pidPath

    def _startProcess(self):
        executable = sys.executable
        env = os.environ

        twistdBinaries = procutils.which("twistd2.4") + procutils.which(
            "twistd")
        if not twistdBinaries:
            return defer.fail(
                RuntimeError("Couldn't find twistd to start subprocess"))
        twistd = twistdBinaries[0]

        setsid = procutils.which("setsid")

        self.connector = JuiceConnector(self.juice, self)

        args = [
            sys.executable,
            twistd,
            '--logfile=%s' % (self.logPath,)]

        if not runtime.platform.isWindows():
            args.append('--pidfile=%s' % (self.pidPath,))

        args.extend(['-noy',
                     self.tacPath])

        if setsid:
            args = ['setsid'] + args
            executable = setsid[0]

        self.process = process.spawnProcess(
            self.connector, executable, tuple(args), env=env)

    class stopped(modal.mode):
        def getProcess(self):
            self.mode = 'starting'
            self.waitingForProcess = []

            self._startProcess()

            # Mode has changed, this will call some other
            # implementation of getProcess.
            return self.getProcess()

        def stopProcess(self):
            return defer.succeed(None)

    class starting(modal.mode):
        def getProcess(self):
            d = defer.Deferred()
            self.waitingForProcess.append(d)
            return d

        def stopProcess(self):
            def eb(err):
                err.trap(ProcessUnavailable)

            d = defer.Deferred().addErrback(eb)
            self.waitingForProcess.append(d)

            self.mode = 'waiting_ready'
            return d

        def childProcessCreated(self):
            self.mode = 'ready'

            if self.onProcessStartup is not None:
                self.onProcessStartup()

            for d in self.waitingForProcess:
                d.callback(self.juice)
            del self.waitingForProcess

        def childProcessTerminated(self, reason):
            _childProcTerminated(self, reason)
            if self.onProcessTermination is not None:
                self.onProcessTermination()

    class ready(modal.mode):
        def getProcess(self):
            return defer.succeed(self.juice)

        def stopProcess(self):
            self.mode = 'stopping'
            self.onShutdown = defer.Deferred()
            Shutdown().do(self.juice)
            return self.onShutdown

        def childProcessTerminated(self, reason):
            self.mode = 'stopped'
            self.process = self.connector = None
            if self.onProcessTermination is not None:
                self.onProcessTermination()

    class stopping(modal.mode):
        def getProcess(self):
            return defer.fail(ProcessUnavailable("Shutting down"))

        def stopProcess(self):
            return self.onShutdown

        def childProcessTerminated(self, reason):
            self.mode = 'stopped'
            self.process = self.connector = None
            self.onShutdown.callback(None)

    class waiting_ready(modal.mode):
        def getProcess(self):
            return defer.fail(ProcessUnavailable("Shutting down"))

        def childProcessCreated(self):
            # This will put us into the stopped state - no big deal,
            # we are going into the ready state as soon as it returns.
            _childProcTerminated(self, RuntimeError("Shutting down"))

            # Dip into the ready mode for ever so brief an instant so
            # that we can shut ourselves down.
            self.mode = 'ready'
            return self.stopProcess()

        def childProcessTerminated(self, reason):
            _childProcTerminated(self, reason)
            if self.onProcessTermination is not None:
                self.onProcessTermination()


class JuiceConnector(protocol.ProcessProtocol):

    def __init__(self, proto, controller):
        self.juice = proto
        self.controller = controller

    def connectionMade(self):
        log.msg("Subprocess started.")
        self.juice.makeConnection(self)
        self.controller.childProcessCreated()

    # Transport
    disconnecting = False

    def write(self, data):
        self.transport.write(data)

    def writeSequence(self, data):
        self.transport.writeSequence(data)

    def loseConnection(self):
        self.transport.loseConnection()

    def getPeer(self):
        return ('omfg what are you talking about',)

    def getHost(self):
        return ('seriously it is a process this makes no sense',)

    def inConnectionLost(self):
        log.msg("Standard in closed")
        protocol.ProcessProtocol.inConnectionLost(self)

    def outConnectionLost(self):
        log.msg("Standard out closed")
        protocol.ProcessProtocol.outConnectionLost(self)

    def errConnectionLost(self):
        log.msg("Standard err closed")
        protocol.ProcessProtocol.errConnectionLost(self)

    def outReceived(self, data):
        self.juice.dataReceived(data)

    def errReceived(self, data):
        log.msg("Received stderr from subprocess: " + repr(data))

    def processEnded(self, status):
        log.msg("Process ended")
        self.juice.connectionLost(status)
        self.controller.childProcessTerminated(status)


class JuiceChild(juice.Juice):
    """
    Protocol class which runs in the child process

    This just defines one behavior on top of a regular juice protocol: the
    shutdown command, which drops the connection and stops the reactor.
    """
    shutdown = False

    def connectionLost(self, reason):
        juice.Juice.connectionLost(self, reason)
        if self.shutdown:
            reactor.stop()

    def command_SHUTDOWN(self):
        log.msg("Shutdown message received, goodbye.")
        self.shutdown = True
        return {}

    command_SHUTDOWN.command = Shutdown


class SetStore(juice.Command):
    """
    Specify the location of the site store.
    """
    commandName = 'Set-Store'
    arguments = [('storepath', juice.Path())]


class SuspendProcessor(juice.Command):
    """
    Prevent a particular reliable listener from receiving any notifications
    until a L{ResumeProcessor} command is sent or the batch process is
    restarted.
    """
    commandName = 'Suspend-Processor'
    arguments = [('storepath', juice.Path()),
                 ('storeid', juice.Integer())]


class ResumeProcessor(juice.Command):
    """
    Cause a particular reliable listener to begin receiving notifications
    again.
    """
    commandName = 'Resume-Processor'
    arguments = [('storepath', juice.Path()),
                 ('storeid', juice.Integer())]


class CallItemMethod(juice.Command):
    """
    Invoke a particular method of a particular item.
    """
    commandName = 'Call-Item-Method'
    arguments = [('storepath', juice.Path()),
                 ('storeid', juice.Integer()),
                 ('method', juice.String())]


class BatchProcessingControllerService(service.Service):
    """
    Controls starting, stopping, and passing messages to the system process in
    charge of remote batch processing.

    @ivar batchController: A reference to the L{ProcessController} for
        interacting with the batch process, if one exists.  Otherwise C{None}.
    """
    implements(iaxiom.IBatchService)

    batchController = None

    def __init__(self, store):
        self.store = store
        self.setName("Batch Processing Controller")

    def startService(self):
        service.Service.startService(self)
        tacPath = util.sibpath(__file__, "batch.tac")
        proto = BatchProcessingProtocol()
        rundir = self.store.dbdir.child("run")
        logdir = rundir.child("logs")
        for d in rundir, logdir:
            try:
                d.createDirectory()
            except OSError:
                pass
        self.batchController = ProcessController(
            "batch", proto, tacPath,
            self._setStore, self._restartProcess,
            logdir.child("batch.log").path,
            rundir.child("batch.pid").path)

    def _setStore(self):
        return SetStore(storepath=self.store.dbdir).do(
            self.batchController.juice)

    def _restartProcess(self):
        reactor.callLater(1.0, self.batchController.getProcess)

    def stopService(self):
        service.Service.stopService(self)
        d = self.batchController.stopProcess()
        d.addErrback(lambda err: err.trap(error.ProcessDone))
        return d

    def call(self, itemMethod):
        """
        Invoke the given bound item method in the batch process.

        Return a Deferred which fires when the method has been invoked.
        """
        item = itemMethod.__self__
        method = itemMethod.__func__.__name__
        return self.batchController.getProcess().addCallback(
            CallItemMethod(storepath=item.store.dbdir,
                           storeid=item.storeID,
                           method=method).do)

    def start(self):
        if self.batchController is not None:
            self.batchController.getProcess()

    def suspend(self, storepath, storeID):
        return self.batchController.getProcess().addCallback(
            SuspendProcessor(storepath=storepath, storeid=storeID).do)

    def resume(self, storepath, storeID):
        return self.batchController.getProcess().addCallback(
            ResumeProcessor(storepath=storepath, storeid=storeID).do)


class _SubStoreBatchChannel(object):
    """
    SubStore adapter for passing messages to the batch processing system
    process.

    SubStores are adaptable to L{iaxiom.IBatchService} via this adapter.
    """
    implements(iaxiom.IBatchService)

    def __init__(self, substore):
        self.storepath = substore.dbdir
        self.service = iaxiom.IBatchService(substore.parent)

    def call(self, itemMethod):
        return self.service.call(itemMethod)

    def start(self):
        self.service.start()

    def suspend(self, storeID):
        return self.service.suspend(self.storepath, storeID)

    def resume(self, storeID):
        return self.service.resume(self.storepath, storeID)


def storeBatchServiceSpecialCase(st, pups):
    """
    Adapt a L{Store} to L{IBatchService}.

    If C{st} is a substore, return a simple wrapper that delegates to the site
    store's L{IBatchService} powerup.  Return C{None} if C{st} has no
    L{BatchProcessingControllerService}.
    """
    if st.parent is not None:
        try:
            return _SubStoreBatchChannel(st)
        except TypeError:
            return None
    storeService = service.IService(st)
    try:
        return storeService.getServiceNamed("Batch Processing Controller")
    except KeyError:
        return None


class BatchProcessingProtocol(JuiceChild):
    siteStore = None

    def __init__(self, service=None, issueGreeting=False):
        juice.Juice.__init__(self, issueGreeting)
        self.storepaths = []
        if service is not None:
            service.cooperator = cooperator.Cooperator()
        self.service = service

    def connectionLost(self, reason):
        # In the child process, we are a server.  In the child process, we
        # don't want to keep running after we can't talk to the client anymore.
        if self.isServer:
            reactor.stop()

    def command_SET_STORE(self, storepath):
        from coherence.extern.twisted.axiom import store

        assert self.siteStore is None

        self.siteStore = store.Store(storepath, debug=False)
        self.subStores = {}
        self.pollCall = task.LoopingCall(self._pollSubStores)
        self.pollCall.start(10.0)

        return {}

    command_SET_STORE.command = SetStore

    def command_SUSPEND_PROCESSOR(self, storepath, storeid):
        return self.subStores[storepath.path].suspend(storeid).addCallback(
            lambda ign: {})

    command_SUSPEND_PROCESSOR.command = SuspendProcessor

    def command_RESUME_PROCESSOR(self, storepath, storeid):
        return self.subStores[storepath.path].resume(storeid).addCallback(
            lambda ign: {})

    command_RESUME_PROCESSOR.command = ResumeProcessor

    def command_CALL_ITEM_METHOD(self, storepath, storeid, method):
        return self.subStores[storepath.path].call(storeid,
                                                   method).addCallback(
            lambda ign: {})

    command_CALL_ITEM_METHOD.command = CallItemMethod

    def _pollSubStores(self):
        from coherence.extern.twisted.axiom import store, substore

        # Any service which has encountered an error will have logged it and
        # then stopped.  Prune those here, so that they are noticed as missing
        # below and re-added.
        for path, svc in list(self.subStores.items()):
            if not svc.running:
                del self.subStores[path]

        try:
            paths = set([p.path for p in
                         self.siteStore.query(substore.SubStore).getColumn(
                             "storepath")])
        except eaxiom.SQLError as e:
            # Generally, database is locked.
            log.msg("SubStore query failed with SQLError: %r" % (e,))
        except:
            # WTF?
            log.msg("SubStore query failed with bad error:")
            log.err()
        else:
            for removed in set(self.subStores) - paths:
                self.subStores[removed].disownServiceParent()
                del self.subStores[removed]
                if VERBOSE:
                    log.msg("Removed SubStore " + removed)
            for added in paths - set(self.subStores):
                try:
                    s = store.Store(added, debug=False)
                except eaxiom.SQLError as e:
                    # Generally, database is locked.
                    log.msg(
                        "Opening sub-Store failed with SQLError: %r" % (e,))
                except:
                    log.msg("Opening sub-Store failed with bad error:")
                    log.err()
                else:
                    self.subStores[added] = BatchProcessingService(s,
                                                                   style=iaxiom.REMOTE)
                    self.subStores[added].setServiceParent(self.service)
                    if VERBOSE:
                        log.msg("Added SubStore " + added)


class BatchProcessingService(service.Service):
    """
    Steps over the L{iaxiom.IBatchProcessor} powerups for a single L{axiom.store.Store}.
    """

    def __init__(self, store, style=iaxiom.LOCAL):
        self.store = store
        self.style = style
        self.suspended = []

    def suspend(self, storeID):
        item = self.store.getItemByID(storeID)
        self.suspended.append(item)
        return item.suspend()

    def resume(self, storeID):
        item = self.store.getItemByID(storeID)
        self.suspended.remove(item)
        return item.resume()

    def call(self, storeID, methodName):
        return defer.maybeDeferred(
            getattr(self.store.getItemByID(storeID), methodName))

    def items(self):
        return self.store.powerupsFor(iaxiom.IBatchProcessor)

    def processWhileRunning(self):
        """
        Run tasks until stopService is called.
        """
        work = self.step()
        for result, more in work:
            yield result
            if not self.running:
                break
            if more:
                delay = 0.1
            else:
                delay = 10.0
            yield task.deferLater(reactor, delay, lambda: None)

    def step(self):
        while True:
            items = list(self.items())

            if VERBOSE:
                log.msg(
                    "Found %d processors for %s" % (len(items), self.store))

            ran = False
            more = False
            while items:
                ran = True
                item = items.pop()
                if VERBOSE:
                    log.msg("Stepping processor %r (suspended is %r)" % (
                    item, self.suspended))
                try:
                    itemHasMore = item.store.transact(item.step,
                                                      style=self.style,
                                                      skip=self.suspended)
                except _ProcessingFailure as e:
                    log.msg("%r failed while processing %r:" % (
                    e.reliableListener, e.workUnit))
                    log.err(e.failure)
                    e.mark()

                    # _Fuck_.  /Fuck/.  If user-code in or below (*fuck*)
                    # item.step creates a Failure on any future iteration
                    # (-Fuck-) of this loop, it will get a reference to this
                    # exception instance, since it's in locals and Failures
                    # extract and save locals (Aaarrrrggg).  Get rid of this so
                    # that doesn't happen.  See also the definition of
                    # _ProcessingFailure.__init__.
                    e = None
                else:
                    if itemHasMore:
                        more = True
                yield None, bool(more or items)
            if not ran:
                yield None, more

    def startService(self):
        service.Service.startService(self)
        self.parent.cooperator.coiterate(self.processWhileRunning())

    def stopService(self):
        service.Service.stopService(self)
        self.store.close()


class BatchManholePowerup(item.Item):
    """
    Previously, an L{IConchUser} powerup.  This class is only still defined for
    schema compatibility.  Any instances of it will be deleted by an upgrader.
    See #1001.
    """
    schemaVersion = 2
    unused = attributes.integer(
        doc="Satisfy Axiom requirement for at least one attribute")


registerDeletionUpgrader(BatchManholePowerup, 1, 2)
