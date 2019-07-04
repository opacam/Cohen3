import platform

__version_info__ = (0, 9, 2)
__version__ = '.'.join(map(str, __version_info__))
__url__ = 'https://github.com/opacam/Cohen3'
__service_name__ = 'Cohen3'

SERVER_ID = ','.join([platform.system(),
                      platform.release(),
                      f'UPnP/1.0,{__service_name__}',
                      __version__])
