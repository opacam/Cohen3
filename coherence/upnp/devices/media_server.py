# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php
# Copyright 2006,2007 Frank Scholz <coherence@beebits.net>

import os
import re
import traceback
import urllib.error
import urllib.parse
import urllib.request
from io import StringIO

from lxml import etree
from twisted.internet import defer
from twisted.python import util
from twisted.web import resource
from twisted.web import static

from coherence import log, __version__, __url__, __service_name__
from coherence.upnp.core import xml_constants
from coherence.upnp.core.utils import ReverseProxyResource
from coherence.upnp.core.utils import StaticFile
from coherence.upnp.devices.basics import BasicDeviceMixin
from coherence.upnp.services.servers.connection_manager_server import \
    ConnectionManagerServer
from coherence.upnp.services.servers.content_directory_server import \
    ContentDirectoryServer
from coherence.upnp.services.servers.media_receiver_registrar_server import \
    FakeMediaReceiverRegistrarBackend
from coherence.upnp.services.servers.media_receiver_registrar_server import \
    MediaReceiverRegistrarServer
from coherence.upnp.services.servers.scheduled_recording_server import \
    ScheduledRecordingServer

COVER_REQUEST_INDICATOR = re.compile(r".*?cover\.[A-Z|a-z]{3,4}$")
ATTACHMENT_REQUEST_INDICATOR = re.compile(r".*?attachment=.*$")
TRANSCODED_REQUEST_INDICATOR = re.compile(r".*/transcoded/.*$")


class MSRoot(resource.Resource, log.LogAble):
    logCategory = 'mediaserver'

    def __init__(self, server, store):
        resource.Resource.__init__(self)
        log.LogAble.__init__(self)
        self.server = server
        self.store = store

    def getChildWithDefault(self, path, request):
        self.info('%s getChildWithDefault, %s, %s, %s %s',
                  self.server.device_type, request.method,
                  path, request.uri, request.client)
        headers = request.getAllHeaders()
        self.debug('\t-> headers are: {}'.format(headers))
        if not isinstance(path, bytes):
            path = path.encode('ascii')
        if path.endswith(b'\''):
            self.warning('\t modified wrong path from {} to {}'.format(
                path, path[:-1]))
            path = path[:-1]
        self.debug('\t-> path is: {} [{}]'.format(path, type(path)))

        try:
            if b'getcontentfeatures.dlna.org' in headers and \
                    headers[b'getcontentfeatures.dlna.org'] != b'1':
                request.setResponseCode(400)
                return static.Data(
                    b'<html><p>wrong value for '
                    b'getcontentFeatures.dlna.org</p></html>',
                    'text/html')
        except Exception as e1:
            self.error(
                'MSRoot.getChildWithDefault: %r' % e1)

        if request.method == b'HEAD':
            if b'getcaptioninfo.sec' in headers:
                self.warning("requesting srt file for id %r", path)
                ch = self.store.get_by_id(path)
                try:
                    location = ch.get_path()
                    caption = ch.caption
                    if caption is None:
                        raise KeyError
                    request.setResponseCode(200)
                    request.setHeader(b'CaptionInfo.sec', caption)
                    return static.Data(b'', 'text/html')
                except Exception as e2:
                    self.error(
                        'MSRoot.getChildWithDefault (method: HEAD): %r' % e2)
                    print(traceback.format_exc())
                    request.setResponseCode(404)
                    return static.Data(
                        b'<html><p>the requested srt file '
                        b'was not found</p></html>',
                        'text/html')

        try:
            request._dlna_transfermode = headers[b'transfermode.dlna.org']
        except KeyError:
            request._dlna_transfermode = b'Streaming'
        if request.method in (b'GET', b'HEAD'):
            if COVER_REQUEST_INDICATOR.match(
                    request.uri.decode('utf-8')):
                self.info("request cover for id %r", path)

                def got_item(ch):
                    if ch is not None:
                        request.setResponseCode(200)
                        file = ch.get_cover()
                        if file and os.path.exists(file):
                            self.info("got cover %s", file)
                            return StaticFile(file)
                    request.setResponseCode(404)
                    return static.Data(
                        b'<html><p>cover requested not found</p></html>',
                        'text/html')

                dfr = defer.maybeDeferred(self.store.get_by_id, path)
                dfr.addCallback(got_item)
                dfr.isLeaf = True
                return dfr

            if ATTACHMENT_REQUEST_INDICATOR.match(
                    request.uri.decode('utf-8')):
                self.info("request attachment %r for id %r",
                          request.args, path)

                def got_attachment(ch):
                    try:
                        # FIXME same as below
                        if 'transcoded' in request.args:
                            if self.server.coherence.config.get('transcoding',
                                                                'no') == 'yes':
                                format = request.args['transcoded'][0]
                                type = request.args['type'][0]
                                self.info("request transcoding %r %r", format,
                                          type)
                                try:
                                    from coherence.transcoder import \
                                        TranscoderManager
                                    manager = TranscoderManager(
                                        self.server.coherence)
                                    return \
                                        manager.select(
                                            format,
                                            ch.item.attachments[
                                                request.args[
                                                    'attachment'][0]])
                                except Exception:
                                    self.debug(traceback.format_exc())
                                request.setResponseCode(404)
                                return static.Data(
                                    b'<html><p>the requested transcoded file '
                                    b'was not found</p></html>',
                                    'text/html')
                            else:
                                request.setResponseCode(404)
                                return static.Data(
                                    b"<html><p>This MediaServer "
                                    b"doesn't support transcoding</p></html>",
                                    'text/html')
                        else:
                            return ch.item.attachments[
                                request.args['attachment'][0]]
                    except Exception:
                        request.setResponseCode(404)
                        return static.Data(
                            b'<html><p>the requested attachment '
                            b'was not found</p></html>',
                            'text/html')

                dfr = defer.maybeDeferred(self.store.get_by_id, path)
                dfr.addCallback(got_attachment)
                dfr.isLeaf = True
                return dfr

        if request.method in (b'GET', b'HEAD') and \
                TRANSCODED_REQUEST_INDICATOR.match(
                    request.uri.decode('utf-8')):
            self.info("request transcoding to %r for id %r",
                      request.uri.split(b'/')[-1], path)
            if self.server.coherence.config.get('transcoding', 'no') == 'yes':
                def got_stuff_to_transcode(ch):
                    # FIXME create a generic transcoder class
                    # and sort the details there
                    format = request.uri.split(b'/')[
                        -1]  # request.args['transcoded'][0]
                    uri = ch.get_path()
                    try:
                        from coherence.transcoder import TranscoderManager
                        manager = TranscoderManager(self.server.coherence)
                        return manager.select(format, uri)
                    except Exception:
                        self.debug(traceback.format_exc())
                        request.setResponseCode(404)
                        return static.Data(
                            b'<html><p>the requested transcoded file '
                            b'was not found</p></html>',
                            'text/html')

                dfr = defer.maybeDeferred(self.store.get_by_id, path)
                dfr.addCallback(got_stuff_to_transcode)
                dfr.isLeaf = True
                return dfr

            request.setResponseCode(404)
            return static.Data(
                b"<html><p>This MediaServer "
                b"doesn't support transcoding</p></html>",
                'text/html')

        if request.method == b'POST' and request.uri.endswith(b'?import'):
            d = self.import_file(path, request)
            if isinstance(d, defer.Deferred):
                d.addBoth(self.import_response, path)
                d.isLeaf = True
                return d
            return self.import_response(None, path)

        if (b'user-agent' in headers and
                (headers[b'user-agent'].find(b'Xbox/') in [0, None] or  # XBox
                 headers[b'user-agent'].startswith(  # wmp11
                     b"""Mozilla/4.0 (compatible; UPnP/1.0; Windows""")) and
                path in [b'description-1.xml', b'description-2.xml']):
            self.info(
                'XBox/WMP alert, we need to '
                'simulate a Windows Media Connect server')
            if b'xbox-description-1.xml' in self.children:
                self.msg('returning xbox-description-1.xml')
                return self.children[b'xbox-description-1.xml']

        # resource http://XXXX/<deviceID>/config
        # configuration for the given device
        # accepted methods:
        # GET, HEAD:
        #       returns the configuration data (in XML format)
        # POST: stop the current device and restart it
        #       with the posted configuration data
        if path in (b'config'):
            backend = self.server.backend
            backend_type = backend.__class__.__name__

            def constructConfigData(backend):
                msg = "<plugin active=\"yes\">"
                msg += "<backend>" + backend_type.decode('utf-8') if \
                    isinstance(backend_type, bytes) else \
                    backend_type + "</backend>"
                for key, value in list(backend.config.items()):
                    msg += "<" + key + ">" + value.decode('utf-8') if \
                        isinstance(value, bytes) else value + "</" + key + ">"
                msg += "</plugin>"
                return msg.encode('ascii')

            if request.method in (b'GET', b'HEAD'):
                # the client wants to retrieve the
                #  configuration parameters for the backend
                msg = constructConfigData(backend)
                request.setResponseCode(200)
                return static.Data(msg, 'text/xml')
            elif request.method in (b'POST'):
                # the client wants to update the configuration parameters
                # for the backend we relaunch the backend with the
                # new configuration (after content validation)

                def convert_elementtree_to_dict(root):
                    active = False
                    for name, value in list(root.items()):
                        if name == 'active':
                            if value in ('yes'):
                                active = True
                        break
                    if active is False:
                        return None
                    dict = {}
                    for element in root.getchildren():
                        key = element.tag
                        text = element.text
                        if key != 'backend':
                            dict[key] = text
                    return dict

                new_config = None
                try:
                    element_tree = etree.fromstring(request.content.getvalue())
                    new_config = convert_elementtree_to_dict(element_tree)
                    self.server.coherence.remove_plugin(self.server)
                    self.warning("%s %s (%s) with id %s desactivated",
                                 backend.name, self.server.device_type,
                                 backend, str(self.server.uuid)[5:])
                    if new_config is None:
                        msg = "<plugin active=\"no\"/>"
                    else:
                        new_backend = self.server.coherence.add_plugin(
                            backend_type, **new_config)
                        if self.server.coherence.writeable_config():
                            self.server.coherence.store_plugin_config(
                                new_backend.uuid, new_config)
                            msg = "<html><p>Device restarted. Config file " \
                                  "has been modified with posted data.</p>" \
                                  "</html>"  # constructConfigData(new_backend)
                        else:
                            msg = "<html><p>Device restarted. " \
                                  "Config file not modified</p>" \
                                  "</html>"  # constructConfigData(new_backend)
                    request.setResponseCode(202)
                    return static.Data(msg.encode('ascii'), 'text/html')
                except SyntaxError as e:
                    request.setResponseCode(400)
                    return static.Data(
                        "<html><p>Invalid data posted:<BR>{}</p>"
                        "</html>".format(e).encode('ascii'),
                        'text/html')
            else:
                # invalid method requested
                request.setResponseCode(405)
                return static.Data(
                    b"<html><p>This resource does not allow "
                    b"the requested HTTP method</p></html>",
                    'text/html')

        if path in self.children:
            return self.children[path]
        if request.uri == b'/':
            return self
        return self.getChild(path, request)

    def requestFinished(self, result, id, request):
        self.info("finished, remove %d from connection table", id)
        self.info("finished, sentLength: %d chunked: %d code: %d",
                  request.sentLength, request.chunked, request.code)
        self.info("finished %r", request.headers)
        self.server.connection_manager_server.remove_connection(id)

    def import_file(self, name, request):
        self.info("import file, id %s", name)
        print("import file, id %s" % name)

        def got_file(ch):
            print("ch", ch)
            if ch is not None:
                if hasattr(self.store, 'backend_import'):
                    response_code = self.store.backend_import(
                        ch, request.content)
                    if isinstance(response_code, defer.Deferred):
                        return response_code
                    request.setResponseCode(response_code)
                    return
            else:
                request.setResponseCode(404)

        dfr = defer.maybeDeferred(self.store.get_by_id, name)
        dfr.addCallback(got_file)
        return dfr

    def prepare_connection(self, request):
        new_id, _, _ = self.server.connection_manager_server.add_connection(
            '', 'Output', -1, '')
        self.info("startup, add %d to connection table", new_id)
        d = request.notifyFinish()
        d.addBoth(self.requestFinished, new_id, request)

    def prepare_headers(self, ch, request):
        request.setHeader(
            b'transferMode.dlna.org',
            request._dlna_transfermode)
        if hasattr(ch, 'item') and hasattr(ch.item, 'res'):
            if ch.item.res[0].protocolInfo is not None:
                additional_info = ch.item.res[0].get_additional_info()
                if additional_info != '*':
                    request.setHeader(
                        b'contentFeatures.dlna.org',
                        additional_info.encode('ascii'))
                elif b'getcontentfeatures.dlna.org' in request.getAllHeaders():
                    request.setHeader(
                        b'contentFeatures.dlna.org',
                        b"DLNA.ORG_OP=01;DLNA.ORG_CI=0;"
                        b"DLNA.ORG_FLAGS=01500000000000000000000000000000")

    def process_child(self, ch, name, request):
        self.debug('process_child: {} [child: {}, request: {}]'.format(
            name, ch, request))
        if ch is not None:
            self.info('Child found %s', ch)
            if (request.method == b'GET' or
                    request.method == b'HEAD'):
                headers = request.getAllHeaders()
                if b'content-length' in headers:
                    self.warning(
                        '%s request with content-length %r '
                        'header - sanitizing',
                        request.method, headers[b'content-length'])
                    del request.received_headers[b'content-length']
                self.debug('data', )
                if len(request.content.getvalue()) > 0:
                    """ shall we remove that?
                        can we remove that?
                    """
                    self.warning(
                        '%s request with %r bytes of message-body'
                        ' - sanitizing',
                        request.method,
                        len(request.content.getvalue()))
                    request.content = StringIO()

            if hasattr(ch, "location"):
                self.debug("we have a location %s",
                           isinstance(ch.location, resource.Resource))
                if (isinstance(ch.location, ReverseProxyResource) or
                        isinstance(ch.location, resource.Resource)):
                    # self.info('getChild proxy %s to %s' % (
                    #     name, ch.location.uri))
                    self.prepare_connection(request)
                    self.prepare_headers(ch, request)
                    return ch.location
            try:
                p = ch.get_path()
            except TypeError:
                return self.list_content(name, ch, request)
            except Exception as msg:
                self.debug("error accessing items path %r", msg)
                self.debug(traceback.format_exc())
                return self.list_content(name, ch, request)
            if p is not None and os.path.exists(p):
                self.info("accessing path %r", p)
                self.prepare_connection(request)
                self.prepare_headers(ch, request)
                ch = StaticFile(p)
            else:
                self.debug("accessing path %r failed", p)
                return self.list_content(name, ch, request)

        if ch is None:
            p = util.sibpath(__file__.encode('ascii'), name)
            self.debug('checking if msroot is file: %r', p)
            if os.path.exists(p):
                ch = StaticFile(p)
        self.info('MSRoot ch %r', ch)
        return ch

    def getChild(self, name, request):
        self.info('getChild %s, %s', name, request)
        if not isinstance(name, bytes):
            name = name.encode('ascii')
        ch = self.store.get_by_id(name)
        self.info('\t-child is: %r', ch)
        if isinstance(ch, defer.Deferred):
            ch.addCallback(self.process_child, name, request)
            # ch.addCallback(self.delayed_response, request)
            return ch
        return self.process_child(ch, name, request)

    def list_content(self, name, item, request):
        self.info('list_content %s %s %s', name, item, request)
        page = b"""<html><head><title>%r</title></head><body><p>%r</p>""" % \
               (item.get_name().encode('ascii', 'xmlcharrefreplace'),
                item.get_name().encode('ascii', 'xmlcharrefreplace'))

        if (hasattr(item, 'mimetype') and item.mimetype in ['directory',
                                                            'root']):
            uri = request.uri
            if uri[-1] != b'/':
                uri += b'/'

            def build_page(r, page):
                # self.debug("build_page", r)
                page += b"""<ul>"""
                if r is not None:
                    for c in r:
                        if hasattr(c, 'get_url'):
                            path = c.get_url()
                        elif hasattr(c, 'get_path') and c.get_path is not None:
                            # path = c.get_path().encode(
                            #     'utf-8').encode('string_escape')
                            path = c.get_path()
                            if isinstance(path, str):
                                path = path.encode(
                                    'ascii', 'xmlcharrefreplace')
                            else:
                                path = path.decode('utf-8').encode(
                                    'ascii', 'xmlcharrefreplace')
                        else:
                            path = request.uri.split(b'/')
                            path[-1] = str(c.get_id())
                            path = '/'.join(path)
                        title = c.get_name()
                        try:
                            if isinstance(title, str):
                                title = title.encode('ascii',
                                                     'xmlcharrefreplace')
                            else:
                                title = title.decode('utf-8').encode(
                                    'ascii', 'xmlcharrefreplace')
                        except (UnicodeEncodeError, UnicodeDecodeError):
                            title = c.get_name().encode('utf-8').encode(
                                'string_escape')
                        page += b'<li><a href="%r">%r</a></li>' % \
                                (path, title)
                page += b"""</ul>"""
                page += b"""</body></html>"""
                return static.Data(page, 'text/html')

            children = item.get_children()
            if isinstance(children, defer.Deferred):
                print("list_content, we have a Deferred", children)
                children.addCallback(build_page, page)
                # children.addErrback(....) #FIXME
                return children

            return build_page(children, page)

        elif hasattr(item, 'mimetype') and item.mimetype.find('image/') == 0:
            # path = item.get_path().encode('utf-8').encode('string_escape')
            path = urllib.parse.quote(item.get_path().encode('utf-8'))
            title = item.get_name().decode(
                'utf-8').encode('ascii', 'xmlcharrefreplace')
            page += """<p><img src="%s" alt="%s"></p>""" % \
                    (path, title)
        else:
            pass
        page += """</body></html>"""
        return static.Data(page.encode('ascii'), 'text/html')

    def listchilds(self, uri):
        if isinstance(uri, bytes):
            uri = uri.decode('utf-8')
        self.info('listchilds %s', uri)
        if uri[-1] != '/':
            uri += '/'
        cl = '<p><a href=%s0>content</a></p>' % uri
        cl += '<li><a href=%sconfig>config</a></li>' % uri
        for c in self.children:
            cl += '<li><a href=%s%s>%s</a></li>' % (uri, c, c)
        return cl

    def import_response(self, result, id):
        return \
            static.Data(b'<html><p>import of %r finished</p></html>' % id,
                        'text/html')

    def render(self, request):
        return \
            '<html><p>root of the %s MediaServer</p>' \
            '<p><ul>%s</ul></p></html>' % (
                self.server.backend, self.listchilds(request.uri))


class RootDeviceXML(static.Data):
    def __init__(self, hostname, uuid, urlbase,
                 device_type='MediaServer',
                 version=2,
                 friendly_name='Coherence UPnP A/V MediaServer',
                 xbox_hack=False,
                 services=None,
                 devices=None,
                 icons=None,
                 presentation_url=None,
                 dlna_caps=None):
        uuid = str(uuid)
        root = etree.Element(
            'root', nsmap={None: xml_constants.UPNP_DEVICE_NS})
        device_type = 'urn:schemas-upnp-org:device:%s:%d' % (
            device_type, int(version))
        e = etree.SubElement(root, 'specVersion')
        etree.SubElement(e, 'major').text = '1'
        etree.SubElement(e, 'minor').text = '0'

        d = etree.SubElement(root, 'device')
        etree.SubElement(d, 'deviceType').text = device_type

        if xbox_hack:
            etree.SubElement(d, 'friendlyName').text = \
                friendly_name + ' : 1 : Windows Media Connect'
            etree.SubElement(d, 'modelName').text = 'Windows Media Connect'
        else:
            etree.SubElement(d, 'friendlyName').text = friendly_name
            etree.SubElement(d, 'modelName').text = __service_name__

        etree.SubElement(d, 'manufacturer').text = 'beebits.net'
        etree.SubElement(d, 'manufacturerURL').text = __url__
        etree.SubElement(d, 'modelDescription').text = __service_name__

        etree.SubElement(d, 'modelNumber').text = __version__
        etree.SubElement(d, 'modelURL').text = __url__
        etree.SubElement(d, 'serialNumber').text = '0000001'
        etree.SubElement(d, 'UDN').text = uuid
        etree.SubElement(d, 'UPC').text = ''

        if icons:
            e = etree.SubElement(d, 'iconList')
            for icon in icons:

                icon_path = ''
                if 'url' in icon:
                    if icon['url'].startswith('file://'):
                        icon_path = icon['url'][7:]
                    elif icon['url'] == '.face':
                        icon_path = os.path.join(os.path.expanduser('~'),
                                                 ".face")
                    else:
                        from pkg_resources import resource_filename

                        icon_path = os.path.abspath(resource_filename(
                            __name__, os.path.join('..', '..', '..', 'misc',
                                                   'device-icons',
                                                   icon['url'])))

                if os.path.exists(icon_path):
                    i = etree.SubElement(e, 'icon')
                    for k, v in list(icon.items()):
                        if k == 'url':
                            if v.startswith('file://'):
                                etree.SubElement(i, k).text = \
                                    '/' + uuid[5:] + '/' + os.path.basename(v)
                                continue
                            elif v == '.face':
                                etree.SubElement(i, k).text = \
                                    '/' + uuid[5:] + '/' + 'face-icon.png'
                                continue
                            else:
                                etree.SubElement(i, k).text = \
                                    '/' + uuid[5:] + '/' + os.path.basename(v)
                                continue
                        etree.SubElement(i, k).text = str(v)

        if services:
            e = etree.SubElement(d, 'serviceList')
            for service in services:
                id = service.get_id()

                if not xbox_hack and id == 'X_MS_MediaReceiverRegistrar':
                    continue

                s = etree.SubElement(e, 'service')
                try:
                    namespace = service.namespace
                except AttributeError:
                    namespace = 'schemas-upnp-org'

                if hasattr(service, 'version') and service.version < version:
                    v = service.version
                else:
                    v = version

                etree.SubElement(
                    s, 'serviceType').text = 'urn:%s:service:%s:%d' % \
                                             (namespace, id, int(v))
                try:
                    namespace = service.id_namespace
                except AttributeError:
                    namespace = 'upnp-org'

                etree.SubElement(s, 'serviceId').text = \
                    'urn:%s:serviceId:%s' % (namespace, id)
                etree.SubElement(s, 'SCPDURL').text = \
                    '/' + uuid[5:] + '/' + id + '/' + \
                    service.scpd_url.decode('utf-8')
                etree.SubElement(s, 'controlURL').text = \
                    '/' + uuid[5:] + '/' + id + '/' + \
                    service.control_url.decode('utf-8')
                etree.SubElement(s, 'eventSubURL').text = \
                    '/' + uuid[5:] + '/' + id + '/' + \
                    service.subscription_url.decode('utf-8')

        if devices:
            etree.SubElement(d, 'deviceList')

        if presentation_url is None:
            presentation_url = '/' + uuid[5:]
        etree.SubElement(d, 'presentationURL').text = presentation_url
        if dlna_caps is not None:
            # TODO: Implement dlna caps for GstreamerPlayer
            print('RootDeviceXML.__init__: dlna caps for GstreamerPlayer'
                  ' still not implemented')

        x = etree.SubElement(d, 'X_DLNADOC')
        x.text = 'DMS-1.50'
        x = etree.SubElement(d, 'X_DLNADOC')
        x.text = 'M-DMS-1.50'
        x = etree.SubElement(d, 'X_DLNACAP')
        x.text = 'av-upload,image-upload,audio-upload'

        self.xml = etree.tostring(root, encoding='utf-8', xml_declaration=True,
                                  pretty_print=True)
        static.Data.__init__(self, self.xml, 'text/xml')


class MediaServer(log.LogAble, BasicDeviceMixin):
    logCategory = 'mediaserver'

    device_type = 'MediaServer'

    presentationURL = None

    def __init__(self, coherence, backend, **kwargs):
        BasicDeviceMixin.__init__(self, coherence, backend, **kwargs)
        log.LogAble.__init__(self)

    def fire(self, backend, **kwargs):

        if not kwargs.get('no_thread_needed', False):
            # this could take some time, put it in a  thread to be sure
            # it doesn't block as we can't tell for sure that
            # every backend is implemented properly

            from twisted.internet import threads
            d = threads.deferToThread(backend, self, **kwargs)

            def backend_ready(backend):
                self.backend = backend

            def backend_failure(x):
                self.warning(
                    'backend %s not installed, '
                    'MediaServer activation aborted - %s',
                    backend, x.getErrorMessage())
                self.debug(x)

            d.addCallback(backend_ready)
            d.addErrback(backend_failure)

            # FIXME: we need a timeout here so if the signal
            # we wait for not arrives we'll can close down this device
        else:
            self.backend = backend(self, **kwargs)

    def init_complete(self, backend):
        if self.backend != backend:
            return
        self._services = []
        self._devices = []

        try:
            self.connection_manager_server = ConnectionManagerServer(self)
            self._services.append(self.connection_manager_server)
        except LookupError as msg:
            self.warning('ConnectionManagerServer %s', msg)
            raise LookupError(msg)

        try:
            transcoding = False
            if self.coherence.config.get('transcoding', 'no') == 'yes':
                transcoding = True
            self.content_directory_server = \
                ContentDirectoryServer(self, transcoding=transcoding)
            self._services.append(self.content_directory_server)
        except LookupError as msg:
            self.warning('ContentDirectoryServer %s', msg)
            raise LookupError(msg)

        try:
            self.media_receiver_registrar_server = \
                MediaReceiverRegistrarServer(
                    self,
                    backend=FakeMediaReceiverRegistrarBackend())
            self._services.append(self.media_receiver_registrar_server)
        except LookupError as msg:
            self.warning('MediaReceiverRegistrarServer (optional) %s', msg)

        try:
            self.scheduled_recording_server = ScheduledRecordingServer(self)
            self._services.append(self.scheduled_recording_server)
        except LookupError as msg:
            self.info('ScheduledRecordingServer %s', msg)

        upnp_init = getattr(self.backend, "upnp_init", None)
        if upnp_init:
            upnp_init()

        self.web_resource = MSRoot(self, backend)
        self.coherence.add_web_resource(str(self.uuid)[5:], self.web_resource)

        version = int(self.version)
        while version > 0:
            self.web_resource.putChild(
                b'description-%r.xml' % version,
                RootDeviceXML(
                    self.coherence.hostname,
                    str(self.uuid),
                    self.coherence.urlbase,
                    self.device_type, version,
                    friendly_name=self.backend.name,
                    services=self._services,
                    devices=self._devices,
                    icons=self.icons,
                    presentation_url=self.presentationURL))
            self.web_resource.putChild(
                b'xbox-description-%r.xml' % version,
                RootDeviceXML(
                    self.coherence.hostname,
                    str(self.uuid),
                    self.coherence.urlbase,
                    self.device_type, version,
                    friendly_name=self.backend.name,
                    xbox_hack=True,
                    services=self._services,
                    devices=self._devices,
                    icons=self.icons,
                    presentation_url=self.presentationURL))
            version -= 1

        self.web_resource.putChild(b'ConnectionManager',
                                   self.connection_manager_server)
        self.web_resource.putChild(b'ContentDirectory',
                                   self.content_directory_server)
        if hasattr(self, "scheduled_recording_server"):
            self.web_resource.putChild(b'ScheduledRecording',
                                       self.scheduled_recording_server)
        if hasattr(self, "media_receiver_registrar_server"):
            self.web_resource.putChild(b'X_MS_MediaReceiverRegistrar',
                                       self.media_receiver_registrar_server)

        for icon in self.icons:
            if 'url' in icon:
                if icon['url'].startswith('file://'):
                    if os.path.exists(icon['url'][7:]):
                        self.web_resource.putChild(
                            os.path.basename(icon['url']).encode('ascii'),
                            StaticFile(icon['url'][7:],
                                       defaultType=icon['mimetype']))
                elif icon['url'] == '.face':
                    face_path = os.path.abspath(
                        os.path.join(os.path.expanduser('~'), ".face"))
                    if os.path.exists(face_path):
                        self.web_resource.putChild(
                            b'face-icon.png',
                            StaticFile(
                                face_path, defaultType=icon['mimetype']))
                else:
                    from pkg_resources import resource_filename
                    icon_path = os.path.abspath(
                        resource_filename(
                            __name__,
                            os.path.join('..', '..', '..', 'misc',
                                         'device-icons', icon['url'])))
                    if os.path.exists(icon_path):
                        self.web_resource.putChild(
                            icon['url'].encode('ascii'),
                            StaticFile(icon_path,
                                       defaultType=icon['mimetype']))

        self.register()
        self.warning("%s %s (%s) activated with id %s", self.device_type,
                     self.backend.name, self.backend, str(self.uuid)[5:])
