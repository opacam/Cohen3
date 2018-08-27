# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2007 - Frank Scholz <coherence@beebits.net>
from lxml import etree
from twisted.python import failure

from coherence import log
from coherence.upnp.core import soap_lite
from coherence.upnp.core.utils import getPage


class SOAPProxy(log.Loggable):
    """ A Proxy for making remote SOAP calls.

        Based upon twisted.web.soap.Proxy and
        extracted to remove the SOAPpy dependency

        Pass the URL of the remote SOAP server to the constructor.

        Use proxy.callRemote('foobar', 1, 2) to call remote method
        'foobar' with args 1 and 2, proxy.callRemote('foobar', x=1)
        will call foobar with named argument 'x'.
    """

    logCategory = 'soap'

    def __init__(self, url, namespace=None, envelope_attrib=None, header=None,
                 soapaction=None):
        log.Loggable.__init__(self)
        self.url = url
        self.namespace = namespace
        self.header = header
        self.action = None
        self.soapaction = soapaction
        self.envelope_attrib = envelope_attrib

    def callRemote(self, soapmethod, arguments):
        soapaction = soapmethod or self.soapaction
        url_bytes = self.url.encode('ascii')
        if '#' not in soapaction:
            soapaction = '#'.join((self.namespace[1], soapaction))
        self.action = soapaction.split('#')[1]

        self.info("callRemote %r %r %r %r", self.soapaction, soapmethod,
                  self.namespace, self.action)

        headers = {b'content-type': b'text/xml ;charset="utf-8"',
                   b'SOAPACTION': '"{}"'.format(soapaction).encode('ascii'), }
        if 'headers' in arguments:
            headers.update(arguments['headers'])
            del arguments['headers']

        payload = soap_lite.build_soap_call(self.action, arguments,
                                            ns=self.namespace[1])

        self.info("callRemote soapaction:  %s %s", self.action, self.url)
        self.debug("callRemote payload:  %s", payload)

        def gotError(error, url):
            self.warning("error requesting url %r", url)
            self.debug(error)
            try:
                # TODO: Must deal with error handling
                self.error('\t-> callRemote [type: {}]: {} => {}'.format(
                    type(error.value.__traceback__),
                    'error.value.__traceback__',
                    error.value.__traceback__))
                tree = etree.fromstring(error.value.__traceback__)
                body = tree.find(
                    '{http://schemas.xmlsoap.org/soap/envelope/}Body')
                return failure.Failure(Exception("%s - %s" % (
                    body.find(
                        './/{urn:schemas-upnp-org:control-1-0}errorCode').text,
                    body.find(
                        './/{urn:schemas-upnp-org:control-1-0}errorDescription').text)))
            except:
                import traceback
                self.debug(traceback.format_exc())
            return error

        return getPage(
            url_bytes,
            postdata=payload,
            method=b"POST",
            headers=headers).addCallbacks(
            self._cbGotResult, gotError, None, None, [url_bytes], None)

    def _cbGotResult(self, result):
        page, headers = result

        def print_c(e):
            for c in e.getchildren():
                print(c, c.tag)
                print_c(c)

        self.debug("result: %r", page)

        tree = etree.fromstring(page)
        body = tree.find('{http://schemas.xmlsoap.org/soap/envelope/}Body')
        response = body.find(
            '{%s}%sResponse' % (self.namespace[1], self.action))
        if response is None:
            """ fallback for improper SOAP action responses """
            response = body.find('%sResponse' % self.action)
        self.debug("callRemote response  %s", response)
        result = {}
        if response is not None:
            for elem in response:
                result[elem.tag] = self.decode_result(elem)

        return result

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
