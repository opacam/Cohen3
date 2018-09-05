# -*- test-case-name: epsilon.test.test_juice -*-
# Copyright 2005 Divmod, Inc.  See LICENSE file for details

__metaclass__ = type

import pprint
import warnings

from twisted.internet.defer import Deferred, maybeDeferred, fail
from twisted.internet.main import CONNECTION_LOST
from twisted.internet.protocol import ServerFactory, ClientFactory
from twisted.internet.ssl import Certificate
from twisted.python import log, filepath
from twisted.python.failure import Failure

from coherence.extern.twisted.epsilon import extime
from coherence.extern.twisted.epsilon.liner import LineReceiver

ASK = '_ask'
ANSWER = '_answer'
COMMAND = '_command'
ERROR = '_error'
ERROR_CODE = '_error_code'
ERROR_DESCRIPTION = '_error_description'
LENGTH = '_length'
BODY = 'body'

debug = False


class JuiceBox(dict):
    """ I am a packet in the JUICE protocol.  """

    def __init__(self, __body='', **kw):
        self.update(kw)
        if __body:
            assert isinstance(__body, str), "body must be a string: %r" % (
                repr(__body),)
            self['body'] = __body

    def body():
        def get(self):
            warnings.warn(
                "body attribute of boxes is now just a regular field",
                stacklevel=2)
            return self['body']

        def set(self, newbody):
            warnings.warn(
                "body attribute of boxes is now just a regular field",
                stacklevel=2)
            self['body'] = newbody

        return get, set

    body = property(*body())

    def copy(self):
        newBox = self.__class__()
        newBox.update(self)
        return newBox

    def serialize(self,
                  delimiter='\r\n',
                  escaped='\r\n '):
        assert LENGTH not in self

        L = []
        for (k, v) in self.items():
            if k == BODY:
                k = LENGTH
                v = str(len(self[BODY]))
            L.append(k.replace('_', '-').title())
            L.append(': ')
            L.append(v.replace(delimiter, escaped))
            L.append(delimiter)

        L.append(delimiter)
        if BODY in self:
            L.append(self[BODY])

        bytes = ''.join(L)
        return bytes

    def sendTo(self, proto):
        """
        Serialize and send this box to a Juice instance.  By the time it is
        being sent, several keys are required.  I must have exactly ONE of::

            -ask
            -answer
            -error

        If the '-ask' header is set, then the '-command' header must also be
        set.
        """
        proto.sendPacket(self)


# juice.Box => JuiceBox


Box = JuiceBox


class TLSBox(JuiceBox):
    def __repr__(self):
        return 'TLS(**%s)' % (super(TLSBox, self).__repr__(),)

    def __init__(self, __certificate, __verify=None, __sslstarted=None, **kw):
        super(TLSBox, self).__init__(**kw)
        self.certificate = __certificate
        self.verify = __verify
        self.sslstarted = __sslstarted

    def sendTo(self, proto):
        super(TLSBox, self).sendTo(proto)
        if self.verify is None:
            proto.startTLS(self.certificate)
        else:
            proto.startTLS(self.certificate, self.verify)
        if self.sslstarted is not None:
            self.sslstarted()


class QuitBox(JuiceBox):
    def __repr__(self):
        return 'Quit(**%s)' % (super(QuitBox, self).__repr__(),)

    def sendTo(self, proto):
        super(QuitBox, self).sendTo(proto)
        proto.transport.loseConnection()


class _SwitchBox(JuiceBox):
    def __repr__(self):
        return 'Switch(**%s)' % (super(_SwitchBox, self).__repr__(),)

    def __init__(self, __proto, **kw):
        super(_SwitchBox, self).__init__(**kw)
        self.innerProto = __proto

    def sendTo(self, proto):
        super(_SwitchBox, self).sendTo(proto)
        proto._switchTo(self.innerProto)


class NegotiateBox(JuiceBox):
    def __repr__(self):
        return 'Negotiate(**%s)' % (super(NegotiateBox, self).__repr__(),)

    def sendTo(self, proto):
        super(NegotiateBox, self).sendTo(proto)
        proto._setProtocolVersion(int(self['version']))


class JuiceError(Exception):
    pass


class RemoteJuiceError(JuiceError):
    """
    This error indicates that something went wrong on the remote end of the
    connection, and the error was serialized and transmitted to you.
    """

    def __init__(self, errorCode, description, fatal=False):
        """Create a remote error with an error code and description.
        """
        Exception.__init__(self, "Remote[%s]: %s" % (errorCode, description))
        self.errorCode = errorCode
        self.description = description
        self.fatal = fatal


class UnhandledRemoteJuiceError(RemoteJuiceError):
    def __init__(self, description):
        errorCode = "UNHANDLED"
        RemoteJuiceError.__init__(self, errorCode, description)


class JuiceBoxError(JuiceError):
    pass


class MalformedJuiceBox(JuiceBoxError):
    pass


class UnhandledCommand(JuiceError):
    pass


class IncompatibleVersions(JuiceError):
    pass


class _Transactor:
    def __init__(self, store, callable):
        self.store = store
        self.callable = callable

    def __call__(self, box):
        return self.store.transact(self.callable, box)

    def __repr__(self):
        return '<Transaction in: %s of: %s>' % (self.store, self.callable)


class DispatchMixin:
    baseDispatchPrefix = 'juice_'
    autoDispatchPrefix = 'command_'

    wrapper = None

    def _auto(self, aCallable, proto, namespace=None):
        if aCallable is None:
            return None
        command = aCallable.command
        if namespace not in command.namespaces:
            # if you're in the wrong namespace, you are very likely not allowed
            # to invoke the command you are trying to invoke.  some objects
            # have commands exposed in a separate namespace for security
            # reasons, since the security model is a role : namespace mapping.
            log.msg(
                'WRONG NAMESPACE: %r, %r' % (namespace, command.namespaces))
            return None

        def doit(box):
            kw = stringsToObjects(box, command.arguments, proto)
            for name, extraArg in command.extra:
                kw[name] = extraArg.fromTransport(proto.transport)

            # def checkIsDict(result):
            #     if not isinstance(result, dict):
            #         raise RuntimeError("%r returned %r, not dictionary" % (
            #                 aCallable, result))
            #     return result
            def checkKnownErrors(error):
                key = error.trap(*command.allErrors)
                code = command.allErrors[key]
                desc = str(error.value)
                return Failure(RemoteJuiceError(
                    code, desc, error in command.fatalErrors))

            return maybeDeferred(aCallable, **kw).addCallback(
                command.makeResponse, proto).addErrback(
                checkKnownErrors)

        return doit

    def _wrap(self, aCallable):
        if aCallable is None:
            return None
        wrap = self.wrapper
        if wrap is not None:
            return wrap(aCallable)
        else:
            return aCallable

    def normalizeCommand(self, cmd):
        """Return the canonical form of a command.
        """
        return cmd.upper().strip().replace('-', '_')

    def lookupFunction(self, proto, name, namespace):
        """Return a callable to invoke when executing the named command.
        """
        # Try to find a method to be invoked in a transaction first
        # Otherwise fallback to a "regular" method
        fName = self.autoDispatchPrefix + name
        fObj = getattr(self, fName, None)
        if fObj is not None:
            # pass the namespace along
            return self._auto(fObj, proto, namespace)

        assert namespace is None, 'Old-style parsing'
        # Fall back to simplistic command dispatching - we probably want to get
        # rid of this eventually, there's no reason to do extra work and write
        # fewer docs all the time.
        fName = self.baseDispatchPrefix + name
        return getattr(self, fName, None)

    def dispatchCommand(self, proto, cmd, box, namespace=None):
        fObj = self.lookupFunction(proto, self.normalizeCommand(cmd),
                                   namespace)
        if fObj is None:
            return fail(UnhandledCommand(cmd))
        return maybeDeferred(self._wrap(fObj), box)


PYTHON_KEYWORDS = [
    'and', 'del', 'for', 'is', 'raise', 'assert', 'elif', 'from', 'lambda',
    'return', 'break', 'else', 'global', 'not', 'try', 'class', 'except',
    'if', 'or', 'while', 'continue', 'exec', 'import', 'pass', 'yield',
    'def', 'finally', 'in', 'print']


def normalizeKey(key):
    lkey = key.lower().replace('-', '_')
    if lkey in PYTHON_KEYWORDS:
        return lkey.title()
    return lkey


def parseJuiceHeaders(lines):
    """
    Create a JuiceBox from a list of header lines.

    @param lines: a list of lines.
    """
    b = JuiceBox()
    bodylen = 0
    key = None
    for L in lines:
        if L[0] == ' ':
            # continuation
            assert key is not None
            b[key] += '\r\n' + L[1:]
            continue
        parts = L.split(': ', 1)
        if len(parts) != 2:
            raise MalformedJuiceBox("Wrong number of parts: %r" % (L,))
        key, value = parts
        key = normalizeKey(key)
        b[key] = value
    return int(b.pop(LENGTH, 0)), b


class JuiceParserBase(DispatchMixin):

    def __init__(self):
        self._outstandingRequests = {}

    def _puke(self, failure):
        log.msg("Juice server or network failure "
                "unhandled by client application:")
        log.err(failure)
        log.msg(
            "Dropping connection!  "
            "To avoid, add errbacks to ALL remote commands!")
        if self.transport is not None:
            self.transport.loseConnection()

    _counter = 0

    def _nextTag(self):
        self._counter += 1
        return '%x' % (self._counter,)

    def failAllOutgoing(self, reason):
        OR = list(self._outstandingRequests.items())
        self._outstandingRequests = None  # we can never send another request
        for key, value in OR:
            value.errback(reason)

    def juiceBoxReceived(self, box):
        if debug:
            log.msg(
                "Juice receive: %s" % pprint.pformat(dict(iter(box.items()))))

        if ANSWER in box:
            question = self._outstandingRequests.pop(box[ANSWER])
            question.addErrback(self._puke)
            self._wrap(question.callback)(box)
        elif ERROR in box:
            question = self._outstandingRequests.pop(box[ERROR])
            question.addErrback(self._puke)
            self._wrap(question.errback)(
                Failure(RemoteJuiceError(box[ERROR_CODE],
                                         box[ERROR_DESCRIPTION])))
        elif COMMAND in box:
            cmd = box[COMMAND]

            def sendAnswer(answerBox):
                if ASK not in box:
                    return
                if self.transport is None:
                    return
                answerBox[ANSWER] = box[ASK]
                answerBox.sendTo(self)

            def sendError(error):
                if ASK not in box:
                    return error
                if error.check(RemoteJuiceError):
                    code = error.value.errorCode
                    desc = error.value.description
                    if error.value.fatal:
                        errorBox = QuitBox()
                    else:
                        errorBox = JuiceBox()
                else:
                    errorBox = QuitBox()
                    log.err(error)  # here is where server-side logging happens
                    # if the error isn't handled
                    code = 'UNHANDLED'
                    desc = "Unhandled Remote System Exception "
                errorBox[ERROR] = box[ASK]
                errorBox[ERROR_DESCRIPTION] = desc
                errorBox[ERROR_CODE] = code
                if self.transport is not None:
                    errorBox.sendTo(self)
                return None  # intentionally stop the error here: don't log the
                # traceback if it's handled, do log it (earlier) if
                # it isn't

            self.dispatchCommand(self, cmd, box).addCallbacks(sendAnswer,
                                                              sendError
                                                              ).addErrback(
                self._puke)
        else:
            raise RuntimeError(
                "Empty packet received over connection-oriented juice: %r" % (
                    box,))

    def sendBoxCommand(self, command, box, requiresAnswer=True):
        """
        Send a command across the wire with the given C{juice.Box}.

        Returns a Deferred which fires with the response C{juice.Box} when it
        is received, or fails with a C{juice.RemoteJuiceError} if an error is
        received.

        If the Deferred fails and the error is not handled by the caller of
        this method, the failure will be logged and the connection dropped.
        """
        if self._outstandingRequests is None:
            return fail(CONNECTION_LOST)
        box[COMMAND] = command
        tag = self._nextTag()
        if requiresAnswer:
            box[ASK] = tag
            result = self._outstandingRequests[tag] = Deferred()
        else:
            result = None
        box.sendTo(self)
        return result


class Argument:
    optional = False

    def __init__(self, optional=False):
        self.optional = optional

    def retrieve(self, d, name):
        if self.optional:
            value = d.get(name)
            if value is not None:
                del d[name]
        else:
            value = d.pop(name)
        return value

    def fromBox(self, name, strings, objects, proto):
        st = self.retrieve(strings, name)
        if self.optional and st is None:
            objects[name] = None
        else:
            objects[name] = self.fromStringProto(st, proto)

    def toBox(self, name, strings, objects, proto):
        obj = self.retrieve(objects, name)
        if self.optional and obj is None:
            # strings[name] = None
            return
        else:
            strings[name] = self.toStringProto(obj, proto)

    def fromStringProto(self, inString, proto):
        return self.fromString(inString)

    def toStringProto(self, inObject, proto):
        return self.toString(inObject)

    def fromString(self, inString):
        raise NotImplementedError()

    def toString(self, inObject):
        raise NotImplementedError()


class JuiceList(Argument):
    def __init__(self, subargs):
        self.subargs = subargs

    def fromStringProto(self, inString, proto):
        boxes = parseString(inString)
        values = [stringsToObjects(box, self.subargs, proto)
                  for box in boxes]
        return values

    def toStringProto(self, inObject, proto):
        return ''.join([objectsToStrings(
            objects, self.subargs, Box(), proto
        ).serialize() for objects in inObject])


class ListOf(Argument):
    def __init__(self, subarg, delimiter=', '):
        self.subarg = subarg
        self.delimiter = delimiter

    def fromStringProto(self, inString, proto):
        strings = inString.split(self.delimiter)
        L = [self.subarg.fromStringProto(string, proto)
             for string in strings]
        return L

    def toStringProto(self, inObject, proto):
        L = []
        for inSingle in inObject:
            outString = self.subarg.toStringProto(inSingle, proto)
            assert self.delimiter not in outString
            L.append(outString)
        return self.delimiter.join(L)


class Integer(Argument):
    fromString = int

    def toString(self, inObject):
        return str(int(inObject))


class String(Argument):
    def toString(self, inObject):
        return inObject

    def fromString(self, inString):
        return inString


class EncodedString(Argument):

    def __init__(self, encoding):
        self.encoding = encoding

    def toString(self, inObject):
        return inObject.encode(self.encoding)

    def fromString(self, inString):
        return inString.decode(self.encoding)


# Temporary backwards compatibility for Exponent


Body = String


class Unicode(String):
    def toString(self, inObject):
        # assert isinstance(inObject, unicode)
        return String.toString(self, inObject.encode('utf-8'))

    def fromString(self, inString):
        # assert isinstance(inString, str)
        return String.fromString(self, inString).decode('utf-8')


class Path(Unicode):
    def fromString(self, inString):
        return filepath.FilePath(Unicode.fromString(self, inString))

    def toString(self, inObject):
        return Unicode.toString(self, inObject.path)


class Float(Argument):
    fromString = float
    toString = str


class Base64Binary(Argument):
    def toString(self, inObject):
        return inObject.encode('base64').replace('\n', '')

    def fromString(self, inString):
        return inString.decode('base64')


class Time(Argument):
    def toString(self, inObject):
        return inObject.asISO8601TimeAndDate()

    def fromString(self, inString):
        return extime.Time.fromISO8601TimeAndDate(inString)


class ExtraArg:
    def fromTransport(self, inTransport):
        raise NotImplementedError()


class Peer(ExtraArg):
    def fromTransport(self, inTransport):
        return inTransport.getQ2QPeer()


class PeerDomain(ExtraArg):
    def fromTransport(self, inTransport):
        return inTransport.getQ2QPeer().domain


class PeerUser(ExtraArg):
    def fromTransport(self, inTransport):
        return inTransport.getQ2QPeer().resource


class Host(ExtraArg):
    def fromTransport(self, inTransport):
        return inTransport.getQ2QHost()


class HostDomain(ExtraArg):
    def fromTransport(self, inTransport):
        return inTransport.getQ2QHost().domain


class HostUser(ExtraArg):
    def fromTransport(self, inTransport):
        return inTransport.getQ2QHost().resource


class Boolean(Argument):
    def fromString(self, inString):
        if inString == 'True':
            return True
        elif inString == 'False':
            return False
        else:
            raise RuntimeError("Bad boolean value: %r" % (inString,))

    def toString(self, inObject):
        if inObject:
            return 'True'
        else:
            return 'False'


class Command:
    class __metaclass__(type):
        def __new__(cls, name, bases, attrs):
            re = attrs['reverseErrors'] = {}
            er = attrs['allErrors'] = {}
            for v, k in attrs.get('errors', {}).items():
                re[k] = v
                er[v] = k
            for v, k in attrs.get('fatalErrors', {}).items():
                re[k] = v
                er[v] = k
            return type.__new__(cls, name, bases, attrs)

    arguments = []
    response = []
    extra = []
    namespaces = [None]  # This is set to [None] on purpose: None means
    # "no namespace", not "empty list".  "empty
    # list" will make your command invalid in _all_
    # namespaces, effectively uncallable.
    errors = {}
    fatalErrors = {}

    commandType = Box
    responseType = Box

    def commandName():
        def get(self):
            return self.__class__.__name__
            raise NotImplementedError("Missing command name")

        return get,

    commandName = property(*commandName())

    def __init__(self, **kw):
        self.structured = kw
        givenArgs = [normalizeKey(k) for k in list(kw.keys())]
        forgotten = []
        for name, arg in self.arguments:
            if normalizeKey(name) not in givenArgs and not arg.optional:
                forgotten.append(normalizeKey(name))
        #         for v in kw.itervalues():
        #             if v is None:
        #                 from pprint import pformat
        #                 raise RuntimeError("ARGH: %s" % pformat(kw))
        if forgotten:
            if len(forgotten) == 1:
                plural = 'an argument'
            else:
                plural = 'some arguments'
            raise RuntimeError("You forgot %s to %r: %s" % (
                plural, self.commandName, ', '.join(forgotten)))
        forgotten = []

    def makeResponse(cls, objects, proto):
        try:
            return objectsToStrings(objects, cls.response, cls.responseType(),
                                    proto)
        except Exception as e:
            log.msg("Exception in %r.makeResponse [ERROR: %r]" % (cls, e,))
            raise

    makeResponse = classmethod(makeResponse)

    def do(self, proto, namespace=None, requiresAnswer=True):
        if namespace is not None:
            cmd = namespace + ":" + self.commandName
        else:
            cmd = self.commandName

        def _massageError(error):
            error.trap(RemoteJuiceError)
            rje = error.value
            return Failure(self.reverseErrors.get(rje.errorCode,
                                                  UnhandledRemoteJuiceError)(
                rje.description))

        d = proto.sendBoxCommand(
            cmd, objectsToStrings(self.structured, self.arguments,
                                  self.commandType(),
                                  proto),
            requiresAnswer)

        if requiresAnswer:
            d.addCallback(stringsToObjects, self.response, proto)
            d.addCallback(self.addExtra, proto.transport)
            d.addErrback(_massageError)

        return d

    def addExtra(self, d, transport):
        for name, extraArg in self.extra:
            d[name] = extraArg.fromTransport(transport)
        return d


class ProtocolSwitchCommand(Command):
    """Use this command to switch from something Juice-derived to a different
    protocol mid-connection.  This can be useful to use juice as the
    connection-startup negotiation phase.  Since TLS is a different layer
    entirely, you can use Juice to negotiate the security parameters of your
    connection, then switch to a different protocol, and the connection will
    remain secured.
    """

    def __init__(self, __protoToSwitchToFactory, **kw):
        self.protoToSwitchToFactory = __protoToSwitchToFactory
        super(ProtocolSwitchCommand, self).__init__(**kw)

    def makeResponse(cls, innerProto, proto):
        return _SwitchBox(innerProto)

    makeResponse = classmethod(makeResponse)

    def do(self, proto, namespace=None):
        d = super(ProtocolSwitchCommand, self).do(proto)
        proto._lock()

        def switchNow(ign):
            innerProto = self.protoToSwitchToFactory.buildProtocol(
                proto.transport.getPeer())
            proto._switchTo(innerProto, self.protoToSwitchToFactory)
            return ign

        def die(ign):
            proto.transport.loseConnection()
            return ign

        def handle(ign):
            self.protoToSwitchToFactory.clientConnectionFailed(None, Failure(
                CONNECTION_LOST))
            return ign

        return d.addCallbacks(switchNow, handle).addErrback(die)


class Negotiate(Command):
    commandName = 'Negotiate'

    arguments = [('versions', ListOf(Integer()))]
    response = [('version', Integer())]

    responseType = NegotiateBox


class Juice(LineReceiver, JuiceParserBase):
    """
    JUICE (JUice Is Concurrent Events) is a simple connection-oriented
    request/response protocol.  Packets, or "boxes", are collections of
    RFC2822-inspired headers, plus a body.  Note that this is NOT a literal
    interpretation of any existing RFC, 822, 2822 or otherwise, but a simpler
    version that does not do line continuations, does not specify any
    particular format for header values, dispatches semantic meanings of most
    headers on the -Command header rather than giving them global meaning, and
    allows multiple sets of headers (messages, or JuiceBoxes) on a connection.

    All headers whose names begin with a dash ('-') are reserved for use by the
    protocol.  All others are for application use - their meaning depends on
    the value of the "-Command" header.
    """

    protocolName = 'juice-base'

    hostCertificate = None

    MAX_LENGTH = 1024 * 1024

    isServer = property(lambda self: self._issueGreeting,
                        doc="""
                        True if this is a juice server, e.g. it is going to
                        issue or has issued a server greeting upon
                        connection.
                        """)

    isClient = property(lambda self: not self._issueGreeting,
                        doc="""
                        True if this is a juice server, e.g. it is not going to
                        issue or did not issue a server greeting upon
                        connection.
                        """)

    def __init__(self, issueGreeting):
        """
        @param issueGreeting: whether to issue a greeting when connected.  This
        should be set on server-side Juice protocols.
        """
        JuiceParserBase.__init__(self)
        self._issueGreeting = issueGreeting

    def __repr__(self):
        return '<%s %s/%s at 0x%x>' % (
            self.__class__.__name__,
            self.isClient and 'client' or 'server',
            self.innerProtocol, id(self))

    __locked = False

    def _lock(self):
        """
        Lock this Juice instance so that no further Juice traffic may be sent.
        This is used when sending a request to switch underlying protocols.
        You probably want to subclass ProtocolSwitchCommand rather than calling
        this directly.
        """
        self.__locked = True

    innerProtocol = None

    def _switchTo(self, newProto, clientFactory=None):
        """
        Switch this Juice instance to a new protocol.  You need to do this
        'simultaneously' on both ends of a connection; the easiest way to do
        this is to use a subclass of ProtocolSwitchCommand.
        """

        assert self.innerProtocol is None,\
            "Protocol can only be safely switched once."
        self.setRawMode()
        self.innerProtocol = newProto
        self.innerProtocolClientFactory = clientFactory
        newProto.makeConnection(self.transport)

    innerProtocolClientFactory = None

    def juiceBoxReceived(self, box):
        if self.__locked and COMMAND in box and ASK in box:
            # This is a command which will trigger an answer, and we can no
            # longer answer anything, so don't bother delivering it.
            return
        return super(Juice, self).juiceBoxReceived(box)

    def sendPacket(self, completeBox):
        """
        Send a juice.Box to my peer.

        Note: transport.write is never called outside of this method.
        """
        assert not self.__locked, \
            "You cannot send juice packets when a connection is locked"
        if self._startingTLSBuffer is not None:
            self._startingTLSBuffer.append(completeBox)
        else:
            if debug:
                log.msg("Juice send: %s" % pprint.pformat(
                    dict(iter(completeBox.items()))))

            self.transport.write(completeBox.serialize())

    def sendCommand(self, command, __content='', __answer=True, **kw):
        box = JuiceBox(__content, **kw)
        return self.sendBoxCommand(command, box, requiresAnswer=__answer)

    _outstandingRequests = None
    _justStartedTLS = False

    def makeConnection(self, transport):
        self._transportPeer = transport.getPeer()
        self._transportHost = transport.getHost()
        log.msg("%s %s connection established (HOST:%s PEER:%s)" % (
            self.isClient and "client" or "server",
            self.__class__.__name__,
            self._transportHost,
            self._transportPeer))
        self._outstandingRequests = {}
        self._requestBuffer = []
        LineReceiver.makeConnection(self, transport)

    _startingTLSBuffer = None

    def prepareTLS(self):
        self._startingTLSBuffer = []

    def startTLS(self, certificate, *verifyAuthorities):
        if self.hostCertificate is None:
            self.hostCertificate = certificate
            self._justStartedTLS = True
            self.transport.startTLS(certificate.options(*verifyAuthorities))
            stlsb = self._startingTLSBuffer
            if stlsb is not None:
                self._startingTLSBuffer = None
                for box in stlsb:
                    self.sendPacket(box)
        else:
            raise RuntimeError(
                "Previously authenticated connection between %s and %s "
                "is trying to re-establish as %s" % (
                    self.hostCertificate,
                    Certificate.peerFromTransport(self.transport),
                    (certificate, verifyAuthorities)))

    def dataReceived(self, data):
        # If we successfully receive any data after TLS has been started, that
        # means the connection was secured properly.  Make a note of that fact.
        if self._justStartedTLS:
            self._justStartedTLS = False
        return LineReceiver.dataReceived(self, data)

    def connectionLost(self, reason):
        log.msg("%s %s connection lost (HOST:%s PEER:%s)" % (
            self.isClient and 'client' or 'server',
            self.__class__.__name__,
            self._transportHost,
            self._transportPeer))
        self.failAllOutgoing(reason)
        if self.innerProtocol is not None:
            self.innerProtocol.connectionLost(reason)
            if self.innerProtocolClientFactory is not None:
                self.innerProtocolClientFactory.clientConnectionLost(None,
                                                                     reason)

    def lineReceived(self, line):
        if line:
            self._requestBuffer.append(line)
        else:
            buf = self._requestBuffer
            self._requestBuffer = []
            bodylen, b = parseJuiceHeaders(buf)
            if bodylen:
                self._bodyRemaining = bodylen
                self._bodyBuffer = []
                self._pendingBox = b
                self.setRawMode()
            else:
                self.juiceBoxReceived(b)

    def rawDataReceived(self, data):
        if self.innerProtocol is not None:
            self.innerProtocol.dataReceived(data)
            return
        self._bodyRemaining -= len(data)
        if self._bodyRemaining <= 0:
            if self._bodyRemaining < 0:
                self._bodyBuffer.append(data[:self._bodyRemaining])
                extraData = data[self._bodyRemaining:]
            else:
                self._bodyBuffer.append(data)
                extraData = ''
            self._pendingBox['body'] = ''.join(self._bodyBuffer)
            self._bodyBuffer = None
            b, self._pendingBox = self._pendingBox, None
            self.juiceBoxReceived(b)
            if self.innerProtocol is not None:
                self.innerProtocol.makeConnection(self.transport)
                if extraData:
                    self.innerProtocol.dataReceived(extraData)
            else:
                self.setLineMode(extraData)
        else:
            self._bodyBuffer.append(data)

    protocolVersion = 0

    def _setProtocolVersion(self, version):
        # if we ever want to actually mangle encodings, this is the place to do
        # it!
        self.protocolVersion = version
        return version

    def renegotiateVersion(self, newVersion):
        assert \
            newVersion in VERSIONS, (
                "This side of the connection doesn't support version %r" %
                (newVersion,))
        v = VERSIONS[:]
        v.remove(newVersion)
        return Negotiate(versions=[newVersion]).do(self).addCallback(
            lambda ver: self._setProtocolVersion(ver['version']))

    def command_NEGOTIATE(self, versions):
        for version in versions:
            if version in VERSIONS:
                return dict(version=version)
        raise IncompatibleVersions()

    command_NEGOTIATE.command = Negotiate


VERSIONS = [1]

from io import StringIO


class _ParserHelper(Juice):
    def __init__(self):
        Juice.__init__(self, False)
        self.boxes = []
        self.results = Deferred()

    def getPeer(self):
        return 'string'

    def getHost(self):
        return 'string'

    disconnecting = False

    def juiceBoxReceived(self, box):
        self.boxes.append(box)

    # Synchronous helpers
    def parse(cls, fileObj):
        p = cls()
        p.makeConnection(p)
        p.dataReceived(fileObj.read())
        return p.boxes

    parse = classmethod(parse)

    def parseString(cls, data):
        return cls.parse(StringIO(data))

    parseString = classmethod(parseString)


parse = _ParserHelper.parse
parseString = _ParserHelper.parseString


def stringsToObjects(strings, arglist, proto):
    objects = {}
    myStrings = strings.copy()
    for argname, argparser in arglist:
        argparser.fromBox(argname, myStrings, objects, proto)
    return objects


def objectsToStrings(objects, arglist, strings, proto):
    myObjects = {}
    for (k, v) in list(objects.items()):
        myObjects[normalizeKey(k)] = v

    for argname, argparser in arglist:
        argparser.toBox(argname, strings, myObjects, proto)
    return strings


class JuiceServerFactory(ServerFactory):
    protocol = Juice

    def buildProtocol(self, addr):
        prot = self.protocol(True)
        prot.factory = self
        return prot


class JuiceClientFactory(ClientFactory):
    protocol = Juice

    def buildProtocol(self, addr):
        prot = self.protocol(False)
        prot.factory = self
        return prot
