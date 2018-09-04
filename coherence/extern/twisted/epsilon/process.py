# -*- test-case-name: epsilon.test.test_process -*-
# Copyright (c) 2008 Divmod.  See LICENSE for details.

"""
Process and stdio related functionality.
"""

import imp
import os
import sys

from twisted.application.service import Service
from twisted.internet import reactor
from twisted.internet.stdio import StandardIO

from coherence.extern.twisted.epsilon.structlike import record


def spawnProcess(processProtocol, executable, args=(), env={},
                 path=None, uid=None, gid=None, usePTY=0,
                 packages=()):
    """Launch a process with a particular Python environment.

    All arguments as to reactor.spawnProcess(), except for the
    addition of an optional packages iterable.  This should be
    of strings naming packages the subprocess is to be able to
    import.
    """

    env = env.copy()

    pythonpath = []
    for pkg in packages:
        p = os.path.split(imp.find_module(pkg)[1])[0]
        if p.startswith(os.path.join(sys.prefix, 'lib')):
            continue
        pythonpath.append(p)
    pythonpath = list(set(pythonpath))
    pythonpath.extend(env.get('PYTHONPATH', '').split(os.pathsep))
    env['PYTHONPATH'] = os.pathsep.join(pythonpath)

    return reactor.spawnProcess(processProtocol, executable, args,
                                env, path, uid, gid, usePTY)


def spawnPythonProcess(processProtocol, args=(), env={},
                       path=None, uid=None, gid=None, usePTY=0,
                       packages=()):
    """Launch a Python process

    All arguments as to spawnProcess(), except the executable
    argument is omitted.
    """
    return spawnProcess(processProtocol, sys.executable,
                        args, env, path, uid, gid, usePTY,
                        packages)


class StandardIOService(record('protocol'), Service):
    """
    Service for connecting a protocol to stdio.
    """

    def startService(self):
        """
        Connect C{self.protocol} to standard io.
        """
        StandardIO(self.protocol)
