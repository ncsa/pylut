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
        self._inode      = None     #filesystem specific (Lustre==FID)
        self._statinfo   = None     #os.lstat
        self._checksum   = None     #hashlib.md5().hexdigest
        if self.absname is None:
            self.absname = os.path.abspath( path )
        if self.mountpoint is None:
            self.mountpoint = getmountpoint( self.absname )
        self.parent = os.path.dirname( self.absname )
        if self.absname == self.mountpoint:
            self.parent = ''
        elif self.absname == self.parent:
            self.parent = ''


    def __repr__( self ):
        return '<{0} {1} {2}>'.format( self.__class__.__name__, self._inode, self.absname )


    def __str__( self ):
        return self.absname


    def inode( self ):
        """
        Attempt to get a filesystem specific version of file identifier
        (for example: Lustre FID)
        For normal inode, just use self.ino, which is part of stat and should be faster anyway
        """
        #TODO-call inode() method of appropriate module for type of filesystem
        if self._inode is None:
            self._inode = pylut.inode( self.absname )
        return self._inode


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


    #TODO-stripeinfo is Lustre-specific, probably could monkeypatch it in from pylut
    def stripeinfo( self ):
        """
        Return stripe information, getting it if needed
        Lustre stripe is valid only for dirs and regular files
        None will be returned for non-regular files
        """
        try:
            rv = self._stripeinfo
        except AttributeError:
            if self.is_regular() or self.is_dir():
                self._stripeinfo = pylut.getstripeinfo( self.absname )
            else:
                self._stripeinfo = pylut.LustreStripeInfo()
        return self._stripeinfo


    def checksum( self ):
        """
        Return checksum of regular file, calculating it first if needed
        Return string of zeros for dirs and non-regular files
        """
        if self._checksum is None:
            if self.exists():
                if self.is_regular():
                    cksum = hashlib.md5()
                    with open( self.absname, 'rb' ) as f:
                        for chunk in iter( lambda: f.read( self.md5_blocksize ), b'' ):
                            cksum.update( chunk )
                    self._checksum = cksum.hexdigest()
                else:
                    self._checksum = '0'*32
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
        """ Returns True if entry is a directory, False otherwise
        """
        return stat.S_ISDIR( self.mode )


    def is_file( self ):
        """ Return True if entry is any non-device file type
            (regular file, symlink, fifo or socket); False otherwise
        """
        return stat.S_ISREG( self.mode ) or \
               stat.S_ISLNK( self.mode ) or \
               stat.S_ISFIFO( self.mode ) or \
               stat.S_ISSOCK( self.mode )


    def is_device( self ):
        """ Return True if entry is a CHR or BLK device file
        """
        return stat.S_ISCHR( self.mode ) or \
               stat.S_ISBLK( self.mode )


    def is_symlink( self ):
        """ Return True if entry is a symbolic link
        """
        return stat.S_ISLNK( self.mode )


    def is_regular( self ):
        """ Return True if entry is a regular file; False otherwise
        """
        return stat.S_ISREG( self.mode )


    def is_special( self ):
        """ Return True if entry is a fifo or socket or device; False otherwise
        """
        return stat.S_ISFIFO( self.mode ) or \
               stat.S_ISSOCK( self.mode )
        

    def compare( self, other, attrnames ):
        """ Compare (one or more) attributes (given by attrnames)
            Returns a tuple of True/False values for each attribute
            Result tuple has the same order as attrnames
        """
        return tuple( getattr( self, x ) == getattr( other, x ) for x in attrnames )


    def update( self ):
        """ Force update of all transient information 
            (stripeinfo, statinfo, inode, checksum)
        """
        self._statinfo = None
        self._inode = None
        self._checksum = None
        #TODO-stripeinfo is Lustre-specific, probably could monkeypatch it in from pylut
        try:
            del self._stripeinfo
        except ( AttributeError ):
            pass


    def __getattr__( self, name ):
        # allow easy stat information lookup
        if name in self.statinfo_keys:
            return self.stat()[ name ]
        # allow easy stripeinfo lookup
        #TODO-stripeinfo is Lustre-specific, probably could monkeypatch it in from pylut
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
