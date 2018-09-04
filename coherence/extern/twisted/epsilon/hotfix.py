import inspect


class NoSuchHotfix(Exception):
    """
    Man you must be pretty stupid.
    """


_alreadyInstalled = set()


def require(packageName, fixName):
    if (packageName, fixName) in _alreadyInstalled:
        return

    if (packageName, fixName) == ('twisted', 'filepath_copyTo'):
        from twisted.python import filepath
        if filepath.FilePath('a') != filepath.FilePath('a'):
            from coherence.extern.twisted.epsilon.hotfixes import \
                filepath_copyTo
            filepath_copyTo.install()
    elif (packageName, fixName) == ('twisted', 'timeoutmixin_calllater'):
        from twisted.protocols import policies
        if not hasattr(policies.TimeoutMixin, 'callLater'):
            from coherence.extern.twisted.epsilon.hotfixes import \
                timeoutmixin_calllater
            timeoutmixin_calllater.install()
    elif (packageName, fixName) == ('twisted', 'delayedcall_seconds'):
        from twisted.internet import base
        args = inspect.getargs(base.DelayedCall.__init__.__code__)[0]
        if 'seconds' not in args:
            from coherence.extern.twisted.epsilon.hotfixes import \
                delayedcall_seconds
            delayedcall_seconds.install()
    elif (packageName, fixName) == ('twisted', 'deferredgenerator_tfailure'):
        from twisted.internet import defer
        result = []

        def test():
            d = defer.waitForDeferred(defer.succeed(1))
            yield d
            result.append(d.getResult())

        defer.deferredGenerator(test)()
        if result == [1]:
            from coherence.extern.twisted.epsilon.hotfixes import \
                deferredgenerator_tfailure
            deferredgenerator_tfailure.install()
        else:
            assert result == [None]
    elif (packageName, fixName) == (
    "twisted", "proto_helpers_stringtransport"):
        from twisted.test.proto_helpers import StringTransport
        st = StringTransport()
        try:
            st.write('foo')
        except TypeError as e:
            pass
        else:
            from coherence.extern.twisted.epsilon.hotfixes import \
                proto_helpers_stringtransport
            proto_helpers_stringtransport.install()
    elif (packageName, fixName) == ("twisted", "internet_task_Clock"):
        from twisted.internet import base
        from twisted import version
        from coherence.extern.twisted.epsilon.hotfixes import \
            internet_task_clock
        if internet_task_clock.clockIsBroken():
            internet_task_clock.install()
    elif (packageName, fixName) == ("twisted", "trial_assertwarns"):
        from twisted.trial.unittest import TestCase
        if not hasattr(TestCase, "failUnlessWarns"):
            from coherence.extern.twisted.epsilon.hotfixes import \
                trial_assertwarns
            trial_assertwarns.install()
    elif (packageName, fixName) == ("twisted", "plugin_package_paths"):
        try:
            from twisted.plugin import pluginPackagePaths
        except ImportError:
            from coherence.extern.twisted.epsilon.hotfixes import \
                plugin_package_paths
            plugin_package_paths.install()
    elif (packageName, fixName) == ("twisted", "loopbackasync_reentrancy"):
        # This one is really hard to detect reasonably.  Invoking the code
        # involves triggering the reactor, which it would be good to avoid. 
        from twisted import version
        if (version.major, version.minor) < (8, 2):
            from coherence.extern.twisted.epsilon.hotfixes import \
                loopbackasync_reentrancy
            loopbackasync_reentrancy.install()
    else:
        raise NoSuchHotfix(packageName, fixName)

    _alreadyInstalled.add((packageName, fixName))
