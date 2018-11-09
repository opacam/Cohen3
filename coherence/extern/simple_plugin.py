# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2007, Frank Scholz <coherence@beebits.net>

'''
Simple Plugin
=============

Real simple plugin system meant as a replacement when setuptools/pkg_resources
are not available.
'''

import os
import sys


class Plugin(object):
    ''' a new style class that
        betrays all its sub-classes
    '''
    pass


class Reception(object):
    '''
    Singleton class which holds information about known plugins.

    Currently a singleton, and even a class, seems to be overkill for this,
    but maybe we'll add some more functionality later.
    '''

    _instance_ = None  # Singleton

    def __new__(cls, *args, **kwargs):
        '''Creates the singleton.'''
        obj = getattr(cls, '_instance_', None)
        if obj is not None:
            return obj
        else:
            obj = super(Reception, cls).__new__(cls)
            cls._instance_ = obj
            return obj

    def __init__(self, plugin_path=None, log=None):
        '''Initializes the class and checks in if a path is provided.'''
        self.log = log
        if plugin_path is not None:
            self.checkin(plugin_path)

    def checkin(self, plugin_path):
        '''Import all valid files from plugin_path.'''
        if plugin_path not in sys.path:
            sys.path.insert(0, plugin_path)
        for plugin in os.listdir(plugin_path):
            p = os.path.join(plugin_path, plugin)
            if plugin != '__init__.py' and os.path.isfile(p) and \
                    os.path.splitext(p)[1] == '.py':
                try:
                    __import__(os.path.splitext(plugin)[0], None, None, [''])
                except Exception as msg:
                    if self.log is None:
                        print(f'can\'t import '
                              f'{os.path.splitext(plugin)[0]} - {msg}')
                    else:
                        self.log(f'can\'t import '
                                 f'{os.path.splitext(plugin)[0]} - {msg}')

    def guestlist(self, plugin_class=Plugin):
        '''Returns a list of all Plugin subclasses.'''
        found = []

        def get_subclass(klass, subclasses):
            if len(subclasses) == 0:
                found.append(klass)
            else:
                for k in subclasses:
                    get_subclass(k, k.__subclasses__())

        get_subclass(plugin_class, plugin_class.__subclasses__())

        return found
