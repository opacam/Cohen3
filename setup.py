# -*- coding: utf-8 -*-

import sys
import os

__version__ = "0.7.0"

try:
  import setuptools
  from setuptools import setup, find_packages

  packages = find_packages()
except ImportError:
  setuptools = None
  from distutils.core import setup

  packages = ['coherence', ]

  def find_packages(path):
    for f in os.listdir(path):
      if f[0] == '.':
        continue
      if os.path.isdir(os.path.join(path, f)):
        next_path = os.path.join(path, f)
        if '__init__.py' in os.listdir(next_path):
          packages.append(next_path.replace(os.sep, '.'))
        find_packages(next_path)

  find_packages('coherence')

cmdclass = {}


DOCPAGES = (
  ('manpage', 'docs/man/cohen.rst', 'docs/man/cohen.1'),
)

setup_args = {
  'name': "Cohen",
  'version': __version__,
  'description': """Cohen - DLNA/UPnP Media Server""",
  'long_description': """
Cohen is a DLNA/UPnP Media Server written in Python,
providing several UPnP MediaServers and MediaRenderers
to make simple publishing and streaming different types of media content to your network.

Cohen is actually a highly simplified and refreshed version of Coherence Framework project
(http://coherence-project.org) by Frank Scholz (dev@coherence-project.org).
""",
  'author': "unintended",
  'author_email': 'unintended.github@gmail.com',
  'license': "MIT",
  'packages': packages,
  'scripts': ['bin/cohen'],
  'url': "https://github.com/unintended/Cohen",
  'download_url': 'http://coherence-project.org/download/Coherence-%s.tar.gz' % __version__,
  'keywords': ['UPnP', 'DLNA', 'multimedia', 'gstreamer'],
  'classifiers': ['Development Status :: 5 - Production/Stable',
                  'Environment :: Console',
                  'Environment :: Web Environment',
                  'License :: OSI Approved :: MIT License',
                  'Operating System :: OS Independent',
                  'Programming Language :: Python',
                  ],
  'package_data': {
    'coherence': ['upnp/core/xml-service-descriptions/*.xml'],
    'misc': ['device-icons/*.png'],
  },
}

if setuptools:
  requires = [
    'ConfigObj >= 4.3',
    'Twisted >= 14.0',
    'zope.interface',
    'louie',
    'livestreamer',
    'lxml',
    'python-dateutil',
    'pyopenssl'
  ]
  if sys.platform in ('win32', 'sunos5'):
    requires.append('Netifaces >= 0.4')

  entry_points = """
    [coherence.plugins.backend.media_server]
    FSStore = coherence.backends.fs_storage:FSStore
    MediaStore = coherence.backends.mediadb_storage:MediaStore
    ElisaMediaStore = coherence.backends.elisa_storage:ElisaMediaStore
    FlickrStore = coherence.backends.flickr_storage:FlickrStore
    AxisCamStore = coherence.backends.axiscam_storage:AxisCamStore
    BuzztardStore = coherence.backends.buzztard_control:BuzztardStore
    IRadioStore = coherence.backends.iradio_storage:IRadioStore
    LastFMStore = coherence.backends.lastfm_storage:LastFMStore
    AmpacheStore = coherence.backends.ampache_storage:AmpacheStore
    TrackerStore = coherence.backends.tracker_storage:TrackerStore
    DVBDStore = coherence.backends.dvbd_storage:DVBDStore
    AppleTrailersStore = coherence.backends.appletrailers_storage:AppleTrailersStore
    LolcatsStore = coherence.backends.lolcats_storage:LolcatsStore
    TEDStore = coherence.backends.ted_storage:TEDStore
    BBCStore = coherence.backends.bbc_storage:BBCStore
    SWR3Store = coherence.backends.swr3_storage:SWR3Store
    Gallery2Store = coherence.backends.gallery2_storage:Gallery2Store
    YouTubeStore = coherence.backends.youtube_storage:YouTubeStore
    MiroGuideStore = coherence.backends.miroguide_storage:MiroGuideStore
    ITVStore = coherence.backends.itv_storage:ITVStore
    PicasaStore = coherence.backends.picasa_storage:PicasaStore
    TestStore = coherence.backends.test_storage:TestStore
    PlaylistStore = coherence.backends.playlist_storage:PlaylistStore
    YamjStore = coherence.backends.yamj_storage:YamjStore
    BansheeStore = coherence.backends.banshee_storage:BansheeStore
    FeedStore = coherence.backends.feed_storage:FeedStore
    RadiotimeStore = coherence.backends.radiotime_storage:RadiotimeStore
    AudioCDStore = coherence.backends.audiocd_storage:AudioCDStore
    TwitchStore = coherence.backends.twitch_storage:TwitchStore

    [coherence.plugins.backend.media_renderer]
    ElisaPlayer = coherence.backends.elisa_renderer:ElisaPlayer
    GStreamerPlayer = coherence.backends.gstreamer_renderer:GStreamerPlayer
    BuzztardPlayer = coherence.backends.buzztard_control:BuzztardPlayer

    [coherence.plugins.backend.binary_light]
    SimpleLight = coherence.backends.light:SimpleLight

    [coherence.plugins.backend.dimmable_light]
    BetterLight = coherence.backends.light:BetterLight
  """

  setup(cmdclass=cmdclass, install_requires=requires, entry_points=entry_points)
else:
  setup(cmdclass=cmdclass)
