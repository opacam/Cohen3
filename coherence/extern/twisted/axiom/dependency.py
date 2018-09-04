# Copright 2008 Divmod, Inc.  See LICENSE file for details.
# -*- test-case-name: axiom.test.test_dependency -*-
"""
A dependency management system for items.
"""

import itertools
import sys

from zope.interface.advice import addClassAdvisor

from coherence.extern.twisted.axiom.attributes import reference, boolean, AND
from coherence.extern.twisted.axiom.errors import ItemNotFound, \
    DependencyError, UnsatisfiedRequirement
from coherence.extern.twisted.axiom.item import Item
from coherence.extern.twisted.epsilon.structlike import record

# There is probably a cleaner way to do this.
_globalDependencyMap = {}


def dependentsOf(cls):
    deps = _globalDependencyMap.get(cls, None)
    if deps is None:
        return []
    else:
        return [d[0] for d in deps]


## Totally ripping off z.i


def dependsOn(itemType, itemCustomizer=None, doc='',
              indexed=True, whenDeleted=reference.NULLIFY):
    """
    This function behaves like L{axiom.attributes.reference} but with
    an extra behaviour: when this item is installed (via
    L{axiom.dependency.installOn} on a target item, the
    type named here will be instantiated and installed on the target
    as well.

    For example::

      class Foo(Item):
          counter = integer()
          thingIDependOn = dependsOn(Baz, lambda baz: baz.setup())

    @param itemType: The Item class to instantiate and install.
    @param itemCustomizer: A callable that accepts the item installed
    as a dependency as its first argument. It will be called only if
    an item is created to satisfy this dependency.

    @return: An L{axiom.attributes.reference} instance.
    """

    frame = sys._getframe(1)
    locals = frame.f_locals

    # Try to make sure we were called from a class def.
    if (locals is frame.f_globals) or ('__module__' not in locals):
        raise TypeError("dependsOn can be used only from a class definition.")
    ref = reference(reftype=itemType, doc=doc, indexed=indexed, allowNone=True,
                    whenDeleted=whenDeleted)
    if "__dependsOn_advice_data__" not in locals:
        addClassAdvisor(_dependsOn_advice)
    locals.setdefault('__dependsOn_advice_data__', []).append(
        (itemType, itemCustomizer, ref))
    return ref


def _dependsOn_advice(cls):
    if cls in _globalDependencyMap:
        print("Double advising of %s. dependency map from first time: %s" % (
            cls, _globalDependencyMap[cls]))
        # bail if we end up here twice, somehow
        return cls
    for itemType, itemCustomizer, ref in cls.__dict__[
        '__dependsOn_advice_data__']:
        classDependsOn(cls, itemType, itemCustomizer, ref)
    del cls.__dependsOn_advice_data__
    return cls


def classDependsOn(cls, itemType, itemCustomizer, ref):
    _globalDependencyMap.setdefault(cls, []).append(
        (itemType, itemCustomizer, ref))


class _DependencyConnector(Item):
    """
    I am a connector between installed items and their targets.
    """
    installee = reference(doc="The item installed.")
    target = reference(doc="The item installed upon.")
    explicitlyInstalled = boolean(doc="Whether this item was installed"
                                      "explicitly (and thus whether or not it"
                                      "should be automatically uninstalled when"
                                      "nothing depends on it)")


def installOn(self, target):
    """
    Install this object on the target along with any powerup
    interfaces it declares. Also track that the object now depends on
    the target, and the object was explicitly installed (and therefore
    should not be uninstalled by subsequent uninstallation operations
    unless it is explicitly removed).
    """
    _installOn(self, target, True)


def _installOn(self, target, __explicitlyInstalled=False):
    depBlob = _globalDependencyMap.get(self.__class__, [])
    dependencies, itemCustomizers, refs = (list(map(list, list(zip(*depBlob))))
                                           or ([], [], []))
    # See if any of our dependencies have been installed already
    for dc in self.store.query(_DependencyConnector,
                               _DependencyConnector.target == target):
        if dc.installee.__class__ in dependencies:
            i = dependencies.index(dc.installee.__class__)
            refs[i].__set__(self, dc.installee)
            del dependencies[i], itemCustomizers[i], refs[i]
        if (dc.installee.__class__ == self.__class__
                and self.__class__ in set(
                    itertools.chain([blob[0][0] for blob in
                                     list(_globalDependencyMap.values())]))):
            # Somebody got here before we did... let's punt
            raise DependencyError("An instance of %r is already "
                                  "installed on %r." % (self.__class__,
                                                        target))
    # The rest we'll install
    for i, cls in enumerate(dependencies):
        it = cls(store=self.store)
        if itemCustomizers[i] is not None:
            itemCustomizers[i](it)
        _installOn(it, target, False)
        refs[i].__set__(self, it)
    # And now the connector for our own dependency.

    dc = self.store.findUnique(
        _DependencyConnector,
        AND(_DependencyConnector.target == target,
            _DependencyConnector.installee == self,
            _DependencyConnector.explicitlyInstalled == __explicitlyInstalled),
        None)
    assert dc is None, "Dependency connector already exists, wtf are you doing?"
    _DependencyConnector(store=self.store, target=target,
                         installee=self,
                         explicitlyInstalled=__explicitlyInstalled)

    target.powerUp(self)

    callback = getattr(self, "installed", None)
    if callback is not None:
        callback()


def uninstallFrom(self, target):
    """
    Remove this object from the target, as well as any dependencies
    that it automatically installed which were not explicitly
    "pinned" by calling "install", and raising an exception if
    anything still depends on this.
    """

    # did this class powerup on any interfaces? powerdown if so.
    target.powerDown(self)

    for dc in self.store.query(_DependencyConnector,
                               _DependencyConnector.target == target):
        if dc.installee is self:
            dc.deleteFromStore()

    for item in installedUniqueRequirements(self, target):
        uninstallFrom(item, target)

    callback = getattr(self, "uninstalled", None)
    if callback is not None:
        callback()


def installedOn(self):
    """
    If this item is installed on another item, return the install
    target. Otherwise return None.
    """
    try:
        return self.store.findUnique(_DependencyConnector,
                                     _DependencyConnector.installee == self
                                     ).target
    except ItemNotFound:
        return None


def installedDependents(self, target):
    """
    Return an iterable of things installed on the target that
    require this item.
    """
    for dc in self.store.query(_DependencyConnector,
                               _DependencyConnector.target == target):
        depends = dependentsOf(dc.installee.__class__)
        if self.__class__ in depends:
            yield dc.installee


def installedUniqueRequirements(self, target):
    """
    Return an iterable of things installed on the target that this item
    requires and are not required by anything else.
    """

    myDepends = dependentsOf(self.__class__)
    # XXX optimize?
    for dc in self.store.query(_DependencyConnector,
                               _DependencyConnector.target == target):
        if dc.installee is self:
            # we're checking all the others not ourself
            continue
        depends = dependentsOf(dc.installee.__class__)
        if self.__class__ in depends:
            raise DependencyError(
                "%r cannot be uninstalled from %r, "
                "%r still depends on it" % (self, target, dc.installee))

        for cls in myDepends[:]:
            # If one of my dependencies is required by somebody
            # else, leave it alone
            if cls in depends:
                myDepends.remove(cls)

    for dc in self.store.query(_DependencyConnector,
                               _DependencyConnector.target == target):
        if (dc.installee.__class__ in myDepends
                and not dc.explicitlyInstalled):
            yield dc.installee


def installedRequirements(self, target):
    """
    Return an iterable of things installed on the target that this
    item requires.
    """
    myDepends = dependentsOf(self.__class__)
    for dc in self.store.query(_DependencyConnector,
                               _DependencyConnector.target == target):
        if dc.installee.__class__ in myDepends:
            yield dc.installee


def onlyInstallPowerups(self, target):
    """
    Deprecated - L{Item.powerUp} now has this functionality.
    """
    target.powerUp(self)


class requiresFromSite(
    record('powerupInterface defaultFactory siteDefaultFactory',
           defaultFactory=None,
           siteDefaultFactory=None)):
    """
    A read-only descriptor that will return the site store's powerup for a
    given item.

    @ivar powerupInterface: an L{Interface} describing the powerup that the
    site store should be adapted to.

    @ivar defaultFactory: a 1-argument callable that takes the site store and
    returns a value for this descriptor.  This is invoked in cases where the
    site store does not provide a default factory of its own, and this
    descriptor is retrieved from an item in a store with a parent.

    @ivar siteDefaultFactory: a 1-argument callable that takes the site store
    and returns a value for this descriptor.  This is invoked in cases where
    this descriptor is retrieved from an item in a store without a parent.
    """

    def _invokeFactory(self, defaultFactory, siteStore):
        if defaultFactory is None:
            raise UnsatisfiedRequirement()
        return defaultFactory(siteStore)

    def __get__(self, oself, type=None):
        """
        Retrieve the value of this dependency from the site store.
        """
        siteStore = oself.store.parent
        if siteStore is not None:
            pi = self.powerupInterface(siteStore, None)
            if pi is None:
                pi = self._invokeFactory(self.defaultFactory, siteStore)
        else:
            pi = self._invokeFactory(self.siteDefaultFactory, oself.store)
        return pi
