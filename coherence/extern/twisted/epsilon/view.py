# -*- test-case-name: epsilon.test.test_view -*-

"""
Utility functionality for creating wrapping sequences so as to transform
their indices in some manner.
"""


class SlicedView(object):
    """
    Wrapper around a sequence which allows indexing and non-extended
    slicing, adjusting all indices using a transformation defined by a
    L{slice} object.

    For example::

        s = ['a', 'b']
        t = SlicedView(s, slice(1, None))
        t[0] == 'b'

    @ivar sequence: The underlying sequence from which to retrieve elements.
    @ivar bounds: A C{slice} instance defining the boundaries of this view.
    """

    def __init__(self, sequence, bounds):
        self.sequence = sequence
        self.bounds = bounds

    def _getIndices(self):
        start, stop, step = self.bounds.indices(len(self.sequence))
        indices = range(start, stop, step)
        return indices

    def __getitem__(self, index):
        """
        Compute the index in the underlying sequence of the given view index
        and return the corresponding element.

        @raise IndexError: If C{index} is out of bounds for the view.
        @raise ValueError: If C{self.bounds} is out of bounds for
        C{self.sequence}.
        """
        if isinstance(index, slice):
            return SlicedView(self, index)
        return self.sequence[self._getIndices()[index]]

    def __len__(self):
        """
        Compute the length of this view onto the sequence and return it.
        """
        return len(self._getIndices())
