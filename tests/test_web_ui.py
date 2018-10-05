# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2018 Pol Canelles <canellestudi@gmail.com>

"""
Test cases for `~coherence.web.ui`

.. warning:: All the tests done here are without testing a real web socket
             connection. All the calls made to ws are fake calls, cause we
             depend on a real web browser with web sockets enabled. So, all
             java script responses are not tested here.
"""

from coherence import __version__
from coherence.base import Coherence
from twisted.web import static

from coherence.upnp.core import device
from twisted.internet.defer import inlineCallbacks
from twisted.trial import unittest
from tests.web_utils import DummyRequest

index_result = '''\
<html>
<head profile="http://www.w3.org/2005/10/profile">
    <title>COHEN3 - WEB-UI</title>
    <link rel="stylesheet" type="text/css" href="styles/main.css" />
    <link rel="icon" type="image/png" href="/server-images/coherence-icon.ico" />
    <script src="js/jquery-3.3.1.min.js"></script>
    <script type="text/javascript" src="js/coherence.js"></script>
    <script type="text/javascript">
        $(window).on("load", function(){
            // Handler when all assets (including images) are loaded
            console.log("window load ok");
            openTab('home', $('#but-home'));
        });
    </script>
</head>
<header>
    <div id="navbar_menu_box" class="navbar table">
        <ul class="text-center">
    <li class="nav-logo"></li>
    <li class="active">
        
        <a class="tablink" href="#" id="but-home" onclick="openTab('home', this)">
        
        
        Cohen3</a>
    </li><li class="">
        
        <a class="tablink" href="#" id="but-devices" onclick="openTab('devices', this)">
        
        
        Devices</a>
    </li><li class="">
        
        <a class="tablink" href="#" id="but-logging" onclick="openTab('logging', this)">
        
        
        Logging</a>
    </li><li class="">
        
        <a class="tablink" href="#" id="but-about" onclick="openTab('about', this)">
        
        
        About</a>
    </li>
</ul>
    </div>
</header>
<body>
    <div id="cohen-body">
        <!-- The Tabs Containers-->
        <div id="home" class="tabcontent">
            <div class="row top-2">
                <div class="text-center">
                    <h5>dlna/UPnP framework</h5>
                    <img id="logo-image" src="/server-images/coherence-icon.svg" />
                    <h5>for the Digital Living</h5>
                </div>
            </div>
        </div>
        <div id="devices" class="tabcontent top-0">
            <h3 class="title-head-lines bottom-1">
                <span>Devices</span>
            </h3>
            <div class="list ">
                <ul id="devices-list"></ul>
            </div>
            <div class="devices-box"></div>
        </div>
        <div id="logging" class="tabcontent top-0">
            <h3 class="title-head-lines bottom-1">
                <span>Logging</span>
            </h3>
            <div class="log-box"></div>
        </div>
        <div id="about" class="tabcontent top-0">
            <h3 class="title-head-lines bottom-1">
                <span>About</span>
            </h3>
            <div class="text-justify bottom-2">
                <p>Cohen3 is a DLNA/UPnP Media Server written in Python 3,
                   providing several UPnP MediaServers and MediaRenderers to make
                   simple publishing and streaming different types of media content
                    to your network.</p>
            </div>
            <div class="text-center">
                <img id="logo-image" src="/server-images/coherence-icon.svg" />
            </div>
            <div class="footer">
                <p class="left-1">Cohen3 version: %s
                </p>
            </div>
        </div>
    </div>
</body>
<script type="text/javascript" src="js/redirect.js" class="js" id="jsredirect">
</script>
</html>'''


class DummyDevice(device.Device):
    location = b"DummyDevice Location"
    host = b"http://localhost"

    def __init__(self, parent=None, udn=None, friendly_name='DummyDevice'):
        super(DummyDevice, self).__init__(parent=parent, udn=udn)
        self.friendly_name = friendly_name

    def get_friendly_name(self):
        return self.friendly_name

    def get_usn(self):
        return "{} USN".format(self.friendly_name)

    def get_location(self):
        return "{} Location".format(self.friendly_name).encode('ascii')

    def get_device_type(self):
        return "{} type".format(self.friendly_name)

    def get_markup_name(self):
        return "{}:MediaFakeServer 0".format(self.friendly_name)

    def get_devices(self):
        return []


class WebUICoherenceTest(unittest.TestCase):
    def setUp(self):
        self.coherence = Coherence(
            {'unittest': 'yes',
             'web-ui': 'yes',
             'serverport': '9001',
             'logmode': 'error',
             }
        )

    @inlineCallbacks
    def test_web_ui_render_in_coherence(self):
        response = yield self.coherence.web_server.site.get(b"")
        self.assertEqual(response.value(), index_result % __version__)

    @inlineCallbacks
    def test_web_ui_get_child(self):
        req = DummyRequest(b'styles')
        res = yield self.coherence.web_server.web_root_resource.getChild(
            b'styles', req)
        self.assertIsInstance(res, static.File)

    @inlineCallbacks
    def test_web_ui_ws_callback(self):
        self.coherence.web_server.web_root_resource.ws_recived.clear()
        response = yield self.coherence.web_server.site.get(b"")
        factory = self.coherence.web_server.web_root_resource.factory
        factory.protocol.factory = factory
        factory.protocol.onMessage(factory.protocol, b'WebSocket Ready', None)
        self.assertEqual(
            self.coherence.web_server.web_root_resource.ws_recived,
            [b'WebSocket Ready'])

    @inlineCallbacks
    def test_web_ui_devices(self):
        c_dev = DummyDevice(friendly_name='CoherenceDummyDevice')
        self.coherence.add_device(c_dev)
        response = yield self.coherence.web_server.site.get(b"")
        factory = self.coherence.web_server.web_root_resource.factory
        factory.protocol.message_callback(b'WebSocket Ready', False)

        dev = DummyDevice()
        self.coherence.web_server.web_root_resource.devices.add_device(dev)
        self.assertEqual(
            self.coherence.web_server.web_root_resource.devices.detected,
            [("CoherenceDummyDevice", "CoherenceDummyDevice USN"),
             ("DummyDevice", "DummyDevice USN")]
        )

        self.coherence.web_server.web_root_resource.devices.remove_device(
            dev.get_usn())
        self.assertEqual(
            self.coherence.web_server.web_root_resource.devices.detected,
            [("CoherenceDummyDevice", "CoherenceDummyDevice USN")]
        )

        self.coherence.web_server.web_root_resource.devices.remove_device(
            c_dev.get_usn())

    def tearDown(self):
        self.coherence.shutdown()
