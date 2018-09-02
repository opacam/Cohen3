# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2007 - Frank Scholz <coherence@beebits.net>
from lxml import etree
from twisted.internet import defer
from twisted.python import failure
from twisted.web import server, resource

import coherence.extern.louie as louie
from coherence import log, SERVER_ID
from coherence.upnp.core import soap_lite


class errorCode(Exception):
    def __init__(self, status):
        Exception.__init__(self)
        self.status = status


class UPnPPublisher(resource.Resource, log.LogAble):
    """ Based upon twisted.web.soap.SOAPPublisher and
        extracted to remove the SOAPpy dependency

        UPnP requires headers and OUT parameters to be returned
        in a slightly
        different way than the SOAPPublisher class does.
    """
    logCategory = 'soap'
    isLeaf = 1
    encoding = "UTF-8"
    envelope_attrib = None

    def _sendResponse(self, request, response, status=200):
        self.debug('_sendResponse %s %s', status, response)
        if status == 200:
            request.setResponseCode(200)
        else:
            request.setResponseCode(500)

        if self.encoding is not None:
            mimeType = b'text/xml; charset="%r"' % self.encoding
        else:
            mimeType = b"text/xml"
        request.setHeader(b"Content-type", mimeType)
        request.setHeader(b"Content-length", len(response))
        request.setHeader(b"EXT", b'')
        request.setHeader(b"SERVER", SERVER_ID.encode('ascii'))
        r = response if isinstance(response, bytes) else response.encode('ascii')
        request.write(r)
        request.finish()

    def _methodNotFound(self, request, methodName):
        response = soap_lite.build_soap_error(401)
        self._sendResponse(request, response, status=401)

    def _gotResult(self, result, request, methodName, ns):
        self.debug('_gotResult %s %s %s %s', result, request, methodName, ns)

        response = soap_lite.build_soap_call(methodName, result, ns=ns,
                                             is_response=True)
        self._sendResponse(request, response)

    def _gotError(self, failure, request, methodName, ns):
        self.info('_gotError %s %s', failure, failure.value)
        e = failure.value
        status = 500

        if isinstance(e, errorCode):
            status = e.status
        else:
            failure.printTraceback()

        response = soap_lite.build_soap_error(status)
        self._sendResponse(request, response, status=status)

    def lookupFunction(self, functionName):
        function = getattr(self, "soap_%s" % functionName, None)
        if not function:
            function = getattr(self, "soap__generic", None)
        if function:
            return function, getattr(function, "useKeywords", False)
        else:
            return None, None

    def render(self, request):
        """Handle a SOAP command."""
        data = request.content.read()
        headers = request.getAllHeaders()
        self.info('soap_request: %s', headers)

        # allow external check of data
        louie.send('UPnPTest.Control.Client.CommandReceived', None, headers,
                   data)

        def print_c(e):
            for c in e.getchildren():
                print(c, c.tag)
                print_c(c)

        tree = etree.fromstring(data)

        body = tree.find('{http://schemas.xmlsoap.org/soap/envelope/}Body')
        method = body.getchildren()[0]
        methodName = method.tag
        ns = None

        if methodName.startswith('{') and methodName.rfind('}') > 1:
            ns, methodName = methodName[1:].split('}')

        args = []
        kwargs = {}
        for child in method.getchildren():
            kwargs[child.tag] = self.decode_result(child)
            args.append(kwargs[child.tag])

        # p, header, body, attrs = SOAPpy.parseSOAPRPC(data, 1, 1, 1)
        # methodName, args, kwargs, ns = p._name, p._aslist, p._asdict, p._ns

        try:
            headers[b'content-type'].index(b'text/xml')
        except:
            self._gotError(failure.Failure(errorCode(415)), request, methodName)
            return server.NOT_DONE_YET

        self.debug('headers: %r', headers)

        function, useKeywords = self.lookupFunction(methodName)
        # print 'function', function, 'keywords', useKeywords, 'args', args, 'kwargs', kwargs

        if not function:
            self._methodNotFound(request, methodName)
            return server.NOT_DONE_YET
        else:
            keywords = {'soap_methodName': methodName}
            if (b'user-agent' in headers and
                    headers[b'user-agent'].find(b'Xbox/') == 0):
                keywords['X_UPnPClient'] = 'XBox'
            # if(headers.has_key('user-agent') and
            #        headers['user-agent'].startswith("""Mozilla/4.0 (compatible; UPnP/1.0; Windows""")):
            #    keywords['X_UPnPClient'] = 'XBox'
            if (b'x-av-client-info' in headers and
                    headers[b'x-av-client-info'].find(b'"PLAYSTATION3') > 0):
                keywords['X_UPnPClient'] = 'PLAYSTATION3'
            if (b'user-agent' in headers and
                    headers[b'user-agent'].find(
                        b'Philips-Software-WebClient/4.32') == 0):
                keywords['X_UPnPClient'] = 'Philips-TV'
            for k, v in list(kwargs.items()):
                keywords[str(k)] = v
            self.info('call %s %s', methodName, keywords)
            if hasattr(function, "useKeywords"):
                d = defer.maybeDeferred(function, **keywords)
            else:
                d = defer.maybeDeferred(function, *args, **keywords)

        d.addCallback(self._gotResult, request, methodName, ns)
        d.addErrback(self._gotError, request, methodName, ns)
        return server.NOT_DONE_YET

    def decode_result(self, element):
        type = element.get('{http://www.w3.org/1999/XMLSchema-instance}type')
        if type is not None:
            try:
                prefix, local = type.split(":")
                if prefix == 'xsd':
                    type = local
            except ValueError:
                pass

        if type == "integer" or type == "int":
            return int(element.text)
        if type == "float" or type == "double":
            return float(element.text)
        if type == "boolean":
            return element.text == "true"

        return element.text or ""
