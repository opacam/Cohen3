"""
failUnlessWarns assertion from twisted.trial in Twisted 8.0.
"""

import warnings


def failUnlessWarns(self, category, message, filename, f,
                    *args, **kwargs):
    """
    Fail if the given function doesn't generate the specified warning when
    called. It calls the function, checks the warning, and forwards the
    result of the function if everything is fine.

    @param category: the category of the warning to check.
    @param message: the output message of the warning to check.
    @param filename: the filename where the warning should come from.
    @param f: the function which is supposed to generate the warning.
    @type f: any callable.
    @param args: the arguments to C{f}.
    @param kwargs: the keywords arguments to C{f}.

    @return: the result of the original function C{f}.
    """
    warningsShown = []

    def warnExplicit(*args):
        warningsShown.append(args)

    origExplicit = warnings.warn_explicit
    try:
        warnings.warn_explicit = warnExplicit
        result = f(*args, **kwargs)
    finally:
        warnings.warn_explicit = origExplicit

    if not warningsShown:
        self.fail("No warnings emitted")
    first = warningsShown[0]
    for other in warningsShown[1:]:
        if other[:2] != first[:2]:
            self.fail("Can't handle different warnings")
    gotMessage, gotCategory, gotFilename, lineno = first[:4]
    self.assertEqual(gotMessage, message)
    self.assertIdentical(gotCategory, category)

    # Use starts with because of .pyc/.pyo issues.
    self.assertTrue(
        filename.startswith(gotFilename),
        'Warning in %r, expected %r' % (gotFilename, filename))

    # It would be nice to be able to check the line number as well, but
    # different configurations actually end up reporting different line
    # numbers (generally the variation is only 1 line, but that's enough
    # to fail the test erroneously...).
    # self.assertEqual(lineno, xxx)

    return result


def install():
    from twisted.trial.unittest import TestCase
    TestCase.failUnlessWarns = TestCase.assertWarns = failUnlessWarns
