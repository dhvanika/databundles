'''
Created on Jun 11, 2012

@author: eric
'''

class ObjectNumber(object):
    '''
    Static class for holding constants and static methods related 
    to object numbers
    '''
    class _const:
        class ConstError(TypeError): pass
        def __setattr__(self,name,value):
            if self.__dict__.has_key(name):
                raise self.ConstError, "Can't rebind const(%s)"%name
            self.__dict__[name]=value

    TYPE=_const()
    TYPE.DATASET = 'a'
    TYPE.PARTITION = 'b'
    TYPE.TABLE ='c'
    TYPE.COLUMN = 'd'

    TCMAXVAL = 62*62 -1; # maximum for table and column values. 
    PARTMAXVAL = 62*62*62 -1; # maximum for table and column values. 
     
    EPOCH = 1325376000 # Jan 1, 2012 in UNIX time

    @classmethod
    def parse(self, input):
        '''Parse a string into one of the object number classes. '''
        
        if input is None:
            return None
        
        if  isinstance(input, unicode):
            dataset = input.encode('ascii')
      
        if input[0] == self.TYPE.DATASET:
            dataset = int(ObjectNumber.base62_decode(input[1:]))
            return DatasetNumber(dataset)
        elif input[0] == self.TYPE.TABLE:   
            table = int(ObjectNumber.base62_decode(input[-2:]))
            dataset = int(ObjectNumber.base62_decode(input[1:-2]))
            return TableNumber(DatasetNumber(dataset), table)
        elif input[0] == self.TYPE.PARTITION:
            partition = int(ObjectNumber.base62_decode(input[-3:]))
            dataset = int(ObjectNumber.base62_decode(input[1:-3]))  
            return PartitionNumber(DatasetNumber(dataset), partition)              
        elif input[0] == self.TYPE.COLUMN:       
            column = int(ObjectNumber.base62_decode(input[-2:]))
            table = int(ObjectNumber.base62_decode(input[-4:-2]))
            dataset = int(ObjectNumber.base62_decode(input[1:-4]))
            return ColumnNumber(TableNumber(DatasetNumber(dataset), table), column)
        else:
            raise ValueError('Unknow type character: '+input[0]+ ' in '+str(dataset))
       
    
    def __init__(self, primary, suffix=None):
        '''
        Constructor
        '''
        
        # If the primary is the same as this class, it is a copy constructor
        if isinstance(primary, self.__class__) and suffix is None:
            pass
        
        else:
            self.primary = primary
            self.suffix = suffix
    
    
  
    @classmethod
    def base62_encode(cls, num):
        """Encode a number in Base X
    
        `num`: The number to encode
        `alphabet`: The alphabet to use for encoding
        Stolen from: http://stackoverflow.com/a/1119769/1144479
        """
        
        alphabet="0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        
        if (num == 0):
            return alphabet[0]
        arr = []
        base = len(alphabet)
        while num:
            rem = num % base
            num = num // base
            arr.append(alphabet[rem])
        arr.reverse()
        return ''.join(arr)

    @classmethod
    def base62_decode(cls,string):
        """Decode a Base X encoded string into the number
    
        Arguments:
        - `string`: The encoded string
        - `alphabet`: The alphabet to use for encoding
        Stolen from: http://stackoverflow.com/a/1119769/1144479
        """
        
        alphabet="0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        
        base = len(alphabet)
        strlen = len(string)
        num = 0
    
        idx = 0
        for char in string:
            power = (strlen - (idx + 1))
            num += alphabet.index(char) * (base ** power)
            idx += 1
    
        return num



class DatasetNumber():
    '''An identifier for a dataset'''
    def __init__(self, dataset=None):
        '''
        Constructor
        '''
      
        if dataset is None:
            import time
            dataset = int(time.time())
    
        # For Datasets, integer values are time 
        # This calc is OK until 31 Dec 2053 00:00:00 GMT
        if dataset > ObjectNumber.EPOCH:
            dataset = dataset - ObjectNumber.EPOCH
          
        self.dataset = dataset

    def __str__(self):        
        return (ObjectNumber.TYPE.DATASET+
                ObjectNumber.base62_encode(self.dataset))
           
 

class TableNumber(ObjectNumber):
    '''An identifier for a table'''
    def __init__(self, dataset, table):
        if not isinstance(dataset, DatasetNumber):
            raise ValueError("Constructor requires a DatasetNumber")

        if table > ObjectNumber.TCMAXVAL:
            raise ValueError("Value is too large")


        self.dataset = dataset
        self.table = table;
         
         
    def __str__(self):        
        return (ObjectNumber.TYPE.TABLE+
                ObjectNumber.base62_encode(self.dataset.dataset)+
                ObjectNumber.base62_encode(self.table).rjust(2,'0'))
                  
         
class ColumnNumber(ObjectNumber):
    '''An identifier for a column'''
    def __init__(self, table, column):
        if not isinstance(table, TableNumber):
            raise ValueError("Constructor requires a TableNumber")

        if column > ObjectNumber.TCMAXVAL:
            raise ValueError("Value is too large")

        self.table = table
        self.column = column
         
         
    def __str__(self):        
        return (ObjectNumber.TYPE.COLUMN+
                ObjectNumber.base62_encode(self.table.dataset.dataset)+
                ObjectNumber.base62_encode(self.table.table).rjust(2,'0')+
                ObjectNumber.base62_encode(self.column).rjust(2,'0')
                )
           

class PartitionNumber(ObjectNumber):
    '''An identifier for a partition'''
    def __init__(self, dataset, partition):
        '''
        Arguments:
        dataset -- Must be a DatasetNumber
        partition -- an integer, from 0 to 62^3
        '''
        if not isinstance(dataset, DatasetNumber):
            raise ValueError("Constructor requires a DatasetNumber")

        if partition > ObjectNumber.PARTMAXVAL:
            raise ValueError("Value is too large")

        self.dataset = dataset
        self.partition = partition;
         
         
    def __str__(self):        
        return (ObjectNumber.TYPE.PARTITION+
                ObjectNumber.base62_encode(self.dataset.dataset)+
                ObjectNumber.base62_encode(self.partition).rjust(3,'0'))

  

        