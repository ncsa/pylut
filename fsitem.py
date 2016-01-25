import os
import pylut
import stat
import hashlib

class FSItem( object ):
    """
    Encapsulate file information such as name, absolute path,
    mountpoint, stat info (from os.lstat), stripe info, etc.
    """

    # stat info key names
    statinfo_keys = ( 'mode', 'ino', 'dev', 'nlink', 'uid',
                      'gid', 'size', 'atime', 'mtime', 'ctime' )

    # md5 checksum blocksize (assume bigger is better, faster)
    md5_blocksize = 512 * 1024 * 1024

    def __init__( self, path, absname=None,  mountpoint=None ):
        """
        Can instantiate with either a full path only OR pass in all three arguments.
        :param path str: either a full path or just a name
        :param absname str: OPTIONAL the absolute path to the file, if not provided, an attempt will be made to look it up
        :param mountpoint str: OPTIONAL path to the mountpoint, if not provided, an attempt will be made to look it up
        """
        self.name = os.path.basename( path )
        self.absname = absname
        self.mountpoint = mountpoint
        self._statinfo   = None     #os.lstat
        self._stripeinfo = None     #pylut.getstripeinfo
        self._fid        = None     #pylut.path2fid
        self._checksum   = None     #hashlib.md5().hexdigest
        if self.absname is None:
            self.absname = os.path.abspath( path )
        if self.mountpoint is None:
            self.mountpoint = getmountpoint( self.absname )


    def __repr__( self ):
        return '<{0} {1} {2}>'.format( self.__class__.__name__, self._fid, self.absname )


    def __str__( self ):
        return self.absname


    def fid( self ):
        if self._fid is None:
            self._fid = pylut.path2fid( self.absname )
        return self._fid


    def stat( self ):
        """
        Return file stat information, getting it if needed
        """
        # Store statinfo as a local dict
        if self._statinfo is None:
            st = os.lstat( self.absname )
            self._statinfo = {}
            for x in self.statinfo_keys:
                k = 'st_{0}'.format( x )
                self._statinfo[ x ] = getattr( st, k )
        return self._statinfo


    def stripeinfo( self ):
        """
        Return stripe information, getting it if needed
        """
        if self._stripeinfo is None:
            self._stripeinfo = pylut.getstripeinfo( self.absname )
        return self._stripeinfo


    def checksum( self ):
        if self._checksum is None:
            if self.exists():
                cksum = hashlib.md5()
                with open( self.absname, 'rb' ) as f:
                    for chunk in iter( lambda: f.read( self.md5_blocksize ), b'' ):
                        cksum.update( chunk )
                self._checksum = cksum.hexdigest()
        return self._checksum
            


    def exists( self ):
        try:
            self.stat()
        except ( OSError ) as e:
            if e.errno == 2: 
                return False
            raise e
        return True
            

    def is_dir( self ):
        return stat.S_ISDIR( self.mode )


    def is_file( self ):
        return stat.S_ISREG( self.mode )


    def is_symlink( self ):
        return stat.S_ISLNK( self.mode )


    def compare( self, other, attrnames ):
        """ Compare (one or more) attributes (given by attrnames)
            Returns a tuple of True/False values for each attribute
            Result tuple has the same order as attrnames
        """
        return tuple( getattr( self, x ) == getattr( other, x ) for x in attrnames )


    def update( self ):
        """
            Force update of all transient information 
            (stripeinfo, statinfo, fid, checksum)
        """
        self._statinfo = None
        self._stripeinfo = None
        self._fid = None
        self._checksum = None


    def __getattr__( self, name ):
        # allow easy stat information lookup
        if name in self.statinfo_keys:
            return self.stat()[ name ]
        # allow easy stripeinfo lookup
        if name.startswith( 'stripe' ):
            return getattr( self.stripeinfo(), name[6:] )
        raise AttributeError('{0} not found in {1}'.format( 
            name, self.__class__.__name__) )


def getmountpoint( path ):        
    path = os.path.realpath( os.path.abspath( path ) )
    while path != os.path.sep:
        if os.path.ismount( path ):
            return path
        path = os.path.abspath( os.path.join( path, os.pardir ) )
    return path


if __name__ == '__main__':
    raise UserWarning( 'Cmdline not supported' )
