# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2018, Pol Canelles <canellestudi@gmail.com>

'''
WebUI
=====

The :class:`WebUI` is used to enable an html interface where the user can
browse the devices content via web browser. By default, the WebUI interface
is disabled and could be enabled from config file or by config dictionary when
initializing :class:`~coherence.base.Coherence`

.. versionchanged:: 0.8.2

.. note:: Be aware that the browser should support Web Sockets and js enabled.
          All modern browsers should have this features integrated (tested with
          firefox and google chrome).

.. warning:: Don't create your web server into port 9000. This is reserved for
             the js WebSocket.

WebUi Example
-------------

A simple server with *web-ui* enabled::

    from coherence.base import Coherence
    from coherence.upnp.core.uuid import UUID
    from twisted.internet import reactor
    new_uuid = UUID()
    coherence = Coherence(
            {'web-ui': 'yes',
             'serverport': '9001',
             'logmode': 'info',
             'controlpoint': 'yes',
             'plugin': {'backend': 'FSStore',
                        'name': 'WEB UI FSStore',
                        'content': 'path-to-a-directory-with-media-content',
                        'uuid': new_uuid
                        }
             }
    )
    reactor.run()
'''

from os.path import dirname, join, exists
import json

from twisted.web.template import (
    Element, renderer, flatten,
    XMLFile, XMLString, tags, TagLoader)
from twisted.web import server, resource
from twisted.web import static
from twisted.python import util
from twisted.python.filepath import FilePath

from zope.interface import interface

from autobahn.twisted.websocket import (
    WebSocketServerFactory, WebSocketServerProtocol)

from coherence import __version__
from coherence import log

TEMPLATES_DIR = join(dirname(__file__), 'templates')
TEMPLATE_INDEX = FilePath(join(TEMPLATES_DIR, 'template_index.xml'))

template_menu_item = '''\
<ul class="text-center">
    <li class="nav-logo"></li>
    <li  xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1"
     t:render="menu_elements">
        <t:attr name="class"><t:slot name="menu_class" /></t:attr>
        <a class="tablink" href="#" t:render="name">
        <t:attr name="id"><t:slot name="menu_id" /></t:attr>
        <t:attr name="onclick"><t:slot name="menu_click" /></t:attr>
        </a>
    </li>
</ul>
'''


class WSBroadcastServerProtocol(WebSocketServerProtocol):
    '''
    WSBroadcastServerProtocol deals with the async WebSocket client connection.

    .. versionadded:: 0.8.2

    .. versionchanged:: 0.9.0
        Migrated from louie/dispatcher to EventDispatcher

    .. note:: We can attach a callback into the variable message_callback, this
              callback will be triggered whenever onMessage is called.
    '''
    factory = None
    message_callback = None

    def onMessage(self, payload, isBinary):
        self.factory.broadcast(payload.decode('utf-8'))
        if self.message_callback is not None:
            self.message_callback(payload, isBinary)

    def onOpen(self):
        self.factory.register(self)

    def connectionLost(self, reason):
        WebSocketServerProtocol.connectionLost(self, reason)
        self.factory.unregister(self)


class WSBroadcastServerFactory(WebSocketServerFactory):
    '''
    WSBroadcastServerFactory is the central WebSocket server side component
    shared between connections.

    .. versionadded:: 0.8.2
    '''
    def __init__(self, client_tracker):
        WebSocketServerFactory.__init__(self)
        self.client_tracker = client_tracker

    def register(self, client):
        self.client_tracker.register(client)

    def unregister(self, client):
        self.client_tracker.unregister(client)

    def broadcast(self, msg):
        # print(f'WSBroadcastServerFactory: {msg}')
        for c in self.client_tracker.clients:
            c.sendMessage(msg.encode('utf8'), isBinary=False)


class WSClientTracker:
    '''
    Helper to keep track of connections,
    accessed by the sync and async methods.

    .. versionadded:: 0.8.2
    '''
    def __init__(self):
        self.clients = []

    def register(self, client):
        if client not in self.clients:
            self.clients.append(client)

    def unregister(self, client):
        if client in self.clients:
            self.clients.remove(client)


class MenuItemElement(Element):
    '''
    Helper class to render a menu entry for the main navigation bar, created
    with :class:`~coherence.we.ui.MenuNavigationBar`.

    .. versionadded:: 0.8.2
    '''
    def __init__(self, loader, name):
        Element.__init__(self, loader)
        self._name = name.title()

    @renderer
    def name(self, request, tag):
        return tag(self._name)


class MenuNavigationBar(Element):
    '''
    Convenient class to create a dynamic navigation bar

    .. versionadded:: 0.8.2

    .. note:: This is strongly related with the file:
              templates/template_index.html. The content of the each element
              should be implemented dynamically (here or in any subclass) or
              statically (into the mentioned file).
    '''
    loader = XMLString(template_menu_item)
    menuData = ['cohen3', 'devices', 'logging', 'about']

    def __init__(self, page):
        super(MenuNavigationBar, self).__init__()
        self.page = page
        self.coherence = page.coherence
        self.tabs = []

    @renderer
    def menu_elements(self, request, tag):
        for el in self.menuData:
            link = el.lower()
            cls_active = ''
            if el == 'cohen3':
                link = 'home'
                cls_active += 'active'
            tag.fillSlots(menu_id=f'but-{link}')
            tag.fillSlots(menu_class=f'{cls_active}')
            tag.fillSlots(menu_click=f'openTab(\'{link}\', this)')
            yield MenuItemElement(TagLoader(tag), el)


class DevicesWatcher(log.LogAble):
    '''
    To manage the connected devices. Broadcast messages informing about the
    connected/disconnected devices via the web socket interface. This messages
    can be received by the html/js side, which will be responsible to add or
    to remove the devices.

    Args:
        page (object): An instance of :class:`~coherence.web.ui.WebUI`.

    .. versionadded:: 0.8.2
    '''
    addSlash = False
    isLeaf = True
    detected = []

    def __init__(self, page):
        log.LogAble.__init__(self)
        self.factory = page.factory
        self.coherence = page.coherence

    def add_device(self, device):
        self.info(f'DevicesWatcher found device {device.get_usn()} '
                  f'{device.get_friendly_name()} of type '
                  f'{device.get_device_type()}')
        c = self.coherence
        if device.location:
            link = join(
                dirname(device.get_location().decode('utf-8')),
                '0')  # here we force to navigate into the Content folder
        else:
            link = \
                f'http://{device.host}:{c.web_server_port}/' \
                f'{device.udn.replace("uuid:", "")}',
        dev = {'type': 'add-device',
               'name': device.get_markup_name(),
               'usn': device.get_usn(),
               'link': link,
               }
        if (device.get_friendly_name(), device.get_usn()) not in self.detected:
            self.detected.append(
                (device.get_friendly_name(), device.get_usn()))
            self.factory.broadcast(json.dumps(dev))

    def remove_device(self, usn):
        self.info(f'DevicesWatcher remove device {usn}')
        dev = {'type': 'remove-device',
               'usn': usn,
               }
        self.factory.broadcast(json.dumps(dev))
        for d, u in self.detected[:]:
            if u == usn:
                self.detected.remove((d, u))
                break

    def going_live(self):
        # TODO: Properly implement disconnection calls
        # d = self.page.notifyOnDisconnect()
        # d.addCallback(self.remove_me)
        # d.addErrback(self.remove_me)
        devices = []
        for device in self.coherence.get_devices():
            if device is not None:
                # print(device.__dict__)
                self.add_device(device)

        self.coherence.bind(
            coherence_device_detection_completed=self.add_device)
        self.coherence.bind(
            coherence_device_removed=self.remove_device)


def format_log(message, *args, **kwargs):
    '''
    Simple method to format the captured logs.

    Args:
        message (str): Message from the captured log.
        *args (list): The args from the captured log.
        **kwargs (dict): The kwargs from the captured log.

    Returns:
        A formatted string including the args and the kwargs.

    .. versionadded:: 0.8.2
    '''
    if args:
        msg = message % args
    else:
        msg = message
    if kwargs:
        msg = msg.format(**kwargs)
    return msg


class LogsWatcher(log.LogAble):
    '''
    Object that takes control of all known loggers (at init time) and redirects
    them into the web-ui interface.

    Args:
        page (object): An instance of :class:`~coherence.web.ui.WebUI`.
        active (bool): Choice to enable disable the web-ui logging system

    .. versionadded:: 0.8.2
    '''
    logCategory = 'webui-logger'
    addSlash = False
    isLeaf = True
    _messages = []
    _ws_ready = False

    def __init__(self, page, active):
        super(LogsWatcher, self).__init__()
        self.factory = page.factory
        self.coherence = page.coherence
        self.active = active

        # TODO: Maybe this should be implemented differently:
        # we could read from the logfile and extract the last lines
        # from the logfile, this way we will make the logging process
        # lighter and we will make sure to get all the created loggers
        # at anytime, even before this function is initialized.
        for k, v in log.loggers.items():
            webui_logger = v
            webui_logger.log = self.log
            webui_logger.warning = self.warning
            webui_logger.info = self.info
            webui_logger.critical = self.critical
            webui_logger.debug = self.debug
            webui_logger.error = self.error
            webui_logger.exception = self.exception

    def going_live(self):
        self.info(f'add a view to the LogsWatcher {self.coherence}')
        while len(self._messages) > 0:
            m = self._messages.pop(0)
            self.factory.broadcast(m)
        self._ws_ready = True

    def send_log(self, type, message, *args, **kwargs):
        msg = format_log(message, *args, **kwargs)
        print(f'webui-{type}: {msg}')
        m = json.dumps(
            {'type': f'log-{type}',
             'data': f'[{type}] {msg}'})
        if self._ws_ready:
            self.factory.broadcast(m)
        else:
            self._messages.append(m)

    def log(self, message, *args, **kwargs):
        self.send_log('log', message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        self.send_log('warning', message, *args, **kwargs)

    def info(self, message, *args, **kwargs):
        self.send_log('info', message, *args, **kwargs)

    def critical(self, message, *args, **kwargs):
        self.send_log('critical', message, *args, **kwargs)

    def debug(self, message, *args, **kwargs):
        self.send_log('debug', message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        self.send_log('error', message, *args, **kwargs)

    def exception(self, message, *args, **kwargs):
        # self._logger.exception(message, *args, **kwargs)
        self.send_log('exception', message, *args, **kwargs)


class IndexResource(Element, log.LogAble):
    '''
    A sub class of :class:`twisted.web.template.Element` which represents the
    main page for the web-ui interface. This takes care of rendering the main
    page as an element template, so we could add some dynamic elements when
    initializing it, like the navigation bar or the current version of the
    program.

    .. versionadded:: 0.8.2
    '''
    loader = XMLFile(TEMPLATE_INDEX)

    def __init__(self, web_resource):
        super(IndexResource, self).__init__()
        self.resource = web_resource
        self.coherence = web_resource.coherence

    @renderer
    def version(self, request, data):
        return __version__.encode('ascii')

    @renderer
    def menu(self, request, data):
        return MenuNavigationBar(self)


class IWeb(interface.InterfaceClass):
    '''
    Interface class that allow us to register :class:`~coherence.web.ui.WebUI'
     as a new adapter using the `twisted.python.components.registerAdapter`.

     .. note:: See :class:`~coherence.base.WebServerUi' for usage.
    '''
    __module__ = 'zope.interface'

    def goingLive(self):
        pass


class Web(object):
    '''
    Convenient class describing an adapterFactory that allow us to register
    :class:`~coherence.web.ui.WebUI' as a new adapter, using the
    `twisted.python.components.registerAdapter`

    Args:
        coherence (object): An instance of `~coherence.base.Coherence`

     .. note:: See :class:`~coherence.base.WebServerUi` for usage.
    '''
    def __init__(self, coherence):
        super(Web, self).__init__()
        self.coherence = coherence


class WebUI(resource.Resource, log.LogAble):
    '''
    A convenient html interface to browse the connected devices via preferred
    web browser. This interface could be enabled when initializing
    :class:`~coherence.base.Coherence` by setting "'web-ui': 'yes'" into your
    config command or via config file using the same key and value.

    Args:
        coherence (object): An instance of `~coherence.base.Coherence`

    .. versionchanged:: 0.8.2

    .. warning:: Be aware that the browser should support Web Sockets and to
                 have js enabled. All modern browsers should have this features
                 integrated (tested with firefox and google chrome).
    '''
    logCategory = 'webui'

    addSlash = True
    isLeaf = False

    ws_recived = []

    def __init__(self, coherence, *a, **kw):
        resource.Resource.__init__(self)
        log.LogAble.__init__(self)
        self.coherence = coherence

        # WebSocket init
        self.client_tracker = WSClientTracker()
        self.factory = WSBroadcastServerFactory(self.client_tracker)
        self.factory.protocol = WSBroadcastServerProtocol
        self.factory.protocol.message_callback = self.on_ws_message

        # Enable resources
        self.putChild(b'styles',
                      static.File(util.sibpath(__file__, 'static/styles'),
                                  defaultType='text/css'))
        self.putChild(b'server-images',
                      static.File(util.sibpath(__file__, 'static/images'),
                                  defaultType='text/css'))
        self.putChild(b'js',
                      static.File(util.sibpath(__file__, 'static/js'),
                                  defaultType='text/javascript'))

        self.devices = DevicesWatcher(self)
        self.logging = LogsWatcher(self, 'yes')
        self.index = IndexResource(self)

    def on_ws_message(self, payload, isBinary):
        self.info(f'on_ws_message: {payload}')
        self.ws_recived.append(payload)
        if payload == b'WebSocket Ready':
            self.devices.going_live()
            self.logging.going_live()

    def render(self, request):
        request.setHeader(b'content-type', b'text/html; charset=utf-8')
        return super(WebUI, self).render(request)

    def render_GET(self, request):
        d = flatten(request, self.index, request.write)

        def done_index(ignored):
            request.finish()

        d.addBoth(done_index)
        return server.NOT_DONE_YET

    def getChild(self, name, request):
        self.info(f'WebUI getChild: {name}')
        if name in [b'', b'\'']:
            return self

        def exist_child(key, children):
            if key in children:
                # print('\t- found child: ', name)
                return children[key]
            return None
        for na in (name, name.decode('utf-8')):
            for ch in (self.children, self.coherence.children):
                c = exist_child(na, ch)
                if c is not None:
                    return c
        ch = super(WebUI, self).getChild(name, request)
        if isinstance(ch, resource.NoResource):
            self.warning('not found child, checking  static file: ', name)
            p = util.sibpath(__file__, name.decode('utf-8'))
            self.warning(f'looking for file {p}')
            if exists(p):
                ch = static.File(p)
        return ch


if __name__ == '__main__':
    from coherence.base import Coherence
    from coherence.upnp.core.uuid import UUID
    from twisted.internet import reactor
    new_uuid = UUID()
    icon_url = 'file://{}'.format(
        join(dirname(__file__), 'static',
             'images', 'coherence-icon.png'))

    coherence = Coherence(
        {'unittest': 'no',
         'web-ui': 'yes',
         'serverport': '9001',
         'logmode': 'info',
         'controlpoint': 'yes',
         'plugin': {'backend': 'FSStore',
                    'name': 'WEB UI FSStore',
                    'content': '/media/MEDIA/TVSHOWS',  # change path
                    'uuid': new_uuid,
                    'icon': {'mimetype': 'image/png',
                             'width': '256',
                             'height': '256',
                             'depth': '24',
                             'url': icon_url}
                    }
         }
    )
    reactor.run()
