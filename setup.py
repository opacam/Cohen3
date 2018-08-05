# -*- coding: utf-8 -*-

import sys

from setuptools import setup, find_packages

from coherence import __version__

if sys.version_info[:3] < (3, 5, 0):
    raise NotImplemented('Python 3.5+ required, bye-bye')

packages = find_packages()

DOCPAGES = (
    ('manpage', 'docs/man/cohen3.rst', 'docs/man/cohen3.1'),
)

deps = [
    'ConfigObj >= 4.3',
    'Twisted >= 18.7',
    'zope.interface',
    'louie-latest',
    'livestreamer',
    'lxml',
    'python-dateutil',
    'pyopenssl'
]
if sys.platform in ('win32', 'sunos5'):
    deps.append('Netifaces >= 0.4')

entry_points = """
    [coherence.plugins.backend.media_server]
    AmpacheStore = coherence.backends.ampache_storage:AmpacheStore
    AppleTrailersStore = coherence.backends.appletrailers_storage:AppleTrailersStore
    AudioCDStore = coherence.backends.audiocd_storage:AudioCDStore
    AxisCamStore = coherence.backends.axiscam_storage:AxisCamStore
    BansheeStore = coherence.backends.banshee_storage:BansheeStore
    BBCStore = coherence.backends.bbc_storage:BBCStore
    BuzztardStore = coherence.backends.buzztard_control:BuzztardStore
    DVBDStore = coherence.backends.dvbd_storage:DVBDStore
    ElisaMediaStore = coherence.backends.elisa_storage:ElisaMediaStore
    FeedStore = coherence.backends.feed_storage:FeedStore
    FlickrStore = coherence.backends.flickr_storage:FlickrStore
    FSStore = coherence.backends.fs_storage:FSStore
    Gallery2Store = coherence.backends.gallery2_storage:Gallery2Store
    IRadioStore = coherence.backends.iradio_storage:IRadioStore
    ITVStore = coherence.backends.itv_storage:ITVStore
    LastFMStore = coherence.backends.lastfm_storage:LastFMStore
    LolcatsStore = coherence.backends.lolcats_storage:LolcatsStore
    MediaStore = coherence.backends.mediadb_storage:MediaStore
    MiroGuideStore = coherence.backends.miroguide_storage:MiroGuideStore
    PicasaStore = coherence.backends.picasa_storage:PicasaStore
    PlaylistStore = coherence.backends.playlist_storage:PlaylistStore
    RadiotimeStore = coherence.backends.radiotime_storage:RadiotimeStore
    SWR3Store = coherence.backends.swr3_storage:SWR3Store
    TEDStore = coherence.backends.ted_storage:TEDStore
    TestStore = coherence.backends.test_storage:TestStore
    TrackerStore = coherence.backends.tracker_storage:TrackerStore
    TwitchStore = coherence.backends.twitch_storage:TwitchStore
    YamjStore = coherence.backends.yamj_storage:YamjStore
    YouTubeStore = coherence.backends.youtube_storage:YouTubeStore
    
    [coherence.plugins.backend.media_renderer]
    BuzztardPlayer = coherence.backends.buzztard_control:BuzztardPlayer
    ElisaPlayer = coherence.backends.elisa_renderer:ElisaPlayer
    GStreamerPlayer = coherence.backends.gstreamer_renderer:GStreamerPlayer
"""

setup(name='Cohen3',
      version=__version__,
      description="Cohen3 - DLNA/UPnP Media Server",
      long_description="Cohen3 is a DLNA/UPnP Media Server rewritten in Python3"
                       " from the Python2 version Cohen (original project"
                       " was coherence-project), providing several "
                       "UPnP MediaServers and MediaRenderers to make simple "
                       "publishing and streaming different types of media "
                       "content to your network.",
      author='opacam',
      author_email='canellestudi@gmail.com',
      license='MIT',
      packages=packages,
      scripts=['bin/cohen3'],
      url='https://github.com/opacam/Cohen3',
      keywords=['UPnP', 'DLNA', 'multimedia', 'gstreamer'],
      classifiers=['Development Status :: 5 - Production/Stable',
                   'Environment :: Console',
                   'Environment :: Web Environment',
                   'License :: OSI Approved :: MIT License',
                   'Operating System :: OS Independent',
                   'Programming Language :: Python :: 3',
                   'Programming Language :: Python :: 3.5',
                   'Topic :: Internet :: WWW/HTTP',
                   'Topic :: Multimedia :: Sound/Audio',
                   'Topic :: Multimedia :: Video',
                   'Topic :: Utilities',
                   ],
      package_data={
          'coherence': ['upnp/core/xml-service-descriptions/*.xml'],
          'misc': ['device-icons/*.png'],
      },
      install_requires=deps,
      entry_points=entry_points
      )
