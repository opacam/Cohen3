# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2022 Tom Parker-Shemilt <palfrey@tevps.net>
# Copyright 2023 Pol Canelles <canellestudi@gmail.com>

"""
Test cases for L{upnp.backends.mediadb_storage}
"""
import pytest
import shutil
import time

from pathlib import Path

import coherence.log

coherence.log.init()

try:
    from coherence.backends import mediadb_storage

    has_mediadb = True
except ModuleNotFoundError:
    has_mediadb = False


@pytest.fixture(scope="function")
def storage(tmp_path: pytest.TempPathFactory):
    if has_mediadb is False:
        pytest.skip("Mediadb is not installed")
    songs = Path(__file__).parent / "../content"
    media_store = mediadb_storage.MediaStore(
        None,
        name="my media",
        mediadb=f"{Path(tmp_path, 'media.db')}",
        medialocation=f"{songs}",
    )
    media_store.info(songs)

    yield media_store

    shutil.rmtree(tmp_path)


@pytest.mark.skipif(not has_mediadb, reason="Mediadb is not installed")
def test_contentLen(storage):
    storage.upnp_init()
    for x in range(10):
        if storage.db.query(mediadb_storage.Track).count() == 1:
            break
        storage.info(f"waiting {x}")
        time.sleep(1)
    assert storage.db.query(mediadb_storage.Track).count() == 1
