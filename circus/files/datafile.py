import h5py, numpy, re, sys, os
from circus.shared.messages import print_error, print_and_log
from circus.shared.mpi import comm


def get_offset(data_dtype, dtype_offset):

    if dtype_offset == 'auto':
        if data_dtype in ['uint16', numpy.uint16]:
            dtype_offset = 32768
        elif data_dtype in ['int16', numpy.int16]:
            dtype_offset = 0
        elif data_dtype in ['float32', numpy.float32]:
            dtype_offset = 0
        elif data_dtype in ['int8', numpy.int8]:
            dtype_offset = 0        
        elif data_dtype in ['uint8', numpy.uint8]:
            dtype_offset = 127
        elif data_dtype in ['float64', numpy.float64]:
            dtype_offset = 0    
    else:
        try:
            dtype_offset = int(dtype_offset)
        except Exception:
            print_error(["Offset %s is not valid" %dtype_offset])
            sys.exit(0)

    return dtype_offset

class DataFile(object):

    '''
    A generic class that will represent how the program interacts with the data. Such an abstraction
    layer should allow people to write their own wrappers, for several file formats. Note that 
    depending on the complexity of the datastructure, this can slow down the code.

    The method belows are all methods that can be used, at some point, by the different steps of the code. 
    In order to provide a full compatibility with a given file format, they must all be implemented.

    Note also that you must specify if your file format allows parallel write calls, as this is used in
    the filtering and benchmarking steps.
    '''

    _description      = "mydatafile"    
    _extension        = [".myextension"]
    _parallel_write   = False
    _is_writable      = False
    _requiered_fields = {}
    _shape            = (0, 0)
    _max_offset       = 0
    _mandatory        = ['sampling_rate', 'data_dtype', 'data_offset', 'gain']
    # Note that those values can be either infered from header, or otherwise read from the parameter file

    def __init__(self, file_name, is_empty=False, **kwargs):
        '''
        The constructor that will create the DataFile object. Note that by default, values are read from
        the parameter file, but you could completly fill them based on values that would be obtained
        from the datafile itself. 
        What you need to specify
            - _parallel_write : can the file be safely written in parallel ?
            - _is_writable    : if the file can be written
            - _shape          : the size of the data, should be a tuple (max_offset, N_tot)
            - max_offset      : the time length of the data, in time steps
            - comm is a MPI communicator ring, if the file is created in a MPI environment
            - empty is a flag to say if the file is created without data

        Note that you can overwrite values such as N_e, rate from the header in your data. Those will then be
        used in the code, instead of the ones from the parameter files.

        Note also that the code can create empty files [multi-file, benchmarking], this is why there is an empty
        flag to warn the constructor about the fact that the file may be empty
        '''

        self.file_name = file_name
        self.is_empty  = is_empty

        if self.is_empty and not self._is_writable:
            if self.is_master:
                print_error(["The file %s is empty and non writable..." %(extension, self._description)])
            sys.exit(0)

        f_next, extension = os.path.splitext(self.file_name)
        
        if self._extension is not None:
            if not extension in self._extension + [item.upper() for item in self._extension]:
                if self.is_master:
                    print_error(["The extension %s is not valid for a %s file" %(extension, self._description)])
                sys.exit(0)

        self._check_requierements_(**kwargs)

        for key, value in kwargs.items():
            if key == 'nb_channels':
                self._shape = (0, value)
            else:
                self.__setattr__(key, value)

        self._N_t        = None
        self._dist_peaks = None
        self._template_shift = None
        self._safety_time    = None

        if not self.is_empty:
            self._get_info_()
            self._check_valid_()

    def _check_valid_(self):
        for key in self._mandatory:
            if not hasattr(self, key):
                print_error(['%s is a needed attribute of a datafile, and it is not defined' %key])

    def _check_requierements_(self, **kwargs):

        missing = {}

        for key, value in self._requiered_fields.items():
            if key not in kwargs.keys():
                missing[key] = value
                print_error(['%s must be specified as type %s in the [data] section!' %(key, value[0])])
        

        if len(missing) > 0:
            self._display_requierements_()
            sys.exit(0)



    def _display_requierements_(self):

        to_write = ['The parameters for %s file format are:' %self._description.upper(), '']
        for key, values in self._requiered_fields.items():
                
            mystring = '-- %s -- of type %s' %(key, values[0])

            if values[1] is None:
                mystring += ' [** mandatory **]'
            else:
                mystring += ' [default is %s]' %values[1]

            to_write += [mystring]

        print_error(to_write)


    def _get_info_(self):
        '''
            This function is called only if the file is not empty, and should fill the values in the constructor
            such as max_offset, _shape, ...
        '''
        pass


    def _get_chunk_size_(self, chunk_size=None):
        '''
            This function returns a default size for the data chunks
        '''
        if chunk_size is None:
            chunk_size = self.params.getint('data', 'chunk_size')
        
        return chunk_size     


    def _scale_data_to_float32(self, data):

        if self.data_dtype != numpy.float32:
            data  = data.astype(numpy.float32)

        if self.gain != 1:
            data *= self.gain

        return numpy.ascontiguousarray(data)

    def _unscale_data_from_from32(self, data):

        if self.gain != 1:
            data /= self.gain
        
        if self.dtype_offset != 0:
            data  += self.dtype_offset
        
        if data.dtype != self.data_dtype:
            data = data.astype(self.data_dtype)

        return data

    def get_data(self, idx, chunk_size=None, padding=(0, 0), nodes=None):
        '''
        Assuming the analyze function has been called before, this is the main function
        used by the code, in all steps, to get data chunks. More precisely, assuming your
        dataset can be divided in nb_chunks (see analyze) of temporal size (chunk_size), 

            - idx is the index of the chunk you want to load
            - chunk_size is the time of those chunks, in time steps
            - if the data loaded are data[idx:idx+1], padding should add some offsets, 
                in time steps, such that we can load data[idx+padding[0]:idx+padding[1]]
            - nodes is a list of nodes, between 0 and N_total            
        '''

        pass

    def get_snippet(self, time, length, nodes=None):
        '''
            This function should return a time snippet of size length x nodes
            - time is in timestep
            - length is in timestep
            - nodes is a list of nodes, between 0 and N_total
        '''
        return self.get_data(0, chunk_size=length, padding=(time, time), nodes=nodes)


    def set_data(self, time, data):
        '''
            This function writes data at a given time.
            - time is expressed in timestep
            - data must be a 2D matrix of size time_length x N_total
        '''
        pass


    def analyze(self, chunk_size=None):
        '''
            This function should return two values: 
            - the number of temporal chunks of temporal size chunk_size that can be found 
            in the data. Note that even if the last chunk is not complete, it has to be 
            counted. chunk_size is expressed in time steps
            - the length of the last uncomplete chunk, in time steps
        '''
        chunk_size     = self._get_chunk_size_(chunk_size)
        nb_chunks      = numpy.int64(self.shape[0]) // chunk_size
        last_chunk_len = numpy.int64(self.shape[0]) - nb_chunks * chunk_size

        if last_chunk_len > 0:
            nb_chunks += 1

        return nb_chunks, last_chunk_len


    def open(self, mode):
        ''' 
            This function should open the file
            - mode can be to read only 'r', or to write 'w'
        '''
        pass


    def close(self):
        '''
            This function closes the file
        '''
        pass


    def allocate(self, shape, data_dtype):
        '''
            This function may be used during benchmarking mode, or if multi-files mode is activated
            Starting from an empty file, it will allocates a given size:
                - shape is a tuple with (time lenght, N_total)
                - data_dtype is the data type
        '''
        pass


    @property
    def shape(self):
        return self._shape  
         
    @property
    def nb_channels(self):
        return self._shape[1]
    
    @property
    def duration(self):
        return self._shape[0]

    @property
    def is_master(self):
    	return comm.rank == 0