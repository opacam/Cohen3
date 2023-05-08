# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2008, Frank Scholz <coherence@beebits.net>
# Copyright 2023 Pol Canelles <canellestudi@gmail.com>

"""
Test cases for the L{Coherence base class}
"""
import pytest
import threading

from twisted.internet import reactor
from twisted.internet.defer import Deferred
from typing import Iterator
from unittest import mock

from coherence.base import Coherence


COHERENCE_INFO_CONFIG = {
    "logmode": "info",
    "unittest": "yes",
    "controlpoint": "yes",
}
COHERENCE_ERROR_CONFIG = dict(COHERENCE_INFO_CONFIG)
COHERENCE_ERROR_CONFIG["logmode"] = "error"

COHERENCE_WARN_CONFIG = dict(COHERENCE_INFO_CONFIG)
COHERENCE_WARN_CONFIG["logmode"] = "warning"

COHERENCE_DEBUG_CONFIG = dict(COHERENCE_INFO_CONFIG)
COHERENCE_DEBUG_CONFIG["logmode"] = "debug"


def get_coherence_server(config: dict = COHERENCE_INFO_CONFIG) -> Coherence:
    """
    Start a new Coherence server given a configuration file. This new server
    will be returned once the `web_server` property of the server is
    initialized.
    """
    server = Coherence(config)
    # wait for server to be started
    started = threading.Event()

    def wait_started():
        if (
            server.web_server is not None
            and server.web_server_port is not None
        ):
            started.set()
        else:
            reactor.callLater(0.1, wait_started)

    wait_started()
    started.wait()

    return server


@pytest.fixture
def fake_file() -> str:
    """A pytest fixture that returns a fake file."""
    return "/fake_dir/fake_file.log"


@pytest.fixture
def fake_ip() -> str:
    """A pytest fixture that returns a fake ip address."""
    return "192.168.1.24"


@pytest.fixture
def get_ip_mock(fake_ip: str) -> Iterator[mock.MagicMock]:
    """A fixture that mocks the 'coherence.base.get_ip_address' function."""
    with mock.patch("coherence.base.get_ip_address") as mock_get_ip:
        mock_get_ip.return_value = fake_ip
        yield mock_get_ip


def test_singleton(coherence_with_config):
    """Test coherence's singleton."""
    d = Deferred()
    c1 = get_coherence_server(config=COHERENCE_INFO_CONFIG)
    c2 = get_coherence_server(config=COHERENCE_WARN_CONFIG)
    c3 = get_coherence_server(config=COHERENCE_DEBUG_CONFIG)

    def shutdown(r, instance):
        return instance.shutdown()

    d.addCallback(shutdown, c1)
    d.addCallback(shutdown, c2)
    d.addCallback(shutdown, c3)

    reactor.callLater(3, d.callback, None)

    return d


@pytest.mark.parametrize(
    "coherence_with_config",
    [
        (COHERENCE_INFO_CONFIG, "INFO"),
        (COHERENCE_ERROR_CONFIG, "ERROR"),
        (COHERENCE_WARN_CONFIG, "WARNING"),
        (COHERENCE_DEBUG_CONFIG, "DEBUG"),
    ],
    indirect=True,
)
def test_log_level(coherence_with_config):
    """Test coherence's loglevel."""
    coherence_server, expected_data = coherence_with_config
    assert coherence_server.log_level == expected_data


def test_log_file(coherence_with_config, fake_file):
    """Test coherence's logfile."""
    assert coherence_with_config.log_file is None
    coherence_with_config.config["logging"] = {"logfile": fake_file}
    assert coherence_with_config.log_file == fake_file


def test_setup_hostname(coherence_with_config, get_ip_mock, fake_ip):
    """Test coherence's ip address."""
    coherence_with_config.config["interface"] = fake_ip
    # we expect to have an real ip address assigned by the router
    assert coherence_with_config.hostname != "127.0.0.1"
    # set a fake ip address and test the result
    coherence_with_config.setup_hostname()
    assert coherence_with_config.hostname == fake_ip
    get_ip_mock.assert_called_once_with(fake_ip)
