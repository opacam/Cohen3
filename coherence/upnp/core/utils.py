# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright (C) 2006 Fluendo, S.A. (www.fluendo.com).
# Copyright 2006, Frank Scholz <coherence@beebits.net>
# Copyright 2018, Pol Canelles <canellestudi@gmail.com>

'''
Utils
=====

Set of utilities to help process the data and the assets of the Cohen3 project.
It includes several methods which covers different fields, here are grouped by
his functionality:

    - encode/decode strings:
        - :meth:`~coherence.upnp.core.utils.to_string`
        - :meth:`~coherence.upnp.core.utils.to_bytes`
    - parse xml/html data:
        - :meth:`~coherence.upnp.core.utils.parse_xml`
        - :meth:`~coherence.upnp.core.utils.parse_http`
        - :meth:`~coherence.upnp.core.utils.de_chunk_payload`
    - get ip/host:
        - :meth:`~coherence.upnp.core.utils.get_ip_address`
        - :meth:`~coherence.upnp.core.utils.get_host_address`
    - get/download page related:
        - :meth:`~coherence.upnp.core.utils.getPage`
        - :meth:`~coherence.upnp.core.utils.downloadPage`
        - :class:`~coherence.upnp.core.utils.myHTTPPageGetter`
        - :class:`~coherence.upnp.core.utils.HeaderAwareHTTPClientFactory`
    - proxy clients and resources:
        - :class:`~coherence.upnp.core.utils.ProxyClient`
        - :class:`~coherence.upnp.core.utils.ProxyClientFactory`
        - :class:`~coherence.upnp.core.utils.ReverseProxyResource`
        - :class:`~coherence.upnp.core.utils.ReverseProxyUriResource`
    - file assets:
        - :attr:`~coherence.upnp.core.utils.StaticFile`
        - :class:`~coherence.upnp.core.utils.BufferFile`
        - :class:`~coherence.upnp.core.utils.BufferFileTransfer`
    - date/time operations:
        - :class:`~coherence.upnp.core.utils._tz`
        - :class:`~coherence.upnp.core.utils._CET`
        - :class:`~coherence.upnp.core.utils._CEST`
        - :meth:`~coherence.upnp.core.utils.datefaker`
        - :attr:`~coherence.upnp.core.utils._bdates`
    - python 2to3 compatibility methods:
        - :meth:`~coherence.upnp.core.utils.cmp`

'''
import xml.etree.ElementTree as ET
from lxml import etree
from io import BytesIO

from urllib.parse import urlsplit, urlparse

from twisted.internet import reactor, defer, abstract
from twisted.python import failure
from twisted.web import client
from twisted.web import http, static
from twisted.web import proxy, resource, server

from coherence import SERVER_ID
from coherence import log

logger = log.get_logger('utils')

try:
    from twisted.protocols._c_urlarg import unquote
except ImportError:
    from urllib.parse import unquote

try:
    import netifaces

    have_netifaces = True
except ImportError:
    have_netifaces = False


def to_string(x):
    '''
    This method is a helper function that takes care of converting into a
    string any string or bytes string or integer. This is useful for
    decoding twisted responses into the default python 3 string encoding or
    to get a string representation of an object.

    .. versionadded:: 0.8.2

    .. note:: If the argument passed is not of type str, bytes or int,
              it will try to get the string representation of the object.

    .. warning:: This is similar to :meth:`~coherence.upnp.core.utils.to_bytes`
                 but with the difference that the returned result it will be
                 always a string.
    '''
    if isinstance(x, str):
        return x
    elif isinstance(x, bytes):
        return x.decode('utf-8')
    else:
        return str(x)


def to_bytes(x):
    '''
    This method is a helper function that takes care of converting a string
    or string of bytes into bytes, needed for most of the write operations for
    twisted responses. It is useful when we don't know the type of the
    processed string.

    .. versionadded:: 0.8.2

    .. versionchanged:: 0.8.3
       Errors will be bypassed with a warning

    .. note:: If the argument passed is not of type str or bytes, it will be
              converted to his string representation and then it will be
              converted into bytes.

    .. warning:: If, while encoding, some error is encountered, it will be
                 bypassed and user will be notified with a log warning. The
                 conflicting character will be replaced for the symbol "?"
                 (U+FFFD)
    '''
    if isinstance(x, bytes):
        return x

    if isinstance(x, str):
        try:
            return x.encode('ascii')
        except UnicodeEncodeError:
            new_x = x.encode(
                'ascii', errors='replace')
    try:
        return str(x).encode('ascii')
    except UnicodeEncodeError:
        new_x = str(x).encode(
            'ascii', errors='replace')

    logger.warning(
        f'to_bytes: Some characters could not be encoded to bytes...those will'
        f' be replaced by the symbol "?" [string before encode is: {x}]')
    return new_x


def means_true(value):
    '''
    Transform a value representing a boolean into a boolean.

    The valid expressions are:
        - True or 'True'
        - 1 or '1'
        - 'yes' or 'ok'

    .. note:: the string expressions are not case sensitive
    '''
    value = to_string(value).lower()
    return value in [True, 1, '1', 'true', 'yes', 'ok']


def generalise_boolean(value):
    ''' standardize the different boolean incarnations

        transform anything that looks like a 'True' into a '1',
        and everything else into a '0'
    '''
    if means_true(value):
        return '1'
    return '0'


generalize_boolean = generalise_boolean


def parse_xml(data, encoding='utf-8', dump_invalid_data=False):
    '''
    Takes an xml string and returns an XML element hierarchy
    '''
    parser = ET.XMLParser(encoding=encoding)

    # my version of twisted.web returns page_infos as a dictionary in
    # the second item of the data list
    # :fixme: This must be handled where twisted.web is fetching the data
    if isinstance(data, (list, tuple)):
        data = data[0]

    data = to_bytes(data)

    # Guess from who we're getting this?
    data = data.replace(b'\x00', b'')
    try:
        parser.feed(data)
    except Exception as error:
        if dump_invalid_data:
            print(error, repr(data))
        parser.close()
        raise
    else:
        return ET.ElementTree(parser.close())


def parse_with_lxml(data, encoding='utf-8'):
    '''
    Takes an xml string or a response as argument and returns a root tree.
    This method is similar to :meth:`~coherence.upnp.core.utils.parse_xml` but
    here we use the lxml module and a custom parser method to return an
    lxml's ElementTree object.

    .. versionadded:: 0.8.3

    .. note:: This parser allow us to parse successfully some responses which
              contain encoding defined (ex: soap messages) and also has the
              ability to parse a broken xml. This method could be useful to
              parse some small pieces of html code into an xml tree in order
              to extract some info.
    '''
    if isinstance(data, (list, tuple)):
        data = data[0]

    data = to_bytes(data)

    parser = etree.XMLParser(
        recover=True, encoding=encoding)
    tree = etree.parse(BytesIO(data), parser)
    return tree


def parse_http_response(data):
    '''
     Takes a response as argument and returns a tuple: cmd, headers

     The first value of the tuple (cmd) will contain the server response and
     the second one the headers.

     .. note:: don't try to get the body, there are responses without '''
    if isinstance(data, bytes):
        data = data.decode('utf-8')
    header = data.split('\r\n\r\n')[0]

    lines = header.split('\r\n')
    cmd = lines[0].split(' ')
    lines = [x.replace(': ', ':', 1) for x in lines[1:]]
    lines = [x for x in lines if len(x) > 0]

    headers = [x.split(':', 1) for x in lines]
    headers = dict([(x[0].lower().replace("'", ''),
                     x[1].replace("'", '')) for x in headers])

    return cmd, headers


def get_ip_address(ifname):
    '''
    Determine the IP address by interface name

    http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/439094
    (c) Paul Cannon
    Uses the Linux SIOCGIFADDR ioctl to find the IP address associated
    with a network interface, given the name of that interface, e.g. "eth0".
    The address is returned as a string containing a dotted quad.

    Updated to work on BSD. OpenBSD and OSX share the same value for
    SIOCGIFADDR, and its likely that other BSDs do too.

    Updated to work on Windows,
    using the optional Python module netifaces
    http://alastairs-place.net/netifaces/

    Thx Lawrence for that patch!
    '''

    if have_netifaces:
        if ifname in netifaces.interfaces():
            iface = netifaces.ifaddresses(ifname)
            ifaceadr = iface[netifaces.AF_INET]
            # we now have a list of address dictionaries,
            # there may be multiple addresses bound
            return ifaceadr[0]['addr']
    import sys
    if sys.platform in ('win32', 'sunos5'):
        return '127.0.0.1'

    from os import uname
    import socket
    import fcntl
    import struct

    system_type = uname()[0]
    if system_type == 'Linux':
        SIOCGIFADDR = 0x8915
    else:
        SIOCGIFADDR = 0xc0206921

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        ip = socket.inet_ntoa(fcntl.ioctl(
            s.fileno(),
            SIOCGIFADDR,
            struct.pack(b'256s', ifname[:15].encode('ascii'))
        )[20:24])
    except Exception:
        ip = '127.0.0.1'
    # print(f'ip is: {ip}')
    return ip


def get_host_address():
    ''' try to get determine the interface used for
        the default route, as this is most likely
        the interface we should bind to (on a single homed host!)
    '''

    import sys
    if sys.platform == 'win32':
        if have_netifaces:
            interfaces = netifaces.interfaces()
            if len(interfaces):
                # on windows assume first interface is primary
                return get_ip_address(interfaces[0])
    else:
        try:
            route_file = '/proc/net/route'
            route = open(route_file)
            if route:
                tmp = route.readline()  # skip first line
                while tmp != '':
                    tmp = route.readline()
                    li = tmp.split('\t')
                    if (len(li) > 2):
                        if li[1] == '00000000':  # default route...
                            route.close()
                            return get_ip_address(li[0])
        except IOError as msg:
            ''' fallback to parsing the output of netstat '''
            from twisted.internet import utils

            def result(r):
                from os import uname
                (osname, _, _, _, _) = uname()
                osname = osname.lower()
                lines = r.split('\n')
                for li in lines:
                    li = li.strip(' \r\n')
                    parts = [x.strip() for x in li.split(' ') if len(x) > 0]
                    if parts[0] in ('0.0.0.0', 'default'):
                        if osname[:6] == 'darwin':
                            return get_ip_address(parts[5])
                        else:
                            return get_ip_address(parts[-1])
                return '127.0.0.1'

            def fail(f):
                return '127.0.0.1'

            d = utils.getProcessOutput('netstat', ['-rn'])
            d.addCallback(result)
            d.addErrback(fail)
            return d
        except Exception as msg:
            import traceback
            traceback.print_exc()

    ''' return localhost if we haven't found anything '''
    return '127.0.0.1'


def de_chunk_payload(response):
    import io
    ''' This method takes a chunked HTTP data object and unchunks it.'''
    newresponse = io.StringIO()
    # chunked encoding consists of a bunch of lines with
    # a length in hex followed by a data chunk and a CRLF pair.
    response = io.StringIO(response)

    def read_chunk_length():
        line = response.readline()
        try:
            len = int(line.strip(), 16)
        except ValueError:
            len = 0
        return len

    len = read_chunk_length()
    while (len > 0):
        newresponse.write(response.read(len))
        line = response.readline()  # after chunk and before next chunk length
        len = read_chunk_length()

    return newresponse.getvalue()


class Request(server.Request):
    '''
    Custom implementation of twisted.web.server.Request which takes care of
    process data for our needs.
    '''

    def process(self):
        '''
        Process a request.
        '''

        # get site from channel
        self.site = self.channel.site

        # set various default headers
        self.setHeader(b'server', SERVER_ID.encode('ascii'))
        self.setHeader(b'date', http.datetimeToString())
        self.setHeader(b'content-type', b'text/html')

        # Resource Identification
        url = to_string(self.path)

        # remove trailing '/', if ever
        url = url.rstrip('/')

        scheme, netloc, path, query, fragment = urlsplit(url)
        clean_path = path[1:]
        self.prepath = []
        if path == '':
            self.postpath = []
        else:
            raw_p = list(map(unquote, clean_path.split('/')))
            self.postpath = list(i.encode('ascii') for i in raw_p)
        try:
            def deferred_rendering(r):
                self.render(r)

            resrc = self.site.getResourceFor(self)
            if resrc is None:
                self.setResponseCode(
                    http.NOT_FOUND,
                    f'Error: No resource for path {path}'.encode('ascii'))
                self.finish()
            elif isinstance(resrc, defer.Deferred):
                resrc.addCallback(deferred_rendering)
                resrc.addErrback(self.processingFailed)
            else:
                self.render(resrc)

        except Exception as e:
            logger.error(f'Error on render Request: {e}')
            self.processingFailed(failure.Failure())


class Site(server.Site):
    '''Custom implementation of :obj:`twisted.web.server.Site`'''
    noisy = False
    requestFactory = Request

    def startFactory(self):
        pass
        # http._logDateTimeStart()


class ProxyClient(proxy.ProxyClient, log.LogAble):

    def __init__(self, command, rest, version, headers, data, father):
        log.LogAble.__init__(self)
        # headers['connection'] = 'close'
        self.send_data = 0
        proxy.ProxyClient.__init__(self, command, rest, version,
                                   headers, data, father)

    def handleStatus(self, version, code, message):
        if message:
            # Add a whitespace to message, this allows empty messages
            # transparently
            message = f' {message}'
        if version == 'ICY':
            version = 'HTTP/1.1'
        proxy.ProxyClient.handleStatus(self, version, code, message)

    def handleHeader(self, key, value):
        if not key.startswith('icy-'):
            proxy.ProxyClient.handleHeader(self, key, value)

    def handleResponsePart(self, buffer):
        self.send_data += len(buffer)
        proxy.ProxyClient.handleResponsePart(self, buffer)


class ProxyClientFactory(proxy.ProxyClientFactory):
    # :fixme: Why here proxy.ProxyClient is used instad of our own
    # ProxyClent? Is out ProxyClient used at all?
    protocol = proxy.ProxyClient


class ReverseProxyResource(proxy.ReverseProxyResource):
    '''
    Resource that renders the results gotten from another server.

    Put this resource in the tree to cause everything below it to be relayed
    to a different server.
    '''

    proxyClientFactoryClass = ProxyClientFactory
    '''
    proxyClientFactoryClass (:obj:`twisted.web.proxy.ProxyClientFactory`):
    a proxy client factory class, used to create new connections.
    '''

    def __init__(self, host, port, path, reactor=reactor):
        '''
        Args:
          host (str): the host of the web server to proxy.
          port (int): the port of the web server to proxy.
          path (str): the base path to fetch data from. Note that you shouldn't
                      put any trailing slashes in it, it will be added
                      automatically in request. For example, if you put
                      B{/foo}, a request on B{/bar} will be proxied to
                      B{/foo/bar}.
          reactor (:obj:`twisted.internet.interfaces.IReactorTCP`):
              the reactor used to create connections.
        '''
        resource.Resource.__init__(self)
        self.host = host
        self.port = port
        self.path = path
        self.qs = ''
        self.reactor = reactor

    def getChild(self, path, request):
        return ReverseProxyResource(
            self.host, self.port, self.path + b'/' + path)

    def render(self, request):
        '''
        Render a request by forwarding it to the proxied server.
        '''
        # RFC 2616 tells us that we can omit the port if it's the default port,
        # but we have to provide it otherwise
        if self.port == 80:
            host = self.host
        else:
            host = self.host + b':' + to_bytes(self.port)
        request.requestHeaders.setRawHeaders(b'host', [host])
        request.content.seek(0, 0)
        qs = urlparse(request.uri)[4]
        if qs == b'':
            qs = self.qs
        if qs:
            rest = self.path + b'?' + qs
        else:
            rest = self.path
        clientFactory = self.proxyClientFactoryClass(
            request.method, rest, request.clientproto,
            request.getAllHeaders(), request.content.read(), request)
        self.reactor.connectTCP(self.host, self.port, clientFactory)
        return server.NOT_DONE_YET

    def resetTarget(self, host, port, path, qs=''):
        self.host = host
        self.port = port
        self.path = path
        self.qs = qs


class ReverseProxyUriResource(ReverseProxyResource):
    uri = None

    def __init__(self, uri, reactor=reactor):
        self.uri = to_bytes(uri)
        _, host_port, path, params, _ = urlsplit(self.uri)
        if host_port.find(b':') != -1:
            host, port = tuple(host_port.split(b':'))
            port = int(port)
        else:
            host = host_port
            port = 80
        if path == b'':
            path = b'/'
        if params == b'':
            rest = path
        else:
            rest = b'?'.join((path, params))
        ReverseProxyResource.__init__(self, host, port, rest, reactor)

    def resetUri(self, uri):
        self.uri = uri
        _, host_port, path, params, _ = urlsplit(uri)
        if host_port.find(b':') != -1:
            host, port = tuple(host_port.split(b':'))
            port = int(port)
        else:
            host = host_port
            port = 80
        self.resetTarget(host, port, path, params)


# already on twisted.web since at least 8.0.0
class myHTTPPageGetter(client.HTTPPageGetter):
    followRedirect = True


class HeaderAwareHTTPClientFactory(client.HTTPClientFactory):
    protocol = myHTTPPageGetter
    noisy = False

    def buildProtocol(self, addr):
        p = client.HTTPClientFactory.buildProtocol(self, addr)
        p.method = self.method
        p.followRedirect = self.followRedirect
        return p

    def page(self, page):
        client.HTTPClientFactory.page(self, (page, self.response_headers))


# deprecated, do not use
# already in twisted.web since at least 1.3.0
HeaderAwareHTTPDownloader = client.HTTPDownloader


def getPage(url, contextFactory=None, *args, **kwargs):
    '''
    Download a web page as a string.

    Download a page. Return a deferred, which will callback with a
    page (as a string) or errback with a description of the error.

    See :obj:`twisted.web.client.HTTPClientFactory` to see what extra args
    can be passed.

    .. note:: This function is like `twisted.web.client.getPage`, except it
              uses our HeaderAwareHTTPClientFactory instead of
              HTTPClientFactory and sets the user agent.
    '''

    url_bytes = to_bytes(url)
    if args is None:
        args = []
    if kwargs is None:
        kwargs = {}

    if 'headers' in kwargs and 'user-agent' in kwargs['headers']:
        kwargs['agent'] = kwargs['headers']['user-agent']
    elif 'agent' not in kwargs:
        kwargs['agent'] = 'Coherence PageGetter'
    new_kwargs = {}
    for k, v in kwargs.items():
        if k == 'headers':
            new_kwargs[k] = {}
            for kh, vh in kwargs['headers'].items():
                h_key = to_bytes(kh)
                h_val = to_bytes(vh)
                new_kwargs['headers'][h_key] = h_val
        else:
            new_kwargs[k] = v
    logger.info(f'getPage [url]: {url} [type: {type(url)}]')
    logger.debug(f'\t->[args]: {args} [type: {type(args)}]')
    logger.debug(f'\t->[kwargs]: {kwargs}')
    logger.debug(f'\t->[new_kwargs]: {new_kwargs}]')
    return client._makeGetterFactory(
        url_bytes,
        HeaderAwareHTTPClientFactory,
        contextFactory=contextFactory,
        *args, **new_kwargs).deferred


def downloadPage(url, file, contextFactory=None, *args, **kwargs):
    '''
    Download a web page to a file.

    Args:
        url (str or bytes): target url to download.
        file (str or file-like object): path to file on filesystem, or a
                                        file-like object.

    .. note:: See `twisted.web.client.HTTPDownloader` to see what extra args
              can be passed.
    '''
    url_bytes = to_bytes(url)

    if 'headers' in kwargs and 'user-agent' in kwargs['headers']:
        kwargs['agent'] = kwargs['headers']['user-agent']
    elif 'agent' not in kwargs:
        kwargs['agent'] = 'Coherence PageGetter'
    new_kwargs = {}
    for k, v in kwargs.items():
        if k == 'headers':
            new_kwargs[k] = {}
            for kh, vh in kwargs['headers'].items():
                h_key = to_bytes(kh)
                h_val = to_bytes(vh)
                new_kwargs['headers'][h_key] = h_val
        else:
            new_kwargs[k] = v
    logger.info(f'downloadPage [url]: {url} [type: {type(url)}]')
    logger.debug(f'\t->[args]: {args} [type: {type(args)}]')
    logger.debug(f'\t->[kwargs]: {kwargs}')
    logger.debug(f'\t->[new_kwargs]: {new_kwargs}]')
    return client.downloadPage(
        url_bytes, file, contextFactory=contextFactory,
        *args, **new_kwargs)


# StaticFile used to be a patched version of static.File. The later
# was fixed in TwistedWeb 8.2.0 and 9.0.0, while the patched variant
# contained deprecated and removed code.
StaticFile = static.File


class BufferFile(static.File):
    '''
    Custom implementation of `twisted.web.static.File` and modified accordingly
    to the patch by John-Mark Gurney (
    http://resnet.uoregon.edu/~gurney_j/jmpc/dist/twisted.web.static.patch)

    .. note:: See `twisted.web.static.File` to see what extra args can be
              passed.
    '''

    def __init__(self, path, target_size=0, *args):
        static.File.__init__(self, path, *args)
        self.target_size = target_size
        self.upnp_retry = None

    def render(self, request):
        # print ''
        # print 'BufferFile', request

        # FIXME detect when request is REALLY finished
        if request is None or request.finished:
            logger.info('No request to render!')
            return ''

        '''You know what you doing.'''
        self.restat()

        if self.type is None:
            self.type, self.encoding = static.getTypeAndEncoding(
                self.basename(),
                self.contentTypes,
                self.contentEncodings,
                self.defaultType)

        if not self.exists():
            return self.childNotFound.render(request)

        if self.isdir():
            return self.redirect(request)

        # for content-length
        if (self.target_size > 0):
            fsize = size = int(self.target_size)
        else:
            fsize = size = int(self.getFileSize())

        # print fsize

        if size == int(self.getFileSize()):
            request.setHeader(b'accept-ranges', b'bytes')

        if self.type:
            request.setHeader(b'content-type', to_bytes(self.type))
        if self.encoding:
            request.setHeader(b'content-encoding', to_bytes(self.encoding))

        try:
            f = self.openForReading()
        except IOError as e:
            import errno
            if e.errno == errno.EACCES:
                return resource.ForbiddenResource().render(request)
            else:
                raise
        if request.setLastModified(self.getmtime()) is http.CACHED:
            return ''
        trans = True

        range = request.getHeader('range')
        # print 'StaticFile', range

        tsize = size
        if range is not None:
            # This is a request for partial data...
            bytesrange = range.split('=')
            assert bytesrange[0] == 'bytes', \
                'Syntactically invalid http range header!'
            start, end = bytesrange[1].split('-', 1)
            if start:
                start = int(start)
                # Are we requesting something
                # beyond the current size of the file?
                if (start >= self.getFileSize()):
                    # Retry later!
                    logger.info(bytesrange)
                    logger.info(
                        'Requesting data beyond current scope -> '
                        'postpone rendering!')
                    self.upnp_retry = reactor.callLater(
                        1.0, self.render, request)
                    return server.NOT_DONE_YET

                f.seek(start)
                if end:
                    # print(f':{end}')
                    end = int(end)
                else:
                    end = size - 1
            else:
                lastbytes = int(end)
                if size < lastbytes:
                    lastbytes = size
                start = size - lastbytes
                f.seek(start)
                fsize = lastbytes
                end = size - 1
            size = end + 1
            fsize = end - int(start) + 1
            # start is the byte offset to begin, and end is the byte offset
            # to end..  fsize is size to send, tsize is the real size of
            # the file, and size is the byte position to stop sending.
            if fsize <= 0:
                request.setResponseCode(http.REQUESTED_RANGE_NOT_SATISFIABLE)
                fsize = tsize
                trans = False
            else:
                request.setResponseCode(http.PARTIAL_CONTENT)
                request.setHeader(b'content-range', (
                    f'bytes {str(start)}-{str(end)}/{str(tsize)} ').encode(
                        'ascii'))
                # print 'StaticFile', start, end, tsize

        request.setHeader('content-length', str(fsize))

        if request.method == b'HEAD' or trans is False:
            # pretend we're a HEAD request, so content-length
            # won't be overwritten.
            request.method = b'HEAD'
            return ''
        # print 'StaticFile out', request.headers, request.code

        # return data
        # size is the byte position to stop sending, not how many bytes to send

        BufferFileTransfer(f, size - f.tell(), request)
        # and make sure the connection doesn't get closed
        return server.NOT_DONE_YET


class BufferFileTransfer(object):
    '''
    A class to represent the transfer of a file over the network.
    '''
    request = None

    def __init__(self, file, size, request):
        self.file = file
        self.size = size
        self.request = request
        self.written = self.file.tell()
        request.registerProducer(self, 0)

    def resumeProducing(self):
        # print 'resumeProducing', self.request,self.size,self.written
        if not self.request:
            return
        data = self.file.read(
            min(abstract.FileDescriptor.bufferSize, self.size - self.written))
        if data:
            self.written += len(data)
            # this .write will spin the reactor, calling .doWrite and then
            # .resumeProducing again, so be prepared for a re-entrant call
            self.request.write(data)
        if self.request and self.file.tell() == self.size:
            self.request.unregisterProducer()
            self.request.finish()
            self.request = None

    def pauseProducing(self):
        pass

    def stopProducing(self):
        # print 'stopProducing',self.request
        self.request.unregisterProducer()
        self.file.close()
        self.request.finish()
        self.request = None


from datetime import datetime, tzinfo, timedelta
import random


class _tz(tzinfo):
    '''
    Custom base class for time zone info classes.
    '''
    def utcoffset(self, dt):
        return self._offset

    def tzname(self, dt):
        return self._name

    def dst(self, dt):
        return timedelta(0)


class _CET(_tz):
    '''
    Custom class for time zone representing Central European Time.
    '''
    _offset = timedelta(minutes=60)
    _name = 'CET'


class _CEST(_tz):
    '''
    Custom class for time zone representing Central European Summer Time.
    '''
    _offset = timedelta(minutes=120)
    _name = 'CEST'


_bdates = [datetime(1997, 2, 28, 17, 20, tzinfo=_CET()),  # Sebastian Oliver
           datetime(1999, 9, 19, 4, 12, tzinfo=_CEST()),  # Patrick Niklas
           datetime(2000, 9, 23, 4, 8, tzinfo=_CEST()),  # Saskia Alexa
           datetime(2003, 7, 23, 1, 18, tzinfo=_CEST()),  # Mara Sophie
           # you are the best!
           ]


def datefaker():
    '''
    Choose a random datetime from :attr:`~coherence.upnp.core.utils._bdates`

    .. note:: Used inside class :class:`~coherence.upnp.core.DIDLLite.Object`,
              method :meth:`~coherence.upnp.core.DIDLLite.Object.toElement`
    '''
    return random.choice(_bdates)


def cmp(x, y):
    '''
    Replacement for built-in function cmp that was removed in Python 3

    Compare the two objects x and y and return an integer according to
    the outcome. The return value is negative if x < y, zero if x == y
    and strictly positive if x > y.

    Args:
        x (object): An object
        y (object): Another object to compare with x
    '''
    return (x > y) - (x < y)
