# -*- test-case-name: epsilon.test.test_descriptor -*-

"""
Provides an 'attribute' class for one-use descriptors.
"""

attribute = None


class _MetaAttribute(type):
    def __new__(meta, name, bases, dict):
        # for reals, yo.
        for kw in ['get', 'set', 'delete']:
            if kw in dict:
                dict[kw] = staticmethod(dict[kw])
        secretClass = type.__new__(meta, name, bases, dict)
        if attribute is None:
            return secretClass
        return secretClass()


class attribute(object, metaclass=_MetaAttribute):
    """
    Convenience class for providing one-shot descriptors, similar to
    'property'.  For example:

        >>> from coherence.extern.twisted.epsilon.descriptor import attribute
        >>> class Dynamo(object):
        ...  class dynamic(attribute):
        ...   def get(self):
        ...    self.dynCount += 1
        ...    return self.dynCount
        ...   def set(self, value):
        ...    self.dynCount += value
        ...  dynCount = 0
        ...
        >>> d = Dynamo()
        >>> d.dynamic
        1
        >>> d.dynamic
        2
        >>> d.dynamic = 6
        >>> d.dynamic
        9
        >>> d.dynamic
        10
        >>> del d.dynamic
        Traceback (most recent call last):
            ...
        AttributeError: attribute cannot be removed
    """

    def __get__(self, oself, type):
        """
        Private implementation of descriptor interface.
        """
        if oself is None:
            return self
        return self.get(oself)

    def __set__(self, oself, value):
        """
        Private implementation of descriptor interface.
        """
        return self.set(oself, value)

    def __delete__(self, oself):
        """
        Private implementation of descriptor interface.
        """
        return self.delete(oself)

    def set(self, value):
        """
        Implement this method to provide attribute setting.  Default behavior
        is that attributes are not settable.
        """
        raise AttributeError('read only attribute')

    def get(self):
        """
        Implement this method to provide attribute retrieval.  Default behavior
        is that unset attributes do not have any value.
        """
        raise AttributeError('attribute has no value')

    def delete(self):
        """
        Implement this method to provide attribute deletion.  Default behavior
        is that attributes cannot be deleted.
        """
        raise AttributeError('attribute cannot be removed')


def requiredAttribute(requiredAttributeName):
    """
    Utility for defining attributes on base classes/mixins which require their
    values to be supplied by their derived classes.  C{None} is a common, but
    almost never suitable default value for these kinds of attributes, as it
    may cause operations in the derived class to fail silently in peculiar
    ways.  If a C{requiredAttribute} is accessed before having its value
    changed, a C{AttributeError} will be raised with a helpful error message.

    @param requiredAttributeName: The name of the required attribute.
    @type requiredAttributeName: C{str}

    Example:
        >>> from coherence.extern.twisted.epsilon.descriptor import requiredAttribute
        ...
        >>> class FooTestMixin:
        ...  expectedResult = requiredAttribute('expectedResult')
        ...
        >>> class BrokenFooTestCase(TestCase, FooTestMixin):
        ...  pass
        ...
        >>> brokenFoo = BrokenFooTestCase()
        >>> print brokenFoo.expectedResult
        Traceback (most recent call last):
            ...
        AttributeError: Required attribute 'expectedResult' has not been
                        changed from its default value on '<BrokenFooTestCase
                        instance>'.
        ...
        >>> class WorkingFooTestCase(TestCase, FooTestMixin):
        ...  expectedResult = 7
        ...
        >>> workingFoo = WorkingFooTestCase()
        >>> print workingFoo.expectedResult
        ... 7
        >>>
    """

    class RequiredAttribute(attribute):
        def get(self):
            if requiredAttributeName not in self.__dict__:
                raise AttributeError(
                    ('Required attribute %r has not been changed'
                     ' from its default value on %r' % (
                         requiredAttributeName, self)))
            return self.__dict__[requiredAttributeName]

        def set(self, value):
            self.__dict__[requiredAttributeName] = value

    return RequiredAttribute


__all__ = ['attribute', 'requiredAttribute']
