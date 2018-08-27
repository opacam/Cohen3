from coherence.upnp.core import soap_lite

__author__ = 'ilya'

import unittest

SOAP_CALL_WITH_ARGS = (
    b'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
    b'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"'
    b' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
    b'<s:Body>'
    b'<u:TestMethodResponse xmlns:u="TestNameSpace">'
    b'<s1>val1</s1>'
    b'<b1>1</b1>'
    b'<f1>1.32</f1>'
    b'<i1>42</i1>'
    b'</u:TestMethodResponse>'
    b'</s:Body>'
    b'</s:Envelope>'
)

SOAP_ERROR = (
    b'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
    b'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"'
    b' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
    b'<s:Body>'
    b'<s:Fault>'
    b'<faultcode>s:Client</faultcode>'
    b'<faultstring>UPnPError</faultstring>'
    b'<detail>'
    b'<UPnPError xmlns="urn:schemas-upnp-org:control-1-0">'
    b'<errorCode>401</errorCode>'
    b'<errorDescription>Invalid Action</errorDescription>'
    b'</UPnPError>'
    b'</detail>'
    b'</s:Fault>'
    b'</s:Body>'
    b'</s:Envelope>'
)


class SoapLiteTestCase(unittest.TestCase):
    def __init__(self, methodName='runTest'):
        super(SoapLiteTestCase, self).__init__(methodName)
        self.maxDiff = None

    def test_build_soap_call_with_args(self):
        r1 = soap_lite.build_soap_call('TestMethod',
                                       arguments={'s1': 'val1',
                                                  'b1': True,
                                                  'f1': 1.32,
                                                  'i1': 42},
                                       ns='TestNameSpace',
                                       is_response=True,
                                       pretty_print=False)
        self.assertSequenceEqual(SOAP_CALL_WITH_ARGS, r1)
        return

    def test_build_soap_error(self):
        r1 = soap_lite.build_soap_error(401, pretty_print=False)
        self.assertSequenceEqual(SOAP_ERROR, r1)
        return
