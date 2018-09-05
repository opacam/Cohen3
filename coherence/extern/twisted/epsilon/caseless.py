# -*- test-case-name: epsilon.test.test_caseless -*-
"""
Helpers for case-insensitive string handling.
"""


class Caseless(object):
    """
    Case-insensitive string wrapper type.

    This wrapper is intended for use with strings that have case-insensitive
    semantics, such as HTTP/MIME header values.  It implements comparison-based
    operations case-insensitively, avoiding the need to manually call C{lower}
    where appropriate, or keep track of which strings are case-insensitive
    throughout various function calls.

    Example usage:

        >>> Caseless('Spam') == Caseless('spam')
        True
        >>> 'spam' in Caseless('Eggs and Spam')
        True

        >>> sorted(['FOO', 'bar'], key=Caseless)
        ['bar', 'FOO']

        >>> d = {Caseless('Content-type'): Caseless('Text/Plain')}
        >>> d[Caseless('Content-Type')].startswith('text/')
        True

    Note:  String methods that return modified strings (such as
    C{decode}/C{encode}, C{join}, C{partition}, C{replace}, C{strip}/C{split})
    don't have an unambiguous return types with regards to case sensitivity, so
    they are not implemented by L{Caseless}.  They should be accessed on the
    underlying cased string instead.  (Excepted are methods like
    C{lower}/C{upper}, whose return case is unambiguous.)

    @ivar cased:  the wrapped string-like object
    """

    def __init__(self, cased):
        if isinstance(cased, Caseless):
            cased = cased.cased
        self.cased = cased

    def __repr__(self):
        return '%s(%r)' % (type(self).__name__, self.cased)

    # Methods delegated to cased
    def __str__(self):
        return str(self.cased)

    def __unicode__(self):
        return str(self.cased)

    def __len__(self):
        return len(self.cased)

    def __getitem__(self, key):
        return self.cased[key]

    def __iter__(self):
        return iter(self.cased)

    def lower(self):
        return self.cased.lower()

    def upper(self):
        return self.cased.upper()

    def title(self):
        return self.cased.title()

    def swapcase(self):
        return self.cased.swapcase()

    # Methods delegated to lower()
    # def __cmp__(self, other):
    #     return cmp(self.lower(), other.lower())

    def __eq__(self, other):
        return self.lower() == other.lower()

    def __ne__(self, other):
        return self.lower() != other.lower()

    def __lt__(self, other):
        return self.lower() < other.lower()

    def __le__(self, other):
        return self.lower() <= other.lower()

    def __gt__(self, other):
        return self.lower() > other.lower()

    def __ge__(self, other):
        return self.lower() >= other.lower()

    def __hash__(self):
        return hash(self.lower())

    def __contains__(self, substring):
        return substring.lower() in self.lower()

    def startswith(self, prefix, *rest):
        if isinstance(prefix, tuple):
            lprefix = tuple(s.lower() for s in prefix)
        else:
            lprefix = prefix.lower()
        return self.lower().startswith(lprefix, *rest)

    def endswith(self, suffix, *rest):
        if isinstance(suffix, tuple):
            lsuffix = tuple(s.lower() for s in suffix)
        else:
            lsuffix = suffix.lower()
        return self.lower().endswith(lsuffix, *rest)

    def count(self, substring, *rest):
        return self.lower().count(substring.lower(), *rest)

    def find(self, substring, *rest):
        return self.lower().find(substring.lower(), *rest)

    def index(self, substring, *rest):
        return self.lower().index(substring.lower(), *rest)

    def rfind(self, substring, *rest):
        return self.lower().rfind(substring.lower(), *rest)

    def rindex(self, substring, *rest):
        return self.lower().rindex(substring.lower(), *rest)
