# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2013, Hartmut Goebel <h.goebel@crazy-compilers.com>

import io
import logging
import os
import sys
import traceback

loggers = {}
BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(8)

# The background is set with 40 plus the number of the color,
# and the foreground with 30

# These are the sequences need to get colored output
RESET_SEQ = "\033[0m"
COLOR_SEQ = "\033[1;%dm"
BOLD_SEQ = "\033[1m"


def formatter_message(message, use_color=True):
    if use_color:
        message = message.replace(
            "$RESET", RESET_SEQ).replace(
            "$BOLD", BOLD_SEQ)
    else:
        message = message.replace(
            "$RESET", "").replace(
            "$BOLD", "")
    return message


COLORS = {
    'WARNING': YELLOW,
    'INFO': WHITE,
    'DEBUG': BLUE,
    'CRITICAL': YELLOW,
    'ERROR': RED
}


class ColoredFormatter(logging.Formatter):
    def __init__(self, msg, use_color = True):
        logging.Formatter.__init__(self, msg)
        self.use_color = use_color

    def format(self, record):
        levelname = record.levelname
        if self.use_color and levelname in COLORS:
            levelname_color = \
                COLOR_SEQ % (30 + COLORS[levelname]) + levelname + RESET_SEQ
            record.levelname = levelname_color
        return logging.Formatter.format(self, record)


# LOG_FORMAT = '%(asctime)s %(levelname)s  %(name)s: %(message)s  (%(filename)s:%(lineno)s)'
# LOG_FORMAT = ('[%(levelname)-10s] [ %(name)-14s %(lineno)-5d] %(message)s')
LOG_FORMAT = ("[%(levelname)-18s][$BOLD%(name)-15s$RESET]  "
              "%(message)s    ($BOLD%(filename)s$RESET:%(lineno)d)")

ENV_VAR_NAME = 'COHEN_DEBUG'

# This is taken from std.-module logging, see Logger.findCaller below.
# _srcfile is used when walking the stack to check when we've got the first
# caller stack frame.
#
if hasattr(sys, 'frozen'):  # support for py2exe
    _srcfile = "coherence%slog%s" % (os.sep, __file__[-4:])
elif __file__[-4:].lower() in ['.pyc', '.pyo']:
    _srcfile = __file__[:-4] + '.py'
else:
    _srcfile = __file__
_srcfile = os.path.normcase(_srcfile)
_srcfiles = (_srcfile, logging._srcfile)


class ColoredLogger(logging.Logger):

    FORMAT = LOG_FORMAT
    COLOR_FORMAT = formatter_message(FORMAT, True)

    def __init__(self, name):
        logging.Logger.__init__(self, name, logging.DEBUG)

        color_formatter = ColoredFormatter(self.COLOR_FORMAT)

        console = logging.StreamHandler()
        console.setFormatter(color_formatter)

        # print(self.handlers)
        if console not in self.handlers:
            self.addHandler(console)
        # print(self.handlers)
        return


# class Logger(ColoredLogger):
#
    def findCaller(self, stack_info=False, use_color=True):
        """
        Find the stack frame of the caller so that we can note the source
        file name, line number and function name.
        """
        f = logging.currentframe()
        # On some versions of IronPython, currentframe() returns None if
        # IronPython isn't run with -X:Frames.
        if f is not None:
            f = f.f_back
        rv = "(unknown file)", 0, "(unknown function)", None
        while hasattr(f, "f_code"):
            co = f.f_code
            filename = os.path.normcase(co.co_filename)
            if filename in _srcfiles:
                f = f.f_back
                continue
            sinfo = None
            if stack_info:
                sio = io.StringIO()
                sio.write('Stack (most recent call last):\n')
                traceback.print_stack(f, file=sio)
                sinfo = sio.getvalue()
                if sinfo[-1] == '\n':
                    sinfo = sinfo[:-1]
                sio.close()
            rv = (co.co_filename, f.f_lineno, co.co_name, sinfo)
            break
        return rv


logging.setLoggerClass(ColoredLogger)


class Loggable(object):
    """
    Base class for objects that want to be able to log messages with
    different level of severity.  The levels are, in order from least
    to most: log, debug, info, warning, error.

    @cvar logCategory: Implementors can provide a category to log their
       messages under.
    """

    logCategory = 'default'
    _Loggable__logger = None

    FORMAT = LOG_FORMAT
    COLOR_FORMAT = formatter_message(FORMAT, True)

    def __init__(self):
        global loggers
        if loggers.get(self.logCategory):
            self._logger = loggers.get(self.logCategory)
        else:
            self._logger = logging.getLogger(self.logCategory)
            loggers[self.logCategory] = self._logger
            self.debug('Added logger with logCategory: {}'.format(
                self.logCategory))
        return

    def log(self, message, *args, **kwargs):
        self._logger.log(message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        self._logger.warning(message, *args, **kwargs)

    def info(self, message, *args, **kwargs):
        self._logger.info(message, *args, **kwargs)

    def critical(self, message, *args, **kwargs):
        self._logger.critical(message, *args, **kwargs)

    def debug(self, message, *args, **kwargs):
        self._logger.debug(message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        self._logger.error(message, *args, **kwargs)

    def exception(self, message, *args, **kwargs):
        self._logger.exception(message, *args, **kwargs)

    fatal = critical
    warn = warning
    msg = info


getLogger = logging.getLogger


def init(logfilename=None, loglevel=logging.WARN):
    global loggers
    if loggers.get('coherence'):
        return loggers.get('coherence')
    else:
        logger = logging.getLogger()
        logging.addLevelName(100, 'NONE')

        logging.basicConfig(
            filename=logfilename,
            level=loglevel,
            format=LOG_FORMAT)

        if ENV_VAR_NAME in os.environ:
            logger.setLevel(os.environ[ENV_VAR_NAME])
        else:
            logger.setLevel(loglevel)
        loggers['coherence'] = logger
        logger.debug('Added logger with logCategory: {}'.format('coherence'))
