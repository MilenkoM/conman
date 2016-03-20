"""A configuration management class built on top of etcd

See:  http://python-etcd.readthedocs.org/

It provides a read-only access and just exposes a nested dict
"""
import functools
from threading import Thread

import etcd
import time
from conman.conman_base import ConManBase


def thrice(delay=0.5):
    """This decorator tries failed operations 3 times before it gives up

    The delay determines how long to wait between tries (in seconds)
    """
    def decorated(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            for i in xrange(3):
                try:
                    return f(*args, **kwargs)
                except Exception:
                    if i == 2:
                        raise
                    time.sleep(delay)
        return wrapped
    return decorated


class ConManEtcd(ConManBase):
    def __init__(self,
                 host='127.0.0.1',
                 port=4001,
                 allow_reconnect=True,
                 on_change=lambda x: None):
        ConManBase.__init__(self)
        self._connect(host, port, allow_reconnect)
        self.on_change = on_change
        self.watchers = {}

    @thrice()
    def _connect(self, host, port, allow_reconnect):
        self.client = etcd.Client(
            host=host,
            port=port,
            allow_reconnect=allow_reconnect)

    def _add_key_recursively(self, target, key, etcd_result):
        if key.startswith('/'):
            key = key[1:]
        if etcd_result.value:
            target[key] = etcd_result.value
        else:
            target[key] = {}
            target = target[key]
            for c in etcd_result.children:
                k = c.key.split('/')[-1]
                self._add_key_recursively(target, k, c)

    def _watch(self, key):
        def watch_key():
            try:
                self.on_change(key)
            except Exception as e:  # noqa
                pass
            self._watch(key)
        t = Thread(target=watch_key).start()
        self.watchers[key] = t

    def add_key(self, key):
        """Add a key to managed etcd keys and store its data

        :param key: the etcd path

        When a key is added all its data is stored as a dict
        """
        etcd_result = self.client.read(key, recursive=True, sorted=True)
        self._add_key_recursively(self._conf, key, etcd_result)
        self._watch(key)

    def refresh(self, key=None):
        """Refresh an existing key or all keys

        :param key: the key to refresh (if None refresh all keys)

        If the key parameter doesn't exist an exception will be raised
        """
        keys = [key] if key else self._conf.keys()
        for k in keys:
            self.add_key(k)

