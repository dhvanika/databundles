'''
Created on Aug 19, 2012

@author: eric
'''
from  sourcesupport.uscensus import UsCensusBundle
import yaml 

class Us2010CensusBundle(UsCensusBundle):
    '''
    Bundle code for US 2000 Census, Summary File 1
    '''

    def __init__(self,directory=None):
        self.super_ = super(Us2010CensusBundle, self)
        self.super_.__init__(directory)
     
        self._table_id_cache = {}
        self._table_iori_cache = {}
        

    def _scrape_urls(self, rootUrl, states_file,  suffix='_uf1'):
        '''Extract all of the URLS from the Census website and store them. 
        Unline the Us2000 version, this one lists one file per state'''
        import urllib
        import urlparse
        import re
        from bs4 import BeautifulSoup
    
        log = self.log
        tick = self.ptick
    
        # Load in a list of states, so we know which links to follow
        with open(states_file) as f:
            states = map(lambda s: s.strip(),f.readlines())
         
        # Root URL for downloading files. 
       
        doc = urllib.urlretrieve(rootUrl)
        
        log('Getting URLS from '+rootUrl)
        # Get all of the links
        log('S = state, T = segment table, g = geo')
        urls = {}
      
        for link in BeautifulSoup(open(doc[0])).find_all('a'):
            tick('S')
            if not link.get('href') or not link.string or not link.contents:
                continue;# Didn't get a sensible link
            # Only descend into links that name a state
            state = link.get('href').strip('/')
          
            if link.string and link.contents[0] and state in states :
                stateUrl = urlparse.urljoin(rootUrl, link.get('href'))
                stateIndex = urllib.urlretrieve(stateUrl)
                # Get all of the zip files in the directory
                
                for link in  BeautifulSoup(open(stateIndex[0])).find_all('a'):
                    
                    if link.get('href') and  '.zip' in link.get('href'):
                        final_url = urlparse.urljoin(stateUrl, link.get('href')).encode('ascii', 'ignore')
                   
                        tick('T')
                        
                        m = re.match('.*/(\w{2})2010.sf1.zip', final_url)

                        if  m:
                            urls[m.group(1)] = str(final_url)
                        else:
                            raise Exception("Regex failed for : "+final_url)
        
        tick('\n')
   
        return {'geos': urls}
    
    def read_packing_list(self):
        '''The packing list is a file, in every state extract directory, 
        that has a section that describes how the tables are packed into segments.
        it appears to be the same for every sttate'''
        import re
    
        # Descend into the first extract directory. The part of the packing list
        # we need is the same for every state. 
      
        pack_list = None
        for state, url in self.urls['geos'].items(): #@UnusedVariable
            with self.filesystem.download(url) as state_file:
                with self.filesystem.unzip_dir(state_file) as files:
                    for f in files:
                        if f.endswith("2010.sf1.prd.packinglist.txt"):
                            pack_list = f
                            break
                    break
        lines = []          
        with open(pack_list) as f:
            for line in f:
                if re.search('^p\d+\|', line):
                    parts = line.strip().split('|')
                    segment, length = parts[1].split(':')
                    lines.append({'table':parts[0],
                                 'segment':segment,
                                 'length':length})
        return lines

    def generate_schema_rows(self):
        '''This generator yields schema rows from the schema defineition
        files. This one is specific to the files produced by dumpoing the Access97
        shell for the 2010 census '''
        import csv
        
        reader  = csv.DictReader(open(self.headers_file, 'rbU') )
        last_seg = None
        table = None
        for row in reader:
            if not row['TABLE NUMBER']:
                continue
            
            if row['SEGMENT'] and row['SEGMENT'] != last_seg:
                last_seg = row['SEGMENT']
            
            # The first two rows for the table give information about the title
            # and population universe, but don't have any column info. 
            if( not row['FIELD CODE']):
                if  row['FIELD NAME'].startswith('Universe:'):
                    table['universe'] = row['FIELD NAME'].replace('Universe:','').strip()  
                else:
                    table = {'type': 'table', 
                             'name':row['TABLE NUMBER'],
                             'description':row['FIELD NAME'],
                             'segment':row['SEGMENT'],
                             'data':  {'segment':row['SEGMENT'], 'fact':True}
                             }
            else:
                
                # The whole table will exist in one segment ( file number ) 
                # but the segment id is not included on the same lines ast the
                # table name. 
                if table:
                    yield table
                    table  = None
                    
                col_pos = int(row['FIELD CODE'][-3:])
                
                yield {
                       'type':'column','name':row['FIELD CODE'], 
                       'description':row['FIELD NAME'].strip(),
                       'segment':int(row['SEGMENT']),
                       'col_pos':col_pos,
                       'decimal':int(row['DECIMAL'] if row['DECIMAL'] else 0)
                       }
 
 
    def generate_seg_rows(self, seg_number, source):
        '''Generate rows for a segment file. Call this generator with send(), 
        passing in the lexpected logrecno. If the next row does not have that 
        value, return a blank row until the logrecno values match. '''
        import csv #, cStringIO
        next_logrecno = None
        with open(source, 'rbU') as f:
            #b = cStringIO.StringIO(f.read()) # Read whole file into memory
            for row in csv.reader( f ):
                # The next_logrec bit takes care of a differece in the
                # segment files -- the PCT tables to not have entries for
                # tracts, so there are gaps in the logrecno sequence for those files. 
                while next_logrecno is not None and next_logrecno != row[4]:
                    next_logrecno = (yield seg_number,  [])
         
                next_logrecno = (yield seg_number,  row)
                 
        return
    
    def merge_strings(self,first, overlay):
        '''return a new buffer that loads the first string, then loverlays the second'''
    
        if len(overlay) > len(first):
            raise ValueError("Overlay can't be longer then string")

        o = bytearray(first) 
        for i in range(len(overlay)):
            o[i] = overlay[i]
            
        return str(o)
    
    def _generate_row(self, first, gens, geodim_gen,  geo_file_path, gln, unpack_str, line, last_line):
        
        import struct 
        
        try:
            geo = struct.unpack(unpack_str, line[:-1])
        except Exception as e:
            self.error("Failed to unpack geo line from line {} of {}".format(gln, geo_file_path))
            self.error("Unpack_str: "+unpack_str)
            self.error("Line: "+line[:-1])
            self.error("Line Length "+str(len(line[:-1])))
            
            # There are a few GEO files that have problems, like the
            # Colorado file. This is a total Hack to fix them. 
            
            if not last_line:
                raise e
            
            # Copy the last line ( which presumably worked OK,with 
            # the shorter current line. The missing fields will "peek through"
            # to make the line the right length
            line = self.merge_strings(last_line, line)
            
            geo = struct.unpack(unpack_str, line[:-1])
        
        last_line = line
        
        if not geo:
            raise ValueError("Failed to match regex on line: "+line) 
    
        segments = {}
       
        logrecno = geo[6]
          
        for seg_number, g in gens:
            try:
                seg_number,  row = g.send(None if first else logrecno)
                segments[seg_number] = row
                # The logrecno must match up across all files, except
                # when ( in PCT tables ) there is no entry
                if len(row) > 5 and row[4] != logrecno:
                    raise Exception("Logrecno mismatch for seg {} : {} != {}"
                                    .format(seg_number, row[4],logrecno))
            except StopIteration:
                # Apparently, the StopIteration exception, raised in
                # a generator function, gets propagated all the way up, 
                # ending all higher level generators. thanks for nuthin. 
                
                #self.error("Breaking iteration for "+str(seg_number))
                segments[seg_number] = None
    
        geodim = geodim_gen.next() if geodim_gen is not None else None
    
        if geodim and geodim[0] != logrecno:
            raise Exception("Logrecno mismatch for geodim : {} != {}"
                                    .format(geodim[0],logrecno))
    
        return logrecno, geo, segments, geodim
    
    
    def generate_rows(self, state, geodim=False):
        '''A Generator that yelds a tuple that has the logrecno row
        for all of the segment files and the geo file. '''
        import re
        
        table = self.schema.table('sf1geo2010')
        header, unpack_str, length = table.get_fixed_unpack() #@UnusedVariable
         
        source_url = self.urls['geos'][state]
        
        geodim_gen = self.generate_geodim_rows(state) if geodim else None
        
        with self.filesystem.download(source_url) as state_file:
    
            segment_files = {}
            geo_file_path = None
            gens = []
            with self.filesystem.unzip_dir(state_file) as files:
                for f in files:
                    g1 = re.match(r'.*/(\w\w)(\d+)2010.sf1', str(f))
                    g2 = re.match(r'.*/(\w\w)geo2010.sf1', str(f))
                    if g1:
                        segment = int(g1.group(2))
                        segment_files[segment] = f 
                        gens.append( (segment, self.generate_seg_rows(segment,f)) )
                    elif g2:
                        geo_file_path = f
                
                with open(geo_file_path, 'rbU') as geofile:
                    first = True
                    
                    gln = 0
                    last_line = None
                    for line in geofile.readlines():
                        gln += 1

                        logrecno, geo, segments, geodim =  self._generate_row(
                            first, gens, geodim_gen,  geo_file_path, gln, unpack_str, line, last_line)

                        yield state, logrecno, dict(zip(header,geo)), segments, geodim
                    
                        first = False
            
                    # Check that there are no extra lines. 
                    lines_left = 0;
                    for seg_number, g in gens: #@UnusedVariable
                        for row in g:
                            print 'Left Over', row
                            lines_left = lines_left + 1    
                    if lines_left > 0:
                        raise Exception("Should not hae extra items left. got {} ".format(str(lines_left)))


    def geo_table_names(self):
        return (['recno',
                 'area',
                 'block',
                 'cons_city',
                 'county',
                 'leg_district',
                 'metro_type',
                 'place',
                 'schools',
                 'spec_area',
                 'state', 
                 'urban_type',     
                 ]
                )
 
            