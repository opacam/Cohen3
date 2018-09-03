# -*- test-case-name: axiom.test.test_sequence -*-

from coherence.extern.twisted.axiom.item import Item
from coherence.extern.twisted.axiom.attributes import reference, integer, AND


class _ListItem(Item):
    typeName = 'list_item'
    schemaVersion = 1

    _index = integer()
    _value = reference()
    _container = reference()


class List(Item):
    typeName = 'list'
    schemaVersion = 1

    length = integer(default=0)

    def __init__(self, *args, **kw):
        super(List, self).__init__(**kw)
        if args:
            self.extend(args[0])

    def _queryListItems(self):
        return self.store.query(_ListItem, _ListItem._container == self)

    def _getListItem(self, index):
        return list(self.store.query(_ListItem,
                                     AND(_ListItem._container == self,
                                         _ListItem._index == index)))[0]

    def _delListItem(self, index, resetIndexes=True):
        for li in self.store.query(_ListItem,
                                   AND(_ListItem._container == self,
                                       _ListItem._index == index)):
            li.deleteFromStore(deleteObject=True)
            break

    def _fixIndex(self, index, truncate=False):
        """
        @param truncate: If true, negative indices which go past the
                         beginning of the list will be evaluated as zero.
                         For example::

                         >>> L = List([1,2,3,4,5])
                         >>> len(L)
                         5
                         >>> L._fixIndex(-9, truncate=True)
                         0
        """
        assert not isinstance(index, slice), 'slices are not supported (yet)'
        if index < 0:
            index += self.length
        if index < 0:
            if not truncate:
                raise IndexError('stored List index out of range')
            else:
                index = 0
        return index

    def __getitem__(self, index):
        index = self._fixIndex(index)
        return self._getListItem(index)._value

    def __setitem__(self, index, value):
        index = self._fixIndex(index)
        self._getListItem(index)._value = value

    def __add__(self, other):
        return list(self) + list(other)
    def __radd__(self, other):
        return list(other) + list(self)

    def __mul__(self, other):
        return list(self) * other
    def __rmul__(self, other):
        return other * list(self)

    def index(self, other, start=0, maximum=None):
        if maximum is None:
            maximum = len(self)
        for pos in range(start, maximum):
            if pos >= len(self):
                break
            if self[pos] == other:
                return pos
        raise ValueError('List.index(x): %r not in List' % other)

    def __len__(self):
        return self.length

    def __delitem__(self, index):
        assert not isinstance(index, slice), 'slices are not supported (yet)'
        self._getListItem(index).deleteFromStore()
        if index < self.length - 1:
            for item in self.store.query(_ListItem, AND(
                    _ListItem._container == self, _ListItem._index > index)):
                item._index -= 1
        self.length -= 1

    def __contains__(self, value):
        return bool(self.count(value))

    def append(self, value):
        """
        @type value: L{axiom.item.Item}
        @param value: Must be stored in the same L{Store<axiom.store.Store>}
                      as this L{List} instance.
        """
        # XXX: Should List.append(unstoredItem) automatically store the item?
        self.insert(self.length, value)

    def extend(self, other):
        for item in iter(other):
            self.append(item)

    def insert(self, index, value):
        index = self._fixIndex(index, truncate=True)
        # If we do List(length=5).insert(50, x), we don't want
        # x's _ListItem._index to actually be 50.
        index = min(index, self.length)
        # This uses list() in case our contents change halfway through.
        # But does that _really_ work?
        for li in list(self.store.query(_ListItem,
                                        AND(_ListItem._container == self,
                                            _ListItem._index >= index))):
            # XXX: The performance of this operation probably sucks
            # compared to what it would be with an UPDATE.
            li._index += 1
        _ListItem(store=self.store,
                  _value=value,
                  _container=self,
                  _index=index)
        self.length += 1

    def pop(self, index=None):
        if index is None:
            index = self.length - 1
        index = self._fixIndex(index)
        x = self[index]
        del self[index]
        return x

    def remove(self, value):
        del self[self.index(value)]

    def reverse(self):
        # XXX: Also needs to be an atomic action.
        length = 0
        for li in list(self.store.query(_ListItem,
                                        _ListItem._container == self,
                                        sort=_ListItem._index.desc)):
            li._index = length
            length += 1
        self.length = length

    def sort(self, *args):
        # We want to sort by value, not sort by _ListItem.  We could
        # accomplish this by having _ListItem.__cmp__ do something
        # with self._value, but that seemed wrong. This was easier.
        values = [li._value for li in self._queryListItems()]
        values.sort(*args)
        index = 0
        for li in self._queryListItems():
            # XXX: Well, can it?
            assert index < len(values), \
                   '_ListItems were added during a sort (can this happen?)'
            li._index = index
            li._value = values[index]
            index += 1

    def count(self, value):
        return self.store.count(_ListItem, AND(
                _ListItem._container == self, _ListItem._value == value))
