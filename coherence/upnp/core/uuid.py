# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php
#
# Copyright 2005, Tim Potter <tpot@samba.org>
# Copyright 2006, Frank Scholz <coherence@beebits.net>
# Copyright 2013, Hartmut Goebel <h.goebel@crazy-compilers.com>
#

import uuid


class UUID:

    def __init__(self):
        self.uuid = 'uuid:' + str(uuid.uuid4())

    def __repr__(self):
        return self.uuid
