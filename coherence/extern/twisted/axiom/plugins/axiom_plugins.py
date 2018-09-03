# Copyright (c) 2008 Divmod.  See LICENSE for details.

"""
Plugins provided by Axiom for Axiom.
"""

import getpass
import code, os, traceback, sys
try:
    import readline
except ImportError:
    readline = None

from zope.interface import directlyProvides

from twisted.python import usage, filepath, log
from twisted.python.reflect import qual
from twisted.plugin import IPlugin

from coherence.extern.twisted.epsilon.hotfix import require
require('twisted', 'filepath_copyTo')

import coherence.extern.twisted.axiom as axiom
from coherence.extern.twisted.axiom import store, attributes, userbase, dependency, errors
from coherence.extern.twisted.axiom.substore import SubStore
from coherence.extern.twisted.axiom.scripts import axiomatic
from coherence.extern.twisted.axiom.listversions import ListVersions
from coherence.extern.twisted.axiom import version
from coherence.extern.twisted.axiom.iaxiom import IVersion

directlyProvides(version, IPlugin, IVersion)

#placate pyflakes
ListVersions


class Upgrade(axiomatic.AxiomaticCommand):
    name = 'upgrade'
    description = 'Synchronously upgrade an Axiom store and substores'

    optParameters = [
        ('count', 'n', '100', 'Number of upgrades to perform per transaction')]

    errorMessageFormat = 'Error upgrading item (with typeName=%s and storeID=%d) from version %d to %d.'

    def upgradeEverything(self, store):
        """
        Upgrade all the items in C{store}.
        """
        for dummy in store._upgradeManager.upgradeBatch(self.count):
            pass

    def upgradeStore(self, store):
        """
        Recursively upgrade C{store}.
        """
        self.upgradeEverything(store)

        for substore in store.query(SubStore):
            self.upgradeStore(substore.open())

    def perform(self, store, count):
        """
        Upgrade C{store} performing C{count} upgrades per transaction.

        Also, catch any exceptions and print out something useful.
        """
        self.count = count

        try:
            self.upgradeStore(store)
            print('Upgrade complete')
        except errors.ItemUpgradeError as e:
            print('Upgrader error:')
            e.originalFailure.printTraceback(file=sys.stdout)
            print(self.errorMessageFormat % (
                e.oldType.typeName, e.storeID, e.oldType.schemaVersion,
                e.newType.schemaVersion))

    def postOptions(self):
        try:
            count = int(self['count'])
        except ValueError:
            raise usage.UsageError('count must be an integer')

        siteStore = self.parent.getStore()
        self.perform(siteStore, count)


class AxiomConsole(code.InteractiveConsole):
    def runcode(self, code):
        """
        Override L{code.InteractiveConsole.runcode} to run the code in a
        transaction unless the local C{autocommit} is currently set to a true
        value.
        """
        if not self.locals.get('autocommit', None):
            return self.locals['db'].transact(code.InteractiveConsole.runcode, self, code)
        return code.InteractiveConsole.runcode(self, code)


class Browse(axiomatic.AxiomaticCommand):
    synopsis = "[options]"

    name = 'browse'
    description = 'Interact with an Axiom store.'

    optParameters = [
        ('history-file', 'h', '~/.axiomatic-browser-history',
         'Name of the file to which to save input history.'),
        ]

    optFlags = [
        ('debug', 'b', 'Open Store in debug mode.'),
        ]

    def postOptions(self):
        interp = code.InteractiveConsole(self.namespace(), '<axiom browser>')
        historyFile = os.path.expanduser(self['history-file'])
        if readline is not None and os.path.exists(historyFile):
            readline.read_history_file(historyFile)
        try:
            interp.interact("%s.  Autocommit is off." % (str(axiom.version),))
        finally:
            if readline is not None:
                readline.write_history_file(historyFile)

    def namespace(self):
        """
        Return a dictionary representing the namespace which should be
        available to the user.
        """
        self._ns = {
            'db': self.store,
            'store': store,
            'autocommit': False,
            }
        return self._ns


class UserbaseMixin:
    def installOn(self, other):
        # XXX check installation on other, not store
        for ls in self.store.query(userbase.LoginSystem):
            raise usage.UsageError("UserBase already installed")
        else:
            ls = userbase.LoginSystem(store=self.store)
            dependency.installOn(ls, other)
            return ls


class Install(axiomatic.AxiomaticSubCommand, UserbaseMixin):
    def postOptions(self):
        self.installOn(self.store)


class Create(axiomatic.AxiomaticSubCommand, UserbaseMixin):
    synopsis = "<username> <domain> [password]"

    def parseArgs(self, username, domain, password=None):
        self['username'] = self.decodeCommandLine(username)
        self['domain'] = self.decodeCommandLine(domain)
        self['password'] = password

    def postOptions(self):
        msg = 'Enter new AXIOM password: '
        while not self['password']:
            password = getpass.getpass(msg)
            second = getpass.getpass('Repeat to verify: ')
            if password == second:
                self['password'] = password
            else:
                msg = 'Passwords do not match.  Enter new AXIOM password: '
        self.addAccount(
            self.store, self['username'], self['domain'], self['password'])

    def addAccount(self, siteStore, username, domain, password):
        """
        Create a new account in the given store.

        @param siteStore: A site Store to which login credentials will be
        added.
        @param username: Local part of the username for the credentials to add.
        @param domain: Domain part of the username for the credentials to add.
        @param password: Password for the credentials to add.
        @rtype: L{LoginAccount}
        @return: The added account.
        """
        for ls in siteStore.query(userbase.LoginSystem):
            break
        else:
            ls = self.installOn(siteStore)
        try:
            acc = ls.addAccount(username, domain, password)
        except userbase.DuplicateUser:
            raise usage.UsageError("An account by that name already exists.")
        return acc


class Disable(axiomatic.AxiomaticSubCommand):
    synopsis = "<username> <domain>"

    def parseArgs(self, username, domain):
        self['username'] = self.decodeCommandLine(username)
        self['domain'] = self.decodeCommandLine(domain)

    def postOptions(self):
        for acc in self.store.query(userbase.LoginAccount,
                                    attributes.AND(userbase.LoginAccount.username == self['username'],
                                                   userbase.LoginAccount.domain == self['domain'])):
            if acc.disabled:
                raise usage.UsageError("That account is already disabled.")
            else:
                acc.disabled = True
                break
        else:
            raise usage.UsageError("No account by that name exists.")


class List(axiomatic.AxiomaticSubCommand):
    def postOptions(self):
        acc = None
        for acc in self.store.query(userbase.LoginMethod):
            if acc.domain is None:
                print(acc.localpart, end=' ')
            else:
                print(acc.localpart + '@' + acc.domain, end=' ')
            if acc.account.disabled:
                print('[DISABLED]')
            else:
                print()
        if acc is None:
            print('No accounts')


class UserBaseCommand(axiomatic.AxiomaticCommand):
    name = 'userbase'
    description = 'LoginSystem introspection and manipulation.'

    subCommands = [
        ('install', None, Install, "Install UserBase on an Axiom database"),
        ('create', None, Create, "Create a new user"),
        ('disable', None, Disable, "Disable an existing user"),
        ('list', None, List, "List users in an Axiom database"),
        ]

    def getStore(self):
        return self.parent.getStore()


class Extract(axiomatic.AxiomaticCommand):
    name = 'extract-user'
    description = 'Remove an account from the login system, moving its associated database to the filesystem.'
    optParameters = [
        ('address', 'a', None, 'localpart@domain-format identifier of the user store to extract.'),
        ('destination', 'd', None, 'Directory into which to extract the user store.')]

    def extractSubStore(self, localpart, domain, destinationPath):
        siteStore = self.parent.getStore()
        la = siteStore.findFirst(
            userbase.LoginMethod,
            attributes.AND(userbase.LoginMethod.localpart == localpart,
                           userbase.LoginMethod.domain == domain)).account
        userbase.extractUserStore(la, destinationPath)

    def postOptions(self):
        localpart, domain = self.decodeCommandLine(self['address']).split('@', 1)
        destinationPath = filepath.FilePath(
            self.decodeCommandLine(self['destination'])).child(localpart + '@' + domain + '.axiom')
        self.extractSubStore(localpart, domain, destinationPath)


class Insert(axiomatic.AxiomaticCommand):
    name = 'insert-user'
    description = 'Insert a user store, such as one extracted with "extract-user", into a site store and login system.'
    optParameters = [
        ('userstore', 'u', None, 'Path to user store to be inserted.')
        ]

    def postOptions(self):
        userbase.insertUserStore(self.parent.getStore(),
                                 filepath.FilePath(self.decodeCommandLine(self['userstore'])))
