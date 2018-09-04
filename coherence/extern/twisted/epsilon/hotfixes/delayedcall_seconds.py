import traceback

from twisted.internet import error, base
from twisted.internet.interfaces import IDelayedCall
from twisted.persisted import styles
from twisted.python import reflect
from zope.interface import implementer


@implementer(IDelayedCall)
class DelayedCall(styles.Ephemeral):
    # enable .debug to record creator call stack, and it will be logged if
    # an exception occurs while the function is being run
    debug = False
    _str = None

    def __init__(self, time, func, args, kw, cancel, reset, seconds=None):
        self.time, self.func, self.args, self.kw = time, func, args, kw
        self.resetter = reset
        self.canceller = cancel
        self.seconds = seconds
        self.cancelled = self.called = 0
        self.delayed_time = 0
        if self.debug:
            self.creator = traceback.format_stack()[:-2]

    def getTime(self):
        """Return the time at which this call will fire

        @rtype: C{float}
        @return: The number of seconds after the epoch at which this call is
        scheduled to be made.
        """
        return self.time + self.delayed_time

    def cancel(self):
        """Unschedule this call

        @raise AlreadyCancelled: Raised if this call has already been
        unscheduled.

        @raise AlreadyCalled: Raised if this call has already been made.
        """
        if self.cancelled:
            raise error.AlreadyCancelled
        elif self.called:
            raise error.AlreadyCalled
        else:
            self.canceller(self)
            self.cancelled = 1
            if self.debug:
                self._str = str(self)
            del self.func, self.args, self.kw

    def reset(self, secondsFromNow):
        """Reschedule this call for a different time

        @type secondsFromNow: C{float}
        @param secondsFromNow: The number of seconds from the time of the
        C{reset} call at which this call will be scheduled.

        @raise AlreadyCancelled: Raised if this call has been cancelled.
        @raise AlreadyCalled: Raised if this call has already been made.
        """
        if self.cancelled:
            raise error.AlreadyCancelled
        elif self.called:
            raise error.AlreadyCalled
        else:
            if self.seconds is None:
                new_time = base.seconds() + secondsFromNow
            else:
                new_time = self.seconds() + secondsFromNow
            if new_time < self.time:
                self.delayed_time = 0
                self.time = new_time
                self.resetter(self)
            else:
                self.delayed_time = new_time - self.time

    def delay(self, secondsLater):
        """Reschedule this call for a later time

        @type secondsLater: C{float}
        @param secondsLater: The number of seconds after the originally
        scheduled time for which to reschedule this call.

        @raise AlreadyCancelled: Raised if this call has been cancelled.
        @raise AlreadyCalled: Raised if this call has already been made.
        """
        if self.cancelled:
            raise error.AlreadyCancelled
        elif self.called:
            raise error.AlreadyCalled
        else:
            self.delayed_time += secondsLater
            if self.delayed_time < 0:
                self.activate_delay()
                self.resetter(self)

    def activate_delay(self):
        self.time += self.delayed_time
        self.delayed_time = 0

    def active(self):
        """Determine whether this call is still pending

        @rtype: C{bool}
        @return: True if this call has not yet been made or cancelled,
        False otherwise.
        """
        return not (self.cancelled or self.called)

    def __le__(self, other):
        return self.time <= other.time

    def __str__(self):
        if self._str is not None:
            return self._str
        if hasattr(self, 'func'):
            if hasattr(self.func, 'func_name'):
                func = self.func.__name__
                if hasattr(self.func, 'im_class'):
                    func = self.func.__self__.__class__.__name__ + '.' + func
            else:
                func = reflect.safe_repr(self.func)
        else:
            func = None

        if self.seconds is None:
            now = base.seconds()
        else:
            now = self.seconds()
        L = ["<DelayedCall %s [%ss] called=%s cancelled=%s" % (
            id(self), self.time - now, self.called, self.cancelled)]
        if func is not None:
            L.extend((" ", func, "("))
            if self.args:
                L.append(", ".join([reflect.safe_repr(e) for e in self.args]))
                if self.kw:
                    L.append(", ")
            if self.kw:
                L.append(", ".join(
                    ['%s=%s' % (k, reflect.safe_repr(v)) for (k, v) in
                     self.kw.items()]))
            L.append(")")

        if self.debug:
            L.append("\n\ntraceback at creation: \n\n%s" % (
                '    '.join(self.creator)))
        L.append('>')

        return "".join(L)


def install():
    global DelayedCall

    base.DelayedCall.__dict__ = DelayedCall.__dict__
    base.DelayedCall.__dict__['__module__'] = 'twisted.internet.base'
    DelayedCall = base.DelayedCall
