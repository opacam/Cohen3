# -*- test-case-name: axiom.test -*-
from coherence.extern.twisted.axiom._version import __version__
from twisted.python import versions


def asTwistedVersion(packageName, versionString):
    return versions.Version(packageName, *list(map(int, versionString.split("."))))


version = asTwistedVersion("axiom", __version__)
