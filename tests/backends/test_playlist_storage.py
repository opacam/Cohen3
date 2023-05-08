# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2018 Pol Canelles <canellestudi@gmail.com>

"""
Test cases for L{upnp.backends.playlist_storage}
"""
import re
import pytest
import pytest_twisted as pt

from coherence.backend import Container
from coherence.backends.playlist_storage import PlaylistStore, PlaylistItem
from coherence.upnp.core import uuid

URL_M3U = (
    "https://gist.githubusercontent.com/random-robbie/"
    "e56919b5603ecc87af885391e7331657/raw/"
    "65661a4e6fa8c706cc8fe1cf7c553927e5cf62a7/BBC.m3u"
)
STORE_UUID = str(uuid.UUID())


@pytest.mark.parametrize(
    "coherence_with_config",
    [
        (
            {
                "logmode": "info",
                "unittest": "yes",
                "plugin": [
                    {
                        "backend": "PlaylistStore",
                        "name": "PlayListServer-test",
                        "playlist_url": URL_M3U,
                        "uuid": STORE_UUID,
                    },
                ],
            },
            None,
        ),
    ],
    indirect=True,
)
@pt.ensureDeferred
async def test_playlist_storage(coherence_with_config):
    """Test the PlaylistStore backend."""
    coherence_server, _ = coherence_with_config
    playlist = coherence_server.active_backends[STORE_UUID].backend

    assert isinstance(playlist, PlaylistStore)

    def got_result(r):
        """Callback function for when the playlist backend is initialized."""
        assert len(r) == 30
        assert len(playlist.store) == 61
        assert playlist.len() == 61

        assert isinstance(playlist.store[0], Container)
        assert isinstance(playlist.store[1000], PlaylistItem)

        playlist_item = playlist.store[1000]
        assert playlist_item.stream_url[0:4] == "http"
        url_pattern = url_pattern = (
            r"http:\/\/\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:8080"
            r"\/[a-zA-Z0-9-]+\/1000"
        )
        assert re.match(url_pattern, playlist_item.get_url()) is not None
        assert playlist_item.get_id() == 1000

        media_item = playlist_item.get_item()
        assert media_item.parentID == 0
        assert media_item.id == 1000
        assert isinstance(media_item.title, str)
        assert len(media_item.title) > 0

    def got_error(r):
        """Error callback function."""
        r.printTraceback()
        raise r

    d = playlist.upnp_init()
    d.addCallback(got_result)
    d.addErrback(got_error)
    await d
