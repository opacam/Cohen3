# -*- test-case-name: epsilon.test.test_setuphelper -*-

# For great justice, take off every zig.
import sys, os, pprint, traceback

from distutils.core import setup


def pluginModules(moduleNames):
    from twisted.python.reflect import namedAny
    for moduleName in moduleNames:
        try:
            yield namedAny(moduleName)
        except ImportError:
            pass
        except ValueError as ve:
            if ve.args[0] != 'Empty module name':
                traceback.print_exc()
        except:
            traceback.print_exc()


def _regeneratePluginCache(pluginPackages):
    print('Regenerating cache with path: ', end=' ')
    pprint.pprint(sys.path)
    from twisted import plugin
    for pluginModule in pluginModules([
        p + ".plugins" for p in pluginPackages]):
        # Not just *some* zigs, mind you - *every* zig:
        print('Full plugin list for %r: ' % (pluginModule.__name__))
        pprint.pprint(list(plugin.getPlugins(plugin.IPlugin, pluginModule)))


def regeneratePluginCache(dist, pluginPackages):
    if 'install' in dist.commands:
        sys.path.insert(0, os.path.abspath(dist.command_obj['install'].install_lib))
        _regeneratePluginCache(pluginPackages)


def autosetup(**kw):
    packages = []
    datafiles = {}
    pluginPackages = []

    for (dirpath, dirnames, filenames) in os.walk(os.curdir):
        dirnames[:] = [p for p in dirnames if not p.startswith('.')]
        pkgName = dirpath[2:].replace('/', '.')
        if '__init__.py' in filenames:
            # The current directory is a Python package
            packages.append(pkgName)
        elif 'plugins' in dirnames:
            # The current directory is for the Twisted plugin system
            pluginPackages.append(pkgName)
            packages.append(pkgName)

    for package in packages:
        if '.' in package:
            continue
        D = datafiles[package] = []
        print('Files in package %r:' % (package,))
        pprint.pprint(os.listdir(package))
        for (dirpath, dirnames, filenames) in os.walk(package):
            dirnames[:] = [p for p in dirnames if not p.startswith('.')]
            for filename in filenames:
                if filename == 'dropin.cache':
                    continue
                if (os.path.splitext(filename)[1] not in ('.py', '.pyc', '.pyo')
                    or '__init__.py' not in filenames):
                    D.append(os.path.join(dirpath[len(package)+1:], filename))
    autoresult = {
        'packages': packages,
        'package_data': datafiles,
        }
    print('Automatically determined setup() args:')
    pprint.pprint(autoresult, indent=4)
    assert 'packages' not in kw
    assert 'package_data' not in kw
    kw.update(autoresult)
    distobj = setup(**kw)
    regeneratePluginCache(distobj, pluginPackages)
    return distobj
