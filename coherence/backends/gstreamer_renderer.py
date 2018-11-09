# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2006-2009 Frank Scholz <coherence@beebits.net>
# Copyright 2018 Pol Canelles <canellestudi@gmail.com>

import os
import platform
import tokenize
from io import StringIO

from twisted.internet import gtk3reactor
gtk3reactor.install()

from twisted.internet import reactor, defer
from twisted.internet.task import LoopingCall
from twisted.python import failure

from coherence.upnp.core import DIDLLite
from coherence.upnp.core.soap_service import errorCode

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
Gst.init(None)

from coherence.backend import Backend

from coherence import log


class Player(log.LogAble):
    logCategory = 'gstreamer_player'
    max_playbin_volume = 1.

    def __init__(self, default_mimetype='audio/mpeg', audio_sink_name=None,
                 video_sink_name=None, audio_sink_options=None,
                 video_sink_options=None):
        log.LogAble.__init__(self)
        self.audio_sink_name = audio_sink_name or 'autoaudiosink'
        self.video_sink_name = video_sink_name or 'autovideosink'
        self.audio_sink_options = audio_sink_options or {}
        self.video_sink_options = video_sink_options or {}

        self.player = None
        self.source = None
        self.sink = None
        self.bus = None

        self.views = []
        self.tags = {}

        self.playing = False
        self.duration = None

        self.mimetype = default_mimetype
        self.create_pipeline(self.mimetype)

    def add_view(self, view):
        self.views.append(view)

    def remove_view(self, view):
        self.views.remove(view)

    def update(self, message=None):
        for v in self.views:
            v(message=message)

    def _is_not_playbin2_friendly(self):
        uname = platform.uname()[1]
        result = False
        if uname.startswith('Nokia'):
            try:
                device = uname.split('-')[1]
            except IndexError:
                device = 'unknown'
            result = device != 'N900'
        return result

    def create_pipeline(self, mimetype):
        self.debug('creating pipeline')
        if self._is_not_playbin2_friendly():
            self.bus = None
            self.player = None
            self.source = None
            self.sink = None

            if mimetype == 'application/ogg':
                self.player = Gst.parse_launch(
                    'gnomevfssrc name=source ! oggdemux ! ivorbisdec !'
                    ' audioconvert ! dsppcmsink name=sink')
                self.player.set_name('oggplayer')
                self.set_volume = self.set_volume_dsp_pcm_sink
                self.get_volume = self.get_volume_dsp_pcm_sink
            elif mimetype == 'application/flac':
                self.player = Gst.parse_launch(
                    'gnomevfssrc name=source ! flacdemux ! flacdec !'
                    ' audioconvert ! dsppcmsink name=sink')
                self.player.set_name('flacplayer')
                self.set_volume = self.set_volume_dsp_pcm_sink
                self.get_volume = self.get_volume_dsp_pcm_sink
            else:
                self.player = Gst.parse_launch(
                    'gnomevfssrc name=source ! id3lib ! dspmp3sink name=sink')
                self.player.set_name('mp3player')
                self.set_volume = self.set_volume_dsp_mp3_sink
                self.get_volume = self.get_volume_dsp_mp3_sink
            self.source = self.player.get_by_name('source')
            self.sink = self.player.get_by_name('sink')
            self.player_uri = 'location'
            self.mute = self.mute_hack
            self.unmute = self.unmute_hack
            self.get_mute = self.get_mute_hack
        else:
            self.player = Gst.ElementFactory.make('playbin', 'player')
            self.player_uri = 'uri'
            self.source = self.sink = self.player
            self.set_volume = self.set_volume_playbin
            self.get_volume = self.get_volume_playbin
            self.mute = self.mute_playbin
            self.unmute = self.unmute_playbin
            self.get_mute = self.get_mute_playbin
            audio_sink = Gst.ElementFactory.make(self.audio_sink_name)
            self._set_props(audio_sink, self.audio_sink_options)
            self.player.set_property('audio-sink', audio_sink)
            video_sink = Gst.ElementFactory.make(self.video_sink_name)
            self._set_props(video_sink, self.video_sink_options)
            self.player.set_property('video-sink', video_sink)

        self.bus = self.player.get_bus()
        self.player_clean = True
        self.bus.connect('message', self.on_message)
        self.bus.add_signal_watch()
        self.update_LC = LoopingCall(self.update)

    def _set_props(self, element, props):
        for option, value in props.items():
            value = self._py_value(value)
            element.set_property(option, value)

    def _py_value(self, s):
        value = None
        g = tokenize.generate_tokens(StringIO(s).readline)
        for toknum, tokval, _, _, _ in g:
            if toknum == tokenize.NUMBER:
                if '.' in tokval:
                    value = float(tokval)
                else:
                    value = int(tokval)
            elif toknum == tokenize.NAME:
                value = tokval

            if value is not None:
                break
        return value

    def get_volume_playbin(self):
        ''' playbin volume is a double from 0.0 - 10.0
        '''
        volume = self.sink.get_property('volume')
        return int((volume * 100) / self.max_playbin_volume)

    def set_volume_playbin(self, volume):
        volume = int(volume)
        if volume < 0:
            volume = 0
        if volume > 100:
            volume = 100
        volume = (volume * self.max_playbin_volume) / 100.
        self.sink.set_property('volume', volume)

    def get_volume_dsp_mp3_sink(self):
        ''' dspmp3sink volume is a n in from 0 to 65535
        '''
        volume = self.sink.get_property('volume')
        return int(volume * 100 / 65535)

    def set_volume_dsp_mp3_sink(self, volume):
        volume = int(volume)
        if volume < 0:
            volume = 0
        if volume > 100:
            volume = 100
        self.sink.set_property('volume', volume * 65535 / 100)

    def get_volume_dsp_pcm_sink(self):
        ''' dspmp3sink volume is a n in from 0 to 65535
        '''
        volume = self.sink.get_property('volume')
        return int(volume * 100 / 65535)

    def set_volume_dsp_pcm_sink(self, volume):
        volume = int(volume)
        if volume < 0:
            volume = 0
        if volume > 100:
            volume = 100
        self.sink.set_property('volume', volume * 65535 / 100)

    def mute_playbin(self):
        self.player.set_property('mute', True)

    def unmute_playbin(self):
        self.player.set_property('mute', False)

    def get_mute_playbin(self):
        return self.player.get_property('mute')

    def mute_hack(self):
        if hasattr(self, 'stored_volume'):
            self.stored_volume = self.sink.get_property('volume')
            self.sink.set_property('volume', 0)
        else:
            self.sink.set_property('mute', True)

    def unmute_hack(self):
        if hasattr(self, 'stored_volume'):
            self.sink.set_property('volume', self.stored_volume)
        else:
            self.sink.set_property('mute', False)

    def get_mute_hack(self):
        if hasattr(self, 'stored_volume'):
            muted = self.sink.get_property('volume') == 0
        else:
            try:
                muted = self.sink.get_property('mute')
            except TypeError:
                if not hasattr(self, 'stored_volume'):
                    self.stored_volume = self.sink.get_property('volume')
                muted = self.stored_volume == 0
            except Exception:
                muted = False
                self.warning('can\'t get mute state')
        return muted

    def get_state(self):
        return self.player.get_state(Gst.CLOCK_TIME_NONE)

    def get_uri(self):
        ''' playbin2 has an empty uri property after a
            pipeline stops, as the uri is nowdays the next
            track to play, not the current one
        '''
        if self.player.get_name() != 'player':
            return self.source.get_property(self.player_uri)
        else:
            try:
                return self.current_uri
            except Exception:
                return None

    def set_uri(self, uri):
        if not isinstance(uri, str):
            uri = uri.encode('utf-8')
        self.source.set_property(self.player_uri, uri)
        if self.player.get_name() == 'player':
            self.current_uri = uri

    def on_message(self, bus, message):
        # print('on_message', message, 'from', message.src.get_name())
        t = message.type
        struct = message.get_structure()
        if t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            self.warning(f'Gstreamer error: {err.message},{debug!r}')
            if self.playing:
                self.seek('-0')
            # self.player.set_state(Gst.State.READY)
        elif t == Gst.MessageType.TAG and \
                message.parse_tag() and struct.has_field('taglist'):
            taglist = struct.get_value('taglist')
            for x in range(taglist.n_tags()):
                key = taglist.nth_tag_name(x)
                val = taglist.get_string(key)[1]
                # print(f'  {key}: {val}')
                self.tags[key] = val
        elif t == Gst.MessageType.STATE_CHANGED:
            if message.src == self.player:
                old, new, pending = message.parse_state_changed()
                print(f'player ({message.src.get_path_string()}) '
                      f'state_change: {old} {new} {pending}')
                if new == Gst.State.PLAYING:
                    self.playing = True
                    self.update_LC.start(1, False)
                    self.update()
                elif old == Gst.State.PLAYING:
                    self.playing = False
                    try:
                        self.update_LC.stop()
                    except Exception:
                        pass
                    self.update()
                # elif new == Gst.State.READY:
                #    self.update()

        elif t == Gst.MessageType.EOS:
            self.debug('reached file end')
            self.seek('-0')
            self.update(message=Gst.MessageType.EOS)

    def query_position(self):
        try:
            position, format = self.player.query_position(Gst.Format.TIME)
        except Exception:
            # print('CLOCK_TIME_NONE', Gst.CLOCK_TIME_NONE)
            position = Gst.CLOCK_TIME_NONE
            position = 0

        if self.duration is None:
            try:
                self.duration, format = self.player.query_duration(
                    Gst.Format.TIME)
            except Exception:
                self.duration = Gst.CLOCK_TIME_NONE
                self.duration = 0
                # import traceback
                # print(traceback.print_exc())

        r = {}
        if self.duration == 0:
            self.duration = None
            self.debug('duration unknown')
            return r
        r['raw'] = {'position': str(position),
                    'remaining': str(self.duration - position),
                    'duration': str(self.duration)}

        position_human = '%d:%02d' % (divmod(position / Gst.SECOND, 60))
        duration_human = '%d:%02d' % (divmod(self.duration / Gst.SECOND, 60))
        remaining_human = '%d:%02d' % (
            divmod((self.duration - position) / Gst.SECOND, 60))

        r['human'] = {'position': position_human, 'remaining': remaining_human,
                      'duration': duration_human}
        r['percent'] = {'position': position * 100 / self.duration,
                        'remaining': 100 - (position * 100 / self.duration)}

        self.debug(r)
        return r

    def load(self, uri, mimetype):
        self.debug(f'load --> {uri} {mimetype}')
        _, state, _ = self.player.get_state(Gst.CLOCK_TIME_NONE)[1]
        if state == Gst.State.PLAYING or state == Gst.State.PAUSED:
            self.stop()

        if self.player.get_name() != 'player':
            self.create_pipeline(mimetype)

        self.player.set_state(Gst.State.READY)
        self.set_uri(uri)
        self.player_clean = True
        self.duration = None
        self.mimetype = mimetype
        self.tags = {}
        # self.player.set_state(Gst.State.PAUSED)
        # self.update()
        self.debug('load <--')
        self.play()

    def play(self):
        uri = self.get_uri()
        mimetype = self.mimetype
        self.debug(f'play --> {uri} {mimetype}')

        if self.player.get_name() != 'player':
            if not self.player_clean:
                # print('rebuild pipeline')
                self.player.set_state(Gst.State.NULL)

                self.create_pipeline(mimetype)

                self.set_uri(uri)
                self.player.set_state(Gst.State.READY)
        else:
            self.player_clean = True
        self.player.set_state(Gst.State.PLAYING)
        self.debug('play <--')

    def pause(self):
        self.debug(f'pause --> {self.get_uri()}')
        self.player.set_state(Gst.State.PAUSED)
        self.debug('pause <--')

    def stop(self):
        self.debug(f'stop --> {self.get_uri()}')
        self.seek('-0')
        self.player.set_state(Gst.State.READY)
        self.update(message=Gst.MessageType.EOS)
        self.debug(f'stop <-- {self.get_uri()}')

    def seek(self, location):
        '''
        @param location:    simple number = time to seek to, in seconds
                            +nL = relative seek forward n seconds
                            -nL = relative seek backwards n seconds
        '''

        _, state, _ = self.player.get_state(Gst.CLOCK_TIME_NONE)
        if state != Gst.State.PAUSED:
            self.player.set_state(Gst.State.PAUSED)
        loc = int(location) * Gst.SECOND
        position = self.player.query_position(Gst.Format.TIME)[1]
        duration = self.player.query_duration(Gst.Format.TIME)[1]

        if location[0] == '+':
            loc = position + (int(location[1:]) * Gst.SECOND)
            loc = min(loc, duration)
        elif location[0] == '-':
            if location == '-0':
                loc = 0
            else:
                loc = position - (int(location[1:]) * Gst.SECOND)
                loc = max(loc, 0)

        self.debug(f'seeking to {loc}')

        # Standard seek mode
        # self.player.seek( 1.0, Gst.Format.TIME,
        #     Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE,
        #     Gst.SeekType.SET, loc,
        #     Gst.SeekType.NONE, 0)
        # event_send = False

        # Simple seek mode
        # self.player.seek_simple(
        #     Gst.Format.TIME,
        #     Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, loc)
        # event_send = False

        # Event seek mode
        event = Gst.Event.new_seek(
            1.0, Gst.Format.TIME,
            Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
            Gst.SeekType.SET, loc,
            Gst.SeekType.NONE, 0)
        event_send = self.player.send_event(event)

        if event_send:
            print(f'seek to {location} ok')
            # self.player.set_start_time(0)
        elif location != '-0':
            print(f'seek to {location} failed')

        if location == '-0':
            content_type, _ = self.mimetype.split('/')
            try:
                self.update_LC.stop()
            except Exception:
                pass
            if self.player.get_name() != 'player':
                self.player.set_state(Gst.State.NULL)
                self.player_clean = False
            elif content_type != 'image':
                self.player.set_state(Gst.State.READY)
            self.update()
        else:
            self.player.set_state(state)
            if state == Gst.State.PAUSED:
                self.update()


class GStreamerPlayer(Backend):
    '''
    A backend with a GStreamer based audio player.

    needs gnomevfssrc from gst-plugins-base
    unfortunately gnomevfs has way too much dependencies

    # not working -> http://bugzilla.gnome.org/show_bug.cgi?id=384140
    # needs the neonhttpsrc plugin from gst-plugins-bad
    # tested with CVS version
    # and with this patch applied
    # --> http://bugzilla.gnome.org/show_bug.cgi?id=375264
    # not working

    and id3demux from gst-plugins-good CVS too

    .. versionchanged:: 0.9.0

        * Migrated from louie/dispatcher to EventDispatcher
        * Introduced :class:`~coherence.backend.Backend`'s inheritance
    '''

    logCategory = 'gstreamer_player'
    implements = ['MediaRenderer']
    vendor_value_defaults = {
        'RenderingControl': {'A_ARG_TYPE_Channel': 'Master'},
        'AVTransport': {
            'A_ARG_TYPE_SeekMode': ('ABS_TIME', 'REL_TIME', 'TRACK_NR')}}
    vendor_range_defaults = {'RenderingControl': {'Volume': {'maximum': 100}}}

    def __init__(self, server, **kwargs):
        Backend.__init__(self, server, **kwargs)
        if (server.coherence.config.get('use_dbus', 'no') != 'yes' and
                server.coherence.config.get('glib', 'no') != 'yes'):
            raise Exception(
                'this media renderer needs use_dbus '
                'enabled in the configuration')
        self.name = kwargs.get('name', 'GStreamer Audio Player')

        audio_sink_name = kwargs.get('audio_sink_name')
        audio_sink_options = kwargs.get('audio_sink_options')
        video_sink_name = kwargs.get('video_sink_name')
        video_sink_options = kwargs.get('video_sink_options')

        self.player = Player(audio_sink_name=audio_sink_name,
                             video_sink_name=video_sink_name,
                             audio_sink_options=audio_sink_options,
                             video_sink_options=video_sink_options)
        self.player.add_view(self.update)

        self.metadata = None
        self.duration = None

        self.view = []
        self.tags = {}

        self.playcontainer = None

        self.dlna_caps = ['playcontainer-0-1']

        self.init_completed = True

    def __repr__(self):
        return str(self.__class__).split('.')[-1]

    def update(self, message=None):
        _, current, _ = self.player.get_state()
        self.debug(f'update current {current}')
        connection_manager = self.server.connection_manager_server
        av_transport = self.server.av_transport_server
        conn_id = connection_manager.lookup_avt_id(self.current_connection_id)
        if current == Gst.State.PLAYING:
            state = 'playing'
            av_transport.set_variable(conn_id, 'TransportState', 'PLAYING')
        elif current == Gst.State.PAUSED:
            state = 'paused'
            av_transport.set_variable(conn_id, 'TransportState',
                                      'PAUSED_PLAYBACK')
        elif self.playcontainer is not None and \
                message == Gst.MessageType.EOS and \
                self.playcontainer[0] + 1 < len(self.playcontainer[2]):
            state = 'transitioning'
            av_transport.set_variable(conn_id, 'TransportState',
                                      'TRANSITIONING')

            next_track = ()
            item = self.playcontainer[2][self.playcontainer[0] + 1]
            infos = connection_manager.get_variable('SinkProtocolInfo')
            local_protocol_infos = infos.value.split(',')
            res = item.res.get_matching(local_protocol_infos,
                                        protocol_type='internal')
            if len(res) == 0:
                res = item.res.get_matching(local_protocol_infos)
            if len(res) > 0:
                res = res[0]
                infos = res.protocolInfo.split(':')
                remote_protocol, remote_network, \
                    remote_content_format, _ = infos
                didl = DIDLLite.DIDLElement()
                didl.addItem(item)
                next_track = (res.data, didl.toString(), remote_content_format)
                self.playcontainer[0] = self.playcontainer[0] + 1

            if len(next_track) == 3:
                av_transport.set_variable(conn_id, 'CurrentTrack',
                                          self.playcontainer[0] + 1)
                self.load(next_track[0], next_track[1], next_track[2])
                self.play()
            else:
                state = 'idle'
                av_transport.set_variable(
                    conn_id, 'TransportState', 'STOPPED')
        elif message == Gst.MessageType.EOS and \
                len(av_transport.get_variable(
                    'NextAVTransportURI').value) > 0:
            state = 'transitioning'
            av_transport.set_variable(
                conn_id, 'TransportState', 'TRANSITIONING')
            CurrentURI = av_transport.get_variable(
                'NextAVTransportURI').value
            metadata = av_transport.get_variable(
                'NextAVTransportURIMetaData')
            CurrentURIMetaData = metadata.value
            av_transport.set_variable(
                conn_id, 'NextAVTransportURI', '')
            av_transport.set_variable(
                conn_id, 'NextAVTransportURIMetaData', '')
            r = self.upnp_SetAVTransportURI(
                self, InstanceID=0, CurrentURI=CurrentURI,
                CurrentURIMetaData=CurrentURIMetaData)
            if r == {}:
                self.play()
            else:
                state = 'idle'
                av_transport.set_variable(
                    conn_id, 'TransportState', 'STOPPED')
        else:
            state = 'idle'
            av_transport.set_variable(
                conn_id, 'TransportState', 'STOPPED')

        self.info('update %r', state)
        self._update_transport_position(state)

    def _update_transport_position(self, state):
        connection_manager = self.server.connection_manager_server
        av_transport = self.server.av_transport_server
        conn_id = connection_manager.lookup_avt_id(self.current_connection_id)

        position = self.player.query_position()
        # print position

        for view in self.view:
            view.status(self.status(position))

        if 'raw' in position:

            if self.duration is None and 'duration' in position['raw']:
                self.duration = int(position['raw']['duration'])
                if self.metadata is not None and len(self.metadata) > 0:
                    # FIXME: duration breaks client parsing MetaData?
                    elt = DIDLLite.DIDLElement.fromString(self.metadata)
                    for item in elt.getItems():
                        for res in item.findall('res'):
                            formatted_duration = self._format_time(
                                self.duration)
                            res.attrib['duration'] = formatted_duration

                    self.metadata = elt.toString()
                    # print self.metadata
                    if self.server is not None:
                        av_transport.set_variable(conn_id,
                                                  'AVTransportURIMetaData',
                                                  self.metadata)
                        av_transport.set_variable(conn_id,
                                                  'CurrentTrackMetaData',
                                                  self.metadata)

            self.info(
                f'{state} {int(position["raw"]["position"]) / Gst.SECOND:d}/'
                f'{int(position["raw"]["remaining"]) / Gst.SECOND:d}/'
                f'{int(position["raw"]["duration"]) / Gst.SECOND:d} - '
                f'{position["percent"]["position"]:d}%%/'
                f'{position["percent"]["remaining"]:d}%% - '
                f'{position["human"]["position"]}/'
                f'{position["human"]["remaining"]}/'
                f'{position["human"]["duration"]}')

            duration = int(position['raw']['duration'])
            formatted = self._format_time(duration)
            av_transport.set_variable(conn_id, 'CurrentTrackDuration',
                                      formatted)
            av_transport.set_variable(conn_id, 'CurrentMediaDuration',
                                      formatted)

            position = int(position['raw']['position'])
            formatted = self._format_time(position)
            av_transport.set_variable(conn_id, 'RelativeTimePosition',
                                      formatted)
            av_transport.set_variable(conn_id, 'AbsoluteTimePosition',
                                      formatted)

    def _format_time(self, time):
        fmt = '%d:%02d:%02d'
        try:
            m, s = divmod(time / Gst.SECOND, 60)
            h, m = divmod(m, 60)
        except ValueError:
            h = m = s = 0
            fmt = '%02d:%02d:%02d'
        formatted = fmt % (h, m, s)
        return formatted

    def load(self, uri, metadata, mimetype=None):
        self.info(f'loading: {uri} {mimetype} ')
        _, state, _ = self.player.get_state()
        connection_id = self.server.connection_manager_server.lookup_avt_id(
            self.current_connection_id)
        # the check whether a stop is really needed is done inside stop
        self.stop(silent=True)

        if mimetype is None:
            _, ext = os.path.splitext(uri)
            if ext == '.ogg':
                mimetype = 'application/ogg'
            elif ext == '.flac':
                mimetype = 'application/flac'
            else:
                mimetype = 'audio/mpeg'
        self.player.load(uri, mimetype)

        self.metadata = metadata
        self.mimetype = mimetype
        self.tags = {}

        if self.playcontainer is None:
            self.server.av_transport_server.set_variable(
                connection_id, 'AVTransportURI', uri)
            self.server.av_transport_server.set_variable(
                connection_id, 'AVTransportURIMetaData', metadata)
            self.server.av_transport_server.set_variable(
                connection_id, 'NumberOfTracks', 1)
            self.server.av_transport_server.set_variable(
                connection_id, 'CurrentTrack', 1)
        else:
            self.server.av_transport_server.set_variable(
                connection_id, 'AVTransportURI', self.playcontainer[1])
            self.server.av_transport_server.set_variable(
                connection_id, 'NumberOfTracks', len(self.playcontainer[2]))
            self.server.av_transport_server.set_variable(
                connection_id, 'CurrentTrack', self.playcontainer[0] + 1)

        self.server.av_transport_server.set_variable(
            connection_id, 'CurrentTrackURI', uri)
        self.server.av_transport_server.set_variable(
            connection_id, 'CurrentTrackMetaData', metadata)

        # self.server.av_transport_server.set_variable(
        #     connection_id, 'TransportState', 'TRANSITIONING')
        # self.server.av_transport_server.set_variable(
        #     connection_id, 'CurrentTransportActions',
        #     'PLAY,STOP,PAUSE,SEEK,NEXT,PREVIOUS')
        if uri.startswith('http://'):
            transport_actions = set(['PLAY,STOP,PAUSE'])
        else:
            transport_actions = set(['PLAY,STOP,PAUSE,SEEK'])

        if len(self.server.av_transport_server.get_variable(
                'NextAVTransportURI').value) > 0:
            transport_actions.add('NEXT')

        if self.playcontainer is not None:
            if len(self.playcontainer[2]) - (self.playcontainer[0] + 1) > 0:
                transport_actions.add('NEXT')
            if self.playcontainer[0] > 0:
                transport_actions.add('PREVIOUS')

        self.server.av_transport_server.set_variable(
            connection_id, 'CurrentTransportActions', transport_actions)

        if state == Gst.State.PLAYING:
            self.info('was playing...')
            self.play()
        self.update()

    def status(self, position):
        uri = self.player.get_uri()
        if uri is None:
            return {'state': 'idle', 'uri': ''}
        else:
            r = {'uri': str(uri),
                 'position': position}
            if self.tags != {}:
                try:
                    r['artist'] = str(self.tags['artist'])
                except KeyError:
                    pass
                try:
                    r['title'] = str(self.tags['title'])
                except KeyError:
                    pass
                try:
                    r['album'] = str(self.tags['album'])
                except KeyError:
                    pass

            if self.player.get_state()[1] == Gst.State.PLAYING:
                r['state'] = 'playing'
            elif self.player.get_state()[1] == Gst.State.PAUSED:
                r['state'] = 'paused'
            else:
                r['state'] = 'idle'

            return r

    def start(self, uri):
        self.load(uri, None)
        self.play()

    def stop(self, silent=False):
        self.info(f'Stopping: {self.player.get_uri()}')
        if self.player.get_uri() is None:
            return
        if self.player.get_state()[1] in [Gst.State.PLAYING, Gst.State.PAUSED]:
            self.player.stop()
            if silent is True:
                self.server.av_transport_server.set_variable(
                    self.server.connection_manager_server.lookup_avt_id(
                        self.current_connection_id), 'TransportState',
                    'STOPPED')

    def play(self):
        self.info(f'Playing: {self.player.get_uri()}')
        if self.player.get_uri() is None:
            return
        self.player.play()
        self.server.av_transport_server.set_variable(
            self.server.connection_manager_server.lookup_avt_id(
                self.current_connection_id), 'TransportState', 'PLAYING')

    def pause(self):
        self.info(f'Pausing: {self.player.get_uri()}')
        self.player.pause()
        self.server.av_transport_server.set_variable(
            self.server.connection_manager_server.lookup_avt_id(
                self.current_connection_id), 'TransportState',
            'PAUSED_PLAYBACK')

    def seek(self, location, old_state):
        self.player.seek(location)
        if old_state is not None:
            self.server.av_transport_server.set_variable(
                0, 'TransportState', old_state)

    def mute(self):
        self.player.mute()
        rcs_id = self.server.connection_manager_server.lookup_rcs_id(
            self.current_connection_id)
        self.server.rendering_control_server.set_variable(
            rcs_id, 'Mute', 'True')

    def unmute(self):
        self.player.unmute()
        rcs_id = self.server.connection_manager_server.lookup_rcs_id(
            self.current_connection_id)
        self.server.rendering_control_server.set_variable(
            rcs_id, 'Mute', 'False')

    def get_mute(self):
        return self.player.get_mute()

    def get_volume(self):
        return self.player.get_volume()

    def set_volume(self, volume):
        self.player.set_volume(volume)
        rcs_id = self.server.connection_manager_server.lookup_rcs_id(
            self.current_connection_id)
        self.server.rendering_control_server.set_variable(
            rcs_id, 'Volume', volume)

    def playcontainer_browse(self, uri):
        '''
        dlna-playcontainer://uuid%3Afe814e3e-5214-4c24-847b-383fb599ff01?
        sid=urn%3Aupnp-org%3AserviceId%3AContentDirectory&
        cid=1441&fid=1444&fii=0&sc=&md=0
        '''
        from urllib.parse import unquote
        from cgi import parse_qs

        def handle_reply(r, uri, action, kw):
            try:
                next_track = ()
                elt = DIDLLite.DIDLElement.fromString(r['Result'])
                item = elt.getItems()[0]
                local_protocol_infos = \
                    self.server.connection_manager_server.get_variable(
                        'SinkProtocolInfo').value.split(',')
                res = item.res.get_matching(local_protocol_infos,
                                            protocol_type='internal')
                if len(res) == 0:
                    res = item.res.get_matching(local_protocol_infos)
                if len(res) > 0:
                    res = res[0]
                    remote_protocol, remote_network, \
                        remote_content_format, _ = res.protocolInfo.split(':')
                    didl = DIDLLite.DIDLElement()
                    didl.addItem(item)
                    next_track = \
                        (res.data, didl.toString(), remote_content_format)
                ''' a list with these elements:

                    the current track index
                     - will change during playback of the container items
                    the initial complete playcontainer-uri
                    a list of all the items in the playcontainer
                    the action methods to do the Browse call on the device
                    the kwargs for the Browse call
                     - kwargs['StartingIndex'] will be modified
                        during further Browse requests
                '''
                self.playcontainer = [int(kw['StartingIndex']), uri,
                                      elt.getItems()[:], action, kw]

                def browse_more(
                        starting_index, number_returned, total_matches):
                    self.info(f'browse_more {starting_index} '
                              f'{number_returned} {total_matches}')
                    try:

                        def handle_error(r):
                            pass

                        def handle_reply(r, starting_index):
                            elt = DIDLLite.DIDLElement.fromString(r['Result'])
                            self.playcontainer[2] += elt.getItems()[:]
                            browse_more(starting_index,
                                        int(r['NumberReturned']),
                                        int(r['TotalMatches']))

                        if ((number_returned != 5 or
                             number_returned <
                             (total_matches - starting_index)) and
                                (total_matches - number_returned) !=
                                starting_index):
                            self.info(
                                'seems we have been returned only '
                                'a part of the result')
                            self.info(f'requested {5:d}, '
                                      f'starting at {starting_index:d}')
                            self.info(f'got {number_returned:d} '
                                      f'out of {total_matches:d}')
                            self.info(f'requesting more starting now at '
                                      f'{starting_index + number_returned:d}')
                            self.playcontainer[4]['StartingIndex'] = str(
                                starting_index + number_returned)
                            d = self.playcontainer[3].call(
                                **self.playcontainer[4])
                            d.addCallback(handle_reply,
                                          starting_index + number_returned)
                            d.addErrback(handle_error)
                    except Exception as e1:
                        self.error(f'playcontainer_browse.'
                                   f'handle_reply.browse_more: {e1!r}')
                        import traceback
                        traceback.print_exc()

                browse_more(int(kw['StartingIndex']), int(r['NumberReturned']),
                            int(r['TotalMatches']))

                if len(next_track) == 3:
                    return next_track
            except Exception as e2:
                self.error(f'playcontainer_browse.handle_reply: {e2!r}')
                import traceback
                traceback.print_exc()

            return failure.Failure(errorCode(714))

        def handle_error(r):
            return failure.Failure(errorCode(714))

        try:
            udn, args = uri[21:].split('?')
            udn = unquote(udn)
            args = parse_qs(args)

            type = args['sid'][0].split(':')[-1]

            try:
                sc = args['sc'][0]
            except Exception:
                sc = ''

            device = self.server.coherence.get_device_with_id(udn)
            service = device.get_service_by_type(type)
            action = service.get_action('Browse')

            kw = {'ObjectID': args['cid'][0],
                  'BrowseFlag': 'BrowseDirectChildren',
                  'StartingIndex': args['fii'][0],
                  'RequestedCount': str(5),
                  'Filter': '*',
                  'SortCriteria': sc}

            d = action.call(**kw)
            d.addCallback(handle_reply, uri, action, kw)
            d.addErrback(handle_error)
            return d
        except Exception as e3:
            self.error(f'playcontainer_browse: {e3!r}')
            return failure.Failure(errorCode(714))

    def upnp_init(self):
        self.current_connection_id = None
        self.server.connection_manager_server.set_variable(
            0,
            'SinkProtocolInfo',
            [f'internal:{self.server.coherence.hostname}:audio/mpeg:*',
             'http-get:*:audio/mpeg:*',
             f'internal:{self.server.coherence.hostname}:audio/mp4:*',
             'http-get:*:audio/mp4:*',
             f'internal:{self.server.coherence.hostname}:application/ogg:*',
             'http-get:*:application/ogg:*',
             f'internal:{self.server.coherence.hostname}:audio/ogg:*',
             'http-get:*:audio/ogg:*',
             f'internal:{self.server.coherence.hostname}:video/ogg:*',
             'http-get:*:video/ogg:*',
             f'internal:{self.server.coherence.hostname}:application/flac:*',
             'http-get:*:application/flac:*',
             f'internal:{self.server.coherence.hostname}:audio/flac:*',
             'http-get:*:audio/flac:*',
             f'internal:{self.server.coherence.hostname}:video/x-msvideo:*',
             'http-get:*:video/x-msvideo:*',
             f'internal:{self.server.coherence.hostname}:video/mp4:*',
             'http-get:*:video/mp4:*',
             f'internal:{self.server.coherence.hostname}:video/quicktime:*',
             'http-get:*:video/quicktime:*',
             f'internal:{self.server.coherence.hostname}:image/gif:*',
             'http-get:*:image/gif:*',
             f'internal:{self.server.coherence.hostname}:image/jpeg:*',
             'http-get:*:image/jpeg:*',
             f'internal:{self.server.coherence.hostname}:image/png:*',
             'http-get:*:image/png:*',
             'http-get:*:*:*'],
            default=True)
        self.server.av_transport_server.set_variable(
            0, 'TransportState', 'NO_MEDIA_PRESENT', default=True)
        self.server.av_transport_server.set_variable(
            0, 'TransportStatus', 'OK', default=True)
        self.server.av_transport_server.set_variable(
            0, 'CurrentPlayMode', 'NORMAL', default=True)
        self.server.av_transport_server.set_variable(
            0, 'CurrentTransportActions', '', default=True)
        self.server.rendering_control_server.set_variable(
            0, 'Volume', self.get_volume())
        self.server.rendering_control_server.set_variable(
            0, 'Mute', self.get_mute())

    def upnp_Play(self, *args, **kwargs):
        InstanceID = int(kwargs['InstanceID'])
        Speed = int(kwargs['Speed'])
        self.play()
        return {}

    def upnp_Pause(self, *args, **kwargs):
        InstanceID = int(kwargs['InstanceID'])
        self.pause()
        return {}

    def upnp_Stop(self, *args, **kwargs):
        InstanceID = int(kwargs['InstanceID'])
        self.stop()
        return {}

    def upnp_Seek(self, *args, **kwargs):
        InstanceID = int(kwargs['InstanceID'])
        Unit = kwargs['Unit']
        Target = kwargs['Target']
        if InstanceID != 0:
            return failure.Failure(errorCode(718))
        if Unit in ['ABS_TIME', 'REL_TIME']:
            old_state = self.server.av_transport_server.get_variable(
                'TransportState').value
            self.server.av_transport_server.set_variable(
                InstanceID, 'TransportState', 'TRANSITIONING')

            sign = ''
            if Target[0] == '+':
                Target = Target[1:]
                sign = '+'
            if Target[0] == '-':
                Target = Target[1:]
                sign = '-'

            h, m, s = Target.split(':')
            seconds = int(h) * 3600 + int(m) * 60 + int(s)
            self.seek(sign + str(seconds), old_state)
        if Unit in ['TRACK_NR']:
            if self.playcontainer is None:
                NextURI = self.server.av_transport_server.get_variable(
                    'NextAVTransportURI', InstanceID).value
                if NextURI != '':
                    self.server.av_transport_server.set_variable(
                        InstanceID, 'TransportState', 'TRANSITIONING')
                    NextURIMetaData = \
                        self.server.av_transport_server.get_variable(
                            'NextAVTransportURIMetaData').value
                    self.server.av_transport_server.set_variable(
                        InstanceID, 'NextAVTransportURI', '')
                    self.server.av_transport_server.set_variable(
                        InstanceID, 'NextAVTransportURIMetaData', '')
                    r = self.upnp_SetAVTransportURI(
                        self, InstanceID=InstanceID,
                        CurrentURI=NextURI,
                        CurrentURIMetaData=NextURIMetaData)
                    return r
            else:
                Target = int(Target)
                if 0 < Target <= len(self.playcontainer[2]):
                    self.server.av_transport_server.set_variable(
                        InstanceID, 'TransportState', 'TRANSITIONING')
                    next_track = ()
                    item = self.playcontainer[2][Target - 1]
                    local_protocol_infos = \
                        self.server.connection_manager_server.get_variable(
                            'SinkProtocolInfo').value.split(',')
                    res = item.res.get_matching(local_protocol_infos,
                                                protocol_type='internal')
                    if len(res) == 0:
                        res = item.res.get_matching(local_protocol_infos)
                    if len(res) > 0:
                        res = res[0]
                        remote_protocol, remote_network, \
                            remote_content_format, _ = \
                            res.protocolInfo.split(':')
                        didl = DIDLLite.DIDLElement()
                        didl.addItem(item)
                        next_track = \
                            (res.data, didl.toString(), remote_content_format)
                        self.playcontainer[0] = Target - 1

                    if len(next_track) == 3:
                        cm = self.server.connection_manager_server
                        self.server.av_transport_server.set_variable(
                            cm.lookup_avt_id(self.current_connection_id),
                            'CurrentTrack',
                            Target)
                        self.load(next_track[0], next_track[1], next_track[2])
                        self.play()
                        return {}
            return failure.Failure(errorCode(711))

        return {}

    def upnp_Next(self, *args, **kwargs):
        InstanceID = int(kwargs['InstanceID'])
        track_nr = self.server.av_transport_server.get_variable('CurrentTrack')
        return self.upnp_Seek(self, InstanceID=InstanceID, Unit='TRACK_NR',
                              Target=str(int(track_nr.value) + 1))

    def upnp_Previous(self, *args, **kwargs):
        InstanceID = int(kwargs['InstanceID'])
        track_nr = self.server.av_transport_server.get_variable('CurrentTrack')
        return self.upnp_Seek(self, InstanceID=InstanceID, Unit='TRACK_NR',
                              Target=str(int(track_nr.value) - 1))

    def upnp_setNextAVTransportURI(self, *args, **kwargs):
        InstanceID = int(kwargs['InstanceID'])
        NextURI = kwargs['NextURI']
        current_connection_id = \
            self.server.connection_manager_server.lookup_avt_id(
                self.current_connection_id)
        NextMetaData = kwargs['NextURIMetaData']
        self.server.av_transport_server.set_variable(
            current_connection_id, 'NextAVTransportURI', NextURI)
        self.server.av_transport_server.set_variable(
            current_connection_id, 'NextAVTransportURIMetaData', NextMetaData)
        if len(NextURI) == 0 and self.playcontainer is None:
            transport_actions = self.server.av_transport_server.get_variable(
                'CurrentTransportActions').value
            transport_actions = set(transport_actions.split(','))
            try:
                transport_actions.remove('NEXT')
                self.server.av_transport_server.set_variable(
                    current_connection_id, 'CurrentTransportActions',
                    transport_actions)
            except KeyError:
                pass
            return {}
        transport_actions = self.server.av_transport_server.get_variable(
            'CurrentTransportActions').value
        transport_actions = set(transport_actions.split(','))
        transport_actions.add('NEXT')
        self.server.av_transport_server.set_variable(
            current_connection_id, 'CurrentTransportActions',
            transport_actions)
        return {}

    def upnp_SetAVTransportURI(self, *args, **kwargs):
        InstanceID = int(kwargs['InstanceID'])
        CurrentURI = kwargs['CurrentURI']
        CurrentURIMetaData = kwargs['CurrentURIMetaData']
        # print('upnp_SetAVTransportURI', InstanceID,
        #       CurrentURI, CurrentURIMetaData)
        if CurrentURI.startswith('dlna-playcontainer://'):
            def handle_result(r):
                self.load(r[0], r[1], mimetype=r[2])
                return {}

            def pass_error(r):
                return r

            d = defer.maybeDeferred(self.playcontainer_browse, CurrentURI)
            d.addCallback(handle_result)
            d.addErrback(pass_error)
            return d
        elif len(CurrentURIMetaData) == 0:
            self.playcontainer = None
            self.load(CurrentURI, CurrentURIMetaData)
            return {}
        else:
            local_protocol_infos = \
                self.server.connection_manager_server.get_variable(
                    'SinkProtocolInfo').value.split(',')
            # print local_protocol_infos
            elt = DIDLLite.DIDLElement.fromString(CurrentURIMetaData)
            if elt.numItems() == 1:
                item = elt.getItems()[0]
                res = item.res.get_matching(local_protocol_infos,
                                            protocol_type='internal')
                if len(res) == 0:
                    res = item.res.get_matching(local_protocol_infos)
                if len(res) > 0:
                    res = res[0]
                    remote_protocol, remote_network, \
                        remote_content_format, _ = \
                        res.protocolInfo.split(':')
                    self.playcontainer = None
                    self.load(res.data, CurrentURIMetaData,
                              mimetype=remote_content_format)
                    return {}
        return failure.Failure(errorCode(714))

    def upnp_SetMute(self, *args, **kwargs):
        InstanceID = int(kwargs['InstanceID'])
        Channel = kwargs['Channel']
        DesiredMute = kwargs['DesiredMute']
        if DesiredMute in ['TRUE', 'True', 'true', '1', 'Yes', 'yes']:
            self.mute()
        else:
            self.unmute()
        return {}

    def upnp_SetVolume(self, *args, **kwargs):
        InstanceID = int(kwargs['InstanceID'])
        Channel = kwargs['Channel']
        DesiredVolume = int(kwargs['DesiredVolume'])
        self.set_volume(DesiredVolume)
        return {}


if __name__ == '__main__':
    import sys

    # FIXME: this tests should be adapted and moved into the tests folder
    # Test audio
    # uri = 'https://sampleswap.org/samples-ghost/INSTRUMENTS%20multisampled' \
    #       '/GUITAR/acoustic%20guitar%20harmonics/1192[kb]E7fret.aif.mp3'
    # p = Player()

    # Test Video
    # uri = 'file:///home/user/videos/sample.mp4'  # example for local files
    uri = 'https://www.sample-videos.com/video/' \
          'mp4/720/big_buck_bunny_720p_1mb.mp4'
    p = Player(default_mimetype='video/x-h264',
               # video_sink_name='ximagesink'
               )

    def check_bus_state(bus, message):
        '''Example function to check the player bus state and act accordingly
        '''
        t = message.type
        if t == Gst.MessageType.EOS:
            print('Reached end of file: Ending reactor/GLib.MainLoop...')
            # For twisted.internet.reactor
            if reactor.running:
                reactor.stop()

            # For GLib.MainLoop()
            # loop.quit()
        elif t == Gst.MessageType.ERROR:
            print('Some error happened: Ending reactor/GLib.MainLoop...')
            # For twisted.internet.reactor
            if reactor.running:
                reactor.stop()

            # For GLib.MainLoop()
            # loop.quit()

    def main(play_uri):
        # Connect the player to a custom function,
        # to check the current player state
        p.bus.connect('message', check_bus_state)

        # Set url to play and start it
        p.set_uri(play_uri)
        p.play()

        # Seek example: The line below will jump to second 5
        # p.seek('+5')

    # Use twisted.internet.reactor (for the main loop)
    if len(sys.argv) > 1:
        reactor.callWhenRunning(main, sys.argv[1])
    else:
        reactor.callWhenRunning(main, uri)
    reactor.run()

    # Use GLib.MainLoop (for the main loop)
    # from gi.repository import GLib
    # loop = GLib.MainLoop()
    # if len(sys.argv) > 1:
    #     main(sys.argv[1])
    # else:
    #     main(uri)
    # loop.run()

    print('Ended reactor/GLib.MainLoop OK')
