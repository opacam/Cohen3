# -*- test-case-name: epsilon.test -*-
from ._version import get_versions
__version__ = get_versions()['version']
del get_versions

from twisted.python import versions


def asTwistedVersion(packageName, versionString):
    print(*list(map(int, versionString.split('+', 1)[0].split("."))))
    return versions.Version(
        packageName, *list(map(int, versionString.split('+', 1)[0].split("."))))


version = asTwistedVersion("epsilon", __version__)

__all__ = ['__version__', 'version']
