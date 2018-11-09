# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2008, Frank Scholz <coherence@beebits.net>

'''
Transcoder classes to be used in combination with a Coherence MediaServer,
using GStreamer pipelines for the actually work and feeding the output into
a http response.
'''

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
from gi.repository import GObject
Gst.init(None)

import os.path
import urllib.request
import urllib.parse
import urllib.error

from twisted.web import resource, server
from twisted.internet import protocol

from coherence import log

import struct


def get_transcoder_name(transcoder):
    return transcoder.name


class InternalTranscoder(object):
    '''Just a class to inherit from and which we can look
    for upon creating our list of available transcoders.'''


class FakeTransformer(Gst.Element, log.LogAble):
    logCategory = 'faker_datasink'

    _sinkpadtemplate = Gst.PadTemplate.new(
        'sinkpadtemplate',
        Gst.PadDirection.SINK,
        Gst.PadPresence.ALWAYS,
        Gst.Caps.new_any())

    _srcpadtemplate = Gst.PadTemplate.new(
        'srcpadtemplate',
        Gst.PadDirection.SRC,
        Gst.PadPresence.ALWAYS,
        Gst.Caps.new_any())

    def __init__(self, destination=None, request=None):
        Gst.Element.__init__(self)
        log.LogAble.__init__(self)
        self.sinkpad = Gst.Pad.new_from_template(
            self._sinkpadtemplate, 'sink')
        self.srcpad = Gst.Pad.new_from_template(
            self._srcpadtemplate, 'src')
        self.add_pad(self.sinkpad)
        self.add_pad(self.srcpad)

        self.sinkpad.set_chain_function_full(self.chainfunc)

        self.buffer = ''
        self.buffer_size = 0
        self.proxy = False
        self.got_new_segment = False
        self.closed = False

    def get_fake_header(self):
        return \
            struct.pack(
                '>L4s', 32, 'ftyp') + \
            b'mp42\x00\x00\x00\x00mp42mp41isomiso2'

    def chainfunc(self, pad, buffer):
        if self.proxy:
            # we are in proxy mode already
            self.srcpad.push(buffer)
            return Gst.FlowReturn.OK

        self.buffer = self.buffer + buffer.data
        if not self.buffer_size:
            try:
                self.buffer_size, a_type = \
                    struct.unpack('>L4s', self.buffer[:8])
            except Exception:
                return Gst.FlowReturn.OK

        if len(self.buffer) < self.buffer_size:
            # we need to buffer more
            return Gst.FlowReturn.OK

        buffer = self.buffer[self.buffer_size:]
        fake_header = self.get_fake_header()
        n_buf = Gst.Buffer(fake_header + buffer)
        self.proxy = True
        self.srcpad.push(n_buf)

        return Gst.FlowReturn.OK


GObject.type_register(FakeTransformer)


class DataSink(Gst.Element, log.LogAble):
    logCategory = 'transcoder_datasink'

    _sinkpadtemplate = Gst.PadTemplate.new(
        'sinkpadtemplate',
        Gst.PadDirection.SINK,
        Gst.PadPresence.ALWAYS,
        Gst.Caps.new_any())

    def __init__(self, destination=None, request=None):
        Gst.Element.__init__(self)
        log.LogAble.__init__(self)
        self.sinkpad = Gst.Pad.new_from_template(
            self._sinkpadtemplate, 'sink')
        self.add_pad(self.sinkpad)

        self.sinkpad.set_chain_function_full(self.chainfunc)
        self.sinkpad.set_event_function_full(self.eventfunc)
        self.destination = destination
        self.request = request

        if self.destination is not None:
            self.destination = open(self.destination, 'wb')
        self.buffer = ''
        self.data_size = 0
        self.got_new_segment = False
        self.closed = False

    def chainfunc(self, pad, inst, buffer):
        size = buffer.get_size()
        buf_data = buffer.extract_dup(0, size)
        if not isinstance(buf_data, bytes):
            buf = buffer.encode('ascii')
        if self.closed:
            return Gst.FlowReturn.OK
        if self.destination is not None:
            self.destination.write(buf_data)
        elif self.request is not None:
            self.buffer += buf_data
            if len(self.buffer) > 200000:
                self.request.write(self.buffer)
                self.buffer = b''
        else:
            self.buffer += buffer.data

        self.data_size += size
        return Gst.FlowReturn.OK

    def eventfunc(self, pad, inst, event):
        if event.type == Gst.Event.new_stream_start('').type:
            if not self.got_new_segment:
                self.got_new_segment = True
            else:
                self.closed = True
        elif event.type == Gst.Event.new_eos().type:
            if self.destination is not None:
                self.destination.close()
            elif self.request is not None:
                if len(self.buffer) > 0:
                    self.request.write(self.buffer)
                self.request.finish()
        return True


GObject.type_register(DataSink)


class GStreamerPipeline(resource.Resource, log.LogAble):
    logCategory = 'gstreamer'
    addSlash = True

    def __init__(self, pipeline, content_type):
        self.pipeline_description = pipeline
        self.contentType = content_type
        self.requests = []
        # if stream has a streamheader (something that has to be prepended
        # before any data), then it will be a tuple of GstBuffers
        self.streamheader = None
        self.parse_pipeline()
        resource.Resource.__init__(self)
        log.LogAble.__init__(self)

    def parse_pipeline(self):
        self.pipeline = Gst.parse_launch(self.pipeline_description)
        self.appsink = Gst.ElementFactory.make('appsink', 'sink')
        self.appsink.set_property('emit-signals', True)
        self.pipeline.add(self.appsink)
        enc = self.pipeline.get_by_name('enc')
        enc.link(self.appsink)
        self.appsink.connect('new-preroll', self.new_preroll)
        self.appsink.connect('new-buffer', self.new_buffer)
        self.appsink.connect('eos', self.eos)

    def start(self, request=None):
        self.info(
            f'GStreamerPipeline start {request} {self.pipeline_description}')
        self.requests.append(request)
        self.pipeline.set_state(Gst.State.PLAYING)

        d = request.notifyFinish()
        d.addBoth(self.requestFinished, request)

    def new_preroll(self, appsink):
        self.debug('new preroll')
        buffer = appsink.emit('pull-preroll')
        if not self.streamheader:
            # check caps for streamheader buffer
            caps = buffer.get_caps()
            s = caps[0]
            if 'streamheader' in s:
                self.streamheader = s['streamheader']
                self.debug('setting streamheader')
                for r in self.requests:
                    self.debug('writing streamheader')
                    for h in self.streamheader:
                        r.write(h.data)
        for r in self.requests:
            self.debug('writing preroll')
            r.write(buffer.data)

    def new_buffer(self, appsink):
        buffer = appsink.emit('pull-buffer')
        if not self.streamheader:
            # check caps for streamheader buffers
            caps = buffer.get_caps()
            s = caps[0]
            if 'streamheader' in s:
                self.streamheader = s['streamheader']
                self.debug('setting streamheader')
                for r in self.requests:
                    self.debug('writing streamheader')
                    for h in self.streamheader:
                        r.write(h.data)
        for r in self.requests:
            r.write(buffer.data)

    def eos(self, appsink):
        self.info('eos')
        for r in self.requests:
            r.finish()
        self.cleanup()

    def getChild(self, name, request):
        self.info(f'getChild {name}, {request}')
        return self

    def render_GET(self, request):
        self.info(f'render GET {request}')
        request.setResponseCode(200)
        if hasattr(self, 'contentType'):
            request.setHeader(b'Content-Type', self.contentType)
        request.write(b'')

        headers = request.getAllHeaders()
        if ('connection' in headers and
                headers['connection'] == 'close'):
            pass
        if self.requests:
            if self.streamheader:
                self.debug('writing streamheader')
                for h in self.streamheader:
                    request.write(h.data)
            self.requests.append(request)
        else:
            self.parse_pipeline()
            self.start(request)
        return server.NOT_DONE_YET

    def render_HEAD(self, request):
        self.info(f'render HEAD {request}')
        request.setResponseCode(200)
        request.setHeader(b'Content-Type', self.contentType)
        request.write(b'')

    def requestFinished(self, result, request):
        self.info(f'requestFinished {result}')
        # TODO: we need to find a way to destroy the pipeline here
        # from twisted.internet import reactor
        # reactor.callLater(0, self.pipeline.set_state, Gst.State.NULL)
        self.requests.remove(request)
        if not self.requests:
            self.cleanup()

    def on_message(self, bus, message):
        t = message.type
        print('on_message', t)
        if t == Gst.Message.ERROR:
            # err, debug = message.parse_error()
            # print(f'Error: {err}', debug)
            self.cleanup()
        elif t == Gst.Message.EOS:
            self.cleanup()

    def cleanup(self):
        self.info('pipeline cleanup')
        self.pipeline.set_state(Gst.State.NULL)
        self.requests = []
        self.streamheader = None


class BaseTranscoder(resource.Resource, log.LogAble):
    logCategory = 'transcoder'
    addSlash = True

    def __init__(self, uri, destination=None, content_type=None):
        if uri[:7] not in ['file://', 'http://']:
            uri = 'file://' + urllib.parse.quote(uri)  # FIXME
        self.uri = uri
        self.destination = destination
        self.contentType = None
        self.pipeline = None
        resource.Resource.__init__(self)
        log.LogAble.__init__(self)
        self.info(f'uri {uri} {type(uri)}')

    def getChild(self, name, request):
        self.info(f'getChild {name}, {request}')
        return self

    def render_GET(self, request):
        self.info(f'render GET {request}')
        request.setResponseCode(200)
        if self.contentType is not None:
            request.setHeader(b'Content-Type', self.contentType)
        request.write(b'')

        headers = request.getAllHeaders()
        if ('connection' in headers and
                headers['connection'] == 'close'):
            pass

        self.start(request)
        return server.NOT_DONE_YET

    def render_HEAD(self, request):
        self.info(f'render HEAD {request}')
        request.setResponseCode(200)
        request.setHeader(b'Content-Type', self.contentType)
        request.write(b'')

    def requestFinished(self, result):
        self.info(f'requestFinished {result}')
        ''' we need to find a way to destroy the pipeline here
        '''
        # from twisted.internet import reactor
        # reactor.callLater(0, self.pipeline.set_state, Gst.State.NULL)
        GObject.idle_add(self.cleanup)

    def on_message(self, bus, message):
        t = message.type
        print('on_message', t)
        if t == Gst.Message.ERROR:
            # err, debug = message.parse_error()
            # print(f'Error: {err}', debug)
            self.cleanup()
        elif t == Gst.Message.EOS:
            self.cleanup()

    def cleanup(self):
        self.pipeline.set_state(Gst.State.NULL)

    def start(self, request=None):
        '''This method should be sub classed for each
        class which inherits from BaseTranscoder'''
        pass


class PCMTranscoder(BaseTranscoder, InternalTranscoder):
    contentType = 'audio/L16;rate=44100;channels=2'
    name = 'lpcm'

    def start(self, request=None):
        self.info(f'PCMTranscoder start {request} {self.uri}')
        self.pipeline = Gst.parse_launch(
            f'{self.uri} ! decodebin ! audioconvert name=conv')

        conv = self.pipeline.get_by_name('conv')
        caps = Gst.Caps.from_string(
            'audio/x-raw-int,rate=44100,endianness=4321,'
            'channels=2,width=16,depth=16,signed=true')
        # FIXME: UGLY. 'filter' is a python builtin!
        filter = Gst.ElementFactory.make('capsfilter', 'filter')
        filter.set_property('caps', caps)
        self.pipeline.add(filter)
        conv.link(filter)

        sink = DataSink(destination=self.destination, request=request)
        self.pipeline.add(sink)
        filter.link(sink)
        self.pipeline.set_state(Gst.State.PLAYING)

        d = request.notifyFinish()
        d.addBoth(self.requestFinished)


class WAVTranscoder(BaseTranscoder, InternalTranscoder):
    contentType = 'audio/x-wav'
    name = 'wav'

    def start(self, request=None):
        self.info(f'start {request}')
        self.pipeline = Gst.parse_launch(
            f'{self.uri} ! decodebin ! audioconvert ! wavenc name=enc')
        enc = self.pipeline.get_by_name('enc')
        sink = DataSink(destination=self.destination, request=request)
        self.pipeline.add(sink)
        enc.link(sink)
        # bus = self.pipeline.get_bus()
        # bus.connect('message', self.on_message)
        self.pipeline.set_state(Gst.State.PLAYING)

        d = request.notifyFinish()
        d.addBoth(self.requestFinished)


class MP3Transcoder(BaseTranscoder, InternalTranscoder):
    contentType = 'audio/mpeg'
    name = 'mp3'

    def start(self, request=None):
        self.info(f'start {request}')
        self.pipeline = Gst.parse_launch(
            f'{self.uri} ! decodebin ! audioconvert ! lame name=enc')
        enc = self.pipeline.get_by_name('enc')
        sink = DataSink(destination=self.destination, request=request)
        self.pipeline.add(sink)
        enc.link(sink)
        self.pipeline.set_state(Gst.State.PLAYING)

        d = request.notifyFinish()
        d.addBoth(self.requestFinished)


class MP4Transcoder(BaseTranscoder, InternalTranscoder):
    ''' Only works if H264 inside Quicktime/MP4 container is input
        Source has to be a valid uri
    '''
    contentType = 'video/mp4'
    name = 'mp4'

    def start(self, request=None):
        self.info(f'start {request}')
        self.pipeline = Gst.parse_launch(
            f'{self.uri} ! qtdemux name=d ! queue ! h264parse '
            f'! mp4mux name=mux d. ! queue ! mux.')
        mux = self.pipeline.get_by_name('mux')
        sink = DataSink(destination=self.destination, request=request)
        self.pipeline.add(sink)
        mux.link(sink)
        self.pipeline.set_state(Gst.State.PLAYING)

        d = request.notifyFinish()
        d.addBoth(self.requestFinished)


class MP2TSTranscoder(BaseTranscoder, InternalTranscoder):
    contentType = 'video/mpeg'
    name = 'mpegts'

    def start(self, request=None):
        self.info(f'start {request}')
        # FIXME - mpeg2enc
        self.pipeline = Gst.parse_launch(
            f'mpegtsmux name=mux {self.uri} ! decodebin2 name=d ! queue '
            f'! ffmpegcolorspace ! mpeg2enc ! queue ! mux. d. '
            f'! queue ! audioconvert ! twolame ! queue ! mux.')
        enc = self.pipeline.get_by_name('mux')
        sink = DataSink(destination=self.destination, request=request)
        self.pipeline.add(sink)
        enc.link(sink)
        self.pipeline.set_state(Gst.State.PLAYING)

        d = request.notifyFinish()
        d.addBoth(self.requestFinished)


class ThumbTranscoder(BaseTranscoder, InternalTranscoder):
    '''
    Should create a valid thumbnail according to the DLNA spec

    .. warning:: Neither width nor height must exceed 160px
    '''
    contentType = 'image/jpeg'
    name = 'thumb'

    def start(self, request=None):
        self.info(f'start {request}')
        '''
        # what we actually want here is a pipeline that calls
        # us when it knows about the size of the original image,
        # and allows us now to adjust the caps-filter with the
        # calculated values for width and height
        new_width = 160
        new_height = 160
        if original_width > 160:
            new_heigth = \
                int(float(original_height) * (160.0/float(original_width)))
            if new_height > 160:
                new_width = \
                    int(float(new_width) * (160.0/float(new_height)))
        elif original_height > 160:
            new_width = \
                int(float(original_width) * (160.0/float(original_height)))
        '''
        try:
            type = request.args['type'][0]
        except IndexError:
            type = 'jpeg'
        if type == 'png':
            self.pipeline = Gst.parse_launch(
                f'{self.uri} ! decodebin2 ! videoscale '
                f'! video/x-raw-yuv,width=160,height=160 ! pngenc name=enc')
            self.contentType = 'image/png'
        else:
            self.pipeline = Gst.parse_launch(
                f'{self.uri} ! decodebin2 ! videoscale '
                f'! video/x-raw-yuv,width=160,height=160 ! jpegenc name=enc')
            self.contentType = 'image/jpeg'
        enc = self.pipeline.get_by_name('enc')
        sink = DataSink(destination=self.destination, request=request)
        self.pipeline.add(sink)
        enc.link(sink)
        self.pipeline.set_state(Gst.State.PLAYING)

        d = request.notifyFinish()
        d.addBoth(self.requestFinished)


class GStreamerTranscoder(BaseTranscoder):
    '''
    A generic Transcoder based on GStreamer.
    '''

    pipeline_description = None
    '''
    The pipeline which will be parsed upon calling the start method,
    has to be set as the attribute :attr:`pipeline_description` to
    the instantiated class.
    '''

    def start(self, request=None):
        if self.pipeline_description is None:
            raise NotImplementedError(
                'Warning: operation cancelled. You must set a value for '
                'GStreamerTranscoder.pipeline_description')
        self.info(f'start {request}')
        self.pipeline = Gst.parse_launch(self.pipeline_description % self.uri)
        enc = self.pipeline.get_by_name('mux')
        sink = DataSink(destination=self.destination, request=request)
        self.pipeline.add(sink)
        enc.link(sink)
        self.pipeline.set_state(Gst.State.PLAYING)

        d = request.notifyFinish()
        d.addBoth(self.requestFinished)


class ExternalProcessProtocol(protocol.ProcessProtocol):

    def __init__(self, caller):
        self.caller = caller

    def connectionMade(self):
        print('pp connection made')

    def outReceived(self, data):
        # print(f'outReceived with {len(data):d} bytes!')
        self.caller.write_data(data)

    def errReceived(self, data):
        # print(f'errReceived! with {len(data):d} bytes!')
        print('pp (err):', data.strip())

    def inConnectionLost(self):
        # print('inConnectionLost! stdin is closed! (we probably did it)')
        pass

    def outConnectionLost(self):
        # print('outConnectionLost! The child closed their stdout!')
        pass

    def errConnectionLost(self):
        # print('errConnectionLost! The child closed their stderr.')
        pass

    def processEnded(self, status_object):
        print(f'processEnded, status {status_object.value.exitCode:d}')
        print('processEnded quitting')
        self.caller.ended = True
        self.caller.write_data('')


class ExternalProcessProducer(object):
    logCategory = 'externalprocess'

    def __init__(self, pipeline, request):
        self.pipeline = pipeline
        self.request = request
        self.process = None
        self.written = 0
        self.data = ''
        self.ended = False
        request.registerProducer(self, 0)

    def write_data(self, data):
        if data:
            # print(f'write {len(data):d} bytes of data')
            self.written += len(data)
            # this .write will spin the reactor, calling .doWrite and then
            # .resumeProducing again, so be prepared for a re-entrant call
            self.request.write(data)
        if self.request and self.ended:
            print('closing')
            self.request.unregisterProducer()
            self.request.finish()
            self.request = None

    def resumeProducing(self):
        # print('resumeProducing', self.request)
        if not self.request:
            return
        if self.process is None:
            argv = self.pipeline.split()
            executable = argv[0]
            argv[0] = os.path.basename(argv[0])
            from twisted.internet import reactor
            self.process = reactor.spawnProcess(ExternalProcessProtocol(self),
                                                executable, argv, {})

    def pauseProducing(self):
        pass

    def stopProducing(self):
        print('stopProducing', self.request)
        self.request.unregisterProducer()
        self.process.loseConnection()
        self.request.finish()
        self.request = None


class ExternalProcessPipeline(resource.Resource, log.LogAble):
    logCategory = 'externalprocess'
    addSlash = False
    pipeline_description = None
    contentType = None

    def __init__(self, uri):
        self.uri = uri
        resource.Resource.__init__(self)
        log.LogAble.__init__(self)

    def getChildWithDefault(self, path, request):
        return self

    def render(self, request):
        print('ExternalProcessPipeline render')
        if self.pipeline_description is None:
            raise NotImplementedError(
                'Warning: operation cancelled. You must set a value for '
                'ExternalProcessPipeline.pipeline_description')
        if self.contentType is not None:
            request.setHeader(b'Content-Type', self.contentType)

        ExternalProcessProducer(self.pipeline_description % self.uri, request)
        return server.NOT_DONE_YET


def transcoder_class_wrapper(klass, content_type, pipeline):
    def create_object(uri):
        transcoder = klass(uri)
        transcoder.contentType = content_type
        transcoder.pipeline_description = pipeline
        return transcoder

    return create_object


class TranscoderManager(log.LogAble):
    '''
    Singleton class which holds information about all available transcoders.
    They are put into a transcoders dict with their id as the key.

    We collect all internal transcoders by searching for all subclasses of
    InternalTranscoder, the class will be the value.

    Transcoders defined in the config are parsed and stored as a dict in the
    transcoders dict.

    In the config, a transcoder description has to look like this:

    *** preliminary, will be extended and
    might even change without further notice ***

    .. code-block:: xml

        <transcoder>
            <pipeline>%s ...</pipeline> <!-- we need a %s here to insert the
                                            source uri (or can we have all the
                                            times pipelines we can prepend with
                                            a '%s !') and an element named mux
                                            where we can attach our sink -->
            <type>gstreamer</type>      <!-- could be gstreamer or process -->
            <name>mpegts</name>
            <target>video/mpeg</target>
            <fourth_field>              <!-- value for the 4th field of the
                                            protocolInfo phalanx, default is
                                            '*' -->
        </transcoder>

    '''

    logCategory = 'transcoder_manager'
    _instance_ = None  # Singleton

    def __new__(cls, *args, **kwargs):
        '''Creates the singleton.'''
        if cls._instance_ is None:
            obj = super(TranscoderManager, cls).__new__(cls)
            if 'coherence' in kwargs:
                obj.coherence = kwargs['coherence']
            cls._instance_ = obj
        return cls._instance_

    def __init__(self, coherence=None):
        '''
        Initializes the class :class:`TranscoderManager`.

        It should be called at least once with the main
        :class:`~coherence.base.Coherence` class passed as an argument,
        so we have access to the config.
        '''
        log.LogAble.__init__(self)
        self.transcoders = {}
        for transcoder in InternalTranscoder.__subclasses__():
            self.transcoders[get_transcoder_name(transcoder)] = transcoder

        if coherence is not None:
            self.coherence = coherence
            try:
                transcoders_from_config = self.coherence.config['transcoder']
                if isinstance(transcoders_from_config, dict):
                    transcoders_from_config = [transcoders_from_config]
            except KeyError:
                transcoders_from_config = []

            for transcoder in transcoders_from_config:
                # FIXME: is anyone checking if all keys are given ?
                pipeline = transcoder['pipeline']
                if '%s' not in pipeline:
                    self.warning('Can\'t create transcoder %r:'
                                 ' missing placehoder \'%%s\' in \'pipeline\'',
                                 transcoder)
                    continue

                try:
                    transcoder_name = transcoder['name']  # .decode('ascii')
                except UnicodeEncodeError:
                    self.warning('Can\'t create transcoder %r:'
                                 ' the \'name\' contains non-ascii letters',
                                 transcoder)
                    continue

                transcoder_type = transcoder['type'].lower()

                if transcoder_type == 'gstreamer':
                    wrapped = transcoder_class_wrapper(GStreamerTranscoder,
                                                       transcoder['target'],
                                                       transcoder['pipeline'])
                elif transcoder_type == 'process':
                    wrapped = transcoder_class_wrapper(ExternalProcessPipeline,
                                                       transcoder['target'],
                                                       transcoder['pipeline'])
                else:
                    self.warning(
                        f'unknown transcoder type {transcoder_type}')
                    continue

                self.transcoders[transcoder_name] = wrapped

        # FIXME reduce that to info later
        self.warning(f'available transcoders {self.transcoders}')

    def select(self, name, uri, backend=None):
        # FIXME:why do we specify the name when trying to get it?

        if backend is not None:
            ''' try to find a transcoder provided by the backend
                and return that here,
                if there isn't one continue with the ones
                provided by the config or the internal ones
            '''
            pass

        transcoder = self.transcoders[name](uri)
        return transcoder
