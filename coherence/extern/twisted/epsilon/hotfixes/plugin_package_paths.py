# Copyright (c) 2007 Twisted Matrix Laboratories.
# Copyright (c) 2008 Divmod.
# See LICENSE for details.


import sys, os


def pluginPackagePaths(name):
    """
    Return a list of additional directories which should be searched for
    modules to be included as part of the named plugin package.

    @type name: C{str}
    @param name: The fully-qualified Python name of a plugin package, eg
        C{'twisted.plugins'}.

    @rtype: C{list} of C{str}
    @return: The absolute paths to other directories which may contain plugin
        modules for the named plugin package.
    """
    package = name.split('.')
    # Note that this may include directories which do not exist.  It may be
    # preferable to remove such directories at this point, rather than allow
    # them to be searched later on.
    #
    # Note as well that only '__init__.py' will be considered to make a
    # directory a package (and thus exclude it from this list).  This means
    # that if you create a master plugin package which has some other kind of
    # __init__ (eg, __init__.pyc) it will be incorrectly treated as a
    # supplementary plugin directory.
    return [
        os.path.abspath(os.path.join(x, *package))
        for x
        in sys.path
        if
        not os.path.exists(os.path.join(x, *package + ['__init__.py']))]


def install():
    import twisted.plugin
    twisted.plugin.pluginPackagePaths = pluginPackagePaths
