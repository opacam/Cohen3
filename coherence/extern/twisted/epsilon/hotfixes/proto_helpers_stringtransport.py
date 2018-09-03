from twisted.test import proto_helpers


class StringTransport:

    def write(self, data):
        if isinstance(data, str): # no, really, I mean it
            raise TypeError("Data must not be unicode")
        self.io.write(data)


def install():
    proto_helpers.StringTransport.__dict__['write'] = StringTransport.__dict__['write']
