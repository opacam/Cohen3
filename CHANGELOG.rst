0.9.1 - Fixes SSDP datagram sending
-----------------------------------

Fixes:
    - Fix SSDP datagram sending
    - Fix `request.setHeader` values
    - Fix urllib3 security vulnerability detected in version 1.23.2

0.9.0 - Introduces new events system
------------------------------------

General:
    - Introduce new events system (EventDispatcher) which replaces
      louie/dispatcher
    - Apply Python3's f-Strings
    - Normalise simple and double quotes (defaults to single quotes)
    - Add/enhance documentation
    - Remove unneeded modules louie and dispatcher as well as the related tests

Fixes:
    - Fix most of the warnings when building docs
    - Fix error on "SUBSCRIBE" for some event calls
    - Fix wrong encoding/decoding strings introduced in the initial python 3 migration
    - Fix extra quotes for SSDPServer's methods: doNotify and doByeBye

0.8.3 - Introduces Backend's models
-----------------------------------

General:
    - Refactor some backends using the new module backends.models
    - Introduces new module: backends.models
    - Add backends status to README
    - Better and cleaner documentation
    - Python 3's f-Strings for backends modules
    - Upgraded dependency for requests package (fix vulnerability)
    - Split into several files the sphinx's documentation
    - Migrate reports from coverage to codecov

Fixes:
    - Fix backend IRadioStore (ShoutCast Radio)
    - Fix backend TEDStore
    - Fix backend LolcatsStore
    - Fix backend AppleTrailersStore
    - Fix the parsing of the soap messages with encoding declared

0.8.2 - Fixes and enhancements
------------------------------

General:
    - Reintroduces WebUI
    - Improve documentation
    - Whole new design for web server html visualization

Fixes:
    - Fix Inotify events
    - Fix test_dbus reactors conflict
    - Fix some travis dependencies
    - Fix wrong log level for init function of the log module

0.8.1 - Fixes and enhancements
------------------------------

General:
    - Automate documentation building via travis
    - Add more sphinx documentation
    - Remove livestreamer as basic dependency
    - Migrate from pygtk to gi.repository
    - Migrate Gstreamer from version 0.10 to 1.0
    - Enhance Travis with more tests
    - Reformat according pep8 directives.

Fixes:
    - Fix quoted keys for some headers
    - Fix Inotify (now uses twisted's Inotify)
    - Fix all pep8/pylint errors

0.8.0 - Cohen3 project started
------------------------------

General:
    - Rename project from Cohen to Cohen3
    - Migrate source code to python version 3
    - Twisted >= 18.7.0 is now required
    - Louie-latest is now required (instead of Louie)

0.7.3 - Fixes and improvements
------------------------------

General:
    - Travis enhancements: make travis upload to pypi

Fixes:
    - Hotfix for LazyContainer

0.7.2 - Minor bugfixes
----------------------

Fixes:
    - Fix issue when Cohen fails to be discovered by xbox 360 dlna client
    - Fix issue when using Lazy Container on Samsung AllShare on 2012 Samsung TV fails

0.7.0 - Cohen project started
-----------------------------

General:
    - lots of refactoring
    - removed lots of Coherence stuff
    - moved to lxml instead of (c)ElementTree
    - Twisted >= 14.0 is now required
    - livestreamer is now required
    - cleanups and fixes

Backends:
    - twitch.tv backend added


0.0.1 - 0.7.0 - Coherence project
---------------------------------

Changelog skipped