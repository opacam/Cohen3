# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2007 - Frank Scholz <coherence@beebits.net>

DLNA_BUS_NAME = 'org.DLNA'  # bus name for DLNA API

BUS_NAME = 'org.Coherence'  # the one with the dots
OBJECT_PATH = '/org/Coherence'  # the one with the slashes ;-)

DEVICE_IFACE = f'{BUS_NAME}.device'
SERVICE_IFACE = f'{BUS_NAME}.service'

CDS_SERVICE = f'{DLNA_BUS_NAME}.DMS.CDS'
