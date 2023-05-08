# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2008, Frank Scholz <coherence@beebits.net>
# Copyright 2014 Hartmut Goebel <h.goebel@crazy-compilers.com>
# Copyright 2023 Pol Canelles <canellestudi@gmail.com>

"""
Test cases for L{upnp.services.servers.content_directory_server}
"""

import pytest
import pytest_twisted as pt

from coherence.upnp.core import DIDLLite


@pt.ensureDeferred
async def test_browse_root(media_server):
    """Test browse root and first child."""
    expected_folders = media_server["expected_folders"]
    cdc = media_server["root_device"].client.content_directory
    r0 = await cdc.browse(process_result=False)

    assert int(r0["TotalMatches"]) == 1  # we expect one folder (content)
    didl = DIDLLite.DIDLElement.fromString(r0["Result"])
    item = didl.getItems()[0]
    assert int(item.parentID) == 1000
    assert int(item.id) == 1001
    assert item.title == "content"

    # browse content folder
    r1 = await cdc.browse(object_id=item.id, process_result=False)
    # Collect expected folders from content directory
    content_id = expected_folders["content"]["id"]
    expected_matches = [
        i
        for i in expected_folders.values()
        if i["parentID"] == content_id  # noqa: E501
    ]
    assert int(r1["TotalMatches"]) == len(expected_matches)


@pytest.mark.parametrize(
    "test_folder",
    ("content", "content/audio", "content/images", "content/video"),
)
@pt.ensureDeferred
async def test_browse_by_id_recursively(media_server, test_folder):
    """
    Test browse collection recursively using the id attribute.
    """
    expected_folders = media_server["expected_folders"]
    expected_files = media_server["expected_files"]
    cdc = media_server["root_device"].client.content_directory

    def check_container(item, item_path):
        item_data = expected_folders[item_path]
        assert int(item.parentID) == item_data["parentID"]
        assert int(item.id) == item_data["id"]
        assert int(item.childCount) == item_data["total_children"]

    def check_item(item, item_path):
        item_data = expected_files[item_path]
        assert int(item.parentID) == item_data["parentID"]
        assert item.id == item_data["id"]
        assert item.title == item_data["title"]

    async def browse_item_by_id(item_id, item_path):
        r = await cdc.browse(object_id=item_id, process_result=False)
        didl = DIDLLite.DIDLElement.fromString(r["Result"])
        for item in didl.getItems():
            child_path = f"{item_path}/{item.title}"
            if item.upnp_class == "object.container":
                check_container(item, child_path)
                await browse_item_by_id(item.id, child_path)
            else:
                check_item(item, child_path)

    initial_data = expected_folders[test_folder]
    await browse_item_by_id(initial_data["id"], test_folder)


@pt.ensureDeferred
async def test_browse_non_existing_object(media_server):
    cdc = media_server["root_device"].client.content_directory
    r = await cdc.browse(object_id="9999.nothing", process_result=False)
    assert r is None


@pt.ensureDeferred
async def test_browse_metadata(media_server):
    cdc = media_server["root_device"].client.content_directory
    r = await cdc.browse(
        object_id="0", browse_flag="BrowseMetadata", process_result=False
    )
    assert int(r["TotalMatches"]) == 1
    didl = DIDLLite.DIDLElement.fromString(r["Result"])
    item = didl.getItems()[0]
    assert item.title == "root"


@pt.ensureDeferred
async def test_xbox_browse(media_server):
    """
    Tries to find the activated FSStore backend and browses all audio files.
    """
    media_server["root_device"].client.overlay_headers = {
        "user-agent": "Xbox/Coherence emulation"
    }
    cdc = media_server["root_device"].client.content_directory
    r = await cdc.browse(object_id="4", process_result=False)
    # we expect all media files here
    assert int(r["TotalMatches"]) == len(media_server["expected_files"])


@pt.ensureDeferred
async def test_xbox_browse_metadata(media_server):
    """
    Tries to find the activated FSStore backend and requests metadata for
    ObjectID 0.
    """
    media_server["root_device"].client.overlay_headers = {
        "user-agent": "Xbox/Coherence emulation"
    }
    cdc = media_server["root_device"].client.content_directory
    r = await cdc.browse(
        object_id="0", browse_flag="BrowseMetadata", process_result=False
    )
    assert int(r["TotalMatches"]) == 1
    didl = DIDLLite.DIDLElement.fromString(r["Result"])
    item = didl.getItems()[0]
    assert item.title == "root"


@pt.ensureDeferred
async def test_xbox_search(media_server):
    """
    Tries to find the activated FSStore backend and searches for all its audio
    files.
    """
    media_server["root_device"].client.overlay_headers = {
        "user-agent": "Xbox/Coherence emulation"
    }
    cdc = media_server["root_device"].client.content_directory
    r = await cdc.search(container_id="4", criteria="")
    # we expect all media files here
    assert len(r) == len(media_server["expected_files"])
