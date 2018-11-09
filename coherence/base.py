# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2006,2007,2008 Frank Scholz <coherence@beebits.net>
# Copyright 2018, Pol Canelles <canellestudi@gmail.com>

'''
Base
====

The core of the project. Holds the class :class:`Coherence` intended to be used
to manage all the resources of the project. Also contains some other classes
which are vital to the project.

:class:`SimpleRoot`
-------------------

A web resource representing a web site. Used to build the contents browser for
our instance of a :class:`WebServer` or :class:`WebServerUi`.

:class:`WebServer`
------------------

A class which takes care of dealing with the web representation of the running
:class:`Coherence`'s instance. This is the default webserver used.

:class:`WebServerUi`
--------------------

The default web server, :class:`WebServer`, can be replaced by this class which
will do the same thing as the default web server, but with a more polished
interface.

:class:`Plugins`
----------------

Manage all the available plugins for the Cohen3 project.

:class:`Coherence`
------------------

The Main class of the Cohen3 project. The Coherence class controls all the
servers initialization depending on the configuration passed.

'''

import copy
import logging
import os
import socket
import traceback

from twisted.internet import defer
from twisted.internet import reactor
from twisted.internet import endpoints
from twisted.internet.tcp import CannotListenError
from twisted.web import resource, static
from twisted.python.util import sibpath

from eventdispatcher import (
    EventDispatcher, ListProperty, DictProperty, Property)

from coherence import __version__
from coherence import log
from coherence.upnp.core.device import Device, RootDevice
from coherence.upnp.core.msearch import MSearch
from coherence.upnp.core.ssdp import SSDPServer
from coherence.upnp.core.utils import to_string
from coherence.upnp.core.utils import Site
from coherence.upnp.core.utils import get_ip_address, get_host_address
from coherence.upnp.devices.control_point import ControlPoint
from coherence.upnp.devices.media_renderer import MediaRenderer
from coherence.upnp.devices.media_server import MediaServer

__import_devices__ = ControlPoint, MediaServer, MediaRenderer

try:
    import pkg_resources
except ImportError:
    pkg_resources = None


class SimpleRoot(resource.Resource, log.LogAble):
    addSlash = True
    logCategory = 'coherence'

    def __init__(self, coherence):
        resource.Resource.__init__(self)
        log.LogAble.__init__(self)
        self.coherence = coherence

        self.putChild(b'styles',
                      static.File(sibpath(__file__, 'web/static/styles'),
                                  defaultType='text/css'))
        self.putChild(b'server-images',
                      static.File(sibpath(__file__, 'web/static/images'),
                                  defaultType='text/css'))

    def getChild(self, name, request):
        self.debug(f'SimpleRoot getChild {name}, {request}')
        name = to_string(name)
        if name == 'oob':
            ''' we have an out-of-band request '''
            return static.File(
                self.coherence.dbus.pinboard[request.args['key'][0]])

        if name in ['', None]:
            return self

        # at this stage, name should be a device UUID
        try:
            return self.coherence.children[name]
        except KeyError:
            self.warning(f'Cannot find device for requested name: {name}')
            request.setResponseCode(404)
            return \
                static.Data(
                    f'<html><p>No device for requested UUID: '
                    f'{name.encode("ascii")}</p></html>'.encode('ascii'),
                    'text/html')

    def listchilds(self, uri):
        uri = to_string(uri)
        self.info(f'listchilds {uri}')
        if uri[-1] != '/':
            uri += '/'

        cl = []
        for child in self.coherence.children:
            device = self.coherence.get_device_with_id(child)
            if device is not None:
                cl.append(
                    f'<li><a href={uri}{child}>'
                    f'{device.get_friendly_device_type()}:'
                    f'{device.get_device_type_version()} '
                    f'{device.get_friendly_name()}'
                    f'</a></li>')

        # We put in a blacklist the styles and server-images folders,
        # in order to avoid to appear into the generated html list
        blacklist = ['styles', 'server-images']
        for c in self.children:
            c = to_string(c)
            if c in blacklist:
                continue
            cl.append(f'<li><a href={uri}{c}>{c}</a></li>')
        return ''.join(cl)

    def render(self, request):
        html = f'''\
        <html>
        <head profile="http://www.w3.org/2005/10/profile">
            <title>Cohen3 (SimpleRoot)</title>
            <link rel="stylesheet" type="text/css" href="/styles/main.css"/>
            <link rel="icon" type="image/png"
            href="/server-images/coherence-icon.ico"/>
        </head>
        <body>
            <div class="text-center column col-100 bottom-0">
                <h5>Dlna/UPnP framework</h5>
                <img id="logo-image"
                    src="/server-images/coherence-icon.svg"/>
                <h5>For the Digital Living</h5>
            </div>
            <div class="column col-100">
                    <h6 class="title-head-lines">
                        <img class="logo-icon"
                        src="/server-images/coherence-icon.svg"></img>
                        Hosting:
                    </h6>
                <div class="list">
                    <ul>{self.listchilds(request.uri)}</ul>
                </div>
            </div>
        </body></html>'''
        return html.encode('ascii')


class WebServer(log.LogAble):
    logCategory = 'webserver'

    def __init__(self, ui, port, coherence):
        log.LogAble.__init__(self)
        self.site = Site(SimpleRoot(coherence))

        self.endpoint = endpoints.TCP4ServerEndpoint(reactor, port)
        self._endpoint_listen(coherence, port)

    def _endpoint_listen(self, coherence, port):
        self.endpoint_listen = self.endpoint.listen(self.site)

        def set_listen_port(p):
            self.endpoint_port = p
            coherence.web_server_port = port
            self.warning(
                f'WebServer on ip '
                f'http://{coherence.hostname}:{coherence.web_server_port}'
                f' ready')

        def clear(whatever):
            self.endpoint_listen = None
            return whatever
        self.endpoint_listen.addCallback(set_listen_port).addBoth(clear)


class WebServerUi(WebServer):
    logCategory = 'webserverui'

    def __init__(self, port, coherence, unittests=False):
        log.LogAble.__init__(self)
        self.coherence = coherence
        from coherence.web.ui import Web, IWeb, WebUI
        from twisted.web import server, resource
        from twisted.python.components import registerAdapter

        def resource_factory(original):
            return WebUI(IWeb, original)

        registerAdapter(resource_factory, Web, resource.IResource)

        self.web_root_resource = WebUI(coherence)
        if not unittests:
            site_cls = server.Site
        else:
            from tests.web_utils import DummySite
            site_cls = DummySite
        self.site = site_cls(self.web_root_resource)

        self.endpoint = endpoints.TCP4ServerEndpoint(reactor, port)
        self._endpoint_listen(coherence, port)

        self.ws_endpoint = endpoints.TCP4ServerEndpoint(reactor, 9000)
        self._ws_endpoint_listen(coherence)

    def _endpoint_listen(self, coherence, port):
        self.endpoint_listen = self.endpoint.listen(self.site)

        def set_listen_port(p):
            self.endpoint_port = p
            coherence.web_server_port = port
            self.warning(
                f'WebServerUi on ip '
                f'http://{coherence.hostname}:{coherence.web_server_port}'
                f' ready')

        def clear(whatever):
            self.endpoint_listen = None
            return whatever
        self.endpoint_listen.addCallback(set_listen_port).addBoth(clear)

    def _ws_endpoint_listen(self, coherence):
        self.ws_endpoint_listen = self.ws_endpoint.listen(
            self.web_root_resource.factory)

        def set_ws_listen_port(p):
            self.ws_endpoint_port = p

        def clear_ws(whatever):
            self.ws_endpoint_listen = None
            return whatever
        self.ws_endpoint_listen.addCallback(
            set_ws_listen_port).addBoth(clear_ws)


class Plugins(log.LogAble):
    logCategory = 'plugins'
    __instance = None  # Singleton
    __initialized = False

    _valids = ('coherence.plugins.backend.media_server',
               'coherence.plugins.backend.media_renderer',
               'coherence.plugins.backend.binary_light',
               'coherence.plugins.backend.dimmable_light')

    _plugins = {}

    def __new__(cls, *args, **kwargs):
        if cls.__instance is None:
            cls.__instance = super(Plugins, cls).__new__(cls)
            cls.__instance.__initialized = False
            cls.__instance.__cls = cls
        return cls.__instance

    def __init__(self, ids=_valids):
        # initialize only once
        if self.__initialized:
            return
        self.__initialized = True

        log.LogAble.__init__(self)
        if not isinstance(ids, (list, tuple)):
            ids = (ids,)
        if pkg_resources:
            for group in ids:
                for entrypoint in pkg_resources.iter_entry_points(group):
                    # set a placeholder for lazy loading
                    self._plugins[entrypoint.name] = entrypoint
        else:
            self.info('no pkg_resources, fallback to simple plugin handling')

        if len(self._plugins) == 0:
            self._collect_from_module()

    def __repr__(self):
        return str(self._plugins)

    def __getitem__(self, key):
        plugin = self._plugins.__getitem__(key)
        if pkg_resources and isinstance(plugin, pkg_resources.EntryPoint):
            try:
                plugin = plugin.load(require=False)
            except (ImportError, AttributeError,
                    pkg_resources.ResolutionError) as msg:
                self.warning(f'Can\'t load plugin {plugin.name} ({msg}), '
                             f'maybe missing dependencies...')
                self.info(traceback.format_exc())
                del self._plugins[key]
                raise KeyError
            else:
                self._plugins[key] = plugin
        return plugin

    def get(self, key, default=None):
        try:
            return self.__getitem__(key)
        except KeyError:
            return default

    def __setitem__(self, key, value):
        self._plugins.__setitem__(key, value)

    def set(self, key, value):
        return self.__setitem__(key, value)

    def keys(self):
        return list(self._plugins.keys())

    def _collect_from_module(self):
        from coherence.extern.simple_plugin import Reception
        reception = Reception(
            os.path.join(os.path.dirname(__file__), 'backends'),
            log=self.warning)
        self.info(reception.guestlist())
        for cls in reception.guestlist():
            self._plugins[cls.__name__.split('.')[-1]] = cls


class Coherence(EventDispatcher, log.LogAble):
    '''
    The Main class of the Cohen3 project. The Coherence class controls all the
    servers initialization depending on the configuration passed.
    It is also capable of initialize the plugins defined in config variable or
    by configuration file.
    It supports the creation of multiple servers at once.

    **Example of a simple server via plugin AppleTrailersStore**::

        from coherence.base import Coherence
        from coherence.upnp.core.uuid import UUID
        from twisted.internet import reactor
        new_uuid = UUID()

        coherence = Coherence(
            {'logmode': 'info',
             'controlpoint': 'yes',
             'plugin': [{'backend': 'AppleTrailersStore',
                        'name': 'Cohen3 Example FSStore',
                        'uuid': new_uuid,
                        }
                        ]
             }
        )
        reactor.run()

    .. versionchanged:: 0.9.0

        * Introduced inheritance from EventDispatcher
        * The emitted events changed:

            - Coherence.UPnP.Device.detection_completed =>
              coherence_device_detection_completed
            - Coherence.UPnP.Device.removed => coherence_device_removed
            - Coherence.UPnP.RootDevice.removed =>
              coherence_root_device_removed

        * Changed some variables to benefit from the EventDispatcher's
          properties:

            - :attr:`devices`
            - :attr:`children`
            - :attr:`_callbacks`
            - :attr:`active_backends`
            - :attr:`ctrl`
            - :attr:`dbus`
            - :attr:`json`
            - :attr:`msearch`
            - :attr:`ssdp_server`
            - :attr:`transcoder_manager`
            - :attr:`web_server`
    '''

    __instance = None  # Singleton
    __initialized = False
    __incarnations = 0
    __cls = None

    logCategory = 'coherence'

    devices = ListProperty([])
    '''A list of the added devices.'''
    children = DictProperty({})
    '''A dict containing the web resources.'''
    _callbacks = DictProperty({})
    '''A dict containing the callbacks, used by the methods :meth:`subscribe`
    and :meth:`unsubscribe`.'''
    active_backends = DictProperty({})
    '''A dict containing the active backends.'''

    # Services/Devices
    ctrl = Property(None)
    '''A coherence's instance of class
    :class:`~coherence.upnp.devices.control_point.ControlPoint`. This will be
    enabled if we request it by config dict or configuration file via
    keyword *controlpoint = yes*.'''
    dbus = Property(None)
    '''A coherence's instance of class
    :class:`~coherence.dbus_service.DBusPontoon`. This will be
    enabled if we request it by config dict or configuration file via
    keyword *use_dbus = yes*.'''
    json = Property(None)
    '''A coherence's instance of class
    :class:`~coherence.json_service.JsonInterface`. This will be
    enabled if we request it by config dict or configuration file via
    keyword *json = yes*.'''
    msearch = Property(None)
    '''A coherence's instance of class
    :class:`~coherence.upnp.core.msearch.MSearch`. This is automatically
    enabled when :class:`Coherence` is initialized'''
    ssdp_server = Property(None)
    '''A coherence's instance of class
    :class:`~coherence.upnp.core.ssdp.SSDPServer`. This is automatically
    enabled when :class:`Coherence` is initialized'''
    transcoder_manager = Property(None)
    '''A coherence's instance of class
    :class:`~coherence.transcoder.TranscoderManager`. This will be
    enabled if we request itby config dict or configuration file via
    keyword *transcoding = yes*.'''
    web_server = Property(None)
    '''A coherence's instance of class
    :class:`WebServer` or :class:`WebServerUi`. We can request our preference
    by config dict or configuration file. If we use the keyword *web-ui = yes*,
    then the class :class:`WebServerUi` will be used, otherwise, the enabled
    web server will be of class :class:`WebServer`.'''

    def __new__(cls, *args, **kwargs):
        if cls.__instance is None:
            cls.__instance = super(Coherence, cls).__new__(cls)
            cls.__instance.__initialized = False
            cls.__instance.__incarnations = 0
            cls.__instance.__cls = cls
            cls.__instance.config = kwargs.get('config', {})
        cls.__instance.__incarnations += 1
        return cls.__instance

    def __init__(self, config=None):
        # initialize only once
        if self.__initialized:
            return
        self.__initialized = True

        # supers
        log.LogAble.__init__(self)
        EventDispatcher.__init__(self)
        self.register_event(
            'coherence_device_detection_completed',
            'coherence_device_removed',
            'coherence_root_device_removed',
        )

        self.config = config or {}

        self.available_plugins = None

        self.external_address = None
        self.urlbase = None
        self.web_server_port = int(config.get('serverport', 8080))

        # initializes log's system, a COHEN_DEBUG environment
        # variable overwrites all level settings here.
        try:
            logmode = config.get('logging').get('level', 'warning')
        except (KeyError, AttributeError):
            logmode = config.get('logmode', 'warning')
        try:
            subsystems = config.get('logging')['subsystem']
            if isinstance(subsystems, dict):
                subsystems = [subsystems]
            for subsystem in subsystems:
                try:
                    if subsystem['active'] == 'no':
                        continue
                except (KeyError, TypeError):
                    pass
                self.info(f'setting log-level for subsystem '
                          f'{subsystem["name"]} to {subsystem["level"]}')
                logging.getLogger(subsystem['name'].lower()).setLevel(
                    subsystem['level'].upper())
        except (KeyError, TypeError):
            subsystem_log = config.get('subsystem_log', {})
            for subsystem, level in list(subsystem_log.items()):
                logging.getLogger(subsystem.lower()).setLevel(level.upper())
        try:
            logfile = config.get('logging').get('logfile', None)
            if logfile is not None:
                logfile = str(logfile)
        except (KeyError, AttributeError, TypeError):
            logfile = config.get('logfile', None)
        log.init(logfile, logmode.upper())

        self.warning(f'Coherence UPnP framework version {__version__} '
                     f'starting [log level: {logmode}]...')

        network_if = config.get('interface')
        if network_if:
            self.hostname = get_ip_address(f'{network_if}')
        else:
            try:
                self.hostname = socket.gethostbyname(socket.gethostname())
            except socket.gaierror:
                self.warning('hostname can\'t be resolved, '
                             'maybe a system misconfiguration?')
                self.hostname = '127.0.0.1'

        if self.hostname.startswith('127.'):
            # use interface detection via routing table as last resort
            def catch_result(hostname):
                self.hostname = hostname
                self.setup_part2()

            d = defer.maybeDeferred(get_host_address)
            d.addCallback(catch_result)
        else:
            self.setup_part2()

    def clear(self):
        '''We do need this to survive multiple calls to Coherence
        during trial tests'''
        self.unbind_all()
        self.__cls.__instance = None

    def setup_part2(self):
        '''Initializes the basic and optional services/devices and the enabled
        plugins (backends).'''
        self.info(f'running on host: {self.hostname}')
        if self.hostname.startswith('127.'):
            self.warning(f'detection of own ip failed, using {self.hostname} '
                         f'as own address, functionality will be limited')

        unittest = self.config.get('unittest', 'no')
        unittest = False if unittest == 'no' else True

        try:
            # TODO: add ip/interface bind
            self.ssdp_server = SSDPServer(test=unittest)
        except CannotListenError as err:
            self.error(f'Error starting the SSDP-server: {err}')
            self.debug('Error starting the SSDP-server', exc_info=True)
            reactor.stop()
            return

        # maybe some devices are already notified, so we enforce
        # to create the device, if it is not already added...and
        # then we connect the signals for new detections.
        for st, usn in self.ssdp_server.root_devices:
            self.create_device(st, usn)
        self.ssdp_server.bind(new_device=self.create_device)
        self.ssdp_server.bind(removed_device=self.remove_device)

        self.ssdp_server.subscribe('new_device', self.add_device)
        self.ssdp_server.subscribe('removed_device', self.remove_device)

        self.msearch = MSearch(self.ssdp_server, test=unittest)

        reactor.addSystemEventTrigger('before', 'shutdown', self.shutdown,
                                      force=True)

        # Web Server Initialization
        try:
            # TODO: add ip/interface bind
            if self.config.get('web-ui', 'no') != 'yes':
                self.web_server = WebServer(
                    None, self.web_server_port, self)
            else:
                self.web_server = WebServerUi(
                    self.web_server_port, self, unittests=unittest)
        except CannotListenError:
            self.error(
                f'port {self.web_server_port} already in use, aborting!')
            reactor.stop()
            return

        self.urlbase = f'http://{self.hostname}:{self.web_server_port:d}/'
        # self.renew_service_subscription_loop = \
        #     task.LoopingCall(self.check_devices)
        # self.renew_service_subscription_loop.start(20.0, now=False)

        # Plugins Initialization
        try:
            plugins = self.config['plugin']
            if isinstance(plugins, dict):
                plugins = [plugins]
        except Exception:
            plugins = None

        if plugins is None:
            plugins = self.config.get('plugins', None)

        if plugins is None:
            self.info('No plugin defined!')
        else:
            if isinstance(plugins, dict):
                for plugin, arguments in list(plugins.items()):
                    try:
                        if not isinstance(arguments, dict):
                            arguments = {}
                        self.add_plugin(plugin, **arguments)
                    except Exception as msg:
                        self.warning(f'Can\'t enable plugin, {plugin}: {msg}!')
                        self.info(traceback.format_exc())
            else:
                for plugin in plugins:
                    try:
                        if plugin['active'] == 'no':
                            continue
                    except (KeyError, TypeError):
                        pass
                    try:
                        backend = plugin['backend']
                        arguments = copy.copy(plugin)
                        del arguments['backend']
                        backend = self.add_plugin(backend, **arguments)
                        if self.writeable_config():
                            if 'uuid' not in plugin:
                                plugin['uuid'] = str(backend.uuid)[5:]
                                self.config.save()
                    except Exception as msg:
                        self.warning(f'Can\'t enable plugin, {plugin}: {msg}!')
                        self.info(traceback.format_exc())

        self.external_address = ':'.join(
            (self.hostname, str(self.web_server_port)))

        # Control Point Initialization
        if self.config.get('controlpoint', 'no') == 'yes' or self.config.get(
                'json', 'no') == 'yes':
            self.ctrl = ControlPoint(self)

        # Json Interface Initialization
        if self.config.get('json', 'no') == 'yes':
            from coherence.json_service import JsonInterface
            self.json = JsonInterface(self.ctrl)

        # Transcoder Initialization
        if self.config.get('transcoding', 'no') == 'yes':
            from coherence.transcoder import TranscoderManager
            self.transcoder_manager = TranscoderManager(self)

        # DBus Initialization
        if self.config.get('use_dbus', 'no') == 'yes':
            try:
                from coherence import dbus_service
                if self.ctrl is None:
                    self.ctrl = ControlPoint(self)
                self.ctrl.auto_client_append('InternetGatewayDevice')
                self.dbus = dbus_service.DBusPontoon(self.ctrl)
            except Exception as msg:
                self.warning(f'Unable to activate dbus sub-system: {msg}')
                self.debug(traceback.format_exc())

    def add_plugin(self, plugin, **kwargs):
        self.info(f'adding plugin {plugin}')

        self.available_plugins = Plugins()

        # TODO clean up this exception concept
        try:
            plugin_class = self.available_plugins.get(plugin, None)
            if plugin_class is None:
                raise KeyError
            for device in plugin_class.implements:
                try:
                    device_class = globals().get(device, None)
                    if device_class is None:
                        raise KeyError
                    self.info(f'Activating {plugin} plugin as {device}...')
                    new_backend = device_class(self, plugin_class, **kwargs)
                    self.active_backends[str(new_backend.uuid)] = new_backend
                    return new_backend
                except KeyError:
                    self.warning(f'Can\'t enable {plugin} plugin, '
                                 f'sub-system {device} not found!')
                except Exception as e1:
                    self.exception(f'Can\'t enable {plugin} plugin for '
                                   f'sub-system {device} [exception: {e1}]')
                    self.debug(traceback.format_exc())
        except KeyError:
            self.warning(f'Can\'t enable {plugin} plugin, not found!')
        except Exception as e2:
            self.warning(f'Can\'t enable {plugin} plugin, {e2}!')
            self.debug(traceback.format_exc())

    def remove_plugin(self, plugin):
        '''Removes a backend from Coherence

        Args:
            plugin (object): is the object return by add_plugin or
                an UUID string.
        '''
        if isinstance(plugin, str):
            try:
                plugin = self.active_backends[plugin]
            except KeyError:
                self.warning(f'no backend with the uuid {plugin} found')
                return ''

        try:
            del self.active_backends[str(plugin.uuid)]
            self.info(f'removing plugin {plugin}')
            plugin.unregister()
            return plugin.uuid
        except KeyError:
            self.warning(f'no backend with the uuid {plugin.uuid} found')
            return ''

    @staticmethod
    def writeable_config():
        '''Do we have a new-style config file'''
        return False

    def store_plugin_config(self, uuid, items):
        '''Find the backend with uuid and store in its the config the key
        and value pair(s).'''
        plugins = self.config.get('plugin')
        if plugins is None:
            self.warning('storing a plugin config option is only possible'
                         ' with the new config file format')
            return
        if isinstance(plugins, dict):
            plugins = [plugins]
        uuid = str(uuid)
        if uuid.startswith('uuid:'):
            uuid = uuid[5:]
        for plugin in plugins:
            try:
                if plugin['uuid'] == uuid:
                    for k, v in list(items.items()):
                        plugin[k] = v
                    self.config.save()
            except Exception as e:
                self.warning(f'Coherence.store_plugin_config: {e}')
        else:
            self.info(f'storing plugin config option '
                      f'for {uuid} failed, plugin not found')

    def receiver(self, signal, *args, **kwargs):
        pass

    def shutdown(self, force=False):
        if self.__incarnations > 1 and not force:
            self.__incarnations -= 1
            return

        if self.dbus:
            self.dbus.shutdown()
            self.dbus = None

        for backend in self.active_backends.values():
            backend.unregister()
        self.active_backends = {}

        # send service unsubscribe messages
        if self.web_server is not None:
            if hasattr(self.web_server, 'endpoint_listen'):
                if self.web_server.endpoint_listen is not None:
                    self.web_server.endpoint_listen.cancel()
                    self.web_server.endpoint_listen = None
                if self.web_server.endpoint_port is not None:
                    self.web_server.endpoint_port.stopListening()
            if hasattr(self.web_server, 'ws_endpoint_listen'):
                if self.web_server.ws_endpoint_listen is not None:
                    self.web_server.ws_endpoint_listen.cancel()
                    self.web_server.ws_endpoint_listen = None
                if self.web_server.ws_endpoint_port is not None:
                    self.web_server.ws_endpoint_port.stopListening()
        try:
            if hasattr(self.msearch, 'double_discover_loop'):
                self.msearch.double_discover_loop.stop()
            if hasattr(self.msearch, 'port'):
                self.msearch.port.stopListening()
            if hasattr(self.ssdp_server, 'resend_notify_loop'):
                self.ssdp_server.resend_notify_loop.stop()
            if hasattr(self.ssdp_server, 'port'):
                self.ssdp_server.port.stopListening()
            # self.renew_service_subscription_loop.stop()
        except Exception:
            pass

        dev_l = []
        for root_device in self.get_devices():
            if hasattr(root_device, 'root_device_detection_completed'):
                root_device.unbind(
                    root_device_detection_completed=self.add_device)
            for device in root_device.get_devices():
                dd = device.unsubscribe_service_subscriptions()
                dd.addCallback(device.remove)
                dev_l.append(dd)
            rd = root_device.unsubscribe_service_subscriptions()
            rd.addCallback(root_device.remove)
            dev_l.append(rd)

        def homecleanup(result):
            # cleans up anything left over
            self.ssdp_server.unbind(new_device=self.create_device)
            self.ssdp_server.unbind(removed_device=self.remove_device)
            self.ssdp_server.shutdown()
            if self.ctrl:
                self.ctrl.shutdown()
            self.warning('Coherence UPnP framework shutdown')
            return result

        dl = defer.DeferredList(dev_l)
        dl.addCallback(homecleanup)
        return dl

    def check_devices(self):
        '''Iterate over devices and their embedded ones and renew
        subscriptions.'''
        for root_device in self.get_devices():
            root_device.renew_service_subscriptions()
            for device in root_device.get_devices():
                device.renew_service_subscriptions()

    def subscribe(self, name, callback):
        self._callbacks.setdefault(name, []).append(callback)

    def unsubscribe(self, name, callback):
        callbacks = self._callbacks.get(name, [])
        if callback in callbacks:
            callbacks.remove(callback)
        self._callbacks[name] = callbacks

    def callback(self, name, *args):
        for callback in self._callbacks.get(name, []):
            callback(*args)

    def get_device_by_host(self, host):
        found = []
        for device in self.devices:
            if device.get_host() == host:
                found.append(device)
        return found

    def get_device_with_usn(self, usn):
        found = None
        for device in self.devices:
            if device.get_usn() == usn:
                found = device
                break
        return found

    def get_device_with_id(self, device_id):
        # print(f'get_device_with_id [{type(device_id)}]: {device_id}')
        found = None
        for device in self.devices:
            id = device.get_id()
            if device_id[:5] != 'uuid:':
                id = id[5:]
            if id == device_id:
                found = device
                break
        return found

    def get_devices(self):
        # print(f'get_devices: {self.devices}')
        return self.devices

    def get_local_devices(self):
        # print(f'get_local_devices: '
        #       f'{[d for d in self.devices if d.manifestation == "local"]}')
        return [d for d in self.devices if d.manifestation == 'local']

    def get_nonlocal_devices(self):
        # print(f'get_nonlocal_devices: '
        #       f'{[d for d in self.devices if d.manifestation == "remote"]}')
        return [d for d in self.devices if d.manifestation == 'remote']

    def is_device_added(self, infos):
        '''
        Check if the device exists in our list of created :attr:`devices`.

        Args:
            infos (dict): Information about the device

        Returns:
            True if the device exists in our list of :attr:`devices`,
            otherwise, returns False.

        .. versionadded:: 0.9.0
        '''
        for d in self.devices:
            if d.st == infos['ST'] and d.usn == infos['USN']:
                return True
        return False

    def create_device(self, device_type, infos):
        if self.is_device_added(infos):
            self.warning(
                f'No need to create the device, we already added device: '
                f'{infos["ST"]} with usn {infos["USN"]}...!!')
            return
        self.info(f'creating {infos["ST"]} {infos["USN"]}')
        if infos['ST'] == 'upnp:rootdevice':
            self.info(f'creating upnp:rootdevice  {infos["USN"]}')
            root = RootDevice(infos)
            root.bind(root_detection_completed=self.add_device)
        else:
            self.info(f'creating device/service  {infos["USN"]}')
            root_id = infos['USN'][:-len(infos['ST']) - 2]
            root = self.get_device_with_id(root_id)
            # TODO: must check that this is working as expected
            device = Device(root, udn=infos['UDN'])

    def add_device(self, device, *args):
        self.info(f'adding device {device.get_id()} {device.get_usn()} '
                  f'{device.friendly_device_type}')
        self.devices.append(device)
        self.dispatch_event(
            'coherence_device_detection_completed', device=device)

    def remove_device(self, device_type, infos):
        self.info(f'removed device {infos["ST"]} {infos["USN"]}')
        device = self.get_device_with_usn(infos['USN'])
        if device:
            self.dispatch_event('coherence_device_removed',
                                infos['USN'], device.client)
            self.devices.remove(device)
            device.remove()
            if infos['ST'] == 'upnp:rootdevice':
                self.dispatch_event(
                    'coherence_root_device_removed',
                    infos['USN'], device.client)
                self.callback('removed_device', infos['ST'], infos['USN'])

    def add_web_resource(self, name, sub):
        self.children[name] = sub

    def remove_web_resource(self, name):
        try:
            del self.children[name]
        except KeyError:
            ''' probably the backend init failed '''
            pass

    @staticmethod
    def check_louie(receiver, signal, method='connect'):
        '''
        Check if the connect or disconnect method's arguments are valid in
        order to automatically convert to EventDispatcher's bind
        The old valid signals are:

            - Coherence.UPnP.Device.detection_completed
            - Coherence.UPnP.RootDevice.detection_completed
            - Coherence.UPnP.Device.removed
            - Coherence.UPnP.RootDevice.removed

        .. versionadded:: 0.9.0
        '''
        if not callable(receiver):
            raise Exception('The receiver should be callable in order to use'
                            ' the method {method}')
        if not signal:
            raise Exception(
                f'We need a signal in order to use method {method}')
        if not (signal.startswith('Coherence.UPnP.Device.') or
                signal.startswith('Coherence.UPnP.RootDevice.')):
            raise Exception(
                'We need a signal an old signal starting with: '
                '"Coherence.UPnP.Device." or "Coherence.UPnP.RootDevice."')

    def connect(self, receiver, signal=None, sender=None, weak=True):
        '''
        Wrapper method around the deprecated method louie.connect. It will
        check if the passed signal is supported by executing the method
        :meth:`check_louie`.

        .. warning:: This will probably be removed at some point, if you use
                     the connect method you should migrate to the new event
                     system EventDispatcher.

        .. versionchanged:: 0.9.0
            Added EventDispatcher's compatibility for some basic signals
        '''
        self.check_louie(receiver, signal, 'connect')
        if signal.endswith('.detection_completed'):
            self.bind(coherence_device_detection_completed=receiver)
        elif signal.endswith('.Device.removed'):
            self.bind(coherence_device_removed=receiver)
        elif signal.endswith('.RootDevice.removed'):
            self.bind(coherence_root_device_removed=receiver)
        else:
            raise Exception(
                f'Unknown signal {signal}, we cannot bind that signal.')

    def disconnect(self, receiver, signal=None, sender=None, weak=True):
        '''
        Wrapper method around the deprecated method louie.disconnect. It will
        check if the passed signal is supported by executing the method
        :meth:`check_louie`.

        .. warning:: This will probably be removed at some point, if you use
                     the disconnect method you should migrate to the new event
                     system EventDispatcher.

        .. versionchanged:: 0.9.0
            Added EventDispatcher's compatibility for some basic signals
        '''
        self.check_louie(receiver, signal, 'disconnect')
        if signal.endswith('.detected'):
            self.unbind(
                coherence_device_detection_completed=receiver)
        elif signal.endswith('.removed'):
            self.unbind(
                control_point_client_removed=receiver)
        else:
            raise Exception(
                f'Unknown signal {signal}, we cannot unbind that signal.')
