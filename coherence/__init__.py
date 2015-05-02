import platform


__version_info__ = (0, 7, 0)
__version__ = '.'.join(map(str, __version_info__))
__url__ = 'https://github.com/unintended/Cohen'
__service_name__ = 'Cohen'

SERVER_ID = ','.join([platform.system(),
                      platform.release(),
                      'UPnP/1.0,%s' % __service_name__,
                      __version__])
