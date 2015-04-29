from coherence.upnp.core import soap_lite

__author__ = 'ilya'

import unittest

SOAP_CALL_WITH_ARGS = (
  '<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
  '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"'
  ' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
  '<s:Body>'
  '<u:TestMethodResponse xmlns:u="TestNameSpace">'
  '<i1>42</i1>'
  '<f1>1.32</f1>'
  '<s1>val1</s1>'
  '<b1>1</b1>'
  '</u:TestMethodResponse>'
  '</s:Body>'
  '</s:Envelope>'
)

SOAP_ERROR = (
  '<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
  '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"'
  ' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
  '<s:Body>'
  '<s:Fault>'
  '<faultcode>s:Client</faultcode>'
  '<faultstring>UPnPError</faultstring>'
  '<detail>'
  '<UPnPError xmlns="urn:schemas-upnp-org:control-1-0">'
  '<errorCode>401</errorCode>'
  '<errorDescription>Invalid Action</errorDescription>'
  '</UPnPError>'
  '</detail>'
  '</s:Fault>'
  '</s:Body>'
  '</s:Envelope>'
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