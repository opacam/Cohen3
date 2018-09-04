# Copyright 2005 Divmod, Inc.  See LICENSE file for details
# -*- test-case-name: vertex.test.test_juice -*-

__metaclass__ = type

from twisted.internet.protocol import Protocol


class LineReceiver(Protocol):
    lineMode = True
    MAX_LINE_LENGTH = 1024 * 1024
    buffer = ''
    delimiter = '\r\n'

    def lineReceived(self, line):
        pass

    def rawDataReceived(self, data):
        pass

    def setLineMode(self, extra=''):
        self.lineMode = True
        if extra:
            self.dataReceived(extra)

    def isDisconnecting(self):
        if self.transport is None:
            # XXX This _ought_ to be horribly broken but in fact it is
            # not. TODO: Investigate further.  -glyph
            return False
        if self.transport.disconnecting:
            return True
        return False

    def setRawMode(self):
        self.lineMode = False

    def dataReceived(self, data):
        buffer = self.buffer
        buffer += data
        delimiter = self.delimiter
        begin = 0
        raw = False
        while self.lineMode:
            end = buffer.find(delimiter, begin)
            if end == -1:
                break
            line = buffer[begin:end]
            self.lineReceived(line)
            if self.isDisconnecting():
                self.buffer = ''
                return
            begin = end + len(delimiter)
        else:
            raw = True
        if begin:
            buffer = buffer[begin:]
        if raw:
            self.buffer = ''
            if self.isDisconnecting():
                return
            if buffer:
                self.rawDataReceived(buffer)
        else:
            self.buffer = buffer
