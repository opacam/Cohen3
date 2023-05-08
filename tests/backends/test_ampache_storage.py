# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2014, Hartmut Goebel <h.goebel@goebel-consult.de>
# Copyright 2023 Pol Canelles <canellestudi@gmail.com>

"""
Test cases for L{backends.ampache_storage}
"""
import pytest

from lxml import etree

from coherence.backends import ampache_storage

SONG = """
<!-- taken from https://github.com/ampache/ampache/wiki/XML-API
but the original was not valid XML, so we can not trust it
-->
<root>
  <song id="3180">
    <title>Hells Bells</title>
    <artist id="129348">AC/DC</artist>
    <album id="2910">Back in Black</album>
    <tag id="2481" count="3">Rock &amp; Roll</tag>
    <tag id="2482" count="1">Rock</tag>
    <tag id="2483" count="1">Roll</tag>
    <track>4</track>
    <time>234</time>
    <url>http://localhost/play/index.php?oid=123908...</url>
    <size>654321</size>
    <art>http://localhost/image.php?id=129348</art>
    <preciserating>3</preciserating>
    <rating>2.9</rating>
  </song>
</root>
"""

SONG_370 = """
<!-- real-world example from Ampache 3.7.0 -->
<root>
<song id="3440">
  <title><![CDATA[Achilles Last Stand]]></title>
  <artist id="141"><![CDATA[Led Zeppelin]]></artist>
  <album id="359"><![CDATA[Presence]]></album>
  <tag id="" count="0"><![CDATA[]]></tag>
  <filename><![CDATA[/mnt/Musique/Led Zeppelin/Presence/01 - Achilles Last Stand.mp3]]></filename>
  <track>1</track>
  <time>625</time>
  <year>1976</year>
  <bitrate>248916</bitrate>
  <mode>vbr</mode>
  <mime>audio/mpeg</mime>
  <url><![CDATA[http://songserver/ampache/play/index.php?ssid=1e11a4&type=song&oid=3440&uid=4&name=Led%20Zeppelin%20-%20Achilles%20Last%20Stand.mp3]]></url>
  <size>19485595</size>
  <mbid></mbid>
  <album_mbid></album_mbid>
  <artist_mbid></artist_mbid>
  <art><![CDATA[http://songserver/ampache/image.php?id=359&object_type=album&auth=1e11a40&name=art.]]></art>
  <preciserating>0</preciserating>
  <rating>0</rating>
  <averagerating></averagerating>
</song>
</root>
"""  # noqa: E501


def expected_duration(total_seconds: str) -> str:
    """Convert the time element into a more human-readable format."""

    hours, remainder = divmod(int(total_seconds), 3600)
    minutes, seconds = divmod(remainder, 60)

    return f"{hours:02}:{minutes:02}:{seconds:02}"


class DummyStore:
    def __init__(self):
        pass

    @property
    def proxy(self):
        return False


@pytest.fixture
def dummy_store():
    return DummyStore()


@pytest.fixture(params=[SONG, SONG_370])
def song_xml(request):
    return etree.fromstring(request.param).find("song")


def test_track(dummy_store, song_xml):
    """Test tracks with XML from Ampache"""
    track = ampache_storage.Track(dummy_store, song_xml)
    assert track.get_id() == "song." + song_xml.get("id")
    assert track.parent_id == "album." + song_xml.find("album").get("id")
    assert track.duration == expected_duration(song_xml.find("time").text)
    assert track.get_url() == song_xml.find("url").text
    assert track.get_name() == song_xml.find("title").text
    assert track.title == song_xml.find("title").text
    assert track.artist == song_xml.find("artist").text
    assert track.album == song_xml.find("album").text
    assert track.genre is None
    assert track.track_nr == song_xml.find("track").text
    assert track.cover == song_xml.find("art").text
    assert track.mimetype == (
        song_xml.find("mime").text if song_xml.find("mime") else "audio/mpeg"
    )
    assert track.size == int(song_xml.find("size").text)
    assert track.get_path() is None
    assert track.get_children() == []
    assert track.get_child_count() == 0
