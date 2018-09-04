from traceback import print_exc
from weakref import ref

from twisted.python import log

from coherence.extern.twisted.axiom import iaxiom


class CacheFault(KeyError):
    """
    An item has fallen out of cache, but the weakref callback has not yet run.
    """


class CacheInconsistency(RuntimeError):
    """
    A key being cached is already present in the cache.
    """


def logErrorNoMatterWhat():
    try:
        log.msg("Exception in finalizer cannot be propagated")
        log.err()
    except:
        try:
            emergLog = open("WEAKREF_EMERGENCY_ERROR.log", 'a')
            print_exc(file=emergLog)
            emergLog.flush()
            emergLog.close()
        except:
            # Nothing can be done.  We can't get an emergency log file to write
            # to.  Don't bother.
            return


def createCacheRemoveCallback(cacheRef, key, finalizer):
    """
    Construct a callable to be used as a weakref callback for cache entries.

    The callable will invoke the provided finalizer, as well as removing the
    cache entry if the cache still exists and contains an entry for the given
    key.

    @type  cacheRef: L{weakref.ref} to L{FinalizingCache}
    @param cacheRef: A weakref to the cache in which the corresponding cache
        item was stored.

    @param key: The key for which this value is cached.

    @type  finalizer: callable taking 0 arguments
    @param finalizer: A user-provided callable that will be called when the
        weakref callback runs.
    """

    def remove(reference):
        # Weakref callbacks cannot raise exceptions or DOOM ensues
        try:
            finalizer()
        except:
            logErrorNoMatterWhat()
        try:
            cache = cacheRef()
            if cache is not None:
                if key in cache.data:
                    if cache.data[key] is reference:
                        del cache.data[key]
        except:
            logErrorNoMatterWhat()

    return remove


class FinalizingCache:
    """
    A cache that stores values by weakref.

    A finalizer is invoked when the weakref to a cached value is broken.

    @type data: L{dict}
    @ivar data: The cached values.
    """

    def __init__(self, _ref=ref):
        self.data = {}
        self._ref = _ref

    def cache(self, key, value):
        """
        Add an entry to the cache.

        A weakref to the value is stored, rather than a direct reference. The
        value must have a C{__finalizer__} method that returns a callable which
        will be invoked when the weakref is broken.

        @param key: The key identifying the cache entry.

        @param value: The value for the cache entry.
        """
        fin = value.__finalizer__()
        try:
            # It's okay if there's already a cache entry for this key as long
            # as the weakref has already been broken. See the comment in
            # get() for an explanation of why this might happen.
            if self.data[key]() is not None:
                raise CacheInconsistency(
                    "Duplicate cache key: %r %r %r" % (
                        key, value, self.data[key]))
        except KeyError:
            pass
        callback = createCacheRemoveCallback(self._ref(self), key, fin)
        self.data[key] = self._ref(value, callback)
        return value

    def uncache(self, key, value):
        """
        Remove a key from the cache.

        As a sanity check, if the specified key is present in the cache, it
        must have the given value.

        @param key: The key to remove.

        @param value: The expected value for the key.
        """
        try:
            assert self.get(key) is value
            del self.data[key]
        except KeyError:
            # If the entry has already been removed from the cache, this will
            # result in KeyError which we ignore. If the entry is still in the
            # cache, but the weakref has been broken, this will result in
            # CacheFault (a KeyError subclass) which we also ignore. See the
            # comment in get() for an explanation of why this might happen.
            pass

    def get(self, key):
        """
        Get an entry from the cache by key.

        @raise KeyError: if the given key is not present in the cache.

        @raise CacheFault: (a L{KeyError} subclass) if the given key is present
            in the cache, but the value it points to is gone.
        """
        o = self.data[key]()
        if o is None:
            # On CPython, the weakref callback will always(?) run before any
            # other code has a chance to observe that the weakref is broken;
            # and since the callback removes the item from the dict, this
            # branch of code should never run. However, on PyPy (and possibly
            # other Python implementations), the weakref callback does not run
            # immediately, thus we may be able to observe this intermediate
            # state. Should this occur, we remove the dict item ourselves,
            # and raise CacheFault (which is a KeyError subclass).
            del self.data[key]
            raise CacheFault(
                "FinalizingCache has %r but its value is no more." % (key,))
        log.msg(interface=iaxiom.IStatEvent, stat_cache_hits=1, key=key)
        return o
