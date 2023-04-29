# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2023 Pol Canelles <canellestudi@gmail.com>

import json
import os
import pytest
import pytest_twisted as pt
import shutil

from pathlib import Path
from typing import Any, Dict, Tuple, Union
from twisted.internet import reactor
from twisted.internet.defer import Deferred

from coherence.base import Coherence
from coherence.upnp.core.uuid import UUID
from coherence.upnp.devices.control_point import DeviceQuery


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


@pytest.fixture(scope="function")
def content_directory(
        tmp_path: pytest.TempPathFactory
) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    """Create a temporary file structure."""
    file_structure_path = Path(__file__).parent / "content_directory.json"
    with open(file_structure_path, "r") as f:
        file_structure_dict = json.load(f)

    expected_data_folders = {}
    expected_data_files = {}

    # Recursively create directories and files
    def create_file_structure(parent_path: Path, node: dict):
        nonlocal expected_data_folders, expected_data_files
        if node["type"] == "folder":
            new_path = parent_path / node["name"]
            new_path.mkdir()
            # we want our relative path without the temp directory
            rel_path = str(new_path).replace(f"{tmp_path}/", "")
            expected_data_folders[rel_path] = {
                "id": node["id"],
                "title": node["name"],
                "parentID": node.get("parentID"),
                "upnp_class": node["upnp_class"],
                "total_children": len(node["children"]),
            }
            for child in node["children"]:
                create_file_structure(new_path, child)
        elif node["type"] == "file":
            new_path = parent_path / node["name"]
            new_path.touch()
            # we want our relative path without the temp directory
            rel_path = str(new_path).replace(f"{tmp_path}/", "")
            expected_data_files[rel_path] = {
                "id": node["id"],
                "title": node["name"],
                "parentID": node.get("parentID"),
                "upnp_class": node["upnp_class"],
            }
        else:
            raise ValueError("Invalid node type")

    root_path = Path(tmp_path)
    create_file_structure(root_path, file_structure_dict)

    yield str(root_path), expected_data_folders, expected_data_files

    # Remove temporary files and directories
    for child in root_path.glob("**/*"):
        child.unlink() if child.is_file() else shutil.rmtree(child)
    # Restore global variables to initial state
    expected_data_folders = {}
    expected_data_files = {}


@pt.async_yield_fixture(scope="function")
async def media_server(
        content_directory: Tuple[str, Dict[str, Any], Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Pytest fixture that initializes a `Coherence server` with a `FSStore`
    backend. Once initialized the server with the backend, it will create a
    `DeviceQuery` asking for the data of our FSStore backend. We will yield
    a dictionary with a Coherence server, a RootDevice, the path of the
    temporary collection as a string, a dictionary containing the expected
    folders information and a dictionary with the expected files data of our
    temporary media files collection.
    """
    content_path, expected_folders, expected_files = content_directory

    store_uuid = str(UUID())
    coherence_config = {
        "unittest": "yes",
        "logmode": "error",
        "no-subsystem_log": {
            "controlpoint": "error",
            "action": "info",
            "soap": "error",
        },
        "controlpoint": "yes",
        "plugin": {
            "backend": "FSStore",
            "name": f"MediaServer-{os.getpid()}",
            "content": content_path,
            "uuid": store_uuid,
            "enable_inotify": False,
        },
    }
    coherence_server = Coherence(coherence_config)

    # we need to wait coherence to be initialized
    backend_deferred = Deferred()

    def wait_for_backend():
        if (
            coherence_server.ctrl
            and coherence_server.active_backends
            and coherence_server.active_backends[store_uuid].backend
        ):
            backend_deferred.callback(
                coherence_server.active_backends[store_uuid].backend
            )
        else:
            reactor.callLater(0.1, wait_for_backend)

    wait_for_backend()
    await backend_deferred

    # Add a device query and yield the MediaServer instance.
    result_deferred = Deferred()

    def got_result(ms):
        result_deferred.callback(ms)

    coherence_server.ctrl.add_query(
        DeviceQuery("uuid", store_uuid, got_result, timeout=10, oneshot=True)
    )
    root_device = await result_deferred
    assert store_uuid == root_device.udn
    yield {
        "coherence_server": coherence_server,
        "root_device": root_device,
        "content_path": content_path,
        "expected_folders": expected_folders,
        "expected_files": expected_files,
    }

    # clean up
    coherence_server.shutdown()
    coherence_server.clear()
