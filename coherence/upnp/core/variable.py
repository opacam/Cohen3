# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright (C) 2006 Fluendo, S.A. (www.fluendo.com).
# Copyright 2006, Frank Scholz <coherence@beebits.net>
# Copyright 2018, Pol Canelles <canellestudi@gmail.com>

'''
:class:`StateVariable`
----------------------

The :class:`StateVariable` implements an UPnP variable with the ability to
emmit changes via EventDispatcher whenever some class variable changes.
'''

import time

from eventdispatcher import EventDispatcher

from coherence.upnp.core import utils

try:
    # FIXME:  there is some circular import,
    # service imports variable, variable imports service
    # how is this done properly?
    from coherence.upnp.core import service
except ImportError:
    from . import service

from coherence import log


class StateVariable(EventDispatcher, log.LogAble):
    '''
    Represents a UPnP variable. It has the ability to dispatch changes whenever
    some class variable changes.

    .. versionchanged:: 0.9.0

        * Migrated from louie/dispatcher to EventDispatcher
        * Added two more class variables:

            - :attr:`StateVariable.dispatch_targets`
            - :attr:`StateVariable.dispatch_events`

        * The emitted events changed:

            - Coherence.UPnP.StateVariable.changed =>
              state_variable_changed
            - Coherence.UPnP.StateVariable.{var name}.changed =>
              state_variable_{var name}_changed

    .. warning: This class is special regarding EventDispatcher, because we
                initialize the event into the service and in the class,
                and we only do that if the target service has inherited from
                EventDispatcher, otherwise we only implements EventDispatcher
                into this class.
    '''

    logCategory = 'variable'

    dispatch_targets = []
    dispatch_events = []

    def __init__(self, upnp_service, name, implementation, instance,
                 send_events,
                 data_type, allowed_values):
        log.LogAble.__init__(self)
        EventDispatcher.__init__(self)

        self.service = upnp_service

        self.dispatch_events = [
            f'state_variable_{name}_changed',
            'state_variable_changed']
        self.dispatch_targets = [self]
        if isinstance(self.service, EventDispatcher):
            self.dispatch_targets.append(self.service)
        for target in self.dispatch_targets:
            for evt in self.dispatch_events:
                if evt not in target.event_dispatcher_event_callbacks:
                    target.register_event(evt)

        self.name = name
        self.implementation = implementation
        self.instance = instance
        self.send_events = utils.means_true(send_events)
        self.never_evented = False
        self.data_type = data_type
        self.allowed_values = allowed_values
        if self.allowed_values is None:
            self.allowed_values = []
        self.has_vendor_values = False
        self.allowed_value_range = None
        self.dependant_variable = None

        self.default_value = ''
        self.old_value = ''
        self.value = ''
        self.last_time_touched = None

        self._callbacks = []
        if isinstance(self.service, service.ServiceServer):
            self.moderated = self.service.is_variable_moderated(name)
            self.updated = False

    def as_tuples(self):
        r = []
        r.append(('Name', self.name))
        if self.send_events:
            r.append(('Evented', 'yes'))
        else:
            r.append(('Evented', 'no'))
        r.append(('Data Type', self.data_type))
        r.append(('Default Value', self.default_value))
        r.append(('Current Value', str(self.value)))
        if self.allowed_values is not None and \
                len(self.allowed_values) > 0:
            r.append(('Allowed Values',
                      ','.join(self.allowed_values)))
        return r

    def set_default_value(self, value):
        self.update(value)
        self.default_value = self.value

    def set_allowed_values(self, values):
        if not isinstance(values, (list, tuple)):
            values = [values]
        self.allowed_values = values

    def set_allowed_value_range(self, **kwargs):
        self.allowed_value_range = kwargs

    def get_allowed_values(self):
        return self.allowed_values

    def set_never_evented(self, value):
        self.never_evented = utils.means_true(value)

    def update(self, value):
        if not isinstance(self.service, service.Service):
            if self.name == 'ContainerUpdateIDs':
                old_value = self.value
                if self.updated:
                    if isinstance(value, tuple):
                        v = old_value.split(',')
                        i = 0
                        while i < len(v):
                            if v[i] == str(value[0]):
                                del v[i:i + 2]
                                old_value = ','.join(v)
                                break
                            i += 2
                        if len(old_value):
                            new_value = old_value + ',' + str(
                                value[0]) + ',' + str(value[1])
                        else:
                            new_value = str(value[0]) + ',' + str(value[1])
                    else:
                        if len(old_value):
                            new_value = str(old_value) + ',' + str(value)
                        else:
                            new_value = str(value)
                else:
                    if isinstance(value, tuple):
                        new_value = str(value[0]) + ',' + str(value[1])
                    else:
                        new_value = value
            else:
                if self.data_type == 'string':
                    if isinstance(value, str):
                        value = value.split(',')
                    if (isinstance(value, tuple) or
                            isinstance(value, set)):
                        value = list(value)
                    if not isinstance(value, list):
                        value = [value]
                    new_value = []
                    for v in value:
                        if type(v) == str:
                            v = v  # .encode('utf-8')
                        else:
                            v = str(v)
                        if len(self.allowed_values):
                            if self.has_vendor_values:
                                new_value.append(v)
                            elif v.upper() in [x.upper() for x in
                                               self.allowed_values]:
                                new_value.append(v)
                            else:
                                self.warning(
                                    f'Variable {self.name} update, '
                                    f'{self.has_vendor_values} value {v} '
                                    f'doesn\'t fit in {self.allowed_values}')
                                new_value = 'Coherence_Value_Error'
                        else:
                            new_value.append(v)
                    new_value = ','.join(new_value)
                elif self.data_type == 'boolean':
                    new_value = utils.generalise_boolean(value)
                elif self.data_type == 'bin.base64':
                    new_value = value
                else:
                    new_value = int(value)
        else:
            if self.data_type == 'string':
                if type(value) != str:
                    value = str(value)
                if len(self.allowed_values):
                    if self.has_vendor_values:
                        new_value = value
                    elif value.upper() in [v.upper() for v in
                                           self.allowed_values]:
                        new_value = value
                    else:
                        self.warning(f'Variable {self.name} NOT updated, '
                                     f'value {value} doesn\'t fit')
                        new_value = 'Coherence_Value_Error'
                else:
                    new_value = value
            elif self.data_type == 'boolean':
                new_value = utils.generalise_boolean(value)
            elif self.data_type == 'bin.base64':
                new_value = value
            else:
                try:
                    new_value = int(value)
                except ValueError:
                    new_value = 'Coherence_Value_Error'

        if new_value == 'Coherence_Value_Error':
            return
        if new_value == self.value:
            self.info(f'variable NOT updated, no value change'
                      f' {self.name} {self.value}')
            return
        self.old_value = self.value
        self.value = new_value
        self.last_time_touched = time.time()

        # print(f'UPDATED {self.name} {self.service} '
        #       f'{isinstance(self.service, service.Service)} '
        #       f'{self.instance} {self.value} {self._callbacks}')
        self.notify()

        if isinstance(self.service, service.Service):
            # self.notify()
            pass
        else:
            self.updated = True
            if self.service.last_change is not None:
                self.service.last_change.updated = True

    def subscribe(self, callback):
        self._callbacks.append(callback)
        callback(self)

    def notify(self):
        if self.name.startswith('A_ARG_TYPE_'):
            return
        self.info(
            f'Variable {self.name} sends notify about new value >{self.value}<'
        )
        # if self.old_value == '':
        #    return

        for target in self.dispatch_targets:
            for evt in self.dispatch_events:
                target.dispatch_event(evt, variable=self)
        # print(f'CALLBACKS {self.name} {self.instance} {self._callbacks}')
        for callback in self._callbacks:
            callback(self)

    def __repr__(self):
        return \
            f'Variable: {self.name}, {str(self.service)}, {self.instance:d},' \
            f' {self.implementation}, {self.data_type},' \
            f' {str(self.allowed_values)}, {str(self.default_value)},' \
            f' {str(self.old_value)}, {str(self.value)},' \
            f' {str(self.send_events)}'
