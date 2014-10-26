# Copyright (c) 2014 Canonical Ltd
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import os
import multiprocessing

from oslo.config import cfg
import psutil

from nova.openstack.common.gettextutils import _   # noqa
from nova.openstack.common import log as logging

CONF = cfg.CONF

log = logging.getLogger(__name__)

def get_memory_info(meminfo="/proc/meminfo", unit='mB'):
    # read a /proc/meminfo style file and return
    # a dict with 'total', 'free', and 'used'
    mpliers = {'kB': 2**10, 'mB': 2 ** 20, 'B': 1, 'gB': 2 ** 30}
    data = {}
    with open(meminfo, "r") as fp:
        for line in fp:
            try:
                key, value, kunit = line.split()
            except ValueError:
                key, value = line.split()
                kunit = 'B'
            key = key[:-1]  # remove trailing ':'
            data[key] = int(value) * mpliers[kunit]

    if 'MemAvailable' in data:
        free = data['MemAvailable']
    else:
        free = data['MemFree'] + data['Cached']

    return {'total': data['MemTotal'] / mpliers[unit],
            'free': free / mpliers[unit],
            'used': (data['MemTotal'] - free) / mpliers[unit]}

def get_disk_info():
    st = os.statvfs(CONF.instances_path)
    return {
        'total': st.f_blocks * st.f_frsize,
        'available': st.f_bavail * st.f_frsize,
        'used': (st.f_blocks - st.f_bfree) * st.f_frsize
    }

def get_cpu_count():
    return multiprocessing.cpu_count()
