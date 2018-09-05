# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2007 - Frank Scholz <coherence@beebits.net>
from lxml import etree
from twisted.python import failure

from coherence import log
from coherence.upnp.core import soap_lite
from coherence.upnp.core.utils import getPage


class SOAPProxy(log.LogAble):
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
        log.LogAble.__init__(self)
        if not isinstance(url, bytes):
            self.warning('SOAPProxy.__init__: '
                         'url is not string bytes...modifying')
            url = url.encode('ascii')
        self.url = url
        self.namespace = namespace
        self.header = header
        self.action = None
        self.soapaction = soapaction
        self.envelope_attrib = envelope_attrib

    def callRemote(self, soapmethod, arguments):
        soapaction = soapmethod or self.soapaction
        if '#' not in soapaction:
            soapaction = '#'.join((self.namespace[1], soapaction))
        self.action = soapaction.split('#')[1].encode('ascii')

        self.info("callRemote %r %r %r %r", self.soapaction, soapmethod,
                  self.namespace, self.action)
        self.debug('\t- arguments: {}'.format(arguments))
        self.debug('\t- action: {}'.format(self.action))
        self.debug('\t- namespace: {}'.format(self.namespace))

        headers = {'content-type': 'text/xml ;charset="utf-8"',
                   'SOAPACTION': '"{}"'.format(soapaction), }
        if 'headers' in arguments:
            headers.update(arguments['headers'])
            del arguments['headers']

        payload = soap_lite.build_soap_call(self.action, arguments,
                                            ns=self.namespace[1])
        self.debug('\t- payload: {}'.format(payload))

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
                        './/{urn:schemas-upnp-org:control-1-0}'
                        'errorCode').text,
                    body.find(
                        './/{urn:schemas-upnp-org:control-1-0}'
                        'errorDescription').text)))
            except Exception as e:
                self.error('callRemote error on getting traceback: %r' % e)
                import traceback
                self.debug(traceback.format_exc())
            return error

        return getPage(
            self.url,
            postdata=payload,
            method=b"POST",
            headers=headers).addCallbacks(
            self._cbGotResult, gotError, None, None, [self.url], None)

    def _cbGotResult(self, result):
        page, headers = result

        def print_c(e):
            for c in e.getchildren():
                print(c, c.tag)
                print_c(c)

        self.debug("_cbGotResult.action: %r", self.action)
        self.debug("_cbGotResult.result: %r", page)

        a = self.action.decode('utf-8')
        tree = etree.fromstring(page)
        body = tree.find('{http://schemas.xmlsoap.org/soap/envelope/}Body')
        response = body.find(
            '{%s}%sResponse' % (self.namespace[1], a))
        if response is None:
            """ fallback for improper SOAP action responses """
            response = body.find('%sResponse' % a)
        self.debug("callRemote response  %s", response)
        result = {}
        if response is not None:
            for elem in response:
                result[elem.tag] = self.decode_result(elem)

        return result

    def decode_result(self, element):
        self.debug('decode_result [element]: {}'.format(element))
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
