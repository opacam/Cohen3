#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php
#
# Copyright 2009, Benjamin Kampmann <ben.kampmann@gmail.com>
# Copyright 2014, Hartmut Goebel <h.goebel@crazy-compilers.com>
# Copyright 2018, Pol Canelles <canellestudi@gmail.com>

from twisted.internet import reactor

from coherence.base import Coherence
from coherence.upnp.core import DIDLLite


# browse callback
def process_media_server_browse(result, client):
    print(f"browsing root of: {client.device.get_friendly_name()}")
    print(f"result contains: {result['NumberReturned']}", end=' ')
    print(f"out of {result['TotalMatches']} total matches.")

    elt = DIDLLite.DIDLElement.fromString(result['Result'])
    for item in elt.getItems():

        if item.upnp_class.startswith("object.container"):
            print("  container", item.title, f"({item.id})", end=' ')
            print("with", item.childCount, "items.")

        if item.upnp_class.startswith("object.item"):
            print("  item", item.title, f"({item.id}).")


# called for each media server found
def media_server_found(device):
    print(f"Media Server found: {device.get_friendly_name()}")

    d = device.client.content_directory.browse(
        0,
        browse_flag='BrowseDirectChildren',
        process_result=False,
        backward_compatibility=False)
    d.addCallback(process_media_server_browse, device.client)


# sadly they sometimes get removed as well :(
def media_server_removed(*args):
    print(f'Media Server gone: {args}')


def start():
    # Initialize coherence and make sure that
    # at least we have one server to explore
    coherence = Coherence(
        {'logmode': 'warning',
         'controlpoint': 'yes',
         'plugin': [
             {'backend': 'LolcatsStore',
              'name': 'Cohen3 LolcatsStore',
              'proxy': 'no',
              },
         ]
         }
    )

    coherence.bind(coherence_device_detection_completed=media_server_found)
    coherence.bind(coherence_device_removed=media_server_removed)


if __name__ == "__main__":
    reactor.callWhenRunning(start)
    reactor.run()
