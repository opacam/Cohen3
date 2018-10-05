# Classes credits to Brian Muller for his gist contribution:
# https://gist.github.com/bmuller/1873035#file-twisted_web_test_utils-py
'''
Helpers to test `twisted.web` resources.

Examples
--------
Simple site test example::
    from coherence.web.ui import WebUI
    from tests.web_utils import DummySite
    from tests.test_web_ui import index_result

    class WebUIRenderTest(unittest.TestCase):
    def setUp(self):
        self.web = DummySite(WebUI(None))

    @inlineCallbacks
    def test_web_ui_index(self):

        response = yield self.web.get(b"")
        self.assertEqual(response.value(), index_result % __version__)
'''
from twisted.web import server
from twisted.internet.defer import succeed
from twisted.web.test.test_web import DummyRequest


class SmartDummyRequest(DummyRequest):
    '''Dummy request to help test site'''
    headers = {}

    def __init__(self, method, url, args=None, headers=None):
        DummyRequest.__init__(self, url.split(b'/'))
        self.method = method
        self.headers.update(headers or {})

        # set args
        args = args or {}
        for k, v in args.items():
            self.addArg(k, v)

    def value(self):
        return b"".join(self.written).decode('utf-8')


class DummySite(server.Site):
    '''Dummy site to help test Resource'''
    def get(self, url, args=None, headers=None):
        return self._request("GET", url, args, headers)

    def post(self, url, args=None, headers=None):
        return self._request("POST", url, args, headers)

    def _request(self, method, url, args, headers):
        request = SmartDummyRequest(method, url, args, headers)
        resource = self.getResourceFor(request)
        result = resource.render(request)
        return self._resolveResult(request, result)

    def _resolveResult(self, request, result):
        if isinstance(result, str):
            request.write(result)
            request.finish()
            return succeed(request)
        elif result is server.NOT_DONE_YET:
            if request.finished:
                return succeed(request)
            else:
                return request.notifyFinish().addCallback(lambda _: request)
        else:
            raise ValueError("Unexpected return value: %r" % (result,))
