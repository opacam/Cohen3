# -*- coding: utf-8 -*-
#
# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2008, Frank Scholz <coherence@beebits.net>

import os.path
from os import getenv

hot_dirs = {'XDG_MUSIC_DIR': ('audio', 'audio'),
            'XDG_PICTURES_DIR': ('image', 'images'),
            'XDG_VIDEOS_DIR': ('video', 'videos')}


def xdg_content():
    content = []
    xdg_config_home = os.path.expanduser(
        getenv('XDG_CONFIG_HOME', '~/.config'))
    user_dirs_file = os.path.join(xdg_config_home, 'user-dirs.dirs')
    if os.path.exists(user_dirs_file):
        f = open(user_dirs_file)
        for line in f.readlines():
            if not line.startswith('#'):
                line = line.strip()
                key, value = line.split('=')
                try:
                    info = hot_dirs[key]
                    value = value.strip('"')
                    value = os.path.expandvars(value)
                    content.append((value, info[0], info[1]))
                except KeyError:
                    pass
        f.close()

    if len(content) > 0:
        return content
    return None


if __name__ == '__main__':
    print(xdg_content())
