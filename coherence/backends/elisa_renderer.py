# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2006, Frank Scholz <coherence@beebits.net>

from twisted.internet.defer import Deferred
from twisted.internet.task import LoopingCall
from twisted.python import failure
from twisted.spread import pb

from coherence.backend import Backend
from coherence.upnp.core import DIDLLite
from coherence.upnp.core.soap_service import errorCode


class ElisaPlayer(Backend):
    '''a backend to the Elisa player

    .. versionchanged:: 0.9.0

        * Migrated from louie/dispatcher to EventDispatcher
        * Introduced :class:`~coherence.backend.Backend`'s inheritance
    '''
    logCategory = 'elisa_player'

    implements = ['MediaRenderer']
    vendor_value_defaults = {
        'RenderingControl': {'A_ARG_TYPE_Channel': 'Master'}}
    vendor_range_defaults = {'RenderingControl': {'Volume': {'maximum': 100}}}

    def __init__(self, server, **kwargs):
        Backend.__init__(self, server, **kwargs)
        self.name = kwargs.get('name', 'Elisa MediaRenderer')
        self.host = kwargs.get('host', '127.0.0.1')
        self.player = None
        self.metadata = None

        if self.host == 'internal':
            try:
                from elisa.core import common
                self.player = common.get_application().get_player()
                self.init_completed = True
            except ImportError:
                self.warning('this works only from within Elisa')
                raise ImportError
        else:
            factory = pb.PBClientFactory()
            factory.noisy = False
            reactor.connectTCP(self.host, 8789, factory)
            d = factory.getRootObject()

            def result(player):
                self.player = player
                self.init_completed = True

            def got_error(error):
                self.warning('connection to Elisa failed!')
                self.on_init_failed(msg=error)

            d.addCallback(lambda object: object.callRemote('get_player'))
            d.addCallback(result)
            d.addErrback(got_error)

        self.playing = False
        self.state = None
        self.duration = None
        self.view = []
        self.tags = {}
        self.poll_LC = LoopingCall(self.poll_player)

    def call_player(self, method, callback, *args):
        self.debug(f'call player.{method}{args}')
        if self.host == 'internal':
            dfr = Deferred()
            dfr.addCallback(callback)
            result = getattr(self.player, method)(*args)
            dfr.callback(result)
        else:
            dfr = self.player.callRemote(method, *args)
            dfr.addCallback(callback)
        return dfr

    def __repr__(self):
        return str(self.__class__).split('.')[-1]

    def poll_player(self):

        def got_result(result):
            self.info(f'poll_player {result}')
            if self.server is not None:
                connection_id = \
                    self.server.connection_manager_server.lookup_avt_id(
                        self.current_connection_id)
            if result in ('STOPPED', 'READY'):
                transport_state = 'STOPPED'
            if result == 'PLAYING':
                transport_state = 'PLAYING'
            if result == 'PAUSED':
                transport_state = 'PAUSED_PLAYBACK'

            if transport_state == 'PLAYING':
                self.query_position()

            if self.state != transport_state:
                self.state = transport_state
                if self.server is not None:
                    self.server.av_transport_server.set_variable(
                        connection_id, 'TransportState', transport_state)

        self.call_player('get_readable_state', got_result)

    def query_position(self):
        def got_result(result):
            self.info(f'query_position {result}')
            position, duration = result
            if self.server is not None:
                connection_id = \
                    self.server.connection_manager_server.lookup_avt_id(
                        self.current_connection_id)
                self.server.av_transport_server.set_variable(
                    connection_id, 'CurrentTrack', 0)

            if position is not None:
                m, s = divmod(position / 1000000000, 60)
                h, m = divmod(m, 60)
                if self.server is not None:
                    self.server.av_transport_server.set_variable(
                        connection_id, 'RelativeTimePosition',
                        f'{h:02d}:{m:02d}:{s:02d}')
                    self.server.av_transport_server.set_variable(
                        connection_id, 'AbsoluteTimePosition',
                        f'{h:02d}:{m:02d}:{s:02d}')

            if duration is not None:
                m, s = divmod(duration / 1000000000, 60)
                h, m = divmod(m, 60)

                if self.server is not None:
                    self.server.av_transport_server.set_variable(
                        connection_id, 'CurrentTrackDuration',
                        f'{h:02d}:{m:02d}:{s:02d}')
                    self.server.av_transport_server.set_variable(
                        connection_id, 'CurrentMediaDuration',
                        f'{h:02d}:{m:02d}:{s:02d}')

                if self.duration is None:
                    if self.metadata is not None:
                        elt = DIDLLite.DIDLElement.fromString(self.metadata)
                        for item in elt.getItems():
                            for res in item.findall('res'):
                                res.attrib['duration'] = \
                                    f'{h:d}:{m:02d}:{s:02d}'
                        self.metadata = elt.toString()

                        if self.server is not None:
                            self.server.av_transport_server.set_variable(
                                connection_id, 'AVTransportURIMetaData',
                                self.metadata)
                            self.server.av_transport_server.set_variable(
                                connection_id, 'CurrentTrackMetaData',
                                self.metadata)

                    self.duration = duration

        self.call_player('get_status', got_result)

    def load(self, uri, metadata):

        def got_result(result):
            self.duration = None
            self.metadata = metadata
            self.tags = {}
            connection_id = \
                self.server.connection_manager_server.lookup_avt_id(
                    self.current_connection_id)
            self.server.av_transport_server.set_variable(
                connection_id, 'CurrentTransportActions', 'Play,Stop,Pause')
            self.server.av_transport_server.set_variable(
                connection_id, 'NumberOfTracks', 1)
            self.server.av_transport_server.set_variable(
                connection_id, 'CurrentTrackURI', uri)
            self.server.av_transport_server.set_variable(
                connection_id, 'AVTransportURI', uri)
            self.server.av_transport_server.set_variable(
                connection_id, 'AVTransportURIMetaData', metadata)
            self.server.av_transport_server.set_variable(
                connection_id, 'CurrentTrackURI', uri)
            self.server.av_transport_server.set_variable(
                connection_id, 'CurrentTrackMetaData', metadata)

        self.call_player('set_uri', got_result, uri)

    def start(self, uri, metadata=None):
        self.load(uri, metadata)
        self.play()

    def stop(self):
        def got_result(result):
            self.server.av_transport_server.set_variable(
                self.server.connection_manager_server.lookup_avt_id(
                    self.current_connection_id),
                'TransportState', 'STOPPED')

        self.call_player('stop', got_result)

    def play(self):
        def got_result(result):
            self.server.av_transport_server.set_variable(
                self.server.connection_manager_server.lookup_avt_id(
                    self.current_connection_id),
                'TransportState', 'PLAYING')

        self.call_player('play', got_result)

    def pause(self):
        def got_result(result):
            self.server.av_transport_server.set_variable(
                self.server.connection_manager_server.lookup_avt_id(
                    self.current_connection_id),
                'TransportState', 'PAUSED_PLAYBACK')

        self.call_player('pause', got_result)

    def seek(self, location):
        '''
        @param location:    simple number = time to seek to, in seconds
                            +nL = relative seek forward n seconds
                            -nL = relative seek backwards n seconds
        '''

    def mute(self):
        def got_result(result):
            rcs_id = self.server.connection_manager_server.lookup_rcs_id(
                self.current_connection_id)
            # FIXME: use result, not True
            self.server.rendering_control_server.set_variable(
                rcs_id, 'Mute', 'True')

        self.call_player('mute', got_result)

    def unmute(self):
        def got_result(result):
            rcs_id = self.server.connection_manager_server.lookup_rcs_id(
                self.current_connection_id)
            # FIXME: use result, not False
            self.server.rendering_control_server.set_variable(
                rcs_id, 'Mute', 'False')

        self.call_player('un_mute', got_result)

    def get_mute(self):
        def got_infos(result):
            self.info(f'got_mute: {result}')
            return result

        return self.call_player('get_mute', got_infos)

    def get_volume(self):
        ''' playbin volume is a double from 0.0 - 10.0
        '''

        def got_infos(result):
            self.info(f'got_volume: {result}')
            return result

        return self.call_player('get_volume', got_infos)

    def set_volume(self, volume):
        volume = int(volume)
        if volume < 0:
            volume = 0
        if volume > 100:
            volume = 100

        def got_result(result):
            rcs_id = self.server.connection_manager_server.lookup_rcs_id(
                self.current_connection_id)
            # FIXME: use result, not volume
            self.server.rendering_control_server.set_variable(rcs_id, 'Volume',
                                                              volume)

        self.call_player('set_volume', got_result, volume)

    def upnp_init(self):
        self.current_connection_id = None
        self.server.connection_manager_server.set_variable(
            0, 'SinkProtocolInfo',
            [f'internal:{self.host}:*:*', 'http-get:*:audio/mpeg:*'],
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
        self.poll_LC.start(1.0, True)

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

    def upnp_SetAVTransportURI(self, *args, **kwargs):
        InstanceID = int(kwargs['InstanceID'])
        CurrentURI = kwargs['CurrentURI']
        CurrentURIMetaData = kwargs['CurrentURIMetaData']
        local_protocol_infos = \
            self.server.connection_manager_server.get_variable(
                'SinkProtocolInfo').value.split(',')
        # print '>>>', local_protocol_infos
        if len(CurrentURIMetaData) == 0:
            self.load(CurrentURI, CurrentURIMetaData)
        else:
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
                        remote_content_format, _ = res.protocolInfo.split(
                            ':')
                    self.load(res.data, CurrentURIMetaData)
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


def main():
    f = ElisaPlayer(None)

    def call_player():
        f.get_volume()
        f.get_mute()
        f.poll_player()

    reactor.callLater(2, call_player)


if __name__ == '__main__':
    from twisted.internet import reactor

    reactor.callWhenRunning(main)
    reactor.run()
