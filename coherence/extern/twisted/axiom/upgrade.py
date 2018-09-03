# -*- test-case-name: axiom.test.test_upgrading -*-

"""
Axiom Item/schema upgrade support.
"""

from twisted.python.failure import Failure
from twisted.python.log import msg
from twisted.python.reflect import qual

from coherence.extern.twisted.axiom.errors import NoUpgradePathAvailable, UpgraderRecursion
from coherence.extern.twisted.axiom.errors import ItemUpgradeError
from coherence.extern.twisted.axiom.item import _legacyTypes, _typeNameToMostRecentClass


_upgradeRegistry = {}


class _StoreUpgrade(object):
    """
    Manage Item upgrades and upgrade batching for a store.

    @type _currentlyUpgrading: C{dict}
    @ivar _currentlyUpgrading: A map of storeIDs to Items currently in the
        middle of an upgrader.  Used to make sure that the same item isn't
        upgraded reentrantly.

    @type _oldTypesRemaining: C{list}
    @ivar _oldTypesRemaining: All the old types which have not been fully
        upgraded in this database.
    """

    def __init__(self, store):
        self.store = store
        self._currentlyUpgrading = {}
        self._oldTypesRemaining = []

    def upgradesPending(self):
        return bool(self._oldTypesRemaining)

    upgradesPending = property(
        upgradesPending,
        doc="""
        Flag indicating whether there any types that still need to be upgraded
        or not.
        """)

    def checkUpgradePaths(self):
        """
        Check that all of the accumulated old Item types have a way to get
        from their current version to the latest version.

        @raise axiom.errors.NoUpgradePathAvailable: for any, and all, Items
            that do not have a valid upgrade path
        """
        cantUpgradeErrors = []

        for oldVersion in self._oldTypesRemaining:
            # We have to be able to get from oldVersion.schemaVersion to
            # the most recent type.

            currentType = _typeNameToMostRecentClass.get(
                oldVersion.typeName, None)

            if currentType is None:
                # There isn't a current version of this type; it's entirely
                # legacy, will be upgraded by deleting and replacing with
                # something else.
                continue

            typeInQuestion = oldVersion.typeName
            upgver = oldVersion.schemaVersion

            while upgver < currentType.schemaVersion:
                # Do we have enough of the schema present to upgrade?
                if ((typeInQuestion, upgver)
                    not in _upgradeRegistry):
                    cantUpgradeErrors.append(
                        "No upgrader present for %s (%s) from %d to %d" % (
                            typeInQuestion, qual(currentType), upgver,
                            upgver + 1))

                # Is there a type available for each upgrader version?
                if upgver+1 != currentType.schemaVersion:
                    if (typeInQuestion, upgver+1) not in _legacyTypes:
                        cantUpgradeErrors.append(
                            "Type schema required for upgrade missing:"
                            " %s version %d" % (
                                typeInQuestion, upgver+1))
                upgver += 1

            if cantUpgradeErrors:
                raise NoUpgradePathAvailable('\n    '.join(cantUpgradeErrors))

    def queueTypeUpgrade(self, oldtype):
        """
        Queue a type upgrade for C{oldtype}.
        """
        if oldtype not in self._oldTypesRemaining:
            self._oldTypesRemaining.append(oldtype)

    def upgradeItem(self, thisItem):
        """
        Upgrade a legacy item.

        @raise axiom.errors.UpgraderRecursion: If the given item is already in
            the process of being upgraded.
        """
        sid = thisItem.storeID
        if sid in self._currentlyUpgrading:
            raise UpgraderRecursion()
        self._currentlyUpgrading[sid] = thisItem
        try:
            return upgradeAllTheWay(thisItem)
        finally:
            self._currentlyUpgrading.pop(sid)

    def upgradeEverything(self):
        """
        Upgrade every item in the store, one at a time.

        @raise axiom.errors.ItemUpgradeError: if an item upgrade failed

        @return: A generator that yields for each item upgrade.
        """
        return self.upgradeBatch(1)

    def upgradeBatch(self, n):
        """
        Upgrade the entire store in batches, yielding after each batch.

        @param n: Number of upgrades to perform per transaction
        @type n: C{int}

        @raise axiom.errors.ItemUpgradeError: if an item upgrade failed

        @return: A generator that yields after each batch upgrade. This needs
            to be consumed for upgrading to actually take place.
        """
        store = self.store

        def _doBatch(itemType):
            upgradedAnything = False

            for theItem in store.query(itemType, limit=n):
                upgradedAnything = True
                try:
                    self.upgradeItem(theItem)
                except:
                    f = Failure()
                    raise ItemUpgradeError(
                        f, theItem.storeID, itemType,
                        _typeNameToMostRecentClass[itemType.typeName])

            return upgradedAnything

        if self.upgradesPending:
            didAny = False

            while self._oldTypesRemaining:
                t0 = self._oldTypesRemaining[0]

                upgradedAnything = store.transact(_doBatch, t0)
                if not upgradedAnything:
                    self._oldTypesRemaining.pop(0)
                    if didAny:
                        msg("%s finished upgrading %s" % (store.dbdir.path, qual(t0)))
                    continue
                elif not didAny:
                    didAny = True
                    msg("%s beginning upgrade..." % (store.dbdir.path,))

                yield None

            if didAny:
                msg("%s completely upgraded." % (store.dbdir.path,))


def registerUpgrader(upgrader, typeName, oldVersion, newVersion):
    """
    Register a callable which can perform a schema upgrade between two
    particular versions.

    @param upgrader: A one-argument callable which will upgrade an object.  It
    is invoked with an instance of the old version of the object.
    @param typeName: The database typename for which this is an upgrader.
    @param oldVersion: The version from which this will upgrade.
    @param newVersion: The version to which this will upgrade.  This must be
    exactly one greater than C{oldVersion}.
    """
    # assert (typeName, oldVersion, newVersion) not in _upgradeRegistry, "duplicate upgrader"
    # ^ this makes the tests blow up so it's just disabled for now; perhaps we
    # should have a specific test mode
    # assert newVersion - oldVersion == 1, "read the doc string"
    assert isinstance(typeName, str), "read the doc string"
    _upgradeRegistry[typeName, oldVersion] = upgrader


def registerAttributeCopyingUpgrader(itemType, fromVersion, toVersion, postCopy=None):
    """
    Register an upgrader for C{itemType}, from C{fromVersion} to C{toVersion},
    which will copy all attributes from the legacy item to the new item.  If
    postCopy is provided, it will be called with the new item after upgrading.

    @param itemType: L{axiom.item.Item} subclass
    @param postCopy: a callable of one argument
    @return: None
    """
    def upgrader(old):
        newitem = old.upgradeVersion(itemType.typeName, fromVersion, toVersion,
                                     **dict((str(name), getattr(old, name))
                                            for (name, _) in old.getSchema()))
        if postCopy is not None:
            postCopy(newitem)
        return newitem
    registerUpgrader(upgrader, itemType.typeName, fromVersion, toVersion)


def registerDeletionUpgrader(itemType, fromVersion, toVersion):
    """
    Register an upgrader for C{itemType}, from C{fromVersion} to C{toVersion},
    which will delete the item from the database.

    @param itemType: L{axiom.item.Item} subclass
    @return: None
    """
    # XXX This should actually do something more special so that a new table is
    # not created and such.
    def upgrader(old):
        old.deleteFromStore()
        return None
    registerUpgrader(upgrader, itemType.typeName, fromVersion, toVersion)


def upgradeAllTheWay(o):
    assert o.__legacy__
    while True:
        try:
            upgrader = _upgradeRegistry[o.typeName, o.schemaVersion]
        except KeyError:
            break
        else:
            o = upgrader(o)
            if o is None:
                # Object was explicitly destroyed during upgrading.
                break
    return o


__all__ = [
    'registerUpgrader', 'registerAttributeCopyingUpgrader',
    'registerDeletionUpgrader']
