# -*- test-case-name: axiom.test.test_listversions -*-

from twisted import plugin
from twisted.python import usage, versions
from zope.interface import classProvides

from coherence.extern.twisted.axiom import iaxiom, item, attributes, plugins
from coherence.extern.twisted.axiom.scripts import axiomatic
from coherence.extern.twisted.epsilon.extime import Time


class ListVersions(usage.Options, axiomatic.AxiomaticSubCommandMixin):
    """
    Command for listing the version history of a store.
    """

    classProvides(plugin.IPlugin, iaxiom.IAxiomaticCommand)
    name = "list-version"
    description = "Display software package version history."

    def postOptions(self):
        for line in listVersionHistory(self.parent.getStore()):
            print(line)


class SystemVersion(item.Item):
    """
    Represents a set of software package versions which, taken together,
    comprise a "system version" of the software that can have affected
    the contents of a Store.

    By recording the changes of these versions in the store itself we can
    better reconstruct its history later.
    """

    creation = attributes.timestamp(
        doc="When this system version set was recorded.",
        allowNone=False)

    def __repr__(self):
        return '<SystemVersion %s>' % (self.creation,)

    def longWindedRepr(self):
        """
        @return: A string representation of this SystemVersion suitable for
        display to the user.
        """
        return '\n\t'.join(
            [repr(self)] + [repr(sv) for sv in self.store.query(
                SoftwareVersion,
                SoftwareVersion.systemVersion == self)])


class SoftwareVersion(item.Item):
    """
    An Item subclass to map L{twisted.python.versions.Version} objects.
    """

    systemVersion = attributes.reference(
        doc="The system version this package version was observed in.",
        allowNone=False)

    package = attributes.text(doc="The software package.",
                              allowNone=False)
    version = attributes.text(doc="The version string of the software.",
                              allowNone=False)
    major = attributes.integer(doc='Major version number.',
                               allowNone=False)
    minor = attributes.integer(doc='Minor version number.',
                               allowNone=False)
    micro = attributes.integer(doc='Micro version number.',
                               allowNone=False)

    def asVersion(self):
        """
        Convert the version data in this item to a
        L{twisted.python.versions.Version}.
        """
        return versions.Version(self.package, self.major, self.minor,
                                self.micro)

    def __repr__(self):
        return '<SoftwareVersion %s: %s>' % (self.package, self.version)


def makeSoftwareVersion(store, version, systemVersion):
    """
    Return the SoftwareVersion object from store corresponding to the
    version object, creating it if it doesn't already exist.
    """
    return store.findOrCreate(SoftwareVersion,
                              systemVersion=systemVersion,
                              package=str(version.package),
                              version=str(version.short()),
                              major=version.major,
                              minor=version.minor,
                              micro=version.micro)


def listVersionHistory(store):
    """
    List the software package version history of store.
    """
    q = store.query(SystemVersion, sort=SystemVersion.creation.descending)
    return [sv.longWindedRepr() for sv in q]


def getSystemVersions(getPlugins=plugin.getPlugins):
    """
    Collect all the version plugins and extract their L{Version} objects.
    """
    return list(getPlugins(iaxiom.IVersion, plugins))


def checkSystemVersion(s, versions=None):
    """
    Check if the current version is different from the previously recorded
    version.  If it is, or if there is no previously recorded version,
    create a version matching the current config.
    """

    if versions is None:
        versions = getSystemVersions()

    currentVersionMap = dict([(v.package, v) for v in versions])
    mostRecentSystemVersion = s.findFirst(SystemVersion,
                                          sort=SystemVersion.creation.descending)
    mostRecentVersionMap = dict([(v.package, v.asVersion()) for v in
                                 s.query(SoftwareVersion,
                                         (SoftwareVersion.systemVersion ==
                                          mostRecentSystemVersion))])

    if mostRecentVersionMap != currentVersionMap:
        currentSystemVersion = SystemVersion(store=s, creation=Time())
        for v in currentVersionMap.values():
            makeSoftwareVersion(s, v, currentSystemVersion)
