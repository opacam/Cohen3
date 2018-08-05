# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

import json
from twisted.web import resource, static
from twisted.internet import defer

from coherence import log


class JsonInterface(resource.Resource, log.Loggable):
    logCategory = 'json'

    def __init__(self, controlpoint):
        resource.Resource.__init__(self)
        log.Loggable.__init__(self)
        self.controlpoint = controlpoint
        self.controlpoint.coherence.add_web_resource('json', self)
        self.children = {}

    def render_GET(self, request):
        d = defer.maybeDeferred(self.do_the_render, request)
        return d

    def render_POST(self, request):
        d = defer.maybeDeferred(self.do_the_render, request)
        return d

    def getChildWithDefault(self, path, request):
        self.info('getChildWithDefault, %s, %s, %s %s %r', request.method, path, request.uri, request.client, request.args)
        #return self.do_the_render(request)
        d = defer.maybeDeferred(self.do_the_render, request)
        return d

    def do_the_render(self, request):
        self.warning('do_the_render, %s, %s, %s %r %s', request.method, request.path, request.uri, request.args, request.client)
        msg = "Houston, we've got a problem"
        path = request.path.split('/')
        path = path[2:]
        self.warning('path %r', path)
        if request.method in ('GET', 'POST'):
            request.postpath = None
            if request.method == 'GET':
                if path[0] == 'devices':
                    return self.list_devices(request)
                else:
                    device = self.controlpoint.get_device_with_id(path[0])
                    if device is not None:
                        service = device.get_service_by_type(path[1])
                        if service is not None:
                            action = service.get_action(path[2])
                            if action is not None:
                                return self.call_action(action, request)
                            else:
                                msg = "action %r on service type %r for device %r not found" % (path[2], path[1], path[0])
                        else:
                            msg = "service type %r for device %r not found" % (path[1], path[0])

                    else:
                        msg = "device with id %r not found" % path[0]

        request.setResponseCode(404, message=msg)
        return static.Data("<html><p>%s</p></html>" % msg, 'text/html')

    def list_devices(self, request):
        devices = []
        for device in self.controlpoint.get_devices():
            devices.append(device.as_dict())
        return static.Data(json.dumps(devices), 'application/json')

    def call_action(self, action, request):
        kwargs = {}
        for entry, value_list in list(request.args.items()):
            kwargs[entry] = str(value_list[0])

        def to_json(result):
            self.warning("to_json")
            return static.Data(json.dumps(result), 'application/json')

        def fail(f):
            request.setResponseCode(404)
            return static.Data("<html><p>Houston, we've got a problem</p></html>", 'text/html')

        d = action.call(**kwargs)
        d.addCallback(to_json)
        d.addErrback(fail)
        return d
