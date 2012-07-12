'''
Created on Jun 22, 2012

@author: eric
'''
import unittest
from  testbundle.bundle import Bundle


class Test(unittest.TestCase):

    def setUp(self):
        
        import os.path, yaml
        self.bundle_dir =  os.path.join(os.path.dirname(os.path.abspath(__file__)),'testbundle')
        Bundle(self.bundle_dir).clean()
        
        bundle_yaml = '''
identity:
    creator: clarinova.com
    dataset: Foobar Example File
    revision: 1
    source: example.com
    subset: SF1
    variation: orig '''
     
        cf = os.path.join(self.bundle_dir,'bundle.yaml')
      
        yaml.dump(yaml.load(bundle_yaml), file(cf, 'w'), indent=4, default_flow_style=False)
     
     
        self.bundle = Bundle(self.bundle_dir)
      
    def test_new_bundle(self):
        pass # Just create the bundle. 
        
    def test_bundle_init(self):
        
        import time

        self.assertIn('id', self.bundle.config.group('identity'))
        self.assertEquals('clarinova.com', self.bundle.identity.creator)
        oid = self.bundle.identity.id_
    
        time.sleep(1)
       
        # Test that the build.yaml file is reloaded, but that the
        # id value does not change. 
        bcf = self.bundle.config.config_file
        bcf.config_dict['identity']['creator'] = 'foobar'
        self.assertFalse(self.bundle.config.config_file_changed())
        bcf.rewrite()
        self.assertTrue(self.bundle.config.config_file_changed())

        bundle =  Bundle(self.bundle_dir)     
        self.assertEquals('foobar', bundle.identity.creator)
        self.assertEquals(oid, bundle.identity.id_)

      
    def test_identity(self):
        self.assertEqual('example.com', self.bundle.identity.source)
        self.assertEqual('Foobar Example File', self.bundle.identity.dataset)
        self.assertEqual('SF1', self.bundle.identity.subset)
        self.assertEqual('orig', self.bundle.identity.variation)
        self.assertEqual('clarinova.com', self.bundle.identity.creator)
        self.assertEqual(1, int(self.bundle.identity.revision))
        self.assertEqual('example.com-foobar_example_file-sf1-orig-a7d9-r1', 
                         self.bundle.identity.name)
      
        self.bundle.identity.source = 'foobar'
        
        self.assertEqual('foobar-foobar_example_file-sf1-orig-a7d9-r1', 
                         self.bundle.identity.name)
     
    def test_schema_direct(self):
        '''Test adding tables directly to the schema'''
        
        # If we don't explicitly set the id_, it will change for every run. 
        self.bundle.identity.id_ = 'aTest'
    
        s = self.bundle.schema
        s.add_table('table 1', altname='alt name a')
        s.add_table('table 2', altname='alt name b')
        s.add_table('table 1', altname='alt name c')
        
        self.assertIn('cTest01', [t.id_ for t in self.bundle.schema.tables])
        self.assertIn('cTest02', [t.id_ for t in self.bundle.schema.tables])
        self.assertNotIn('cTest03', [t.id_ for t in self.bundle.schema.tables])
        
        t = s.add_table('table 3', altname='alt name')
        
        t.add_column('col 1',altname='altname1')
        t.add_column('col 2',altname='altname2')
        t.add_column('col 3',altname='altname3')
        t.add_column('col 3',altname='altname3')
        
        self.assertIn('dTest0301', [c.id_ for c in t.columns])
        self.assertIn('dTest0302', [c.id_ for c in t.columns])
        self.assertIn('dTest0303', [c.id_ for c in t.columns])
        
    def test_generate_schema(self):
        '''Uses the generateSchema method in the bundle'''
        self.bundle.schema.generate()

    def test_db_bundle(self):
        
        db_path = self.bundle.database.path
        
        bundle = Bundle(db_path)
        
        for i in bundle.schema.tables:
            print i.name
        
    def test_partition(self):
        
        ##
        ## TODO THis does does not test the 'table' parameter of the ParitionId
        ##
 
       
        from  databundles.partition import  PartitionId
        pid1 = PartitionId(time=1, space=1)
        pid2 = PartitionId(time=2, space=2)
        pid3 = PartitionId(space=3,)
        
        self.bundle.partitions.new_partition(pid1, data={'pid':'pid1'})
        self.bundle.partitions.new_partition(pid2, data={'pid':'pid2'})
        self.bundle.partitions.new_partition(pid3, data={'pid':'pid3'})
        self.bundle.partitions.new_partition(pid1, data={'pid':'pid1'})
        self.bundle.partitions.new_partition(pid2, data={'pid':'pid2'})
        self.bundle.partitions.new_partition(pid3, data={'pid':'pid3'})
        
        self.assertEqual(3, len(self.bundle.partitions.all))
        
        p = self.bundle.partitions.new_partition(pid1)   
        self.assertEquals('pid1',p.data['pid'] )
      
        p = self.bundle.partitions.new_partition(pid2)   
        self.assertEquals('pid2',p.data['pid'] ) 

        p = self.bundle.partitions.new_partition(pid3)   
        self.assertEquals('pid3',p.data['pid'] ) 

        p = self.bundle.partitions.find(pid1)   
        self.assertEquals('pid1',p.data['pid'] )
      
        p = self.bundle.partitions.find(pid2)   
        self.assertEquals('pid2',p.data['pid'] ) 

        p = self.bundle.partitions.find(pid3)   
        self.assertEquals('pid3',p.data['pid'] ) 
         
        p = self.bundle.partitions.find_orm(pid3)   
        s = self.bundle.database.session
        p.data['foo'] = 'bar'
        s.commit()
        
        p = self.bundle.partitions.find(pid3)   
        self.assertEquals('bar',p.data['foo'] ) 
        
        
        print p.database.path
        self.bundle.library.put(p)
        
if __name__ == "__main__":
    if True:
        unittest.main()
    else:
        suite = unittest.TestSuite()
        suite.addTest(Test('test_bundle_init'))
        #unittest.TextTestRunner().run(suite)