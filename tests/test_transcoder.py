# -*- coding: utf-8 -*-

from twisted.trial.unittest import TestCase

try:
    from coherence import transcoder as tc

    known_transcoders = [tc.PCMTranscoder, tc.WAVTranscoder, tc.MP3Transcoder,
                         tc.MP4Transcoder, tc.MP2TSTranscoder,
                         tc.ThumbTranscoder]
except ImportError as ie:
    tc = None
    tc_msg = 'Error importing Coherence transcoder: {}'.format(ie)
    print(tc_msg)


class TranscoderTestMixin(object):
    if tc is None:
        skip = tc_msg

    def setUp(self):
        self.manager = tc.TranscoderManager()

    def tearDown(self):
        # as it is a singleton ensuring that we always get a clean
        # and fresh one is tricky and hacks the internals
        tc.TranscoderManager._instance = None
        del self.manager


class TestTranscoderManagerSingletony(TranscoderTestMixin, TestCase):
    def test_is_really_singleton(self):
        # FIXME: singleton tests should be outsourced some when
        old_id = id(self.manager)
        new_manager = tc.TranscoderManager()
        self.assertEqual(old_id, id(new_manager))


class TestTranscoderAutoloading(TranscoderTestMixin, TestCase):
    class CoherenceStump(object):
        def __init__(self, **kwargs):
            self.config = kwargs

    failing_config = {'name': 'failing', 'pipeline': 'wrong',
                      'type': 'process', 'target': 'yay'}

    gst_config = {'name': 'supertest', 'pipeline': 'pp%spppl',
                  'type': 'gstreamer', 'target': 'yay'}

    process_config = {'name': 'megaprocess', 'pipeline': 'uiui%suiui',
                      'type': 'process', 'target': 'yay'}

    bad_name_config = {'name': 'so bäd', 'pipeline': 'fake %s',
                       'type': 'process', 'target': 'norway'}

    def setUp(self):
        self.manager = None

    def test_is_loading_all_known_transcoders(self):
        self.manager = tc.TranscoderManager()
        self._check_for_transcoders(known_transcoders)

    def _check_for_transcoders(self, transcoders):
        for klass in transcoders:
            loaded_transcoder = self.manager.transcoders[
                tc.get_transcoder_name(klass)]
            self.assertEqual(loaded_transcoder, klass)

    def test_is_loading_no_config(self):
        coherence = self.CoherenceStump()
        self.manager = tc.TranscoderManager(coherence)
        self._check_for_transcoders(known_transcoders)

    def test_is_loading_one_gst_from_config(self):
        coherence = self.CoherenceStump(transcoder=self.gst_config)
        self.manager = tc.TranscoderManager(coherence)
        self._check_for_transcoders(known_transcoders)
        my_pipe = self.manager.select('supertest', 'http://my_uri')
        self.assertTrue(isinstance(my_pipe, tc.GStreamerTranscoder))
        self._check_transcoder_attrs(my_pipe,
                                     pipeline='pp%spppl', uri="http://my_uri")

    def _check_transcoder_attrs(self, transcoder, pipeline=None, uri=None):
        # bahh... relying on implementation details of the basetranscoder here
        self.assertEqual(transcoder.pipeline_description, pipeline)
        self.assertEqual(transcoder.uri, uri)

    def test_is_loading_one_process_from_config(self):
        coherence = self.CoherenceStump(transcoder=self.process_config)
        self.manager = tc.TranscoderManager(coherence)
        self._check_for_transcoders(known_transcoders)
        transcoder = self.manager.select('megaprocess', 'http://another/uri')
        self.assertTrue(isinstance(transcoder, tc.ExternalProcessPipeline))

        self._check_transcoder_attrs(transcoder, 'uiui%suiui',
                                     'http://another/uri')

    def test_placeholdercheck_in_config(self):
        # this pipeline does not contain the '%s' placeholder and because
        # of that should not be created

        coherence = self.CoherenceStump(transcoder=self.failing_config)
        self.manager = tc.TranscoderManager(coherence)
        self._check_for_transcoders(known_transcoders)
        self.assertRaises(KeyError, self.manager.select, 'failing',
                          'http://another/uri')

    # TODO: Must redo test badname
    # def test_badname_in_config(self):
    #     # this pipeline does not contain the '%s' placeholder and because
    #     # of that should not be created
    #
    #     coherence = self.CoherenceStump(transcoder=self.bad_name_config)
    #     self.manager = tc.TranscoderManager(coherence)
    #     self._check_for_transcoders(known_transcoders)
    #     self.assertRaises(KeyError, self.manager.select, 'so bäd',
    #                       'http://another/uri')

    def test_is_loading_multiple_from_config(self):
        coherence = self.CoherenceStump(transcoder=[self.gst_config,
                                                    self.process_config])
        self.manager = tc.TranscoderManager(coherence)
        self._check_for_transcoders(known_transcoders)

        # check the megaprocess
        transcoder = self.manager.select('megaprocess', 'http://another/uri')
        self.assertTrue(isinstance(transcoder, tc.ExternalProcessPipeline))

        self._check_transcoder_attrs(transcoder, 'uiui%suiui',
                                     'http://another/uri')

        # check the gstreamer transcoder
        transcoder = self.manager.select('supertest', 'http://another/uri2')
        self.assertTrue(isinstance(transcoder, tc.GStreamerTranscoder))

        self._check_transcoder_attrs(transcoder, 'pp%spppl',
                                     'http://another/uri2')

    def test_loaded_gst_always_new_instance(self):
        coherence = self.CoherenceStump(transcoder=self.gst_config)
        self.manager = tc.TranscoderManager(coherence)
        self._check_for_transcoders(known_transcoders)
        transcoder_a = self.manager.select('supertest', 'http://my_uri')
        self.assertTrue(isinstance(transcoder_a, tc.GStreamerTranscoder))
        self._check_transcoder_attrs(transcoder_a, pipeline='pp%spppl',
                                     uri="http://my_uri")

        transcoder_b = self.manager.select('supertest', 'http://another/uri')
        self.assertTrue(isinstance(transcoder_b, tc.GStreamerTranscoder))
        self._check_transcoder_attrs(transcoder_b, pipeline='pp%spppl',
                                     uri="http://another/uri")

        self.assertNotEqual(transcoder_a, transcoder_b)
        self.assertNotEqual(id(transcoder_a), id(transcoder_b))
