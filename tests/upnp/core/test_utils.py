# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2008, Frank Scholz <coherence@beebits.net>
# Copyright 2023 Pol Canelles <canellestudi@gmail.com>

"""
Test cases for L{upnp.core.utils}
"""

import pytest
import shutil

from typing import Callable
from twisted.internet import reactor
from twisted.protocols import policies

# from twisted.python.filepath import FilePath
from twisted.web import static, server
from coherence.upnp.core import utils

# This data is joined using CRLF pairs.
testChunkedData = [
    '200',
    '<?xml version="1.0" ?> ',
    '<root xmlns="urn:schemas-upnp-org:device-1-0">',
    '	<specVersion>',
    '		<major>1</major> ',
    '		<minor>0</minor> ',
    '	</specVersion>',
    '	<device>',
    '		<deviceType>urn:schemas-upnp-org:device:MediaRenderer:1</deviceType> ',  # noqa: E501
    '		<friendlyName>DMA201</friendlyName> ',
    '		<manufacturer>   </manufacturer> ',
    '		<manufacturerURL>   </manufacturerURL> ',
    '		<modelDescription>DMA201</modelDescription> ',
    '		<modelName>DMA</modelName> ',
    '		<modelNumber>201</modelNumber> ',
    '		<modelURL>   </modelURL> ',
    '		<serialNumber>0',
    '200',
    '00000000001</serialNumber> ',
    '		<UDN>uuid:BE1C49F2-572D-3617-8F4C-BB1DEC3954FD</UDN> ',
    '		<UPC /> ',
    '		<serviceList>',
    '			<service>',
    '				<serviceType>urn:schemas-upnp-org:service:ConnectionManager:1</serviceType>',  # noqa: E501
    '				<serviceId>urn:upnp-org:serviceId:ConnectionManager</serviceId>',  # noqa: E501
    '				<controlURL>http://10.63.1.113:4444/CMSControl</controlURL>',  # noqa: E501
    '				<eventSubURL>http://10.63.1.113:4445/CMSEvent</eventSubURL>',  # noqa: E501
    '				<SCPDURL>/upnpdev.cgi?file=/ConnectionManager.xml</SCPDURL>',  # noqa: E501
    '			</service>',
    '			<service>',
    '				<serv',
    '223',
    'iceType>urn:schemas-upnp-org:service:AVTransport:1</serviceType>',
    '				<serviceId>urn:upnp-org:serviceId:AVTransport</serviceId>',
    '				<controlURL>http://10.63.1.113:4444/AVTControl</controlURL>',  # noqa: E501
    '				<eventSubURL>http://10.63.1.113:4445/AVTEvent</eventSubURL>',  # noqa: E501
    '				<SCPDURL>/upnpdev.cgi?file=/AVTransport.xml</SCPDURL>',
    '			</service>',
    '			<service>',
    '				<serviceType>urn:schemas-upnp-org:service:RenderingControl:1</serviceType>',  # noqa: E501
    '				<serviceId>urn:upnp-org:serviceId:RenderingControl</serviceId>',  # noqa: E501
    '				<controlURL>http://10.63.1.113:4444/RCSControl</',
    'c4',
    'controlURL>',
    '				<eventSubURL>http://10.63.1.113:4445/RCSEvent</eventSubURL>',  # noqa: E501
    '				<SCPDURL>/upnpdev.cgi?file=/RenderingControl.xml</SCPDURL>',  # noqa: E501
    '			</service>',
    '		</serviceList>',
    '	</device>',
    '</root>' '',
    '0',
    '',
]

testChunkedDataResult = [
    '<?xml version="1.0" ?> ',
    '<root xmlns="urn:schemas-upnp-org:device-1-0">',
    '	<specVersion>',
    '		<major>1</major> ',
    '		<minor>0</minor> ',
    '	</specVersion>',
    '	<device>',
    '		<deviceType>urn:schemas-upnp-org:device:MediaRenderer:1</deviceType> ',  # noqa: E501
    '		<friendlyName>DMA201</friendlyName> ',
    '		<manufacturer>   </manufacturer> ',
    '		<manufacturerURL>   </manufacturerURL> ',
    '		<modelDescription>DMA201</modelDescription> ',
    '		<modelName>DMA</modelName> ',
    '		<modelNumber>201</modelNumber> ',
    '		<modelURL>   </modelURL> ',
    '		<serialNumber>000000000001</serialNumber> ',
    '		<UDN>uuid:BE1C49F2-572D-3617-8F4C-BB1DEC3954FD</UDN> ',
    '		<UPC /> ',
    '		<serviceList>',
    '			<service>',
    '				<serviceType>urn:schemas-upnp-org:service:ConnectionManager:1</serviceType>',  # noqa: E501
    '				<serviceId>urn:upnp-org:serviceId:ConnectionManager</serviceId>',  # noqa: E501
    '				<controlURL>http://10.63.1.113:4444/CMSControl</controlURL>',  # noqa: E501
    '				<eventSubURL>http://10.63.1.113:4445/CMSEvent</eventSubURL>',  # noqa: E501
    '				<SCPDURL>/upnpdev.cgi?file=/ConnectionManager.xml</SCPDURL>',  # noqa: E501
    '			</service>',
    '			<service>',
    '				<serviceType>urn:schemas-upnp-org:service:AVTransport:1</serviceType>',  # noqa: E501
    '				<serviceId>urn:upnp-org:serviceId:AVTransport</serviceId>',
    '				<controlURL>http://10.63.1.113:4444/AVTControl</controlURL>',  # noqa: E501
    '				<eventSubURL>http://10.63.1.113:4445/AVTEvent</eventSubURL>',  # noqa: E501
    '				<SCPDURL>/upnpdev.cgi?file=/AVTransport.xml</SCPDURL>',
    '			</service>',
    '			<service>',
    '				<serviceType>urn:schemas-upnp-org:service:RenderingControl:1</serviceType>',  # noqa: E501
    '				<serviceId>urn:upnp-org:serviceId:RenderingControl</serviceId>',  # noqa: E501
    '				<controlURL>http://10.63.1.113:4444/RCSControl</controlURL>',  # noqa: E501
    '				<eventSubURL>http://10.63.1.113:4445/RCSEvent</eventSubURL>',  # noqa: E501
    '				<SCPDURL>/upnpdev.cgi?file=/RenderingControl.xml</SCPDURL>',  # noqa: E501
    '			</service>',
    '		</serviceList>',
    '	</device>',
    '</root>',
    '',
]


@pytest.fixture
def site(tmp_path: str) -> server.Site:
    """
    Pytest fixture that creates a test directory, a file within the test
    directory, and returns a twisted.web.server.Site object for the directory.
    """
    name = tmp_path / "site"
    name.mkdir()
    (name / "file").write_bytes(b"0123456789")
    r = static.File(name)
    yield server.Site(r, timeout=None)
    shutil.rmtree(name)


@pytest.fixture
def port(site: server.Site) -> int:
    """
    Pytest fixture that returns a TCP port that is being listened by a reactor
    wrapping the server.Site object.
    """
    wrapper = policies.WrappingFactory(site)
    port = reactor.listenTCP(0, wrapper, interface="127.0.0.1")
    yield port.getHost().port
    port.stopListening()


@pytest.fixture
def get_url(port: int) -> Callable[[str], str]:
    """
    Pytest fixture that returns a function that accepts a string path, and
    returns a full url that can be used to access the specified path.
    """

    def _get_url(path):
        return f"http://127.0.0.1:{port}/{path}"

    return _get_url


def test_chunked_data() -> None:
    """Tests proper reassembling of a chunked http-response
    based on a test and data provided by Lawrence
    """
    test_data = "\r\n".join(testChunkedData)
    new_data = utils.de_chunk_payload(test_data)
    assert new_data == "\r\n".join(testChunkedDataResult)


def test_get_page(site: server.Site, get_url: Callable[[str], str]) -> None:
    """
    Tests proper retrieval of the page specified by the get_url function, and
    the verification of the response content and headers.
    """
    content = b"0123456789"
    headers = {
        b"accept-ranges": [b"bytes"],
        b"content-length": [b"10"],
        b"content-type": [b"text/html"],
    }

    # Define a generator function that calls the coroutine
    def _get_page() -> None:
        response = yield utils.getPage(get_url("file"))
        assert isinstance(response, tuple)
        assert response[0] == content
        original_headers = response[1]
        for header in headers:
            assert header in original_headers
            assert original_headers[header] == headers[header]

    # Call the generator function to start the test
    _get_page()
