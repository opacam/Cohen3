# -*- test-case-name: axiom.test -*-
from _version import __version__
from twisted.python import versions


def asTwistedVersion(packageName, versionString):
    # print(*list(map(int, versionString.split('+', 1)[0].split("."))))
    return versions.Version(
        packageName, *list(map(int, versionString.split('+', 1)[0].split("."))))


version = asTwistedVersion("axiom", __version__)
