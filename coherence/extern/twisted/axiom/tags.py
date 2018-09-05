from coherence.extern.twisted.axiom.attributes import \
    text, reference, integer, AND, timestamp
from coherence.extern.twisted.axiom.item import Item
from coherence.extern.twisted.epsilon.extime import Time


class Tag(Item):
    typeName = 'tag'
    schemaVersion = 1

    name = text(doc="""
    The short string which is being applied as a tag to an Item.
    """)

    created = timestamp(doc="""
    When this tag was applied to the Item to which it applies.
    """)

    object = reference(doc="""
    The Item to which this tag applies.
    """)

    catalog = reference(doc="""
    The L{Catalog} item in which this tag was created.
    """)

    tagger = reference(doc="""
    An optional reference to the Item which is responsible for this tag's
    existence.
    """)


class _TagName(Item):
    """
    Helper class to make Catalog.tagNames very fast.  One of these is created
    for each distinct tag name that is created.  _TagName Items are never
    deleted from the database.
    """
    typeName = 'tagname'

    name = text(doc="""
    The short string which uniquely represents this tag.
    """, indexed=True)

    catalog = reference(doc="""
    The L{Catalog} item in which this tag exists.
    """)


class Catalog(Item):
    typeName = 'tag_catalog'
    schemaVersion = 2

    tagCount = integer(default=0)

    def tag(self, obj, tagName, tagger=None):
        """
        """
        # check to see if that tag exists.  Put the object attribute first,
        # since each object should only have a handful of tags and the object
        # reference is indexed.  As long as this is the case, it doesn't matter
        # whether the name or catalog attributes are indexed because selecting
        # from a small set of results is fast even without an index.
        if self.store.findFirst(Tag,
                                AND(Tag.object == obj,
                                    Tag.name == tagName,
                                    Tag.catalog == self)):
            return

        # if the tag doesn't exist, maybe we
        # need to create a new tagname object
        self.store.findOrCreate(_TagName, name=tagName, catalog=self)

        # Increment only if we are creating a new tag
        self.tagCount += 1
        Tag(store=self.store, object=obj,
            name=tagName, catalog=self,
            created=Time(), tagger=tagger)

    def tagNames(self):
        """
        Return an iterator of unicode strings - the unique tag names which have
        been applied objects in this catalog.
        """
        return self.store.query(_TagName, _TagName.catalog == self).getColumn(
            "name")

    def tagsOf(self, obj):
        """
        Return an iterator of unicode strings - the tag names which apply to
        the given object.
        """
        return self.store.query(
            Tag,
            AND(Tag.catalog == self,
                Tag.object == obj)).getColumn("name")

    def objectsIn(self, tagName):
        return self.store.query(
            Tag,
            AND(Tag.catalog == self,
                Tag.name == tagName)).getColumn("object")


def upgradeCatalog1to2(oldCatalog):
    """
    Create _TagName instances which version 2 of Catalog automatically creates
    for use in determining the tagNames result, but which version 1 of Catalog
    did not create.
    """
    newCatalog = oldCatalog.upgradeVersion('tag_catalog', 1, 2,
                                           tagCount=oldCatalog.tagCount)
    tags = newCatalog.store.query(Tag, Tag.catalog == newCatalog)
    tagNames = tags.getColumn("name").distinct()
    for t in tagNames:
        _TagName(store=newCatalog.store, catalog=newCatalog, name=t)
    return newCatalog


from coherence.extern.twisted.axiom.upgrade import registerUpgrader

registerUpgrader(upgradeCatalog1to2, 'tag_catalog', 1, 2)
