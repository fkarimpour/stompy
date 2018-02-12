import functools
import numpy as np
from collections import OrderedDict
import contextlib
import hashlib
import os
import pickle

# TODO: 
# caching may depend on the working directory -
# as it stands, it may think that the cache directory exists, but if
# the caller has changed directories, it won't find the files.
# not sure of the details, just noticed symptoms like this.
# 5/19/15.


class LRUDict(object):
    def __init__(self, *args, **kwds):
        self.size_limit = kwds.pop("size_limit", None)
        self.data = OrderedDict(*args, **kwds)
        self.check_size_limit()
  
    def __setitem__(self, key, value):
        if key in self.data:
            # remove, so that the new values is at the end
            del self[key]
        self.data[key] = value
        self.check_size_limit()
    def __delitem__(self,key):
        del self.data[key]
        
    def __getitem__(self,key):
        value = self.data[key]
        del self.data[key]
        self.data[key] = value
        return value

    def __len__(self):
        return len(self.data)

    def __str__(self):
        return str(self.data)
    def __repr__(self):
        return repr(self.data)
    def __contains__(self,k):
        return k in self.data
    
    def check_size_limit(self):
        if self.size_limit is not None:
            while len(self) > self.size_limit:
                # print "trimming LRU dict"
                self.data.popitem(last=False)

def memoize_key(*args,**kwargs):
    if 0: # old way
        return str(args) + str(kwargs)
    else:
        # new way - slower, but highly unlikely to get false positives
        return hashlib.md5(pickle.dumps( (args,kwargs) )).hexdigest()

def memoize(lru=None,cache_dir=None):
    """
    add as a decorator to classes, instance methods, regular methods
    to cache results.
    Setting memoize.disabled=True will globally disable caching, though new
    results will still be stored in cache
    passing lru as a positive integer will keep only the most recent
    values
    """
    if cache_dir is not None:
        cache_dir=os.path.abspath( cache_dir )

    def memoize1(obj):
        if lru is not None:
            cache = obj.cache = LRUDict(size_limit=lru)
        else:
            cache = obj.cache = {}

        if cache_dir is not None:
            if not os.path.exists(cache_dir):
                os.makedirs(cache_dir)
                
        @functools.wraps(obj)
        def memoizer(*args, **kwargs):
            recalc= memoizer.recalculate or memoize.recalculate
            key = memoize_key(args,**kwargs)
            value_src=None

            if cache_dir is not None:
                cache_fn=os.path.join(cache_dir,key)
            else:
                cache_fn=None

            if memoize.disabled or recalc or (key not in cache):
                if cache_fn and not (memoize.disabled or recalc):
                    if os.path.exists(cache_fn):
                        with open(cache_fn,'rb') as fp:
                            # print "Reading cache from file"
                            value=pickle.load(fp)
                            value_src='pickle'
                if not value_src:
                    value = obj(*args,**kwargs)
                    value_src='calculated'

                if not memoize.disabled:
                    cache[key]=value
                    if value_src is 'calculated' and cache_fn:
                        with open(cache_fn,'wb') as fp:
                            pickle.dump(value,fp,-1)
                            # print "Wrote cache to file"
            else:
                value = cache[key]
            return value
        # per-method recalculate flags -
        # this is somewhat murky - it depends on @functools passing
        # the original object through, since here memoizer is the return
        # value from functools.wraps, but in the body of memoizer it's
        # not clear whether memoizer is bound to the wrapped or unwrapped
        # function.
        memoizer.recalculate=False

        return memoizer
    return memoize1
memoize.recalculate=False # force recalculation, still store in cache.
memoize.disabled = False  # ignore the cache entirely, don't save new result

# returns a memoize which bases all relative path cache_dirs from
# a given location.  If the given location is a file, then use the dirname
# i.e. 
#  from memoize import memoize_in
#  memoize=memoize_in(__file__)
def memoizer_in(base):
    if os.path.isfile(base):
        base=os.path.dirname(base)
    def memoize_in_path(lru=None,cache_dir=None):
        if cache_dir is not None:
            cache_dir=os.path.join(base,cache_dir)
        return memoize(lru=lru,cache_dir=cache_dir)
    return memoize_in_path

@contextlib.contextmanager
def nomemo():
    saved=memoize.disabled
    memoize.disabled=True
    try:
        yield
    finally:
        memoize.disabled=saved