"""The schema sub-object provides acessors to the schema for a bundle. 

Copyright (c) 2013 Clarinova. This file is licensed under the terms of the
Revised BSD License, included in this distribution as LICENSE.txt
"""

from databundles.dbexceptions import ConfigurationError
from databundles.orm import Column

def _clean_flag( in_flag):
    
    if in_flag is None or in_flag == '0':
        return False;
    
    return bool(in_flag)

def _clean_int(i):
    
    if isinstance(i, int):
        return i
    elif isinstance(i, basestring):
        if len(i) == 0:
            return None
        
        return int(i.strip())
    elif i is None:
        return None
        raise ValueError("Input must be convertable to an int. got:  ".str(i)) 

class Schema(object):
    """Represents the table and column definitions for a bundle
    """
    def __init__(self, bundle):
        from partition import  Partition
        self.bundle = bundle # COuld also be a partition
        
        # the value for a Partition will be a PartitionNumber, and
        # for the schema, we want the dataset number
        if isinstance(self.bundle, Partition):
            self.d_id=self.bundle.bundle.identity.id_
        else:
            self.d_id=self.bundle.identity.id_

        if not self.d_id:
            raise ValueError("self.bundle.identity.oid not set")
        self._seen_tables = {}
      
        self.table_sequence = len(self.tables)+1
        self.col_sequence = 1 


    def clean(self):
        from databundles.orm import Table, Column, Partition
        s = self.bundle.database.session 
        s.query(Partition).delete()        
        s.query(Column).delete() 
        s.query(Table).delete()       
        
    @property
    def tables(self):
        '''Return a list of tables for this bundle'''
        from databundles.orm import Table
        q = (self.bundle.database.session.query(Table)
                .filter(Table.d_id==self.d_id))

        return q.all()
    
    @classmethod
    def get_table_from_database(cls, db, name_or_id):
        from databundles.orm import Table
        import sqlalchemy.orm.exc
        
        try:
            return (db.session.query(Table)
                    .filter(Table.id_==name_or_id).one())
        except sqlalchemy.orm.exc.NoResultFound:
            try:
                return (db.session.query(Table)
                        .filter(Table.name==name_or_id.lower()).one())
            except sqlalchemy.orm.exc.NoResultFound:
                return None
    
    def table(self, name_or_id):
        '''Return an orm.Table object, from either the id or name'''
        return Schema.get_table_from_database(self.bundle.database, name_or_id)

    def add_table(self, name, **kwargs):
        '''Add a table to the schema'''
        from orm import Table
        from identity import TableNumber, ObjectNumber
           
        name = Table.mangle_name(name)
     
        if name in self._seen_tables:
            raise Exception("schema.add_table has already loaded a table named: "+name)
        
        id_ = str(TableNumber(ObjectNumber.parse(self.d_id), self.table_sequence))
      
        data = { k.replace('d_','',1): v for k,v in kwargs.items() if k.startswith('d_') }
      
        row = Table(id = id_,
                    name=name, 
                    d_id=self.d_id, 
                    sequence_id=self.table_sequence,
                    data=data)
     
        self.bundle.database.session.add(row)

        for key, value in kwargs.items():
            if not key:
                continue
            if key[0] != '_' and key not in ['id','id_', 'd_id','name','sequence_id','table','column']:       
                setattr(row, key, value)
     
        self._seen_tables[name] = row
     
        self.table_sequence += 1
        self.col_sequence = 1
        
        if kwargs.get('commit', True):
            self.bundle.database.session.commit()
     
        return row
        
    
    def add_column(self, table, name,**kwargs):
        '''Add a column to the schema'''
    
        kwargs['sequence_id'] =self.col_sequence
    
        c =  table.add_column(name, **kwargs)
        
        self.col_sequence += 1
        
        return c
        
    @property
    def columns(self):
        '''Return a list of tables for this bundle'''
        from databundles.orm import Column
        return (self.bundle.database.session.query(Column).all())
        
    def get_table_meta(self, name_or_id):
        s = self.bundle.database.session
        from databundles.orm import Table, Column
        
        import sqlalchemy
        from sqlalchemy import MetaData, UniqueConstraint, ForeignKeyConstraint,  Index, text
        from sqlalchemy import Column as SAColumn
        from sqlalchemy import Table as SATable
        
        def translate_type(column):
            # Creates a lot of unnecessary objects, but speed is not important here.  
            if column.datatype == Column.DATATYPE_NUMERIC:
                return sqlalchemy.types.Numeric(column.precision, column._scale)
            else:
                return Column.types[column.datatype][0]
        
        metadata = MetaData()
        
        try :
            q =  (s.query(Table)
                       .filter(Table.name==name_or_id)
                       .filter(Table.d_id==self.d_id))
          
            table = q.one()
        except:
            # Try it with just the name
            q =  (s.query(Table).filter(Table.name==name_or_id))
             
            try:
                table = q.one()
            except sqlalchemy.orm.exc.NoResultFound: #@UndefinedVariable
                raise ValueError("No table found for name {}".format(name_or_id))
        
        at = SATable(table.name, metadata)
 
        indexes = {}
        uindexes = {}
        constraints = {}
        foreign_keys = {}
       
        for column in table.columns:
            
            kwargs = {}
        
            if column.default is not None:
                try:
                    int(column.default)
                    kwargs['server_default'] = text(str(column.default))
                except:
                    kwargs['server_default'] = column.default
          
          
          
            ac = SAColumn(column.name, 
                          translate_type(column), 
                          primary_key = ( column.is_primary_key == 1),
                          **kwargs
                          )

            at.append_column(ac);
            
            if column.foreign_key:
                fk = column.foreign_key
                fks = "{}.{}_id".format(fk.capitalize(), fk)
                foreign_keys[column.name] = fks
           
            # assemble non unique indexes
            if column.indexes and column.indexes.strip():
                for cons in column.indexes.strip().split(','):
                    if cons.strip() not in indexes:
                        indexes[cons.strip()] = []
                    indexes[cons.strip()].append(ac)

            # assemble  unique indexes
            if column.uindexes and column.uindexes.strip():
                for cons in column.uindexes.strip().split(','):
                    if cons.strip() not in uindexes:
                        uindexes[cons.strip()] = []
                    uindexes[cons.strip()].append(ac)


            # Assemble constraints
            if column.unique_constraints and column.unique_constraints.strip(): 
                for cons in column.unique_constraints.strip().split(','):
                    
                    if cons.strip() not in constraints:
                        constraints[cons.strip()] = []
                    
                    constraints[cons.strip()].append(column.name)
            

        # Append constraints. 
        for constraint, columns in constraints.items():
            at.append_constraint(UniqueConstraint(name=constraint,*columns))
             
        # Add indexes   
        for index, columns in indexes.items():
            Index(table.name+'_'+index, unique = False ,*columns)
    
        # Add unique indexes   
        for index, columns in uindexes.items():
            Index(table.name+'_'+index, unique = True ,*columns)
        
        #for from_col, to_col in foreign_keys.items():
        #    at.append_constraint(ForeignKeyConstraint(from_col, to_col))
        
        return metadata, at
 
    def generate_indexes(self, table):
        """Used for adding indexes to geo partitions. Generates index CREATE commands"""
        
         
        indexes = {}
        uindexes = {}
        
        for column in table.columns:
            # assemble non unique indexes
            if column.indexes and column.indexes.strip():
                for cons in column.indexes.strip().split(','):
                    if cons.strip() not in indexes:
                        indexes[cons.strip()] = set()
                    indexes[cons.strip()].add(column)

            # assemble  unique indexes
            if column.uindexes and column.uindexes.strip():
                for cons in column.uindexes.strip().split(','):
                    if cons.strip() not in uindexes:
                        uindexes[cons.strip()] = set()
                    uindexes[cons.strip()].add(column)

        for index_name, cols in indexes.items():
            yield "CREATE INDEX IF NOT EXISTS {} ON parcels ({});".format(index_name, ','.join([c.name for c in cols]) )
            
        for index_name, cols in uindexes.items():
            yield "CREATE UNIQUE INDEX IF NOT EXISTS {} ON parcels ({});".format(index_name, ','.join([c.name for c in cols]) )
             
                    
    def create_tables(self):
        '''Create the defined tables as database tables.'''
        self.bundle.database.commit()
        for t in self.tables:
            if not t.name in self.bundle.database.inspector.get_table_names():
                t_meta, table = self.bundle.schema.get_table_meta(t.name) #@UnusedVariable
                t_meta.create_all(bind=self.bundle.database.engine)
        
    def schema_from_file(self, file_):
        '''Read a CSV file, in a particular format, to generate the schema'''
        from orm import Column
        import csv, re
        
        reader  = csv.DictReader(file_)

        t = None

        new_table = True
        last_table = None
        line_no = 1; # Accounts for file header. Data starts on line 2
        for row in reader:
            line_no += 1
            
            if not row.get('column', False) and not row.get('table', False):
                continue
            
            row = { k:str(v).decode('utf8', 'ignore').encode('ascii','ignore').strip() for k,v in row.items()}

            if  row['table'] and row['table'] != last_table:
                new_table = True
                last_table = row['table']
            
            if new_table and row['table']:
                if self.table(row['table']):
                    self.bundle.log("schema_from_file found existing table, exiting. "+row['table'])
                    return
   
                try:
                    t = self.add_table(row['table'], **row)
                except Exception as e:
                    self.bundle.error("schema_from_file Failed to add table: "+row['table'])
                    self.bundle.error(str(row))
                    self.bundle.error(str(e))
                    self.bundle.database.session.rollback()
                    raise
                    return 
                new_table = False
              
            # Ensure that the default doesnt get quotes if it is a number. 
            if row.get('default', False):
                try:
                    default = int(row['default'])
                except:
                    default = row['default']
            else:
                default = None
            
            if not row.get('column', False):
                raise ConfigurationError("Row error: no column on line {}".format(line_no))
            if not row.get('table', False):
                raise ConfigurationError("Row error: no table on line {}".format(line_no))
            if not row.get('type', False):
                raise ConfigurationError("Row error: no type on line {}".format(line_no))
            
            # Build the index and unique constraint values. 
            indexes = [ row['table']+'_'+c for c in row.keys() if (re.match('i\d+', c) and _clean_flag(row[c]))]  
            uindexes = [ row['table']+'_'+c for c in row.keys() if (re.match('ui\d+', c) and _clean_flag(row[c]))]  
            uniques = [ row['table']+'_'+c for c in row.keys() if (re.match('u\d+', c) and  _clean_flag(row[c]))]  
        
            datatype = row['type'].strip().lower()
         
            width = _clean_int(row.get('width', None))
            size = _clean_int(row.get('size',None))
            
            if  width and width > 0:
                illegal_value = '9' * width
            else:
                illegal_value = None
            
            data = { k.replace('d_','',1): v for k,v in row.items() if k.startswith('d_') }
            
            description = row.get('description','').strip()

            self.add_column(t,row['column'],
                                   is_primary_key= True if row.get('is_pk', False) else False,
                                   foreign_key= row['is_fk'] if row.get('is_fk', False) else False,
                                   description=description,
                                   datatype=datatype,
                                   unique_constraints = ','.join(uniques),
                                   indexes = ','.join(indexes),
                                   uindexes = ','.join(uindexes),
                                   default = default,
                                   illegal_value = illegal_value,
                                   size = size,
                                   width = width,
                                   data=data,
                                   sql=row.get('sql',None)
                                   )


    def as_csv(self, f=None):
        """Return the current schema as a CSV file
        
        :param f: A file-like object where the CSV data will be written. If ``None``, 
        will default to stdout. 
        
        """
        import csv, sys
        from collections import OrderedDict

        if f is None:
            f = sys.stdout


        w = None
        
        for table in self.tables:
            for col in table.columns:
                row = OrderedDict()
                row['table'] = table.name
                row['column'] = col.name
                row['id'] = col.id_
                row['is_pk'] = 1 if col.is_primary_key else ''
                row['is_fk'] = col.foreign_key if col.foreign_key else ''
                row['type'] = col.datatype.upper()
                row['default'] = col.default
                row['description'] = col.description

                if not w:
                    w = csv.DictWriter(f,row.keys())
                    w.writeheader()
                
                w.writerow(row)
                
    def as_orm(self):
        """Return a string that holds the schema represented as Sqlalchemy
        classess"""


        def write_file():
            return """
import sqlalchemy
from sqlalchemy import orm
from sqlalchemy import event
from sqlalchemy import Column as SAColumn, Integer, Boolean
from sqlalchemy import Float as Real,  Text, ForeignKey
from sqlalchemy.orm import relationship, backref, deferred
from sqlalchemy.types import TypeDecorator, TEXT, PickleType
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.mutable import Mutable

Base = declarative_base()

"""

        def write_class(table):
            return """
class {name}(Base):
    __tablename__ = '{name}'
""".format(name=table.name.capitalize())
        
        def write_fields(table):
            import re
            
            o = ""
            for col in table.columns:
                opts = []
                optstr = '';
                if col.is_primary_key: opts.append("primary_key=True") 
                if col.foreign_key: opts.append("ForeignKey('{tableuc}.{tablelc}_id')".format(
                                                    tableuc=col.foreign_key.capitalize(), tablelc=col.foreign_key)) 
                
                if  len(opts):
                    optstr = ',' + ','.join(opts)
                  
                o += "    {column} = SAColumn('{column}',sqlalchemy.types.{type}{options})\n".format(
                                            column=col.name, type=col.sqlalchemy_type.__name__,options=optstr)
            
            for col in table.columns:
                if col.foreign_key:
                    rel_name = re.sub('_id$', '', col.name)
                    
                    t = """
    {rel_name}=relationship(\"{that_table_uc}\",
       foreign_keys=[{column}],
       backref=backref('{this_table}_{rel_name}', 
                       order_by='{that_table_uc}.{that_table_lc}_id'))
"""
                    #t = "    {rel_name}=relationship(\"{that_table_uc}\")\n"
                    
                    o += t.format(
                           column=col.name, 
                           that_table_uc=col.foreign_key.capitalize(), 
                           that_table_lc=col.foreign_key,
                           this_table = table.name,
                           rel_name = rel_name
                        
                     )
            
            
            return o
        
        def write_init(table):
            o = "    def __init__(self,**kwargs):\n"
            for col in table.columns:
                o += "        self.{column} = kwargs.get(\"{column}\",None)\n".format(column=col.name)
            
            return o

        out = write_file()
        for table in self.tables:
            out += write_class(table)
            out += "\n"
            out += write_fields(table)
            out += "\n"
            out += write_init(table)
            out += "\n\n"

        return out
    
    def write_orm(self):
        """Writes the ORM file to the lib directory, which is automatically added to the
        import path by the Bundle"""
        import os
        
        lib_dir = self.bundle.filesystem.path('lib')
        if not os.path.exists(lib_dir):
            os.makedirs(lib_dir)
            
        with open(os.path.join(lib_dir,'orm.py'),'w') as f:
            f.write(self.as_orm())
            
        
    def add_views(self):
        """Add views defined in the configuration"""
        
        for p in self.bundle.partitions:

            if not p.table:
                continue
  
            if not self.bundle.config.group('views'):
                raise ConfigurationError('add_views() requires views to be specified in the configuration file')
                
            views = self.bundle.config.views.get(p.table.name, False)
 
            if not views:
                continue
            
            for name, view in views.items():
                self.bundle.log("Adding view: {} to {}".format(name, p.identity.name))
                sql = "DROP VIEW IF EXISTS {}; ".format(name)
                p.database.connection.execute(sql)
                  
                sql = "CREATE VIEW {} AS {};".format(name, view)
                p.database.connection.execute(sql)  
        
    def extract_query(self, source_table, extract_table, extra_columns=None):
     
        st = self.table(source_table)
        
        et = self.table(extract_table)

        if not et:
            raise Exception("Didn't find table {} for source {}".format(extract_table, source_table))

        lines = []
        for col in et.columns: 
            if col.sql:
                sql = col.sql
            else:
                continue

            lines.append("CAST({sql} AS {type}) AS {col}".format(sql=sql, col=col.name,type=col.schema_type))
            
        if extra_columns:
            lines = lines + extra_columns
            
        return  "SELECT " + ',\n'.join(lines) + " FROM {} ".format(st.name)
     
  
        