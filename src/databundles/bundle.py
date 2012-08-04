'''
Created on Jun 9, 2012

@author: eric
'''

from database import Database
from identity import Identity 
from filesystem import  Filesystem
from schema import Schema
from partition import Partitions
import os.path
from exceptions import  ConfigurationError
from run import RunConfig


class Bundle(object):
    '''Represents a bundle, including all configuration 
    and top level operations. '''
 
    def __init__(self):
        '''
        '''
    
        self._schema = None
        self._partitions = None
    
 
    
    @property
    def schema(self):
        if self._schema is None:
            self._schema = Schema(self)
            
        return self._schema
    

    @property
    def partitions(self):     
        if self._partitions is None:
            self._partitions = Partitions(self)  
            
        return self._partitions

    @property
    def identity(self):
        '''Return an identity object. '''
        
        return Identity(**self.config.dict.get('identity'))
    

    @property
    def library(self):    
        import library
        
        return library.get_library()

    
class DbBundle(Bundle):

    def __init__(self, database_file):
        '''Initialize a bundle and all of its sub-components. 
        
        If it does not exist, creates the bundle database and initializes the
        Dataset record and Config records from the bundle.yaml file. Through the
        config object, will trigger a re-load of the bundle.yaml file if it
        has changed. 
        
        Order of operations is:
            Create bundle.db if it does not exist
        '''
        
        super(DbBundle, self).__init__()
       
        
       
        self.database = Database(self, database_file)
        self.config = BundleDbConfig(self.database)

    def table_data(self, query):
        '''Return a petl container for a data table'''
        import petl 
        query = query.strip().lower()
        
        if 'select' not in query:
            query = "select * from {} ".format(query)
 
        
        return petl.fromsqlite3(self.database.path, query)
        

class BuildBundle(Bundle):
    '''A bundle class for building bund files. Uses the bundle.yaml file for
    identity configuration '''

    def __init__(self, bundle_dir=None):
        '''
        '''
        
        super(BuildBundle, self).__init__()
        
        if bundle_dir is None:
            bundle_dir = Filesystem.find_root_dir()
        
        if bundle_dir is None or not os.path.isdir(bundle_dir):
            from exceptions import BundleError
            raise BundleError("BuildBundle must be constructed on a directory")
  
        self.bundle_dir = bundle_dir
        
        self._database  = None
       
        self.filesystem = Filesystem(self, self.bundle_dir)
        self.config = BundleFileConfig(self.bundle_dir)

        import base64
        self.logid = base64.urlsafe_b64encode(os.urandom(6)) 
        self.ptick_count = 0;

        # If a download directory is defined, cache the download
        # otherwize, don't
        self.cache_downloads = self.config.library.downloads is not None
    

    @property
    def database(self):
        
        if self._database is None:
            self._database  = Database(self)
         
        return self._database

    @classmethod
    def rm_rf(cls, d):
        
        if not os.path.exists(d):
            return
        
        for path in (os.path.join(d,f) for f in os.listdir(d)):
            if os.path.isdir(path):
                cls.rm_rf(path)
            else:
                os.unlink(path)
        os.rmdir(d)

    def clean(self):
        '''Remove all files generated by the build process'''
        self.rm_rf(self.filesystem.build_path())
        
        # Should check for a shared download file -- specified
        # as part of the library; Don't delete that. 
        #if not self.cache_downloads :
        #    self.rm_rf(self.filesystem.downloads_path())

    
    def log(self, message, **kwargs):
        '''Log the messsage'''
        print "LOG: ",message

    def error(self, message, **kwargs):
        '''Log an error messsage'''
        print "ERR: ",message

    def progress(self,message):
        '''print message to terminal, in place'''
        print 'PRG: ',message

    def ptick(self,message):
        '''Writes a tick to the stdout, without a space or newline'''
        import sys
        sys.stdout.write(message)
        sys.stdout.flush()
        
        self.ptick_count += len(message)
       
        if self.ptick_count > 72:
            sys.stdout.write("\n")
            self.ptick_count = 0


    ###
    ### Process Methods
    ###


    ### Prepare is run before building, part of the devel process.  

    def pre_prepare(self):
        return True

    def prepare(self):
        return True
    
    def post_prepare(self):
        return True
   
    
    ### Build the final package

    def pre_build(self):
        return True
        
    def build(self):
        return True
    
    def post_build(self):
        return True
    
        
    ### Submit the package to the library
 
    def pre_install(self):
        return True
    
    def install(self):
        return True
        
    def post_install(self):
        return True
    
    ### Submit the package to the repository
 
    def pre_submit(self):
        return True
    
    def submit(self):
        return True
        
    def post_submit(self):
        return True
    

class BundleConfig(object):
   
    def __init__(self):
        pass


class BundleFileConfig(BundleConfig):
    '''Bundle configuration from a bundle.yaml file '''
    
    BUNDLE_CONFIG_FILE = 'bundle.yaml'

    def __init__(self, directory):
        '''Load the bundle.yaml file and create a config object
        
        If the 'id' value is not set in the yaml file, it will be created and the
        file will be re-written
        '''

        super(BundleFileConfig, self).__init__()
        
        self.directory = directory
     
        self._run_config = RunConfig(os.path.join(self.directory,'databundles.yaml'))
     
        self._config_dict = None
        self.dict # Fetch the dict. 
   
        # If there is no id field, create it immediately and
        # write the configuration baci out. 
   
        if not self.identity.id_:
            from identity import DatasetNumber
            self.identity.id_ = str(DatasetNumber())
            self.rewrite()
   
        if not os.path.exists(self.path):
            raise ConfigurationError("Can't find bundle config file: "+self.config_file)

        
    @property
    def dict(self): #@ReservedAssignment
        '''Return a dict/array object tree for the bundle configuration'''
        
        if not self._config_dict:  
            import yaml
            try:
             
                self._config_dict = self.overlay(self._run_config.dict,
                                                 yaml.load(file(self.path, 'r')))

            except Exception as e:
                raise e
                raise NotImplementedError,''' Bundle.yaml missing. 
                Auto-creation not implemented'''
            
        return self._config_dict

    def overlay(self,dict1, dict2):
        '''Overlay the values from an input dictionary into 
        the object configuration, overwritting earlier values. '''
        import copy
        
        dict1 = copy.copy(dict1)
        
        for name,group in dict2.items():
            
            if not name in dict1:
                dict1[name] = {}
            
            try:
                for key,value in group.items():
                    dict1[name][key] = value
            except:
                # item is not a group
                dict1[name] = group 
                
        return dict1

    def __getattr__(self, group):
        '''Fetch a confiration group and return the contents as an 
        attribute-accessible dict'''
        
        inner = self.dict[group]
        
        class attrdict(object):
            def __setattr__(self, key, value):
                key = key.strip('_')
                inner[key] = value

            def __getattr__(self, key):
                key = key.strip('_')
                if key not in inner:
                    return None
                
                return inner[key]
        
        return attrdict()

    @property
    def path(self):
        return os.path.join(self.directory, BundleFileConfig.BUNDLE_CONFIG_FILE)

    def reload(self): #@ReservedAssignment
        '''Reload the configuation from the file'''
        self._config_dict = None
        
    def rewrite(self):
        '''Re-writes the file from its own data. Reformats it, and updates
        themodification time'''
        import yaml
        
        yaml.dump(self.dict, file(self.path, 'w'), indent=4, default_flow_style=False)
   

class BundleDbConfig(BundleConfig):
    '''Binds configuration items to the database, and processes the bundle.yaml file'''

    def __init__(self, database):
        '''Maintain link between bundle.yam file and Config record in database'''
        
        super(BundleDbConfig, self).__init__()
        self.database = database
        self.dataset = self.get_dataset()

    @property
    def dict(self): #@ReservedAssignment
        '''Return a dict/array object tree for the bundle configuration'''
      
        return {'identity':self.dataset.to_dict()}

    def __getattr__(self, group):
        '''Fetch a confiration group and return the contents as an 
        attribute-accessible dict'''
        
        inner = self.dict[group]
        
        class attrdict(object):
            def __setattr__(self, key, value):
                key = key.strip('_')
                inner[key] = value

            def __getattr__(self, key):
                key = key.strip('_')
                if key not in inner:
                    return None
                
                return inner[key]
        
        return attrdict()

    def get_dataset(self):
        '''Initialize the identity, creating a dataset record, 
        from the bundle.yaml file'''
        
        from databundles.orm import Dataset
 
        s = self.database.session

        return  (s.query(Dataset).one())

    def write_dict_to_db(self, dict): #@ReservedAssignment
        from databundles.orm import Config as SAConfig
     
        s = self.database.session
        ds = self.get_or_new_dataset()
         
        s.query(SAConfig).filter(SAConfig.d_id == ds.id_).delete()
        
        for group,gvalues in dict.items():
            if group in ['identity']:
                for key, value in gvalues.items():
                    o = SAConfig(group=group,key=key,d_id=ds.id_,value = value)
                    s.add(o)

        s.commit()

   


    
    