"""Misc support code. 

Copyright (c) 2013 Clarinova. This file is licensed under the terms of the
Revised BSD License, included in this distribution as LICENSE.txt
"""

# Stolen from: http://code.activestate.com/recipes/498245-lru-and-lfu-cache-decorators/

import collections
import functools
from itertools import ifilterfalse
from heapq import nsmallest
from operator import itemgetter
import logging
import yaml
from collections import Mapping, OrderedDict, defaultdict
import os 

logger_init = set()

## {{{ http://code.activestate.com/recipes/52549/ (r3)
class curry:
    def __init__(self, fun, *args, **kwargs):
        self.fun = fun
        self.pending = args[:]
        self.kwargs = kwargs.copy()

    def __call__(self, *args, **kwargs):
        if kwargs and self.kwargs:
            kw = self.kwargs.copy()
            kw.update(kwargs)
        else:
            kw = kwargs or self.kwargs

        return self.fun(*(self.pending + args), **kw)
## end of http://code.activestate.com/recipes/52549/ }}}




def get_logger(name):
    
    logger = logging.getLogger(name)

    if  name not in logger_init:

        formatter = logging.Formatter("%(name)s %(levelname)s %(message)s")
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        #ch.setLevel(logging.DEBUG)
        logger.addHandler(ch)
        #logger.setLevel(logging.DEBUG) 
        
        logger_init.add(name)
     
    return logger


def rm_rf( d):
    """Recursively delete a directory"""
    
    if not os.path.exists(d):
        return
    
    for path in (os.path.join(d,f) for f in os.listdir(d)):
        if os.path.isdir(path):
            rm_rf(path)
        else:
            os.unlink(path)
    os.rmdir(d)

def bundle_file_type(path_or_file):
    '''Return a determination if the file is a sqlite file or a gzip file
    
    Args
        :param path: a string pathname to the file or stream to test
        :type path: a `str` object or file object
        
        :rtype: 'gzip' or 'sqlite' or None
    '''

    import struct

    try:
        loc = path_or_file.tell()
        d = path_or_file.read(15)
        path_or_file.seek(loc)
    except:
        d = None
        
    if not d:
        try:
            with open(path_or_file) as f:
                d = f.read(15)
        except:
            d = None
            
    if not d:
        if path_or_file.endswith('.db'):
            return 'sqlite'
        elif path_or_file.endswith('.gz'):
            return 'gzip'
        else:
            raise Exception("Can'y figure out file type")
    
    if d == 'SQLite format 3':
        return 'sqlite'
    elif hex(struct.unpack('!H',d[0:2])[0]) == '0x1f8b':
        return 'gzip'
    else:
        return None
        

        
class Counter(dict):
    'Mapping where default values are zero'
    def __missing__(self, key):
        return 0

def lru_cache(maxsize=100):
    '''Least-recently-used cache decorator.

    Arguments to the cached function must be hashable.
    Cache performance statistics stored in f.hits and f.misses.
    Clear the cache with f.clear().
    http://en.wikipedia.org/wiki/Cache_algorithms#Least_Recently_Used

    '''
    maxqueue = maxsize * 10
    def decorating_function(user_function,
            len=len, iter=iter, tuple=tuple, sorted=sorted, KeyError=KeyError): #@ReservedAssignment
        cache = {}                  # mapping of args to results
        queue = collections.deque() # order that keys have been used
        refcount = Counter()        # times each key is in the queue
        sentinel = object()         # marker for looping around the queue
        kwd_mark = object()         # separate positional and keyword args

        # lookup optimizations (ugly but fast)
        queue_append, queue_popleft = queue.append, queue.popleft
        queue_appendleft, queue_pop = queue.appendleft, queue.pop

        @functools.wraps(user_function)
        def wrapper(*args, **kwds):
            # cache key records both positional and keyword args
            key = args
            if kwds:
                key += (kwd_mark,) + tuple(sorted(kwds.items()))

            # record recent use of this key
            queue_append(key)
            refcount[key] += 1

            # get cache entry or compute if not found
            try:
                result = cache[key]
                wrapper.hits += 1
            except KeyError:
                result = user_function(*args, **kwds)
                cache[key] = result
                wrapper.misses += 1

                # purge least recently used cache entry
                if len(cache) > maxsize:
                    key = queue_popleft()
                    refcount[key] -= 1
                    while refcount[key]:
                        key = queue_popleft()
                        refcount[key] -= 1
                    del cache[key], refcount[key]

            # periodically compact the queue by eliminating duplicate keys
            # while preserving order of most recent access
            if len(queue) > maxqueue:
                refcount.clear()
                queue_appendleft(sentinel)
                for key in ifilterfalse(refcount.__contains__,
                                        iter(queue_pop, sentinel)):
                    queue_appendleft(key)
                    refcount[key] = 1


            return result

        def clear():
            cache.clear()
            queue.clear()
            refcount.clear()
            wrapper.hits = wrapper.misses = 0

        wrapper.hits = wrapper.misses = 0
        wrapper.clear = clear
        return wrapper
    return decorating_function


def lfu_cache(maxsize=100):
    '''Least-frequenty-used cache decorator.

    Arguments to the cached function must be hashable.
    Cache performance statistics stored in f.hits and f.misses.
    Clear the cache with f.clear().
    http://en.wikipedia.org/wiki/Least_Frequently_Used

    '''
    def decorating_function(user_function):
        cache = {}                      # mapping of args to results
        use_count = Counter()           # times each key has been accessed
        kwd_mark = object()             # separate positional and keyword args

        @functools.wraps(user_function)
        def wrapper(*args, **kwds):
            key = args
            if kwds:
                key += (kwd_mark,) + tuple(sorted(kwds.items()))
            use_count[key] += 1

            # get cache entry or compute if not found
            try:
                result = cache[key]
                wrapper.hits += 1
            except KeyError:
                result = user_function(*args, **kwds)
                cache[key] = result
                wrapper.misses += 1

                # purge least frequently used cache entry
                if len(cache) > maxsize:
                    for key, _ in nsmallest(maxsize // 10,
                                            use_count.iteritems(),
                                            key=itemgetter(1)):
                        del cache[key], use_count[key]

            return result

        def clear():
            cache.clear()
            use_count.clear()
            wrapper.hits = wrapper.misses = 0

        wrapper.hits = wrapper.misses = 0
        wrapper.clear = clear
        return wrapper
    return decorating_function

def patch_file_open():
    ''' A Monkey patch to log opening and closing of files, which is useful for debugging
    file descriptor exhaustion'''
    import __builtin__
    openfiles = set()
    oldfile = __builtin__.file
    class newfile(oldfile):
        def __init__(self, *args,**kwargs):
            self.x = args[0]
            print "### {} OPENING {} ###".format(len(openfiles), str(self.x))         
            oldfile.__init__(self, *args,**kwargs)
            openfiles.add(self)
    
        def close(self):
            print "### {} CLOSING {} ###".format(len(openfiles), str(self.x))
            oldfile.close(self)
            openfiles.remove(self)
            
    def newopen(*args,**kwargs):
        return newfile(*args,**kwargs)
    
    __builtin__.file = newfile
    __builtin__.open = newopen

#patch_file_open()

# From http://stackoverflow.com/questions/528281/how-can-i-include-an-yaml-file-inside-another
class YamlIncludeLoader(yaml.Loader):

    def __init__(self, stream):

        self._root = os.path.split(stream.name)[0]

        super(YamlIncludeLoader, self).__init__(stream)


# From http://pypi.python.org/pypi/layered-yaml-attrdict-config/12.07.1
class OrderedDictYAMLLoader(yaml.Loader):
    'Based on: https://gist.github.com/844388'

    def __init__(self, *args, **kwargs):
        yaml.Loader.__init__(self, *args, **kwargs)
        
        self.dir = None
        for a in args:
            try:
                self.dir = os.path.dirname(a.name)
            except: pass

        
        self.add_constructor(u'tag:yaml.org,2002:map', type(self).construct_yaml_map)
        self.add_constructor(u'tag:yaml.org,2002:omap', type(self).construct_yaml_map)
        self.add_constructor('!include', OrderedDictYAMLLoader.include)

    def construct_yaml_map(self, node):
        data = OrderedDict()
        yield data
        value = self.construct_mapping(node)
        data.update(value)

    def construct_mapping(self, node, deep=False):
        if isinstance(node, yaml.MappingNode):
            self.flatten_mapping(node)
        else:
            raise yaml.constructor.ConstructorError( None, None,
                'expected a mapping node, but found {}'.format(node.id), node.start_mark )

        mapping = OrderedDict()
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                hash(key)
            except TypeError, exc:
                raise yaml.constructor.ConstructorError( 'while constructing a mapping',
                    node.start_mark, 'found unacceptable key ({})'.format(exc), key_node.start_mark )
            value = self.construct_object(value_node, deep=deep)
            mapping[key] = value
        return mapping


    def include(self, node):
        from databundles.dbexceptions import ConfigurationError
        
        if not self.dir:   
            raise ConfigurationError("Can't include file: wasn't able to set base directory")

        filename = os.path.join(self.dir, self.construct_scalar(node))

        if not os.path.exists(filename):
            raise ConfigurationError("Can't include file '{}': Does not exist".format(filename))

        with open(filename, 'r') as f:
            
            parts = filename.split('.')
            ext = parts.pop()
            
            if ext == 'yaml':
                return yaml.load(f, OrderedDictYAMLLoader)
            else:
                return IncludeFile(filename, f.read())

# IncludeFile and include_representer ensures that when config files are re-written, they are
# represented as an include, not the contents of the include
class IncludeFile(str):
    
    def __new__(cls, filename, data):
        s =  str.__new__(cls,  data)
        s.filename = filename
        return s
        
    def __str__(self):
        return self.data
 
def include_representer(dumper, data):
    return dumper.represent_scalar(u'!include', data.filename)
    

# http://pypi.python.org/pypi/layered-yaml-attrdict-config/12.07.1
class AttrDict(OrderedDict):

    def __init__(self, *argz, **kwz):
        super(AttrDict, self).__init__(*argz, **kwz)

    def __setitem__(self, k, v):
        super(AttrDict, self).__setitem__( k,
            AttrDict(v) if isinstance(v, Mapping) else v )
    def __getattr__(self, k):
        if not (k.startswith('__') or k.startswith('_OrderedDict__')): 
            return self[k]
        else: 
            return super(AttrDict, self).__getattr__(k)
    def __setattr__(self, k, v):
        if k.startswith('_OrderedDict__'):
            return super(AttrDict, self).__setattr__(k, v)
        self[k] = v

    @classmethod
    def from_yaml(cls, path, if_exists=False):
        if if_exists and not os.path.exists(path): return cls()
        return cls(yaml.load(open(path), OrderedDictYAMLLoader))

    @staticmethod
    def flatten_dict(data, path=tuple()):
        dst = list()
        for k,v in data.iteritems():
            k = path + (k,)
            if isinstance(v, Mapping):
                for v in v.flatten(k): dst.append(v)
            else: dst.append((k, v))
        return dst

    def flatten(self, path=tuple()):
        return self.flatten_dict(self, path=path)


    def to_dict(self):
        root  = {}
        val = self.flatten()
        for k,v in val:
            dst = root
            for slug in k[:-1]:
                if dst.get(slug) is None:
                    dst[slug] = dict()
                dst = dst[slug]
            if v is not None or not isinstance(dst.get(k[-1]), Mapping ): 
                dst[k[-1]] = v

        return  root

    def update_flat(self, val):
        if isinstance(val, AttrDict): val = val.flatten()
        for k,v in val:
            dst = self
            for slug in k[:-1]:
                if dst.get(slug) is None:
                    dst[slug] = AttrDict()
                dst = dst[slug]
            if v is not None or not isinstance(dst.get(k[-1]), Mapping ): 
                dst[k[-1]] = v

    def update_yaml(self, path): 
        self.update_flat(self.from_yaml(path))

    def clone(self):
        clone = AttrDict()
        clone.update_dict(self)
        return clone

    def rebase(self, base):
        base = base.clone()
        base.update_dict(self)
        self.clear()
        self.update_dict(base)

    def dump(self, stream):
        yaml.representer.SafeRepresenter.add_representer(
            AttrDict, yaml.representer.SafeRepresenter.represent_dict )
        yaml.representer.SafeRepresenter.add_representer(
            OrderedDict, yaml.representer.SafeRepresenter.represent_dict )
        yaml.representer.SafeRepresenter.add_representer(
            defaultdict, yaml.representer.SafeRepresenter.represent_dict )
        yaml.representer.SafeRepresenter.add_representer(
            set, yaml.representer.SafeRepresenter.represent_list )
        
        yaml.representer.SafeRepresenter.add_representer(
            IncludeFile, include_representer)
        
        yaml.safe_dump( self, stream,
            default_flow_style=False, indent=4, encoding='utf-8' )

def configure_logging(cfg, custom_level=None):
    '''Don't know what this is for .... '''
    import itertools as it, operator as op

    if custom_level is None: custom_level = logging.WARNING
    for entity in it.chain.from_iterable(it.imap(
            op.methodcaller('viewvalues'),
            [cfg] + list(cfg.get(k, dict()) for k in ['handlers', 'loggers']) )):
        if isinstance(entity, Mapping)\
            and entity.get('level') == 'custom': entity['level'] = custom_level
    logging.config.dictConfig(cfg)
    logging.captureWarnings(cfg.warnings)

## {{{ http://code.activestate.com/recipes/578272/ (r1)
def toposort(data):
    """Dependencies are expressed as a dictionary whose keys are items
and whose values are a set of dependent items. Output is a list of
sets in topological order. The first set consists of items with no
dependences, each subsequent set consists of items that depend upon
items in the preceeding sets.

>>> print '\\n'.join(repr(sorted(x)) for x in toposort2({
...     2: set([11]),
...     9: set([11,8]),
...     10: set([11,3]),
...     11: set([7,5]),
...     8: set([7,3]),
...     }) )
[3, 5, 7]
[8, 11]
[2, 9, 10]

"""

    from functools import reduce

    # Ignore self dependencies.
    for k, v in data.items():
        v.discard(k)
    # Find all items that don't depend on anything.
    extra_items_in_deps = reduce(set.union, data.itervalues()) - set(data.iterkeys())
    # Add empty dependences where needed
    data.update({item:set() for item in extra_items_in_deps})
    while True:
        ordered = set(item for item, dep in data.iteritems() if not dep)
        if not ordered:
            break
        yield ordered
        data = {item: (dep - ordered)
                for item, dep in data.iteritems()
                    if item not in ordered}
    assert not data, "Cyclic dependencies exist among these items:\n%s" % '\n'.join(repr(x) for x in data.iteritems())
## end of http://code.activestate.com/recipes/578272/ }}}

def chunks(l, n):
    """ Yield successive n-sized chunks from l.
    """
    for i in xrange(0, len(l), n):
        yield l[i:i+n]
        
        
def zip_dir(dir, file_):
    
    import zipfile, glob
    with zipfile.ZipFile(file_, 'w') as zf:
        g = os.path.join(dir,'*')
        print g
        for f in glob.glob(g):
            zf.write(f)
    return dir
    
    
def md5_for_file(file_name, block_size=2**20):
    """Generate an MD5 has for a possibly large file by breaking it into chunks"""
    import hashlib
    with open(file_name) as f:
        md5 = hashlib.md5()
        while True:
            data = f.read(block_size)
            if not data:
                break
            md5.update(data)
    return md5.hexdigest()    
