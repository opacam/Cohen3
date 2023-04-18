# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2023 Pol Canelles <canellestudi@gmail.com>


import pytest
import pytest_twisted as pt

from typing import Any, Tuple, Union
from twisted.internet import reactor
from twisted.internet.defer import Deferred

from coherence.base import Coherence


COHERENCE_BASE_CONFIG = {
    "logmode": "info",
    "unittest": "yes",
    "controlpoint": "yes",
    "web-ui": "no",
}


@pt.async_yield_fixture(scope="function")
async def coherence_with_config(
    request: pytest.FixtureRequest
) -> Union[Coherence, Tuple[Coherence, Any]]:
    # find out if we used the fixture with arguments
    if hasattr(request, "param"):
        coherence_config, expected_data = request.param
    else:
        coherence_config = COHERENCE_BASE_CONFIG
        expected_data = None

    # Init coherence
    coherence = Coherence(coherence_config)

    # determine a property to wait before we yield the server
    config_has_plugin = all(
        [
            "plugin" in coherence_config,
            len(coherence_config.get("plugin", [])) > 0,
        ]
    )
    plugin_uuid = coherence_config.get("plugin", [{"uuid": None}])[0]["uuid"]

    # we need to wait coherence to be initialized before yielding
    d = Deferred()

    def wait_for_initialization():
        if (
            config_has_plugin
            and coherence.active_backends
            and coherence.active_backends[plugin_uuid].backend
        ):
            d.callback(coherence.active_backends[plugin_uuid].backend)
        elif (
            not config_has_plugin
            and coherence.web_server is not None
            and coherence.web_server_port is not None
        ):
            d.callback(coherence)
        else:
            reactor.callLater(0.1, wait_for_initialization)

    wait_for_initialization()
    server_or_backend = await d
    print(f"* server_or_backend is ready: {server_or_backend}")

    # yield the server/backend and expected data (if any)
    # Note: for now, we yield the coherence server, but we could yeld the
    #   `server_or_backend` variable, so we could interact directly with the
    #    backend.
    if hasattr(request, "param"):
        yield coherence, expected_data
    else:
        yield coherence

    # clean up
    coherence.shutdown()
    # There are problems with web-ui and `clear` method so
    # we avoid triggering it whenever we had web-ui enabled
    if coherence_config.get("web-ui", "no") != "yes":
        coherence.clear()
