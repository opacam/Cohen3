# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2007 - Frank Scholz <coherence@beebits.net>
# Copyright 2018, Pol Canelles <canellestudi@gmail.com>

'''
SOAP-lite
=========

Some simple functions to implement the SOAP messages needed by UPnP with
ElementTree.

.. note:: Inspired by ElementSOAP.py
'''

from lxml import etree
from twisted.python.util import OrderedDict

from coherence.upnp.core.xml_constants import ELEMENT_TYPE
from coherence import log

NS_SOAP_ENV = 'http://schemas.xmlsoap.org/soap/envelope/'
NS_SOAP_ENC = 'http://schemas.xmlsoap.org/soap/encoding/'
NS_XSD = 'http://www.w3.org/1999/XMLSchema'
NS_UPNP_ORG_CONTROL_1_0 = 'urn:schemas-upnp-org:control-1-0'

TYPE_MAP = {
    str: 'string',
    bytes: 'bytes',
    int: 'int',
    float: 'float',
    bool: 'boolean'}

UPNPERRORS = {
    401: 'Invalid Action',
    402: 'Invalid Args',
    501: 'Action Failed',
    600: 'Argument Value Invalid',
    601: 'Argument Value Out of Range',
    602: 'Optional Action Not Implemented',
    603: 'Out Of Memory',
    604: 'Human Intervention Required',
    605: 'String Argument Too Long',
    606: 'Action Not Authorized',
    607: 'Signature Failure',
    608: 'Signature Missing',
    609: 'Not Encrypted',
    610: 'Invalid Sequence',
    611: 'Invalid Control URL',
    612: 'No Such Session', }

logger = log.get_logger('soap_lite')


def build_soap_error(status,
                     description='without words',
                     pretty_print=True):
    '''Builds an UPnP SOAP error message.
    '''
    root = etree.Element(etree.QName(NS_SOAP_ENV, 'Fault'))
    etree.SubElement(root, 'faultcode').text = 's:Client'
    etree.SubElement(root, 'faultstring').text = 'UPnPError'
    e = etree.SubElement(root, 'detail')
    e = etree.SubElement(e, etree.QName(NS_UPNP_ORG_CONTROL_1_0, 'UPnPError'),
                         nsmap={None: NS_UPNP_ORG_CONTROL_1_0})
    etree.SubElement(e, 'errorCode').text = str(status)
    etree.SubElement(e, 'errorDescription').text = UPNPERRORS.get(status,
                                                                  description)

    return build_soap_call(None, root, pretty_print=pretty_print)


def build_soap_call(method, arguments, ns=None,
                    is_response=False,
                    pretty_print=True):
    '''Create a shell for a SOAP request or response element:

        - set method to none to omit the method element and
          add the arguments directly to the body (for an error msg)
        - arguments can be a dict or an etree.Element
    '''
    envelope = etree.Element(
        etree.QName(NS_SOAP_ENV, 'Envelope'),
        attrib={etree.QName(NS_SOAP_ENV, 'encodingStyle'): NS_SOAP_ENC},
        nsmap={'s': NS_SOAP_ENV})
    body = etree.SubElement(
        envelope, etree.QName(NS_SOAP_ENV, 'Body'))

    if method:
        if is_response is True:
            method += 'Response'

        if ns:
            tag = etree.QName(ns, method)
            nsmap = {'u': ns}
        else:
            tag = method
            nsmap = None

        re = etree.SubElement(body, tag, nsmap=nsmap)
    else:
        re = body

    # append the arguments
    if isinstance(arguments, (dict, OrderedDict)):
        for arg_name, arg_val in arguments.items():
            if type(arg_val) in TYPE_MAP:
                arg_type = TYPE_MAP[type(arg_val)]
                if arg_type == 'int' or arg_type == 'float':
                    arg_val = str(arg_val)
                if arg_type == 'bytes':
                    arg_val = arg_val.decode('utf-8')
                if arg_type == 'boolean':
                    arg_val = '1' if arg_val else '0'
                e = etree.SubElement(re, arg_name)
                e.text = arg_val
            # elif isinstance(arg_val, ELEMENT_TYPE):
            #   e.append(arg_val)
    elif isinstance(arguments, ELEMENT_TYPE):
        re.append(arguments)

    xml = etree.tostring(envelope, encoding='utf-8', xml_declaration=True,
                         pretty_print=pretty_print)
    logger.debug(f'xml dump:\n{xml}')
    return xml
