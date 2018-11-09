# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2007-2009, Frank Scholz <coherence@beebits.net>
# Copyright 2018, Pol Canelles <canellestudi@gmail.com>

'''
DBUS service class
==================

Module to add dbus compatibility to Cohen3's project.

:class:`DBusCDSService`
-----------------------

The DBus service for UPnP's CDS (Content Directory Service)

:class:`DBusService`
--------------------

The generic DBus service for UPnP.

:class:`DBusDevice`
-------------------

Class representing a DBus device.

:class:`DBusPontoon`
--------------------

Used to initialize DBus from within the class
:class:`~coherence.base.Coherence`.
'''
import time
import urllib.error
import urllib.parse
import urllib.parse
import urllib.request

import dbus
from lxml import etree

from eventdispatcher import EventDispatcher

if dbus.__version__ < '0.82.2':
    raise ImportError(
        'dbus-python module too old, pls get a newer one from '
        'http://dbus.freedesktop.org/releases/dbus-python/')

from dbus.mainloop.glib import DBusGMainLoop

DBusGMainLoop(set_as_default=True)

import dbus.service

from coherence import __version__
from coherence.upnp.core import DIDLLite
from coherence.dbus_constants import *
from coherence import log

from twisted.internet import reactor, task

namespaces = {'{http://purl.org/dc/elements/1.1/}': 'dc:',
              '{urn:schemas-upnp-org:metadata-1-0/upnp/}': 'upnp:',
              '{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}': 'DIDL-Lite:',
              '{urn:schemas-dlna-org:metadata-1-0}': 'dlna:',
              '{http://www.pv.com/pvns/}': 'pv:'}


def un_namespace(text):
    for k, v in list(namespaces.items()):
        if text.startswith(k):
            return text.replace(k, v)
    return text


class DBusCDSService(EventDispatcher, dbus.service.Object, log.LogAble):
    '''
    .. versionchanged:: 0.9.0
        Migrated from louie/dispatcher to EventDispatcher
    '''
    logCategory = 'dbus'
    NOT_FOR_THE_TUBES = True

    def __init__(self, service, dbus_device, bus):
        log.LogAble.__init__(self)
        EventDispatcher.__init__(self)
        self.service = service
        self.dbus_device = dbus_device

        # get the service name
        self.type = self.service.service_type.split(':')[3]

        bus_name = dbus.service.BusName(CDS_SERVICE, bus)

        device_id = dbus_device.id
        self.path = \
            OBJECT_PATH + '/devices/' + device_id + '/services/' + 'CDS'
        dbus.service.Object.__init__(self, bus, bus_name=bus_name,
                                     object_path=self.path)
        self.debug(f'DBusService {service} {self.type}')
        if isinstance(self.service, EventDispatcher):
            self.service.bind(state_variable_changed=self.variable_changed)

        self.subscribeStateVariables()

    def shutdown(self):
        self._release_thyself(suicide_mode=False)

    def _release_thyself(self, suicide_mode=True):
        if isinstance(self.service, EventDispatcher):
            self.service.unbind(state_variable_changed=self.variable_changed)
        self.service = None
        self.dbus_device = None
        self.remove_from_connection()
        self.path = None
        if suicide_mode:
            del self

    def variable_changed(self, variable):
        self.StateVariableChanged(self.dbus_device.device.get_id(), self.type,
                                  variable.name, variable.value)

    @dbus.service.method(CDS_SERVICE, in_signature='', out_signature='s')
    def get_id(self):
        return self.service.id

    @dbus.service.method(CDS_SERVICE, in_signature='', out_signature='s')
    def get_scpd_xml(self):
        return self.service.scpdXML

    @dbus.service.signal(CDS_SERVICE,
                         signature='sssv')
    def StateVariableChanged(self, udn, service, variable, value):
        self.info(f'{self.dbus_device.device.get_friendly_name()} service '
                  f'{self.type} signals StateVariable {variable} '
                  f'changed to {value}')

    @dbus.service.method(CDS_SERVICE, in_signature='', out_signature='as')
    def getAvailableActions(self):
        actions = self.service.get_actions()
        r = []
        for name in list(actions.keys()):
            r.append(name)
        return r

    @dbus.service.method(CDS_SERVICE, in_signature='', out_signature='ssv')
    def subscribeStateVariables(self):
        if not self.service:
            return
        notify = [v for v in list(self.service._variables[0].values()) if
                  v.send_events is True]
        if len(notify) == 0:
            return
        data = {}
        for n in notify:
            if n.name == 'LastChange':
                lc = {}
                for instance, vdict in list(self.service._variables.items()):
                    v = {}
                    for variable in list(vdict.values()):
                        if (variable.name != 'LastChange' and
                                variable.name[0:11] != 'A_ARG_TYPE_' and
                                variable.never_evented is False):
                            if not hasattr(variable, 'dbus_updated'):
                                variable.dbus_updated = None
                    if len(v) > 0:
                        lc[str(instance)] = v
                if len(lc) > 0:
                    data[str(n.name)] = lc
            else:
                data[str(n.name)] = str(n.value)
        return self.dbus_device.device.get_id(), self.type, dbus.Dictionary(
            data, signature='sv', variant_level=3)

    @dbus.service.method(CDS_SERVICE, in_signature='', out_signature='s',
                         async_callbacks=('dbus_async_cb',
                                          'dbus_async_err_cb'))
    def GetSearchCapabilites(self, dbus_async_cb, dbus_async_err_cb):

        r = self.callAction('GetSearchCapabilites', {})
        if r == '':
            return r

        def convert_reply(data):
            dbus_async_cb(str(data['SearchCaps']))

        r.addCallback(convert_reply)
        r.addErrback(dbus_async_err_cb)

    @dbus.service.method(CDS_SERVICE, in_signature='', out_signature='s',
                         async_callbacks=('dbus_async_cb',
                                          'dbus_async_err_cb'))
    def GetSortCapabilities(self, dbus_async_cb, dbus_async_err_cb):

        r = self.callAction('GetSortCapabilities', {})
        if r == '':
            return r

        def convert_reply(data):
            dbus_async_cb(str(data['SortCaps']))

        r.addCallback(convert_reply)
        r.addErrback(dbus_async_err_cb)

    @dbus.service.method(CDS_SERVICE, in_signature='', out_signature='s',
                         async_callbacks=('dbus_async_cb',
                                          'dbus_async_err_cb'))
    def GetSortExtensionCapabilities(self, dbus_async_cb, dbus_async_err_cb):

        r = self.callAction('GetSortExtensionCapabilities', {})
        if r == '':
            return r

        def convert_reply(data):
            dbus_async_cb(str(data['SortExtensionCaps']))

        r.addCallback(convert_reply)
        r.addErrback(dbus_async_err_cb)

    @dbus.service.method(CDS_SERVICE, in_signature='', out_signature='s',
                         async_callbacks=('dbus_async_cb',
                                          'dbus_async_err_cb'))
    def GetFeatureList(self, dbus_async_cb, dbus_async_err_cb):

        r = self.callAction('GetFeatureList', {})
        if r == '':
            return r

        def convert_reply(data):
            dbus_async_cb(str(data['FeatureList']))

        r.addCallback(convert_reply)
        r.addErrback(dbus_async_err_cb)

    @dbus.service.method(CDS_SERVICE, in_signature='', out_signature='i',
                         async_callbacks=('dbus_async_cb',
                                          'dbus_async_err_cb'))
    def GetSystemUpdateID(self, dbus_async_cb, dbus_async_err_cb):

        r = self.callAction('GetSystemUpdateID', {})
        if r == '':
            return r

        def convert_reply(data):
            dbus_async_cb(int(data['Id']))

        r.addCallback(convert_reply)
        r.addErrback(dbus_async_err_cb)

    @dbus.service.method(CDS_SERVICE, in_signature='sssiis',
                         out_signature='aa{sv}iii',  # was viii
                         async_callbacks=('dbus_async_cb',
                                          'dbus_async_err_cb'))
    def Browse(self, ObjectID, BrowseFlag, Filter, StartingIndex,
               RequestedCount, SortCriteria,
               dbus_async_cb, dbus_async_err_cb):

        arguments = {'ObjectID': str(ObjectID),
                     'BrowseFlag': str(BrowseFlag),
                     'Filter': str(Filter),
                     'StartingIndex': int(StartingIndex),
                     'RequestedCount': int(RequestedCount),
                     'SortCriteria': str(SortCriteria)}
        r = self.callAction('Browse', arguments)
        if r == '':
            return r

        def convert_reply(data):
            et = etree.fromstring(data['Result'])
            items = dbus.Array([], signature='v')

            def append(item):
                i = dbus.Dictionary({}, signature='sv')
                for k, v in list(item.attrib.items()):
                    i[un_namespace(k)] = v
                res = dbus.Array([], signature='v')
                for child in item:
                    if un_namespace(child.tag) == 'DIDL-Lite:res':
                        res_dict = dbus.Dictionary({}, signature='sv')
                        res_dict['url'] = str(child.text)
                        for k, v in list(child.attrib.items()):
                            res_dict[un_namespace(k)] = v
                        res.append(res_dict)
                    else:
                        i[un_namespace(child.tag)] = child.text
                if len(res):
                    i['res'] = res
                items.append(i)

            for item in et:
                append(item)

            dbus_async_cb(items, int(data['NumberReturned']),
                          int(data['TotalMatches']), int(data['UpdateID']))

        r.addCallback(convert_reply)
        r.addErrback(dbus_async_err_cb)

    @dbus.service.method(CDS_SERVICE, in_signature='sssiis',
                         out_signature='aa{sv}iii',
                         async_callbacks=('dbus_async_cb',
                                          'dbus_async_err_cb'))
    def Search(self, ContainerID, SearchCriteria, Filter, StartingIndex,
               RequestedCount, SortCriteria,
               dbus_async_cb, dbus_async_err_cb):

        arguments = {'ContainerID': str(ContainerID),
                     'SearchCriteria': str(SearchCriteria),
                     'Filter': str(Filter),
                     'StartingIndex': int(StartingIndex),
                     'RequestedCount': int(RequestedCount),
                     'SortCriteria': str(SortCriteria)}
        r = self.callAction('Search', arguments)
        if r == '':
            return r

        def convert_reply(data):
            et = etree.fromstring(data['Result'])
            items = dbus.Array([], signature='v')

            def append(item):
                i = dbus.Dictionary({}, signature='sv')
                for k, v in list(item.attrib.items()):
                    i[un_namespace(k)] = v
                res = dbus.Array([], signature='v')
                for child in item:
                    if un_namespace(child.tag) == 'DIDL-Lite:res':
                        res_dict = dbus.Dictionary({}, signature='sv')
                        res_dict['url'] = str(child.text)
                        for k, v in list(child.attrib.items()):
                            res_dict[un_namespace(k)] = v
                        res.append(res_dict)
                    else:
                        i[un_namespace(child.tag)] = child.text
                if len(res):
                    i['res'] = res
                items.append(i)

            for item in et:
                append(item)

            dbus_async_cb(items, int(data['NumberReturned']),
                          int(data['TotalMatches']), int(data['UpdateID']))

        r.addCallback(convert_reply)
        r.addErrback(dbus_async_err_cb)

    @dbus.service.method(CDS_SERVICE, in_signature='ss', out_signature='ss',
                         async_callbacks=('dbus_async_cb',
                                          'dbus_async_err_cb'))
    def CreateObject(self, ContainerID, Elements,
                     dbus_async_cb, dbus_async_err_cb):

        arguments = {'ContainerID': str(ContainerID),
                     'Elements': str(Elements)}
        r = self.callAction('CreateObject', arguments)
        if r == '':
            return r

        def convert_reply(data):
            dbus_async_cb(str(data['ObjectID']), str(data['Result']))

        r.addCallback(convert_reply)
        r.addErrback(dbus_async_err_cb)

    @dbus.service.method(CDS_SERVICE, in_signature='s', out_signature='',
                         async_callbacks=('dbus_async_cb',
                                          'dbus_async_err_cb'))
    def DestroyObject(self, ObjectID,
                      dbus_async_cb, dbus_async_err_cb):

        arguments = {'ObjectID': str(ObjectID)}
        r = self.callAction('DestroyObject', arguments)
        if r == '':
            return r

        def convert_reply(data):
            dbus_async_cb()

        r.addCallback(convert_reply)
        r.addErrback(dbus_async_err_cb)

    @dbus.service.method(CDS_SERVICE, in_signature='sss', out_signature='',
                         async_callbacks=('dbus_async_cb',
                                          'dbus_async_err_cb'))
    def UpdateObject(self, ObjectID, CurrentTagValue, NewTagValue,
                     dbus_async_cb, dbus_async_err_cb):

        arguments = {'ObjectID': str(ObjectID),
                     'CurrentTagValue': str(CurrentTagValue),
                     'NewTagValue': NewTagValue}
        r = self.callAction('UpdateObject', arguments)
        if r == '':
            return r

        def convert_reply(data):
            dbus_async_cb()

        r.addCallback(convert_reply)
        r.addErrback(dbus_async_err_cb)

    @dbus.service.method(CDS_SERVICE, in_signature='ss', out_signature='s',
                         async_callbacks=('dbus_async_cb',
                                          'dbus_async_err_cb'))
    def MoveObject(self, ObjectID, NewParentID,
                   dbus_async_cb, dbus_async_err_cb):

        arguments = {'ObjectID': str(ObjectID),
                     'NewParentID': str(NewParentID)}
        r = self.callAction('MoveObject', arguments)
        if r == '':
            return r

        def convert_reply(data):
            dbus_async_cb(str(data['NewObjectID']))

        r.addCallback(convert_reply)
        r.addErrback(dbus_async_err_cb)

    @dbus.service.method(CDS_SERVICE, in_signature='ss', out_signature='i',
                         async_callbacks=('dbus_async_cb',
                                          'dbus_async_err_cb'))
    def ImportResource(self, SourceURI, DestinationURI,
                       dbus_async_cb, dbus_async_err_cb):

        arguments = {'SourceURI': str(SourceURI),
                     'DestinationURI': str(DestinationURI)}
        r = self.callAction('ImportResource', arguments)
        if r == '':
            return r

        def convert_reply(data):
            dbus_async_cb(str(data['TransferID']))

        r.addCallback(convert_reply)
        r.addErrback(dbus_async_err_cb)

    @dbus.service.method(CDS_SERVICE, in_signature='ss', out_signature='i',
                         async_callbacks=('dbus_async_cb',
                                          'dbus_async_err_cb'))
    def ExportResource(self, SourceURI, DestinationURI,
                       dbus_async_cb, dbus_async_err_cb):

        arguments = {'SourceURI': str(SourceURI),
                     'DestinationURI': str(DestinationURI)}
        r = self.callAction('ExportResource', arguments)
        if r == '':
            return r

        def convert_reply(data):
            dbus_async_cb(str(data['TransferID']))

        r.addCallback(convert_reply)
        r.addErrback(dbus_async_err_cb)

    @dbus.service.method(CDS_SERVICE, in_signature='s', out_signature='',
                         async_callbacks=('dbus_async_cb',
                                          'dbus_async_err_cb'))
    def DeleteResource(self, ResourceURI,
                       dbus_async_cb, dbus_async_err_cb):

        arguments = {'ResourceURI': str(ResourceURI)}
        r = self.callAction('DeleteResource', arguments)
        if r == '':
            return r

        def convert_reply(data):
            dbus_async_cb()

        r.addCallback(convert_reply)
        r.addErrback(dbus_async_err_cb)

    @dbus.service.method(CDS_SERVICE, in_signature='i', out_signature='',
                         async_callbacks=('dbus_async_cb',
                                          'dbus_async_err_cb'))
    def StopTransferResource(self, TransferID,
                             dbus_async_cb, dbus_async_err_cb):

        arguments = {'TransferID': str(TransferID)}
        r = self.callAction('StopTransferResource', arguments)
        if r == '':
            return r

        def convert_reply(data):
            dbus_async_cb()

        r.addCallback(convert_reply)
        r.addErrback(dbus_async_err_cb)

    @dbus.service.method(CDS_SERVICE, in_signature='i', out_signature='sss',
                         async_callbacks=('dbus_async_cb',
                                          'dbus_async_err_cb'))
    def GetTransferProgress(self, TransferID,
                            dbus_async_cb, dbus_async_err_cb):

        arguments = {'TransferID': str(TransferID)}
        r = self.callAction('GetTransferProgress', arguments)
        if r == '':
            return r

        def convert_reply(data):
            dbus_async_cb(str(data['TransferStatus']),
                          str(data['TransferLength']),
                          str(data['TransferTotal']))

        r.addCallback(convert_reply)
        r.addErrback(dbus_async_err_cb)

    @dbus.service.method(CDS_SERVICE, in_signature='ss', out_signature='s',
                         async_callbacks=('dbus_async_cb',
                                          'dbus_async_err_cb'))
    def CreateReference(self, ContainerID, ObjectID,
                        dbus_async_cb, dbus_async_err_cb):

        arguments = {'ContainerID': str(ContainerID),
                     'ObjectID': str(ObjectID)}
        r = self.callAction('CreateReference', arguments)
        if r == '':
            return r

        def convert_reply(data):
            dbus_async_cb(str(data['NewID']))

        r.addCallback(convert_reply)
        r.addErrback(dbus_async_err_cb)

    def callAction(self, name, arguments):

        action = self.service.get_action(name)
        if action is not None:
            d = action.call(**arguments)
            return d
        return ''


class DBusService(dbus.service.Object, log.LogAble):
    '''
    .. versionchanged:: 0.9.0
        Migrated from louie/dispatcher to EventDispatcher
    '''
    logCategory = 'dbus'
    SUPPORTS_MULTIPLE_CONNECTIONS = True

    def __init__(self, service, dbus_device, bus):
        log.LogAble.__init__(self)
        self.service = service
        self.dbus_device = dbus_device

        if self.service is not None:
            self.type = self.service.service_type.split(':')[
                3]  # get the service name
            self.type = self.type.replace('-', '')
        else:
            self.type = 'from_the_tubes'

        try:
            bus_name = dbus.service.BusName(SERVICE_IFACE, bus)
        except Exception:
            bus_name = None
            self.tube = bus
        else:
            self.tube = None

        if self.dbus_device is not None:
            self.device_id = self.dbus_device.id
        else:
            self.device_id = 'dev_from_the_tubes'
        self.path = \
            OBJECT_PATH + '/devices/' + self.device_id + \
            '/services/' + self.type

        dbus.service.Object.__init__(self, bus, bus_name=bus_name,
                                     object_path=self.path)
        self.debug(f'DBusService {service} {self.type}')
        if isinstance(self.service, EventDispatcher):
            self.service.bind(
                state_variable_changed=self.variable_changed)

        self.subscribe()
        # interfaces = self._dbus_class_table[
        #     self.__class__.__module__ + '.' + self.__class__.__name__]
        # for (name, funcs) in interfaces.iteritems():
        #    print name, funcs
        #    if funcs.has_key('destroy_object'):
        #        print '''removing \'destroy_object\''''
        #        del funcs['destroy_object']
        #    for func in funcs.values():
        #        if getattr(func, '_dbus_is_method', False):
        #            print self.__class__._reflect_on_method(func)

        # self._get_service_methods()

    def shutdown(self):
        self._release_thyself(suicide_mode=False)

    def _release_thyself(self, suicide_mode=True):
        if isinstance(self.service, EventDispatcher):
            self.service.unbind(
                state_variable_changed=self.variable_changed)
        self.service = None
        self.dbus_device = None
        self.tube = None
        self.remove_from_connection()
        self.path = None
        if suicide_mode:
            del self

    def _get_service_methods(self):
        '''Returns a list of method descriptors for this object'''
        methods = []
        for func in dir(self):
            func = getattr(self, func)
            if callable(func) and hasattr(func, '_dbus_is_method'):
                print(func, func._dbus_interface, func._dbus_is_method)
                if hasattr(func, 'im_func'):
                    print(func.__func__)

    def variable_changed(self, variable):
        # print self.service, 'got signal for change of', variable
        # print variable.name, variable.value
        # print type(variable.name), type(variable.value)
        self.StateVariableChanged(self.device_id, self.type, variable.name,
                                  variable.value)

    @dbus.service.signal(SERVICE_IFACE,
                         signature='sssv')
    def StateVariableChanged(self, udn, service, variable, value):
        self.info(f'{self.device_id} service {self.type} signals '
                  f'StateVariable {variable} changed to {value}')

    @dbus.service.method(SERVICE_IFACE, in_signature='', out_signature='s')
    def get_scpd_xml(self):
        return self.service.get_scpdXML()

    @dbus.service.method(SERVICE_IFACE, in_signature='', out_signature='as')
    def get_available_actions(self):
        actions = self.service.get_actions()
        r = []
        for name in list(actions.keys()):
            r.append(name)
        return r

    @dbus.service.method(SERVICE_IFACE, in_signature='', out_signature='s')
    def get_id(self):
        return self.service.id

    @dbus.service.method(SERVICE_IFACE, in_signature='sv', out_signature='v',
                         async_callbacks=('dbus_async_cb',
                                          'dbus_async_err_cb'))
    def action(self, name, arguments, dbus_async_cb, dbus_async_err_cb):

        # print('action', name, arguments)
        def reply(data):
            dbus_async_cb(
                dbus.Dictionary(data, signature='sv', variant_level=4))

        if self.service.client is not None:
            # print('action', name)
            func = getattr(self.service.client, name, None)
            # print('action', func)
            if callable(func):
                kwargs = {}
                try:
                    for k, v in list(arguments.items()):
                        kwargs[str(k)] = str(v)
                except Exception as e:
                    self.error(f'DBusService.action: {e}')
                d = func(**kwargs)
                d.addCallback(reply)
                d.addErrback(dbus_async_err_cb)
        return ''

    @dbus.service.method(SERVICE_IFACE, in_signature='sa{ss}',
                         out_signature='v',
                         async_callbacks=('dbus_async_cb',
                                          'dbus_async_err_cb',),
                         sender_keyword='sender',
                         connection_keyword='connection')
    def call_action(self, name, arguments, dbus_async_cb, dbus_async_err_cb,
                    sender=None, connection=None):

        print('call_action called by ', sender, connection, self.type,
              self.tube)

        def reply(data, name, connection):
            if hasattr(connection, '_tube'):
                if name == 'Browse':
                    didl = DIDLLite.DIDLElement.fromString(data['Result'])
                    changed = False
                    for item in didl.getItems():
                        new_res = DIDLLite.Resources()
                        for res in item.res:
                            remote_protocol, remote_network, \
                                remote_content_format, _ = \
                                res.protocolInfo.split(':')
                            if remote_protocol == 'http-get' and \
                                    remote_network == '*':
                                quoted_url = 'mirabeau' + '/' + \
                                             urllib.parse.quote_plus(res.data)
                                print('modifying', res.data)
                                host_port = \
                                    ':'.join(
                                        (self.service.device.client.
                                         coherence.mirabeau._external_address,
                                         str(self.service.device.client.
                                             coherence.mirabeau._external_port)
                                         )
                                    )
                                res.data = urllib.parse.urlunsplit(
                                    ('http', host_port, quoted_url, '', ''))
                                print('--->', res.data)
                                new_res.append(res)
                                changed = True
                        item.res = new_res
                    if changed:
                        didl.rebuild()
                        # FIXME this is not the proper way to do it
                        data['Result'] = didl.toString().replace('<ns0:',
                                                                 '<').replace(
                            '</ns0:', '</')
            dbus_async_cb(
                dbus.Dictionary(data, signature='sv', variant_level=4))

        if self.service.client is not None:
            action = self.service.get_action(name)
            if action:
                kwargs = {}
                try:
                    for k, v in list(arguments.items()):
                        kwargs[str(k)] = str(v)
                except Exception as e:
                    self.error(f'DBusService.call_action: {e}')
                d = action.call(**kwargs)
                d.addCallback(reply, name, connection)
                d.addErrback(dbus_async_err_cb)
        return ''

    @dbus.service.method(SERVICE_IFACE, in_signature='v', out_signature='v',
                         async_callbacks=('dbus_async_cb',
                                          'dbus_async_err_cb'))
    def destroy_object(self, arguments, dbus_async_cb, dbus_async_err_cb):

        def reply(data):
            dbus_async_cb(
                dbus.Dictionary(data, signature='sv', variant_level=4))

        if self.service.client is not None:
            kwargs = {}
            for k, v in list(arguments.items()):
                kwargs[str(k)] = str(v)
            d = self.service.client.destroy_object(**kwargs)
            d.addCallback(reply)
            d.addErrback(dbus_async_err_cb)
        return ''

    @dbus.service.method(SERVICE_IFACE, in_signature='', out_signature='ssv')
    def subscribe(self):
        notify = []
        if self.service:
            notify = [v for v in list(self.service._variables[0].values()) if
                      v.send_events]
        if len(notify) == 0:
            return
        data = {}
        for n in notify:
            if n.name == 'LastChange':
                lc = {}
                for instance, vdict in list(self.service._variables.items()):
                    v = {}
                    for variable in list(vdict.values()):
                        if (variable.name != 'LastChange' and
                                variable.name[0:11] != 'A_ARG_TYPE_' and
                                variable.never_evented is False):
                            if not hasattr(variable, 'dbus_updated'):
                                variable.dbus_updated = None

                            # FIXME: we are missing variable dependencies here
                            # if variable.dbus_updated != \
                            #         variable.last_touched:
                            #    v[str(variable.name)] = str(variable.value)
                            #    variable.dbus_updated = time.time()
                    if len(v) > 0:
                        lc[str(instance)] = v
                if len(lc) > 0:
                    data[str(n.name)] = lc
            else:
                data[str(n.name)] = str(n.value)
        return self.dbus_device.device.get_id(), self.type, dbus.Dictionary(
            data, signature='sv', variant_level=3)


class DBusDevice(dbus.service.Object, log.LogAble):
    logCategory = 'dbus'
    SUPPORTS_MULTIPLE_CONNECTIONS = True

    def __init__(self, device, bus):
        log.LogAble.__init__(self)
        if device is not None:
            self.uuid = device.get_id()[5:]
            self.id = self.uuid.replace('-', '')
            # we shouldn't need to do this, but ...
            self.id = self.id.replace('+', '')
        else:
            self.id = 'from_the_tubes'

        try:
            bus_name = dbus.service.BusName(DEVICE_IFACE, bus)
        except Exception:
            bus_name = None
            self.tube = bus
        else:
            self.tube = None

        dbus.service.Object.__init__(self, bus, bus_name=bus_name,
                                     object_path=self.path())

        self.services = []
        self.device = device

        self.debug(f'DBusDevice {device} {self.id}')

        if device is not None:
            for service in device.get_services():
                self.services.append(DBusService(service, self, bus))
                if service.service_type.split(':')[3] == 'ContentDirectory':
                    self.services.append(DBusCDSService(service, self, bus))

    def shutdown(self):
        self._release_thyself(suicide_mode=False)

    def _release_thyself(self, suicide_mode=True):
        for service in self.services:
            service._release_thyself()
        self.services = None
        self.device = None
        self.tube = None
        self.remove_from_connection()

        # FIXME: this is insane
        if suicide_mode:
            del self

    def path(self):
        return OBJECT_PATH + '/devices/' + self.id

    @dbus.service.method(DEVICE_IFACE, in_signature='', out_signature='v')
    def get_info(self):
        services = [x.path for x in self.services
                    if not getattr(x, 'NOT_FOR_THE_TUBES', False)]
        r = {'path': self.path(),
             'device_type': self.device.get_device_type(),
             'friendly_name': self.device.get_friendly_name(),
             'udn': self.device.get_id(),
             'uri': list(urllib.parse.urlsplit(self.device.get_location())),
             'presentation_url': self.device.get_presentation_url(),
             'parent_udn': self.device.get_parent_id(),
             'services': services}
        return dbus.Dictionary(r, signature='sv', variant_level=2)

    @dbus.service.method(DEVICE_IFACE, in_signature='', out_signature='s')
    def get_markup_name(self):
        return self.device.get_markup_name()

    @dbus.service.method(DEVICE_IFACE, in_signature='', out_signature='s')
    def get_friendly_name(self):
        return self.device.get_friendly_name()

    @dbus.service.method(DEVICE_IFACE, in_signature='', out_signature='s')
    def get_friendly_device_type(self):
        return self.device.get_friendly_device_type()

    @dbus.service.method(DEVICE_IFACE, in_signature='', out_signature='i')
    def get_device_type_version(self):
        return int(self.device.get_device_type_version())

    @dbus.service.method(DEVICE_IFACE, in_signature='', out_signature='s')
    def get_id(self):
        return self.device.get_id()

    @dbus.service.method(DEVICE_IFACE, in_signature='', out_signature='s')
    def get_device_type(self):
        return self.device.get_device_type()

    @dbus.service.method(DEVICE_IFACE, in_signature='', out_signature='s')
    def get_usn(self):
        return self.device.get_usn()

    @dbus.service.method(DEVICE_IFACE, in_signature='', out_signature='av')
    def get_device_icons(self):
        return dbus.Array(self.device.icons, signature='av', variant_level=2)


class DBusPontoon(dbus.service.Object, log.LogAble):
    '''
    .. versionchanged:: 0.9.0
        Migrated from louie/dispatcher to EventDispatcher
    '''
    logCategory = 'dbus'
    SUPPORTS_MULTIPLE_CONNECTIONS = True

    def __init__(self, controlpoint, bus=None):
        log.LogAble.__init__(self)
        self.bus = bus or dbus.SessionBus()
        try:
            bus_name = dbus.service.BusName(BUS_NAME, self.bus)
        except Exception:
            bus_name = None
            self.tube = self.bus
        else:
            self.tube = None

        self.bus_name = bus_name
        dbus.service.Object.__init__(self, self.bus, bus_name=self.bus_name,
                                     object_path=OBJECT_PATH)

        self.debug(f'D-Bus pontoon {self} {self.bus} {self.bus_name}')

        self.devices = {}
        self.controlpoint = controlpoint
        self.pinboard = {}

        # i am a stub service if i have no control point
        if self.controlpoint is None:
            return

        for device in self.controlpoint.get_devices():
            self.devices[device.get_id()] = DBusDevice(device, self.bus_name)

        self.controlpoint.bind(
            control_point_client_detected=self._device_detected)
        self.controlpoint.bind(
            control_point_client_removed=self._device_removed)

        self.debug('D-Bus pontoon started')

    def shutdown(self):
        self.controlpoint.unbind(
            control_point_client_detected=self._device_detected)
        self.controlpoint.unbind(
            control_point_client_removed=self._device_removed)
        for device_id, device in self.devices.items():
            device.shutdown()
        self.devices = {}
        self.remove_from_connection()
        self.bus = None

    @dbus.service.method(BUS_NAME, in_signature='sv', out_signature='')
    def pin(self, key, value):
        self.pinboard[key] = value
        print(self.pinboard)

    @dbus.service.method(BUS_NAME, in_signature='s', out_signature='v')
    def get_pin(self, key):
        return self.pinboard.get(key, 'Coherence::Pin::None')

    @dbus.service.method(BUS_NAME, in_signature='s', out_signature='')
    def unpin(self, key):
        del self.pinboard[key]

    @dbus.service.method(BUS_NAME, in_signature='s', out_signature='s')
    def create_oob(self, file):
        print('create_oob')
        key = str(time.time())
        self.pinboard[key] = file
        print(self.pinboard)
        return self.controlpoint.coherence.urlbase + 'oob?key=' + key

    def remove_client(self, usn, client):
        self.info(f'removed {client.device_type} '
                  f'{client.device.get_friendly_name()}')
        try:
            getattr(self,
                    str(f'UPnP_ControlPoint_{client.device_type}_removed'))(
                usn)
        except Exception as e:
            self.error(f'DBusPontoon.remove_client: {e}')

    def remove(self, udn):
        # print 'DBusPontoon remove', udn
        # print 'before remove', self.devices
        d = self.devices.pop(udn)
        d._release_thyself()
        del d
        # print 'after remove', self.devices

    @dbus.service.method(BUS_NAME, in_signature='', out_signature='s')
    def version(self):
        return __version__

    @dbus.service.method(BUS_NAME, in_signature='', out_signature='s')
    def hostname(self):
        return self.controlpoint.coherence.hostname

    @dbus.service.method(BUS_NAME, in_signature='', out_signature='av')
    def get_devices(self):
        r = []
        for device in list(self.devices.values()):
            # r.append(device.path())
            r.append(device.get_info())
        return dbus.Array(r, signature='v', variant_level=2)

    @dbus.service.method(BUS_NAME, in_signature='i', out_signature='av',
                         async_callbacks=('dbus_async_cb',
                                          'dbus_async_err_cb'))
    def get_devices_async(self, for_mirabeau,
                          dbus_async_cb, dbus_async_err_cb):
        infos = []
        allowed_device_types = ['urn:schemas-upnp-org:device:MediaServer:2',
                                'urn:schemas-upnp-org:device:MediaServer:1']

        def iterate_devices(devices):
            for device in devices:
                if for_mirabeau and device.get_device_type() not in \
                        allowed_device_types:
                    continue
                infos.append(device.get_info())
                yield infos

        def done(generator):
            dbus_async_cb(dbus.Array(infos, signature='v', variant_level=2))

        devices = list(self.devices.copy().values())
        dfr = task.coiterate(iterate_devices(devices))
        dfr.addCallbacks(
            done, lambda failure: dbus_async_err_cb(failure.value))

    @dbus.service.method(BUS_NAME, in_signature='s', out_signature='v')
    def get_device_with_id(self, id):
        for device in list(self.devices.values()):
            if id == device.device.get_id():
                return device.get_info()

    @dbus.service.method(BUS_NAME, in_signature='sa{ss}', out_signature='s')
    def add_plugin(self, backend, arguments):
        kwargs = {}
        for k, v in arguments.items():
            kwargs[str(k)] = str(v)
        p = self.controlpoint.coherence.add_plugin(backend, **kwargs)
        return str(p.uuid)

    @dbus.service.method(BUS_NAME, in_signature='s', out_signature='s')
    def remove_plugin(self, uuid):
        return str(self.controlpoint.coherence.remove_plugin(uuid))

    @dbus.service.method(BUS_NAME, in_signature='ssa{ss}', out_signature='s')
    def call_plugin(self, uuid, method, arguments):
        try:
            plugin = self.controlpoint.coherence.active_backends[uuid]
        except KeyError:
            self.warning(f'no backend with the uuid {uuid} found')
            return ''
        function = getattr(plugin.backend, method, None)
        if function is None:
            return ''
        kwargs = {}
        for k, v in arguments.items():
            kwargs[str(k)] = str(v)
        function(**kwargs)
        return uuid

    @dbus.service.method(BUS_NAME, in_signature='ssa{ss}', out_signature='v',
                         async_callbacks=('dbus_async_cb',
                                          'dbus_async_err_cb'))
    def create_object(self, device_id, container_id, arguments, dbus_async_cb,
                      dbus_async_err_cb):
        device = self.controlpoint.get_device_with_id(device_id)
        if device is not None:
            client = device.get_client()
            new_arguments = {}
            for k, v in list(arguments.items()):
                new_arguments[str(k)] = str(v)

            def reply(data):
                dbus_async_cb(
                    dbus.Dictionary(data, signature='sv', variant_level=4))

            d = client.content_directory.create_object(str(container_id),
                                                       new_arguments)
            d.addCallback(reply)
            d.addErrback(dbus_async_err_cb)

    @dbus.service.method(BUS_NAME, in_signature='sss', out_signature='v',
                         async_callbacks=('dbus_async_cb',
                                          'dbus_async_err_cb'))
    def import_resource(self, device_id, source_uri, destination_uri,
                        dbus_async_cb, dbus_async_err_cb):
        device = self.controlpoint.get_device_with_id(device_id)
        if device is not None:
            client = device.get_client()

            def reply(data):
                dbus_async_cb(
                    dbus.Dictionary(data, signature='sv', variant_level=4))

            d = client.content_directory.import_resource(str(source_uri),
                                                         str(destination_uri))
            d.addCallback(reply)
            d.addErrback(dbus_async_err_cb)

    @dbus.service.method(BUS_NAME, in_signature='ss', out_signature='v',
                         async_callbacks=('dbus_async_cb',
                                          'dbus_async_err_cb'))
    def put_resource(self, destination_uri, filepath, dbus_async_cb,
                     dbus_async_err_cb):
        def reply(data):
            dbus_async_cb(200)

        d = self.controlpoint.put_resource(str(destination_uri), str(filepath))
        d.addCallback(reply)
        d.addErrback(dbus_async_err_cb)

    def _device_detected(self, device):
        id = device.get_id()
        print('new_device_detected', device.get_usn(),
              device.friendly_device_type, id)
        if id not in self.devices:
            new_device = DBusDevice(device, self.bus)
            self.devices[id] = new_device
            # print self.devices, id
            info = new_device.get_info()
            self.device_detected(info, id)
            if device.get_friendly_device_type() == 'MediaServer':
                self.UPnP_ControlPoint_MediaServer_detected(info, id)
            elif device.get_friendly_device_type() == 'MediaRenderer':
                self.UPnP_ControlPoint_MediaRenderer_detected(info, id)

    def _device_removed(self, usn=''):
        print('_device_removed', usn)
        id = usn.split('::')[0]
        device = self.devices[id]
        self.device_removed(id)
        # print device.get_friendly_device_type()
        if device.get_friendly_device_type() == 'MediaServer':
            self.UPnP_ControlPoint_MediaServer_removed(id)
        if device.get_friendly_device_type() == 'MediaRenderer':
            self.UPnP_ControlPoint_MediaServer_removed(id)
        reactor.callLater(1, self.remove, id)

    def cp_ms_detected(self, client, udn=''):
        print('cp_ms_detected', udn)
        if client.device.get_id() not in self.devices:
            new_device = DBusDevice(client.device, self.bus)
            self.devices[client.device.get_id()] = new_device
            self.UPnP_ControlPoint_MediaServer_detected(new_device.get_info(),
                                                        udn)

    def cp_mr_detected(self, client, udn=''):
        if client.device.get_id() not in self.devices:
            new_device = DBusDevice(client.device, self.bus)
            self.devices[client.device.get_id()] = new_device
            self.UPnP_ControlPoint_MediaRenderer_detected(
                new_device.get_info(), udn)

    def cp_ms_removed(self, udn):
        print('cp_ms_removed', udn)
        self.UPnP_ControlPoint_MediaServer_removed(udn)
        # schedule removal of device from our cache after signal has
        # been called. Let's assume one second is long enough...
        reactor.callLater(1, self.remove, udn)

    def cp_mr_removed(self, udn):
        # print 'cp_mr_removed', udn
        self.UPnP_ControlPoint_MediaRenderer_removed(udn)
        # schedule removal of device from our cache after signal has
        # been called. Let's assume one second is long enough...
        reactor.callLater(1, self.remove, udn)

    @dbus.service.signal(BUS_NAME,
                         signature='vs')
    def UPnP_ControlPoint_MediaServer_detected(self, device, udn):
        self.info('emitting signal UPnP_ControlPoint_MediaServer_detected')

    @dbus.service.signal(BUS_NAME,
                         signature='s')
    def UPnP_ControlPoint_MediaServer_removed(self, udn):
        self.info('emitting signal UPnP_ControlPoint_MediaServer_removed')

    @dbus.service.signal(BUS_NAME,
                         signature='vs')
    def UPnP_ControlPoint_MediaRenderer_detected(self, device, udn):
        self.info('emitting signal UPnP_ControlPoint_MediaRenderer_detected')

    @dbus.service.signal(BUS_NAME,
                         signature='s')
    def UPnP_ControlPoint_MediaRenderer_removed(self, udn):
        self.info('emitting signal UPnP_ControlPoint_MediaRenderer_removed')

    @dbus.service.signal(BUS_NAME,
                         signature='vs')
    def device_detected(self, device, udn):
        self.info('emitting signal device_detected')

    @dbus.service.signal(BUS_NAME,
                         signature='s')
    def device_removed(self, udn):
        self.info('emitting signal device_removed')

    ''' org.DLNA related methods and signals
    '''

    @dbus.service.method(DLNA_BUS_NAME + '.DMC', in_signature='',
                         out_signature='av')
    def getDMSList(self):
        return dbus.Array(self._get_devices_of_type('MediaServer'),
                          signature='v', variant_level=2)

    def _get_devices_of_type(self, typ):
        return [device.get_info() for device in self.devices.values()
                if device.get_friendly_device_type() == typ]

    @dbus.service.method(DLNA_BUS_NAME + '.DMC', in_signature='',
                         out_signature='av')
    def getDMRList(self):
        return dbus.Array(self._get_devices_of_type('MediaRenderer'),
                          signature='v', variant_level=2)

    @dbus.service.signal(BUS_NAME,
                         signature='vs')
    def DMS_added(self, device, udn):
        self.info('emitting signal DMS_added')

    @dbus.service.signal(BUS_NAME,
                         signature='s')
    def DMS_removed(self, udn):
        self.info('emitting signal DMS_removed')

    @dbus.service.signal(BUS_NAME,
                         signature='vs')
    def DMR_added(self, device, udn):
        self.info('emitting signal DMR_added')

    @dbus.service.signal(BUS_NAME,
                         signature='s')
    def DMR_removed(self, udn):
        self.info('emitting signal DMR_detected')
