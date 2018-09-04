# Copyright (c) 2008 Divmod.  See LICENSE for details.

"""
Package for plugins for interfaces in Axiom.
"""

from coherence.extern.twisted.epsilon.hotfix import require

require('twisted', 'plugin_package_paths')

from twisted.plugin import pluginPackagePaths

__path__.extend(pluginPackagePaths(__name__))
__all__ = []
