'''
Functions related to creating repodata index files.

The way the icons work is the following:
  1. the iconda image is always stored in a file named info/icon.png
     inside the conda-package.
  2. when the index (repodata.json) is created this file is read, and
     instead of encoding the icons content in the repodata itself, a
     reference is created, for example (this is in repodata.json):
        "icon": "58c9e8a4a41c41dc796ffe680c1e02b5.png",
  3. running the index command also creats the icons folder (next to the
     platform specific directories)
'''

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
import bz2
import json
import base64
import hashlib
import tarfile
from io import open
from os.path import isdir, join, getmtime

from conda_build.utils import file_info
from conda.compat import iteritems, PY3


def read_index_tar(tar_path):
    with tarfile.open(tar_path) as t:
        info = json.loads(t.extractfile('info/index.json').read().decode('utf-8'))
        try:
            raw = t.extractfile('info/icon.png').read()
            info['_icondata'] = base64.b64encode(raw).decode('ASCII')
            info['_iconmd5'] = hashlib.md5(raw).hexdigest()
        except KeyError:
            pass
        return info

def write_repodata(repodata, dir_path):
    data = json.dumps(repodata, indent=2, sort_keys=True)
    # strip trailing whitespace
    data = '\n'.join(line.rstrip() for line in data.split('\n'))
    # make sure we have newline at the end
    if not data.endswith('\n'):
        data += '\n'
    with open(join(dir_path, 'repodata.json'), 'w', encoding='utf-8') as fo:
        fo.write(data)
    with open(join(dir_path, 'repodata.json.bz2'), 'wb') as fo:
        fo.write(bz2.compress(data.encode('utf-8')))

def update_index(dir_path, verbose=False, force=False):
    if verbose:
        print("updating index in:", dir_path)
    index_path = join(dir_path, '.index.json')
    if force:
        index = {}
    else:
        try:
            mode_dict = {'mode': 'r', 'encoding': 'utf-8'} if PY3 else {'mode': 'rb'}
            with open(index_path, **mode_dict) as fi:
                index = json.load(fi)
        except (IOError, ValueError):
            index = {}

    files = set(fn for fn in os.listdir(dir_path) if fn.endswith('.tar.bz2'))
    for fn in files:
        path = join(dir_path, fn)
        if fn in index and index[fn]['mtime'] == getmtime(path):
            continue
        if verbose:
            print('updating:', fn)
        d = read_index_tar(path)
        d.update(file_info(path))
        index[fn] = d

    # remove files from the index which are not on disk
    for fn in set(index) - files:
        if verbose:
            print("removing:", fn)
        del index[fn]
    # Deal with Python 2 and 3's different json module type reqs
    mode_dict = {'mode': 'w', 'encoding': 'utf-8'} if PY3 else {'mode': 'wb'}
    with open(index_path, **mode_dict) as fo:
        json.dump(index, fo, indent=2, sort_keys=True, default=str)

    # --- new repodata
    icons = {}
    for fn in index:
        info = index[fn]
        if '_icondata' in info:
            icons[info['_iconmd5']] = base64.b64decode(info['_icondata'])
            assert '%(_iconmd5)s.png' % info == info['icon']
        for varname in ('arch', 'platform', 'mtime', 'ucs',
                        '_icondata', '_iconmd5'):
            try:
                del info[varname]
            except KeyError:
                pass
    if icons:
        icons_dir = join(dir_path, 'icons')
        if not isdir(icons_dir):
            os.mkdir(icons_dir)
        for md5, raw in iteritems(icons):
            with open(join(icons_dir, '%s.png' % md5), 'wb') as fo:
                fo.write(raw)

    repodata = {'packages': index, 'info': {}}
    write_repodata(repodata, dir_path)
