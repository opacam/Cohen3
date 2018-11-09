# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2007 - Frank Scholz <coherence@beebits.net>
# Copyright 2018, Pol Canelles <canellestudi@gmail.com>

'''
:class:`SOAPProxy`
==================

A Proxy for making remote SOAP calls.
'''
from lxml import etree
from twisted.python import failure

from coherence import log
from coherence.upnp.core import soap_lite
from coherence.upnp.core.utils import getPage, parse_with_lxml


class SOAPProxy(log.LogAble):
    '''
    The :class:`SOAPProxy` is based upon :obj:`twisted.web.soap.Proxy`
    and extracted to remove the SOAPpy dependency.

    Initialize the :class:`SOAPProxy` class by passing the URL of the remote
    SOAP server.
    '''

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
        '''
        You can use the method :meth:`callRemote` like

        .. code-block:: python

            proxy.callRemote('foobar', 1, 2)

        to call remote method 'foobar' with args 1 and 2.

        Also you can call the method :meth:`callRemote` with named arguments

        .. code-block:: python

            proxy.callRemote('foobar', x=1)

        .. note:: The named arguments feature it will be useful to pass some
                  headers (if needed) to our soap calls.
        '''
        soapaction = soapmethod or self.soapaction
        if '#' not in soapaction:
            soapaction = '#'.join((self.namespace[1], soapaction))
        self.action = soapaction.split('#')[1].encode('ascii')

        self.info(f'callRemote {self.soapaction} {soapmethod} '
                  f'{self.namespace} {self.action}')

        headers = {'content-type': 'text/xml ;charset="utf-8"',
                   'SOAPACTION': f'"{soapaction}"', }
        if 'headers' in arguments:
            headers.update(arguments['headers'])
            del arguments['headers']

        payload = soap_lite.build_soap_call(
            self.action, arguments, ns=self.namespace[1])
        self.debug(f'callRemote payload is:  {payload}')

        def gotError(error, url):
            self.error(f'callRemote error requesting url {url}')
            self.debug(error)
            try:
                self.error(
                    f'\t-> error.value.response is: {error.value.response}')
                try:
                    tree = etree.fromstring(error.value.response)
                except Exception:
                    self.warning(
                        'callRemote: error on parsing soap result, probably'
                        ' has encoding declaration, trying with another'
                        ' method...')
                    tree = parse_with_lxml(
                        error.value.response, encoding='utf-8')
                body = tree.find(
                    '{http://schemas.xmlsoap.org/soap/envelope/}Body')
                return failure.Failure(Exception('%s - %s' % (
                    body.find(
                        './/{urn:schemas-upnp-org:control-1-0}'
                        'errorCode').text,
                    body.find(
                        './/{urn:schemas-upnp-org:control-1-0}'
                        'errorDescription').text)))
            except Exception as e:
                self.error(f'callRemote error on getting traceback: {e}')
                import traceback
                self.debug(traceback.format_exc())
            return error

        return getPage(
            self.url,
            postdata=payload,
            method=b'POST',
            headers=headers).addCallbacks(
            self._cbGotResult, gotError, None, None, [self.url], None)

    def _cbGotResult(self, result):
        page, headers = result

        def print_c(e):
            for c in e.getchildren():
                print(c, c.tag)
                print_c(c)

        self.debug(f'_cbGotResult.action: {self.action}')
        self.debug(f'_cbGotResult.result: {page}')

        a = self.action.decode('utf-8')
        tree = etree.fromstring(page)
        body = tree.find('{http://schemas.xmlsoap.org/soap/envelope/}Body')
        response = body.find(
            f'{{{self.namespace[1]}}}{a}Response')
        if response is None:
            # fallback for improper SOAP action responses
            response = body.find(f'{a}Response')
        self.debug(f'callRemote response {response}')
        result = {}
        if response is not None:
            for elem in response:
                result[elem.tag] = self.decode_result(elem)

        return result

    def decode_result(self, element):
        self.debug(f'decode_result [element]: {element}')
        type = element.get('{http://www.w3.org/1999/XMLSchema-instance}type')
        if type is not None:
            try:
                prefix, local = type.split(':')
                if prefix == 'xsd':
                    type = local
            except ValueError:
                pass

        if type == 'integer' or type == 'int':
            return int(element.text)
        if type == 'float' or type == 'double':
            return float(element.text)
        if type == 'boolean':
            return element.text == 'true'

        return element.text or ''
