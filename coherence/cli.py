#!/usr/bin/env python

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2006,2007,2008 Frank Scholz <coherence@beebits.net>
# Copyright 2011, Hartmut Goebel <h.goebel@goebel-consult.de>
# Copyright 2020, Pol Canelles <canellestudi@gmail.com>

"""
Cohen is a framework to host DLNA/UPnP devices.

For more information about it and its available backends  point your browser
to: https://opacam.github.io/Cohen3/
"""

import errno
import optparse
import os
import sys
import traceback
import warnings

from configobj import ConfigObj

from coherence import __version__
from coherence.base import Coherence, Plugins

warnings.filterwarnings("ignore", "extern.louie will soon be deprecated")
warnings.filterwarnings("ignore", "coherence.extern.inotify is deprecated.")


def daemonize():
    # thankfully taken from twisted.scripts._twistd_unix.py
    # See http://www.erlenstar.demon.co.uk/unix/faq_toc.html#TOC16
    if os.fork():  # launch child and...
        os._exit(0)  # kill off parent
    os.setsid()
    if os.fork():  # launch child and...
        os._exit(0)  # kill off parent again.
    os.umask(0o77)
    null = os.open("/dev/null", os.O_RDWR)
    for i in range(3):
        try:
            os.dup2(null, i)
        except OSError as e:
            if e.errno != errno.EBADF:
                raise
    os.close(null)


def get_config_file():
    config_dir = os.path.expanduser("~")
    if config_dir == "~":
        config_dir = os.getcwd()

    return os.path.join(config_dir, ".cohen3")


def __opt_option(option, opt, value, parser):
    try:
        key, val = value.split(":", 1)
    except:
        key = value
        val = ""
    parser.values.options[key] = val


class OptionParser(optparse.OptionParser):
    """
    Simple wrapper to add list of available plugins to help
    message, but only if help message is really printed.
    """

    def print_help(self, file=None):
        # hack: avoid plugins are displaying there help message
        sys.argv = sys.argv[:1]
        p = list(Plugins().keys())
        p.sort()
        self.epilog = f'Available backends are: {", ".join(p)}'
        optparse.OptionParser.print_help(self, file)


def get_parser():
    """
    Create an `OptionParser` object with the proper options to initialize an
    instance of a :class:`coherence.Coherence`.
     """
    parser = OptionParser("%prog [options]", version=f"Version: {__version__}")
    parser.add_option("-d", "--daemon", action="store_true", help="daemonize")
    parser.add_option(
        "--noconfig",
        action="store_false",
        dest="configfile",
        help="ignore any configfile found",
    )
    parser.add_option(
        "-c",
        "--configfile",
        default=get_config_file(),
        help="configfile to use, default: %default",
    )
    parser.add_option("-l", "--logfile", help="logfile to use")
    parser.add_option(
        "-o",
        "--option",
        action="callback",
        dest="options",
        metavar="NAME:VALUE",
        default={},
        callback=__opt_option,
        type="string",
        help="activate option (name and value separated by a "
        "colon (`:`), may be given multiple times)",
    )
    parser.add_option(
        "-p",
        "--plugins",
        action="append",
        help="activate plugins (may be given multiple times) "
        "Example: --plugin=backend:FSStore,name:MyCohen",
    )
    return parser


def process_plugins_for(config, options):
    """
    Given a `Coherence` configuration and an object of parsed options, returns
    the configuration based on the supplied options for the plugins.
    """
    plugins = config.get("plugin")
    if isinstance(plugins, dict):
        config["plugin"] = [plugins]
    if not plugins:
        plugins = config.get("plugins", None)
    if not plugins:
        config["plugin"] = []
        plugins = config["plugin"]

    while len(options.plugins) > 0:
        p = options.plugins.pop()
        plugin = {}
        plugin_conf = p.split(",")
        for pair in plugin_conf:
            pair = pair.split(":", 1)
            if len(pair) == 2:
                pair[0] = pair[0].strip()
                if pair[0] in plugin:
                    if not isinstance(plugin[pair[0]], list):
                        new_list = [plugin[pair[0]]]
                        plugin[pair[0]] = new_list
                    plugin[pair[0]].append(pair[1])
                else:
                    plugin[pair[0]] = pair[1]
        try:
            plugins.append(plugin)
        except AttributeError:
            print(
                "mixing commandline plugins and configfile "
                "does not work with the old config file format"
            )
    return config


def run_cohen3_on_twisted_loop():
    """
    Initialize a `Coherence` instance on a `twisted.internet.reactor`'s
    loop, depending on supplied arguments via `cli`.
    """
    parser = get_parser()
    options, args = parser.parse_args()
    if args:
        parser.error("takes no arguments")

    if options.daemon:
        try:
            daemonize()
        except:
            print(traceback.format_exc())

    config = {}

    if options.configfile:
        try:
            config = ConfigObj(options.configfile)
        except IOError:
            print("Config file %r not found, ignoring" % options.configfile)
            pass
    if "logging" not in config:
        config["logging"] = {}

    if options.logfile:
        config["logging"]["logfile"] = options.logfile

    # copy options passed by -o/--option into config
    for k, v in list(options.options.items()):
        if k == "logfile":
            continue
        config[k] = v

    if options.daemon:
        if config["logging"].get("logfile") is None:
            config["logging"]["level"] = "none"
            config["logging"].pop("logfile", None)

    if (
        config.get("use_dbus", "no") == "yes"
        or config.get("glib", "no") == "yes"
        or config.get("transcoding", "no") == "yes"
    ):
        try:
            from twisted.internet import glib2reactor

            glib2reactor.install()
        except AssertionError:
            print("error installing glib2reactor")

    if options.plugins:
        config = process_plugins_for(config, options)

    from twisted.internet import reactor

    reactor.callWhenRunning(Coherence, config)
    reactor.run()


def main():
    run_cohen3_on_twisted_loop()
