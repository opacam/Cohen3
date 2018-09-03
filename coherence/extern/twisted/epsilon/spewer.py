
import sys
import signal
import threading

from twisted.application import service
from twisted.python import reflect, log

class CannotFindFunction(ValueError):
    pass

class Tracer(object):
    skip = object()

    installed = False

    def install(self):
        self.installed = True
        sys.settrace(self.trace)
        threading.settrace(self.trace)

    def uninstall(self):
        self.installed = False
        sys.settrace(None)
        threading.setttrace(None)

    def toggle(self):
        if self.installed:
            self.uninstall()
        else:
            self.install()

    def trace(self, frame, event, arg):
        r = getattr(self, 'trace_' + event.upper())(frame, arg)
        if r is self.skip:
            return None
        elif r is None:
            return self.trace
        else:
            return r

    def trace_CALL(self, frame, arg):
        pass

    def trace_LINE(self, frame, arg):
        pass

    def trace_RETURN(self, frame, arg):
        pass

    def trace_EXCEPTION(self, frame, arg):
        pass


def extractArgs(frame):
    co = frame.f_code
    dict = frame.f_locals
    n = co.co_argcount
    if co.co_flags & 4: n = n+1
    if co.co_flags & 8: n = n+1
    result = {}
    for i in range(n):
        name = co.co_varnames[i]
        result[name] = dict.get(name, "*** undefined ***")
    return result


def formatArgs(args):
    return ', '.join(['='.join((k, reflect.safe_repr(v))) for (k, v) in args.items()])


class Spewer(Tracer):
    callDepth = 0

    def trace_CALL(self, frame, arg):
        self.callDepth += 1

        frameSelf = frame.f_locals.get('self')
        if frameSelf is not None:
            if hasattr(frameSelf, '__class__'):
                k = reflect.qual(frameSelf.__class__)
            else:
                k = reflect.qual(type(frameSelf))
            k = k + '.'
        else:
            k = ''

        print(("%X %s%s%s(%s)" % (
            id(threading.currentThread()),
            self.callDepth * ' ',
            k,
            frame.f_code.co_name,
            formatArgs(extractArgs(frame)))))

    def trace_RETURN(self, frame, arg):
        if arg is not None:
            print(("%X %s<= %s" % (
                id(threading.currentThread()),
                self.callDepth * ' ',
                reflect.safe_repr(arg),)))
        self.callDepth = max(0, self.callDepth - 1)

    def trace_EXCEPTION(self, frame, arg):
        print(("%X %s^- %s" % (
            id(threading.currentThread()),
            self.callDepth * ' ',
            reflect.safe_repr(arg),)))
        self.callDepth = max(0, self.callDepth - 1)


class SignalService(service.Service):
    def __init__(self, sigmap):
        self.sigmap = sigmap

    def startService(self):
        service.Service.startService(self)
        self.oldsigmap = {}
        for sig, handler in list(self.sigmap.items()):
            self.oldsigmap[sig] = signal.signal(sig, handler)

    def stopService(self):
        for sig, handler in list(self.oldsigmap.items()):
            signal.signal(sig, handler)
        del self.oldsigmap
        service.Service.stopService(self)
