"""Object-Rlational Mapping classess, based on Sqlalchemy, for representing the
dataset, partitions, configuration, tables and columns. 

Copyright (c) 2013 Clarinova. This file is licensed under the terms of the
Revised BSD License, included in this distribution as LICENSE.txt
"""
import sqlalchemy
from sqlalchemy import orm
from sqlalchemy import event
from sqlalchemy import Column as SAColumn, Integer, Boolean
from sqlalchemy import Float as Real,  Text, ForeignKey
from sqlalchemy.orm import relationship, deferred
from sqlalchemy.types import TypeDecorator, TEXT, PickleType
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.mutable import Mutable

from sqlalchemy.sql import text
from databundles.identity import  DatasetNumber, ColumnNumber
from databundles.identity import TableNumber, PartitionNumber, ObjectNumber

import json

Base = declarative_base()

class JSONEncodedObj(TypeDecorator):
    "Represents an immutable structure as a json-encoded string."

    impl = TEXT

    def process_bind_param(self, value, dialect):
        if value is not None:
            value = json.dumps(value)
        else:
            value = '{}'
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            try:
                value = json.loads(value)
            except:
                # We've changed from using pickle to json, so this handles legacy cases
                import pickle
                value = pickle.loads(value)
                
                
                
        else:
            value = {}
        return value

class MutationDict(Mutable, dict):
    @classmethod
    def coerce(cls, key, value): #@ReservedAssignment
        "Convert plain dictionaries to MutationDict."

        if not isinstance(value, MutationDict):
            if isinstance(value, dict):
                return MutationDict(value)

            # this call will raise ValueError
            return Mutable.coerce(key, value)
        else:
            return value

    def __setitem__(self, key, value):
        "Detect dictionary set events and emit change events."
        dict.__setitem__(self, key, value)
        self.changed()

    def __delitem__(self, key):
        "Detect dictionary del events and emit change events."

        dict.__delitem__(self, key)
        self.changed()

class MutationObj(Mutable):
    @classmethod
    def coerce(cls, key, value):
        if isinstance(value, dict) and not isinstance(value, MutationDict):
            return MutationDict.coerce(key, value)
        if isinstance(value, list) and not isinstance(value, MutationList):
            return MutationList.coerce(key, value)
        return value
 
    @classmethod
    def _listen_on_attribute(cls, attribute, coerce, parent_cls):
        key = attribute.key
        if parent_cls is not attribute.class_:
            return
 
        # rely on "propagate" here
        parent_cls = attribute.class_
 
        def load(state, *args):
            val = state.dict.get(key, None)
            if coerce:
                val = cls.coerce(key, val)
                state.dict[key] = val
            if isinstance(val, cls):
                val._parents[state.obj()] = key
 
        def set(target, value, oldvalue, initiator):
            if not isinstance(value, cls):
                value = cls.coerce(key, value)
            if isinstance(value, cls):
                value._parents[target.obj()] = key
            if isinstance(oldvalue, cls):
                oldvalue._parents.pop(target.obj(), None)
            return value
 
        def pickle(state, state_dict):
            val = state.dict.get(key, None)
            if isinstance(val, cls):
                if 'ext.mutable.values' not in state_dict:
                    state_dict['ext.mutable.values'] = []
                state_dict['ext.mutable.values'].append(val)
 
        def unpickle(state, state_dict):
            if 'ext.mutable.values' in state_dict:
                for val in state_dict['ext.mutable.values']:
                    val._parents[state.obj()] = key
 
        sqlalchemy.event.listen(parent_cls, 'load', load, raw=True, propagate=True)
        sqlalchemy.event.listen(parent_cls, 'refresh', load, raw=True, propagate=True)
        sqlalchemy.event.listen(attribute, 'set', set, raw=True, retval=True, propagate=True)
        sqlalchemy.event.listen(parent_cls, 'pickle', pickle, raw=True, propagate=True)
        sqlalchemy.event.listen(parent_cls, 'unpickle', unpickle, raw=True, propagate=True)
        
class MutationList(MutationObj, list):
    @classmethod
    def coerce(cls, key, value):
        """Convert plain list to MutationList"""
        self = MutationList((MutationObj.coerce(key, v) for v in value))
        self._key = key
        return self
 
    def __setitem__(self, idx, value):
        list.__setitem__(self, idx, MutationObj.coerce(self._key, value))
        self.changed()
 
    def __setslice__(self, start, stop, values):
        list.__setslice__(self, start, stop, (MutationObj.coerce(self._key, v) for v in values))
        self.changed()
 
    def __delitem__(self, idx):
        list.__delitem__(self, idx)
        self.changed()
 
    def __delslice__(self, start, stop):
        list.__delslice__(self, start, stop)
        self.changed()
 
    def append(self, value):
        list.append(self, MutationObj.coerce(self._key, value))
        self.changed()
 
    def insert(self, idx, value):
        list.insert(self, idx, MutationObj.coerce(self._key, value))
        self.changed()
 
    def extend(self, values):
        list.extend(self, (MutationObj.coerce(self._key, v) for v in values))
        self.changed()
 
    def pop(self, *args, **kw):
        value = list.pop(self, *args, **kw)
        self.changed()
        return value
 
    def remove(self, value):
        list.remove(self, value)
        self.changed()
 
def JSONAlchemy(sqltype):
    """A type to encode/decode JSON on the fly
 
    sqltype is the string type for the underlying DB column.
 
    You can use it like:
    Column(JSONAlchemy(Text(600)))
    """
    class _JSONEncodedObj(JSONEncodedObj):
        impl = sqltype
        
    return MutationObj.as_mutable(_JSONEncodedObj)
        

class SavableMixin(object):
    
    def save(self):
        self.session.commit()
        

class Dataset(Base):
    __tablename__ = 'datasets'
    
    id_ = SAColumn('d_id',Text, primary_key=True)
    name = SAColumn('d_name',Integer, unique=True, nullable=False)
    source = SAColumn('d_source',Text, nullable=False)
    dataset = SAColumn('d_dataset',Text, nullable=False)
    subset = SAColumn('d_subset',Text)
    variation = SAColumn('d_variation',Text)
    creator = SAColumn('d_creator',Text, nullable=False)
    revision = SAColumn('d_revision',Text)
    data = SAColumn('d_data', MutationDict.as_mutable(JSONEncodedObj))

    path = None  # Set by the LIbrary and other queries. 

    tables = relationship("Table", backref='dataset', cascade="all, delete-orphan", 
                          passive_updates=False)
    partitions = relationship("Partition", backref='dataset', cascade="all, delete-orphan",
                               passive_updates=False)
   
    def __init__(self,**kwargs):
        self.id_ = kwargs.get("oid",kwargs.get("id", None)) 
        self.name = kwargs.get("name",None) 
        self.source = kwargs.get("source",None) 
        self.dataset = kwargs.get("dataset",None) 
        self.subset = kwargs.get("subset",None) 
        self.variation = kwargs.get("variation",None) 
        self.creator = kwargs.get("creator",None) 
        self.revision = kwargs.get("revision",None) 

        if not self.id_:
            self.id_ = str(DatasetNumber())
 
    @property
    def creatorcode(self):
        from identity import Identity
        return Identity._creatorcode(self)
    
   
    def __repr__(self):
        return """<datasets: id={} name={} source={} ds={} ss={} var={} creator={} rev={}>""".format(
                    self.id_, self.name, self.source,
                    self.dataset, self.subset, self.variation, 
                    self.creator, self.revision)
        
        
    @property
    def identity(self):
        from identity import Identity
        return Identity(**self.to_dict() )
        
    def to_dict(self):
        return {
                'id':self.id_, 
                'name':self.name, 
                'source':self.source,
                'dataset':self.dataset, 
                'subset':self.subset, 
                'variation':self.variation, 
                'creator':self.creator, 
                'revision':self.revision
                }
        
def _clean_flag( in_flag):
    
    if in_flag is None or in_flag == '0':
        return False;
    
    return bool(in_flag)

class Column(Base):
    __tablename__ = 'columns'

    id_ = SAColumn('c_id',Text, primary_key=True)
    sequence_id = SAColumn('c_sequence_id',Integer)
    t_id = SAColumn('c_t_id',Text,ForeignKey('tables.t_id'))
    name = SAColumn('c_name',Text, unique=True)
    altname = SAColumn('c_altname',Text)
    datatype = SAColumn('c_datatype',Text)
    size = SAColumn('c_size',Integer)
    width = SAColumn('c_width',Integer)
    sql = SAColumn('c_sql',Text)
    precision = SAColumn('c_precision',Integer)
    flags = SAColumn('c_flags',Text)
    description = SAColumn('c_description',Text)
    keywords = SAColumn('c_keywords',Text)
    measure = SAColumn('c_measure',Text)
    units = SAColumn('c_units',Text)
    universe = SAColumn('c_universe',Text)
    _scale = SAColumn('c_scale',Real)
    data = SAColumn('c_data',MutationDict.as_mutable(JSONEncodedObj))

    is_primary_key = SAColumn('c_is_primary_key',Boolean, default = False)
    foreign_key = SAColumn('c_is_foreign_key',Text, default = False)
    unique_constraints = SAColumn('c_unique_constraints',Text)
    indexes = SAColumn('c_indexes',Text)
    uindexes = SAColumn('c_uindexes',Text)
    default = SAColumn('c_default',Text)
    illegal_value = SAColumn('c_illegal_value',Text)

    DATATYPE_TEXT = 'text'
    DATATYPE_INTEGER ='integer' 
    DATATYPE_INTEGER64 ='integer64' 
    DATATYPE_REAL = 'real'
    DATATYPE_FLOAT = 'float'
    DATATYPE_NUMERIC = 'numeric'
    DATATYPE_DATE = 'date'
    DATATYPE_TIME = 'time'
    DATATYPE_TIMESTAMP = 'timestamp'
    DATATYPE_POINT = 'point' # Spatalite, sqlite extensions for geo
    DATATYPE_LINESTRING = 'linestring' # Spatalite, sqlite extensions for geo
    DATATYPE_POLYGON = 'polygon' # Spatalite, sqlite extensions for geo
    DATATYPE_MULTIPOLYGON = 'multipolygon' # Spatalite, sqlite extensions for geo
    DATATYPE_CHAR = 'text'
    DATATYPE_VARCHAR = 'text'
    DATATYPE_BLOB = 'blob'

    types  = {
        DATATYPE_TEXT:(sqlalchemy.types.Text,str,'TEXT'),
        DATATYPE_VARCHAR:(sqlalchemy.types.Text,str,'TEXT'),
        DATATYPE_CHAR:(sqlalchemy.types.Text,str,'TEXT'),
        DATATYPE_INTEGER:(sqlalchemy.types.Integer,int,'INTEGER'),
        DATATYPE_INTEGER64:(sqlalchemy.types.Integer,int,'INTEGER'),
        DATATYPE_REAL:(sqlalchemy.types.Float,float,'REAL'),
        DATATYPE_FLOAT:(sqlalchemy.types.Float,float,'REAL'),
        DATATYPE_NUMERIC:(sqlalchemy.types.Float,float,'REAL'),
        DATATYPE_DATE:(sqlalchemy.types.Date,str,'DATE'),
        DATATYPE_TIME:(sqlalchemy.types.Time,str,'TIME'),
        DATATYPE_TIMESTAMP:(sqlalchemy.types.DateTime,str,'TIMESTAMP'),
        DATATYPE_POINT:(sqlalchemy.types.LargeBinary,buffer,'POINT'),
        DATATYPE_LINESTRING:(sqlalchemy.types.LargeBinary,buffer,'LINESTRING'),
        DATATYPE_POLYGON:(sqlalchemy.types.LargeBinary,buffer,'POLYGON'),
        DATATYPE_MULTIPOLYGON:(sqlalchemy.types.LargeBinary,buffer,'MULTIPOLYGON'),
        DATATYPE_BLOB:(sqlalchemy.types.LargeBinary,buffer,'BLOB')
        }

    @property
    def sqlalchemy_type(self):
        return self.types[self.datatype][0]
    
    @property
    def python_type(self):
        return self.types[self.datatype][1]
 
    @property
    def schema_type(self):
        return self.types[self.datatype][2]
        
        
    def __init__(self,**kwargs):
     
        self.id_ = kwargs.get("oid",None) 
        self.sequence_id = kwargs.get("sequence_id",None) 
        self.t_id = kwargs.get("t_id",None)  
        self.name = kwargs.get("name",None) 
        self.altname = kwargs.get("altname",None) 
        self.is_primary_key = _clean_flag(kwargs.get("is_primary_key",False))
        self.datatype = kwargs.get("datatype",None) 
        self.size = kwargs.get("size",None) 
        self.precision = kwargs.get("precision",None) 
        self.width = kwargs.get("width",None)    
        self.sql = kwargs.get("sql",None)      
        self.flags = kwargs.get("flags",None) 
        self.description = kwargs.get("description",None) 
        self.keywords = kwargs.get("keywords",None) 
        self.measure = kwargs.get("measure",None) 
        self.units = kwargs.get("units",None) 
        self.universe = kwargs.get("universe",None) 
        self._scale = kwargs.get("_scale",None) 
        self.data = kwargs.get("data",None) 

        # the table_name attribute is not stored. It is only for
        # building the schema, linking the columns to tables. 
        self.table_name = kwargs.get("table_name",None) 

        if not self.name:
            raise ValueError('Column must have a name')



    @staticmethod
    def mangle_name(name):
        import re
        try:
            return re.sub('[^\w_]','_',name).lower()
        except TypeError:
            raise TypeError('Not a valid type for name '+str(type(name)))

    @staticmethod
    def before_insert(mapper, conn, target):
        '''event.listen method for Sqlalchemy to set the seqience_id for this  
        object and create an ObjectNumber value for the id_'''
        
        if target.sequence_id is None:
            sql = text('''SELECT max(c_sequence_id)+1 FROM columns WHERE c_t_id = :tid''')
    
            max_id, = conn.execute(sql, tid=target.t_id).fetchone()
      
            if not max_id:
                max_id = 1
                
            target.sequence_id = max_id
        
        Column.before_update(mapper, conn, target)

    @staticmethod
    def before_update(mapper, conn, target):
        '''Set the column id number based on the table number and the 
        sequence id for the column'''
       
        if target.id_  is None:
            table_on = ObjectNumber.parse(target.t_id)
            target.id_ = str(ColumnNumber(table_on, target.sequence_id))
   
    def __repr__(self):
        try :
            return "<columns: {}>".format(self.oid)
        except:
            return "<columns: {}>".format(self.name)
 
event.listen(Column, 'before_insert', Column.before_insert)
event.listen(Column, 'before_update', Column.before_update)
 
class Table(Base):
    __tablename__ ='tables'

    id_ = SAColumn('t_id',Text, primary_key=True)
    d_id = SAColumn('t_d_id',Text,ForeignKey('datasets.d_id'), nullable = False)
    sequence_id = SAColumn('t_sequence_id',Integer, nullable = False)
    name = SAColumn('t_name',Text, unique=True, nullable = False)
    altname = SAColumn('t_altname',Text)
    description = SAColumn('t_description',Text)
    keywords = SAColumn('t_keywords',Text)
    data = SAColumn('t_data',MutationDict.as_mutable(JSONEncodedObj))
    
    columns = relationship(Column, backref='table', cascade="all, delete-orphan")

    def __init__(self,**kwargs):
        self.id_ = kwargs.get("id",None) 
        self.d_id = kwargs.get("d_id",None)
        self.sequence_id = kwargs.get("sequence_id",None)  
        self.name = kwargs.get("name",None) 
        self.altname = kwargs.get("altname",None) 
        self.description = kwargs.get("description",None) 
        self.keywords = kwargs.get("keywords",None) 
        self.data = kwargs.get("data",None) 

        if self.name:
            self.name = self.mangle_name(self.name)

        self.init_on_load()
    
    @orm.reconstructor
    def init_on_load(self):
        self._or_validator = None
        self._and_validator = None
        self._null_row = None
        self._row_hasher = None
        
    @staticmethod
    def before_insert(mapper, conn, target):
        '''event.listen method for Sqlalchemy to set the seqience_id for this  
        object and create an ObjectNumber value for the id_'''
        if target.sequence_id is None:
            sql = text('''SELECT max(t_sequence_id)+1 FROM tables WHERE t_d_id = :did''')
    
            max_id, = conn.execute(sql, did=target.d_id).fetchone()
      
            if not max_id:
                max_id = 1
                
            target.sequence_id = max_id
        
        Table.before_update(mapper, conn, target)
        
    @staticmethod
    def before_update(mapper, conn, target):
        '''Set the Table ID based on the dataset number and the sequence number
        for the table '''
        if isinstance(target,Column):
            raise TypeError('Got a column instead of a table')
        
        if target.id_ is None:
            dataset_id = ObjectNumber.parse(target.d_id)
            target.id_ = str(TableNumber(dataset_id, target.sequence_id))

    @staticmethod
    def mangle_name(name):
        import re
        try:
            return re.sub('[^\w_]','_',name.strip()).lower()
        except TypeError:
            raise TypeError('Not a valid type for name '+str(type(name)))

    @property
    def oid(self):   
        return TableNumber(self.d_id, self.sequence_id)

    def add_column(self, name, **kwargs):

        import sqlalchemy.orm.session
        s = sqlalchemy.orm.session.Session.object_session(self)
        
        name = Column.mangle_name(name)

        if kwargs.get('sequence_id', False):
            sequence = kwargs['sequence_id']
        else:
            sequence = None

        row = Column(id=str(ColumnNumber(ObjectNumber.parse(self.id_),sequence)),
                     name=name, 
                     t_id=self.id_,
                     **kwargs              
                     )
         
        for key, value in kwargs.items():
            if key[0] != '_' and key not in ['d_id','t_id','name']:
                setattr(row, key, value)
            
            if isinstance(value, basestring) and len(value) == 0:
                if key == 'is_primary_key':
                    value = False
                    setattr(row, key, value)
      
        s.add(row)
     
        if kwargs.get('commit', True):
            s.commit()
    
        return row
   
    def column(self, name_or_id, default=None):
        from sqlalchemy.sql import or_
        import sqlalchemy.orm.session
        s = sqlalchemy.orm.session.Session.object_session(self)
        
        q = (s.query(Column)
               .filter(or_(Column.id_==name_or_id,Column.name==name_or_id))
               .filter(Column.t_id == self.id_)
            )
      
        if not default is None:
            try:
                return  q.one()
            except:
                return default
        else:
            return  q.one()
    
    @property
    def primary_key(self):
        for c in self.columns:
            if c.is_primary_key:
                return c
        return None
    
    def get_fixed_regex(self):
            '''Using the size values for the columsn for the table, construct a
            regular expression to  parsing a fixed width file.'''
            import re

            pos = 0;
            regex = ''
            header = []
            
            for col in  self.columns:
                
                if not col.width:
                    continue
                
                pos += col.width
            
                regex += "(.{{{}}})".format(col.width)
                header.append(col.name)
           
            return header, re.compile(regex) , regex 

    def get_fixed_unpack(self):
            '''Using the size values for the columns for the table, construct a
            regular expression to  parsing a fixed width file.'''
        
            unpack_str = ''
            header = []
            length = 0
            
            for col in  self.columns:
                
                if not col.width:
                    continue
                
                length += col.width
            
                unpack_str += "{}s".format(col.width)
                
                header.append(col.name)
           
            return header, unpack_str, length

    @property
    def null_row(self):
        if self._null_row is None:
            self._null_row = []
            for col in self.columns:
                if col.default:
                    self._null_row.append(col.default)
                else:
                    self._null_row.append(None)
            
        return self._null_row

    def _get_validator(self, and_join=True):
        '''Return a lambda function that, when given a row to this table, 
        returns true or false to indicate the validitity of the row
        
        :param and_join: If true, join multiple column validators with AND, other
        wise, OR
        :type and_join: Bool
        
        :rtype: a `LibraryDb` object
    
            
        '''

        f = prior = lambda row : True
        first = True
        for i,col in  enumerate(self.columns):

            if col.data.get('mandatory', False):
                default_value = col.default
                index = i
                
                if and_join:
                    f = lambda row, default_value=default_value, index=index, prior=prior: prior(row) and str(row[index]) != str(default_value)
                elif first:
                    # OR joins would either need the initial F to be 'false', or just don't use it
                    f = lambda row, default_value=default_value, index=index:  str(row[index]) != str(default_value)  
                else:
                    f = lambda row, default_value=default_value, index=index, prior=prior: prior(row) or str(row[index]) != str(default_value)
                            
                prior = f
                first = False
            
        return f
    
    def validate_or(self, values):

        if self._or_validator is None:
            self._or_validator = self._get_validator(and_join=False)
        
        return self._or_validator(values)
     
    def validate_and(self, values):

        if self._and_validator is None:
            self._and_validator = self._get_validator(and_join=True)
        
        return self._and_validator(values)
    
    def _get_hasher(self):
        '''Return a  function to generate a hash for the row'''
        import hashlib
 
        # Try making the hash set from the columns marked 'hash'
        indexes = [ i for i,c in enumerate(self.columns) if  
                   c.data.get('hash',False) and  not c.is_primary_key  ]
 
        # Otherwise, just use everything by the primary key. 
        if len(indexes) == 0:
            indexes = [ i for i,c in enumerate(self.columns) if not c.is_primary_key ]

        def hasher(values):
            m = hashlib.md5()
            for index in indexes: 
                x = values[index]
                try:
                    m.update(x.encode('utf-8')+'|') # '|' is so 1,23,4 and 12,3,4 aren't the same  
                except:
                    m.update(str(x)+'|') 
            return int(m.hexdigest()[:14], 16)
        
        return hasher
    
    def row_hash(self, values):
        '''Calculate a hash from a database row''' 
        
        if self._row_hasher is None:
            self._row_hasher = self._get_hasher()
            
        return self._row_hasher(values)
         
     
event.listen(Table, 'before_insert', Table.before_insert)
event.listen(Table, 'before_update', Table.before_update)

class Config(Base):
    __tablename__ = 'config'

    d_id = SAColumn('co_d_id',Text, primary_key=True)
    group = SAColumn('co_group',Text, primary_key=True)
    key = SAColumn('co_key',Text, primary_key=True)
    #value = SAColumn('co_value', PickleType(protocol=0))
    
    value = SAColumn('co_value', JSONAlchemy(Text()))

    source = SAColumn('co_source',Text)

    def __init__(self,**kwargs):
        self.d_id = kwargs.get("d_id",None) 
        self.group = kwargs.get("group",None) 
        self.key = kwargs.get("key",None) 
        self.value = kwargs.get("value",None)
        self.source = kwargs.get("source",None) 

    def __repr__(self):
        return "<config: {},{},{} = {}>".format(self.d_id, self.group, self.key, self.value)
     

class File(Base, SavableMixin):
    __tablename__ = 'files'

    oid = SAColumn('f_id',Integer, primary_key=True, nullable=False)
    path = SAColumn('f_path',Text, nullable=False)
    source_url = SAColumn('f_source_url',Text)
    process = SAColumn('f_process',Text)
    state = SAColumn('f_state',Text)
    content_hash = SAColumn('f_hash',Text)
    modified = SAColumn('f_modified',Integer)
    size = SAColumn('f_size',Integer)
    group = SAColumn('f_group',Integer)
    ref = SAColumn('f_ref',Text)
 
    def __init__(self,**kwargs):
        self.oid = kwargs.get("oid",None) 
        self.path = kwargs.get("path",None)
        self.source_url = kwargs.get("source_url",None) 
        self.process = kwargs.get("process",None) 
        self.state = kwargs.get("state",None) 
        self.modified = kwargs.get("modified",None) 
        self.size = kwargs.get("size",None)
        self.group = kwargs.get("group",None)
        self.ref = kwargs.get("ref",None)
        self.content_hash = kwargs.get("content_hash",None) 
      
    def __repr__(self):
        return "<file: {}; {}>".format(self.path, self.state)

class Partition(Base):
    __tablename__ = 'partitions'

    id_ = SAColumn('p_id',Text, primary_key=True, nullable=False)
    name = SAColumn('p_name',Text, nullable=False)
    sequence_id = SAColumn('p_sequence_id',Integer)
    t_id = SAColumn('p_t_id',Integer,ForeignKey('tables.t_id'))
    d_id = SAColumn('p_d_id',Text,ForeignKey('datasets.d_id'))
    time = SAColumn('p_time',Text)
    space = SAColumn('p_space',Text)
    grain = SAColumn('p_grain',Text)
    #format = SAColumn('p_format',Text)
    state = SAColumn('p_state',Text)
    data = SAColumn('p_data',MutationDict.as_mutable(JSONEncodedObj))
    

   
    table = relationship('Table', backref='partitions')
    
    def __init__(self,**kwargs):
        self.id_ = kwargs.get("id",kwargs.get("id_",None)) 
        self.name = kwargs.get("name",kwargs.get("name",None)) 
        self.t_id = kwargs.get("t_id",None) 
        self.d_id = kwargs.get("d_id",None) 
        self.space = kwargs.get("space",None) 
        self.time = kwargs.get("time",None)  
        self.table = kwargs.get("table",None) 
        self.grain = kwargs.get('grain',None)
        #self.format = kwargs.get('format',None)
        
        self.data = kwargs.get('data',None)
        
    @property
    def identity(self):
        '''Return this partition information as a PartitionId'''
        from sqlalchemy.orm import object_session
        from identity import PartitionIdentity, GeoPartitionIdentity, HdfPartitionIdentity
        
        #args = {'id': self.id_, 'space':self.space, 'time':self.time, 'grain':self.grain, 'format':self.format}
        args = {'id': self.id_, 'space':self.space, 'time':self.time, 'grain':self.grain}
        
        table = self.table
        
        if table is not None:
            args['table'] = table.name
        
        if self.dataset is None:
            # The relationship will be null until the object is committed
            s = object_session(self)

            ds = s.query(Dataset).filter(Dataset.id_ == self.d_id).one()
            id_ = ds.identity
        else:
            id_ = self.dataset.identity
            
        if self.data.get('db_type') == 'geo':
            return GeoPartitionIdentity(id_, **args)
        elif self.data.get('db_type') == 'hdf':
            return HdfPartitionIdentity(id_, **args)
        else:
            return PartitionIdentity(id_, **args)

    def to_dict(self):
        return self.identity.to_dict()

    def __repr__(self):
        return "<partitions: {}>".format(self.id_)

    @staticmethod
    def before_insert(mapper, conn, target):
        '''event.listen method for Sqlalchemy to set the seqience_id for this  
        object and create an ObjectNumber value for the id_'''
        if target.sequence_id is None:
            sql = text('''SELECT max(p_sequence_id)+1 FROM Partitions WHERE p_d_id = :did''')
    
            max_id, = conn.execute(sql, did=target.d_id).fetchone()
      
            if not max_id:
                max_id = 1
                
            target.sequence_id = max_id
        
        Partition.before_update(mapper, conn, target)

    @staticmethod
    def before_update(mapper, conn, target):
        '''Set the column id number based on the table number and the 
        sequence id for the column'''
        dataset = ObjectNumber.parse(target.d_id)
        target.id_ = str(PartitionNumber(dataset, target.sequence_id))
        
event.listen(Partition, 'before_insert', Partition.before_insert)
event.listen(Partition, 'before_update', Partition.before_update)
