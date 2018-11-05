# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2008, Frank Scholz <coherence@beebits.net>

"""
Test cases for L{dbus_service}
"""

import os
import sys

from twisted.internet.defer import Deferred
from twisted.trial import unittest

from coherence import __version__
from coherence.base import Coherence
from coherence.upnp.core import uuid
from tests import wrapped

from types import FunctionType

try:
    import dbus
    from dbus.mainloop.glib import DBusGMainLoop

    DBusGMainLoop(set_as_default=True)
    import dbus.service
except ImportError:
    dbus = None

try:
    from twisted.internet import gireactor
except ImportError:
    gireactor = None

BUS_NAME = 'org.Coherence'
OBJECT_PATH = '/org/Coherence'


class FunctionRequired(Exception):
    """
    L{Exposer.expose} we need a function to use this decorator.
    """


def get_the_gireactor(f):
    def wrapper(*args):
        print(args)
        if isinstance(f, FunctionType):
            try:
                if "twisted.internet.reactor" in sys.modules and \
                        not isinstance(sys.modules["twisted.internet.reactor"],
                                       gireactor.GIReactor):
                    print(
                        "Something has already installed a Twisted reactor. "
                        "Attempting to uninstall it...",
                        UserWarning,
                    )
                    del sys.modules["twisted.internet.reactor"]
                if "twisted.internet.reactor" not in sys.modules:
                    global reactor
                    gireactor.install(useGtk=False)
                    from twisted.internet import reactor
            except ImportError:
                skip = ("This test needs a GIReactor, please start trial "
                        "with the '-r glib2' option.")
        else:
            raise FunctionRequired()
        return f(*args)
    return wrapper


class TestDBUS(unittest.TestCase):
    if not dbus:
        skip = "Python dbus-bindings not available."
    elif gireactor is None:
        skip = "Python dbus-bindings not available, we need" \
               "a twisted.internet.gireactor.GIReactor"

    def setUp(self):
        self.coherence = Coherence(
            {'unittest': 'yes', 'logmode': 'error', 'use_dbus': 'yes',
             'controlpoint': 'yes'})
        self.bus = dbus.SessionBus()
        self.coherence_service = self.bus.get_object(BUS_NAME, OBJECT_PATH)
        self.uuid = str(uuid.UUID())

    def tearDown(self):

        def cleaner(r):
            self.coherence.clear()
            if "twisted.internet.reactor" in sys.modules:
                del sys.modules["twisted.internet.reactor"]
            return r

        dl = self.coherence.shutdown()
        dl.addBoth(cleaner)
        return dl

    @get_the_gireactor
    def test_dbus_version(self):
        """ tests the version number request via dbus
        """

        d = Deferred()

        @wrapped(d)
        def handle_version_reply(version):
            self.assertEqual(version, __version__)
            d.callback(version)

        self.coherence_service.version(dbus_interface=BUS_NAME,
                                       reply_handler=handle_version_reply,
                                       error_handler=d.errback)
        return d

    @get_the_gireactor
    def test_dbus_plugin_add_and_remove(self):
        """ tests creation and removal of a backend via dbus
        """

        d = Deferred()

        @wrapped(d)
        def add_it(uuid):
            self.coherence_service.add_plugin(
                'YouTubeStore',
                {'name': 'dbus-test-youtube-%d' % os.getpid(), 'uuid': uuid},
                dbus_interface=BUS_NAME,
                reply_handler=handle_add_plugin_reply,
                error_handler=d.errback)

        @wrapped(d)
        def handle_add_plugin_reply(uuid):
            self.assertEqual(self.uuid, uuid)
            reactor.callLater(2, remove_it, uuid)

        @wrapped(d)
        def remove_it(uuid):
            self.coherence_service.remove_plugin(
                uuid,
                dbus_interface=BUS_NAME,
                reply_handler=handle_remove_plugin_reply,
                error_handler=d.errback)

        @wrapped(d)
        def handle_remove_plugin_reply(uuid):
            self.assertEqual(self.uuid, uuid)
            d.callback(uuid)

        add_it(self.uuid)
        return d
