.. _cli:

Command-Line Interface
======================

SYNOPSIS
--------

``cohen3`` <options> [--plugin=<BACKEND> [ , <PARAM_NAME> : <PARAM_VALUE> ] ...]

DESCRIPTION
-----------

Cohen3 is a Python DLNA/UPnP Media Server made to broadcast digital media content over your network.

The core of Cohen provides a (hopefully complete) implementation
of:

  * a SSDP server,
  * a MSEARCH client,
  * server and client for HTTP/SOAP requests, and
  * server and client for Event Subscription and Notification (GENA).

OPTIONS
-------

-v, --version  Show program's version number and exit

--help         Show help message and exit

-d, --daemon  Daemonize

-c, --configfile=PATH  Path to config file

--noconfig           ignore any config file found

-o, --option=OPTION  activate option

-l, --logfile=PATH   Path to log file.


EXAMPLES
--------

:cohen3 --plugin=backend\:FSStore,name\:MyCoherence:
    Start cohen activating the `FSStore` backend.

:cohen3 --plugin=backend\:MediaStore,medialocation\:$HOME/Music/,mediadb\:/tmp/media.db:
    Start cohen3 activating the `MediaStore` backend with media
    located in `$HOME/Music` and the media metadata store in
    `/tmp/media.db`.

AVAILABLE STORES
----------------

BetterLight, AmpacheStore, FlickrStore, MiroStore, ElisaPlayer,
ElisaMediaStore, Gallery2Store, DVBDStore, FSStore, BuzztardPlayer,
BuzztardStore, GStreamerPlayer, ITVStore, SWR3Store, TrackerStore,
LolcatsStore, BBCStore, MediaStore, AppleTrailerStore, LastFMStore,
AxisCamStore, YouTubeStore, TEDStore, IRadioStore, TwitchStore

FILES
-----

:$HOME/.cohen3: default config file

ENVIRONMENT VARIABLES
---------------------

:COHEN_DEBUG=<STORE>:
    Supplies debug information pertaining to the named store.


SEE ALSO
--------

Project Homepage https://github.com/opacam/Cohen3
