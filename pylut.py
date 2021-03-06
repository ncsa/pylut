from runcmd import runcmd, Run_Cmd_Error
import logging
import os
import shutil
import fsitem
import pprint
import collections

log = logging.getLogger( __name__ )

# Look for custom variables from environment
env = {}
for k in [ 'PYLUTRSYNCPATH', 'PYLUTLFSPATH', 'PYLUTRSYNCMAXSIZE' ]:
    env[ k ] = os.environ[ k ]
        

class LustreStripeInfo( object ):
    """
    class LustreStripeInfo( object )
    Simplified access to lustre stripe information
    Can specify the following keys: count size offset
    """
    #TODO - add support for pool
    attrnames = ( 'count', 'size', 'offset', 'pattern', 'gen', 'index_info', )
    index_obdidx = 0
    index_objid = 1
    index_group = 2

    def __init__( self, **kwargs ):
        self.count = None
        self.size = None
        self.offset = None
        self.pattern = None
        self.gen = None
        self.index_info = None
        for k in self.attrnames:
            if k in kwargs:
                val = kwargs[ k ]
                if k not in [ 'index_info' ]:
                    val = int( val )
                setattr( self, k, val )

    @classmethod
    def from_dict( cls, info ):
        return cls( **info )

    @classmethod
    def from_lfs_getstripe( cls, lines ):
        """
        Process lines returned from "lfs getstripe" cmdline tool
        Create LustreStripeInfo instance
        """
        retval = None
        log.debug( 'got lines {0}'.format( lines ) )
        del lines[0] #first line is a repeat of the filename
        if lines[0].startswith( 'stripe_count:' ):
            log.debug( 'this is a directory' )
            parts = lines[0].split()
            retval = cls( count=parts[1], size=parts[3], offset=parts[5] )
        elif len( lines ) < 8:
            raise LustreStripeInfoError( 
                reason='too few input lines, expected 8 or more',
                origin=pprint.pformat( lines )
                )
        else:
            log.debug( 'this is a file' )
            found_objidx = False
            info = {}
            if len( lines[-1] ) < 1: #remove empty last line
                del lines[-1]
            for line in lines:
                if line.startswith( 'lmm_stripe_count' ):
                    info[ 'count' ] = line.split()[-1]
                elif line.startswith( 'lmm_stripe_size' ):
                    info[ 'size' ] = line.split()[-1]
                elif line.startswith( 'lmm_stripe_offset' ):
                    info[ 'offset' ] = line.split()[-1]
                elif line.startswith( 'lmm_pattern' ):
                    info[ 'pattern' ] = line.split()[-1]
                elif line.startswith( 'lmm_layout_gen' ):
                    info[ 'gen' ] = line.split()[-1]
                elif line.startswith( '\tobdidx' ):
                    found_objidx = True
                    info[ 'index_info' ] = []
                    continue
                if found_objidx:
                    parts = line.split()
                    if len( parts ) == 0:
                        break
                    if len( parts ) != 4:
                        raise UserWarning( "\
    invalid lustre stripe info objidx line: '{0}'".format( line ) )
                    info[ 'index_info' ].append( 
                        tuple( int( parts[i] ) for i in ( 0, 1, 3 ) ) )
            retval = cls.from_dict( info )
        log.debug( 'count={0} size={1} offset={2}'.format(
            retval.count, retval.size, retval.offset ) )
        return retval


    def as_dict( self, *names ):
        """ Return elements of stripeinfo as a dict
            Useful for passing to pylut.setstripeinfo
        """
        rv = {}
        for k in names:
            rv[ k ] = self.k
        return rv


    def count_size_as_dict( self ):
        """ Return dict with 'count' and 'size'
            Useful for passing to pylut.setstripeinfo
        """
        return self.as_dict( 'count', 'size' )

    def __repr__( self ):
        return '<{0} (count={1} size={2} offset={3})>'.format( self.__class__.__name__,
            self.count, self.size, self.offset )


def path2fid( path ):
    """
    get fid for a single path
    return FID as string
    """
    cmd = [ env[ 'PYLUTLFSPATH' ], 'path2fid' ]
    opts = None
    args = [ path ]
    retval = None
    ( output, errput ) = runcmd( cmd, opts, args )
    retval = output.rstrip()
    return retval

inode = path2fid


def fid2path( fsname, fid ):
    """
    get all paths for a single fid
    """
    cmd = [ env[ 'PYLUTLFSPATH' ], 'fid2path' ]
    opts = None
    args = [ fsname, fid ]
    retval = None
    ( output, errput ) = runcmd( cmd, opts, args )
    paths = output.split()
    return paths


#TODO - adjust this to take FSItem as input, then can check type without incurring
#       overhead
#       syncfile already expects FSItem, so pylut already depends on fsitem
def getstripeinfo( path ):
    """ get lustre stripe information for path
        INPUT: path to file or dir
        OUTPUT: LustreStripeInfo instance
        NOTE: file type is NOT checked, ie: if called on a pipe i/o will block,
        if called on a socket or softlink an error will be thrown
    """
    cmd = [ env[ 'PYLUTLFSPATH' ], 'getstripe' ]
    opts = None
    args = [ path ]
#    if os.path.isdir( path ):
#        args.insert( 0, '-d' )
    ( output, errput ) = runcmd( cmd, opts, args )
    if True in [ 'has no stripe info' in x for x in (output, errput) ]:
        sinfo = LustreStripeInfo()
    else:
        sinfo = LustreStripeInfo.from_lfs_getstripe( output.splitlines() )
    return sinfo
        

#TODO - adjust this to take FSItem as input, then can check type without incurring
#       overhead
#       syncfile already expects FSItem, so pylut already depends on fsitem
def setstripeinfo( path, count=None, size=None, offset=None ):
    """ set lustre stripe info for path
        path must be either an existing directory or non-existing file
        For efficiency reasons, no checks are done (it is assumed that the 
        calling code already has "stat" information and will perform any necessary
        checks).
        If path is an existing socket or link, an error will be thrown
        If path is an existing fifo, i/o will block (forever?)
        Output: (no return value)
    """
    cmd = [ env[ 'PYLUTLFSPATH' ], 'setstripe' ]
    opts = None
    args = [ path ]
    if count:
        args[0:0] = ['-c', int( count ) ]
    if size:
        args[0:0] = ['-S', int( size ) ]
    if offset:
        args[0:0] = ['-i', int( offset ) ]
    ( output, errput ) = runcmd( cmd, opts, args )


def syncfile( src_path, tgt_path, tmpbase=None, keeptmp=False,
              synctimes=False, syncperms=False, syncowner=False, syncgroup=False,
              pre_checksums=False, post_checksums=True ):
    """
    Lustre stripe aware file sync
    Copies a file to temporary location, then creates a hardlink for the target.
    If either the tmp or the target file already exist, that existing file will
    be checked for accuracy by checking size and mtime (and checksums if
    pre_checksum=True). If synctimes=False, tgt is assumed to be equal if
    tgt_mtime >= src_mtime; otherwise, if syntimes=True, tgt_mtime must be
    exactly equal to src_mtime or tgt will be assumed to be out of sync.  If
    a valid tmp or tgt exist and one or more of synctimes, syncperms,
    syncowner, syncgroup are specified, the specified metadata attributes of
    tmp and/or tgt file will be checked and updated.
    If both tmp and tgt already exist, both will be checked for accuracy
    against src.  If both tmp and tgt are valid (accurate matches), nothing
    happens.
    If at least one of tmp or tgt are found to exist and be valid, the invalid 
    file will be removed and a hardlink created to point to the valid file, thus
    avoiding a full file copy.
    If keeptmp=False, the tmp file hardlink will be removed.
    When copying a file with multiple hard links, set keeptmp=True to keep the
    tempfile around so the other hard links will not result in additional file
    copies.  It is up to the user of this function to remove the tmp files at
    a later time.
    The tmpbase parameter cannot be None (this requirement may be removed in
    a future version).  tmpbase will be created if necessary.  The tmpbase
    directory structure will not be removed and therefore must be cleaned up
    manually.
    If post_checksums=True (default), the checksums for src and tgt should be
    immediately available on the same parameters that were passed in (ie:
    src_path.checksum() and tgt_path.checksum() )
    :param src_path FSItem:
    :param tgt_path FSItem:
    :param tmpbase    str: absolute path to directory where tmp files will be created
    :param keeptmp   bool: if True, do not delete tmpfile (default=False)
    :param synctimes bool: sync file times (default=False)
    :param syncperms bool: sync file permissions (default=False)
    :param syncowner bool: sync file owner (default=False)
    :param syncgroup bool: sync file group (default=False)
    :param pre_checksums  bool: use checksum to determine if src and tgt differ 
                                (default=False)
    :param post_checksums bool: if source was copied to target, compare checksums 
                                to verify target was written correctly 
                                (default=True)
    :return two-tuple: 
        1. fsitem.FSItem: full path to tmpfile (even if keeptmp=False)
        2. action_taken: dict with keys of 'data_copy' and 'meta_update' and values
            of True or False depending on the action taken
        2. sync_results: output from rsync --itemize-changes
    """
    if tmpbase is None:
        #TODO - If tmpbase is None, create one at the mountpoint
        # tmpbase = _pathjoin( 
        #     fsitem.getmountpoint( tgt_path ), 
        #     '.pylutsyncfiletmpbase' )
        raise UserWarning( 'Default tmpbase not yet implemented' )
    # Construct full path to tmpfile: base + <5-char hex value> + <INODE>
    try:
        srcfid = src_path.inode()
    except ( Run_Cmd_Error ) as e:
        raise SyncError( reason=e.reason, origin=e )
    tmpdir = _pathjoin( tmpbase, hex( hash( srcfid ) )[-5:] )
    tmp_path = fsitem.FSItem( os.path.join( tmpdir, srcfid ) )
    log.debug( 'tmp_path:{0}'.format( tmp_path ) )
    # rsync logic: what already exists on the tgt FS and what needs to be updated
    do_mktmpdir = False
    do_setstripe = False
    setstripe_tgt = None
    setstripe_stripeinfo = None
    do_rsync = False
    rsync_src = None
    rsync_tgt = None
    do_hardlink = False
    hardlink_src = None
    hardlink_tgt = None
    do_checksums = False
    sync_action = { 'data_copy': False, 'meta_update': False }
    syncopts = { 'synctimes': synctimes,
                 'syncperms': syncperms,
                 'syncowner': syncowner,
                 'syncgroup': syncgroup,
                 'pre_checksums': pre_checksums,
                 'post_checksums': post_checksums,
               }
    tmp_exists, tmp_data_ok, tmp_meta_ok = ( False, ) * 3
    tgt_exists, tgt_data_ok, tgt_meta_ok = ( False, ) * 3
    tmp_exists = tmp_path.exists()
    if tmp_exists:
        log.debug( 'tmp exists, comparing tmp to src' )
        tmp_data_ok, tmp_meta_ok = _compare_files( src_path, tmp_path, syncopts )
    tgt_exists = tgt_path.exists()
    if tgt_exists:
        log.debug( 'tgt exists, comparing tgt to src' )
        tgt_data_ok, tgt_meta_ok = _compare_files( src_path, tgt_path, syncopts )
    if tmp_exists and tgt_exists:
        log.debug( 'tmp and tgt exist' )
        if tmp_path.inode() == tgt_path.inode():
            log.debug( 'tmp and tgt are same file' )
            if tmp_data_ok:
                if not tmp_meta_ok:
                    log.debug( 'tmp needs metadata update' )
                    sync_action[ 'meta_update' ] = True
                    do_rsync = True
                    rsync_src = src_path
                    rsync_tgt = tmp_path
            else:
                log.debug( 'tmp not ok, unset all' )
                os.unlink( str( tmp_path ) )
                tmp_path.update()
                os.unlink( str( tgt_path ) )
                tgt_path.update()
                tmp_exists, tmp_data_ok, tmp_meta_ok = ( False, ) * 3
                tgt_exists, tgt_data_ok, tgt_meta_ok = ( False, ) * 3
        else:
            log.debug( 'tmp and tgt are different files' )
            # check if one of tmp or tgt are ok, to avoid unnecessary data transfer
            if tmp_data_ok:
                log.debug( 'tmp data ok, unset tgt vars' )
                os.unlink( str( tgt_path ) )
                tgt_path.update()
                tgt_exists, tgt_data_ok, tgt_meta_ok = ( False, ) * 3
            elif tgt_data_ok:
                log.debug( 'tgt data ok, unset tmp vars' )
                os.unlink( str( tmp_path ) )
                tmp_path.update()
                tmp_exists, tmp_data_ok, tmp_meta_ok = ( False, ) * 3
            else:
                log.debug( 'neither tmp nor tgt are ok, unset both' )
                os.unlink( str( tmp_path ) )
                tmp_path.update()
                os.unlink( str( tgt_path ) )
                tgt_path.update()
                tmp_exists, tmp_data_ok, tmp_meta_ok = ( False, ) * 3
                tgt_exists, tgt_data_ok, tgt_meta_ok = ( False, ) * 3
    if tmp_exists != tgt_exists:
        # only one file exists
        if tmp_exists:
            log.debug( 'tmp exists, tgt doesnt' )
            if tmp_data_ok:
                log.debug( 'tmp data ok, tgt needs hardlink' )
                do_hardlink = True
                hardlink_src = tmp_path
                hardlink_tgt = tgt_path
                if not tmp_meta_ok:
                    log.debug( 'tmp needs meta update' )
                    sync_action[ 'meta_update' ] = True
                    do_rsync = True
                    rsync_src = src_path
                    rsync_tgt = tmp_path
            else:
                log.debug( 'tmp not ok, unset tmp vars' )
                os.unlink( str( tmp_path ) )
                tmp_path.update()
                tmp_exists, tmp_data_ok, tmp_meta_ok = ( False, ) * 3
        else:
            log.debug( 'tgt exists, tmp doesnt' )
            if tgt_data_ok:
                log.debug( 'tgt data ok' )
                if keeptmp:
                    log.debug( 'keeptmp=True, tmp needs hardlink' )
                    do_mktmpdir = True
                    do_hardlink = True
                    hardlink_src = tgt_path
                    hardlink_tgt = tmp_path
                else:
                    log.debug( 'keeptmp=False, no action needed' )
                if not tgt_meta_ok:
                    log.debug( 'tgt needs metadata update' )
                    sync_action[ 'meta_update' ] = True
                    do_rsync = True
                    rsync_src = src_path
                    rsync_tgt = tgt_path
            else:
                log.debug( 'tgt not ok, unset tgt vars' )
                os.unlink( str( tgt_path ) )
                tgt_path.update()
                tgt_exists, tgt_data_ok, tgt_meta_ok = ( False, ) * 3
    if not ( tmp_exists or tgt_exists ):
        log.debug( 'neither tmp nor tgt exist' )
        sync_action.update( data_copy   = True,
                            meta_update = True )
        if src_path.is_regular():
            do_setstripe = True
            setstripe_stripeinfo = src_path.stripeinfo()
        if keeptmp:
            do_mktmpdir = True
            setstripe_tgt = tmp_path #will be ignored if do_setstripe is False
            do_rsync = True
            rsync_src = src_path
            rsync_tgt = tmp_path
            do_hardlink = True
            hardlink_src = tmp_path
            hardlink_tgt = tgt_path
            do_checksums = True
        else:
            log.debug( 'keeptmp is false, skipping tmpfile creation' )
            setstripe_tgt = tgt_path #will be ignored if do_setstripe is False
            do_rsync = True
            rsync_src = src_path
            rsync_tgt = tgt_path
            do_checksums = True
    if do_mktmpdir:
        # Ensure tmpdir exists
        log.debug( 'create tmpdir {0}'.format( tmpdir ) )
        try:
            os.makedirs( tmpdir )
        except ( OSError ) as e:
            # OSError: [Errno 17] File exists
            if e.errno != 17:
                raise SyncError(
                    'Unable to create tmpdir {0}'.format( tmpdir ),
                    e
                    )
    if do_setstripe:
        # Set stripe to create the new file with the expected stripe information
        log.debug( 'setstripe (create) {0}'.format( setstripe_tgt ) )
        try:
            setstripeinfo( setstripe_tgt,
                           count=setstripe_stripeinfo.count,
                           size=setstripe_stripeinfo.size )
        except ( Run_Cmd_Error ) as e:
            msg = 'Setstripe failed for {0}'.format( setstripe_tgt )
            raise SyncError( msg, e )
        if rsync_src.size > env[ 'PYLUTRSYNCMAXSIZE' ]:
            # DD for large files
            # TODO - replace dd with ddrescue (for efficient handling of sparse files)
            cmd = [ '/bin/dd' ]
            opts = { 'bs': 4194304,
                     'if': rsync_src,
                     'of': rsync_tgt,
                     'status': 'noxfer',
                   }
            args = None
            ( output, errput ) = runcmd( cmd, opts, args )
            if len( errput.splitlines() ) > 2:
                #TODO - it is hackish to ignore errors based on line count, better is to
                #       use a dd that supports "status=none"
                raise UserWarning( "errors during dd of '{0}' -> '{1}': output='{2}' errors='{3}'".format( 
                    rsync_src, rsync_tgt, output, errput ) )
    if do_rsync:
        # Do the rsync
        cmd = [ env[ 'PYLUTRSYNCPATH' ] ]
        opts = { '--compress-level': 0 }
        args = [ '-l', '-A', '-X', '--super', '--inplace', '--specials' ]
        if synctimes:
            args.append( '-t' )
        if syncperms:
            args.append( '-p' )
        if syncowner:
            args.append( '-o' )
        if syncgroup:
            args.append( '-g' )
        args.extend( [ rsync_src, rsync_tgt ] )
        try:
            ( output, errput ) = runcmd( cmd, opts, args )
        except ( Run_Cmd_Error ) as e:
            raise SyncError( reason=e.reason, origin=e )
        if len( errput ) > 0:
            raise SyncError( 
                reason="errors during sync of '{0}' -> '{1}'".format(
                    rsync_src, rsync_tgt),
                origin="output='{0}' errors='{1}'".format( output, errput ) )
    if do_hardlink:
        log.debug( 'hardlink {0} <- {1}'.format( hardlink_src, hardlink_tgt ) )
        try:
            os.link( str( hardlink_src ), str( hardlink_tgt ) )
        except ( OSError ) as e:
            raise SyncError( 
                reason='Caught exception for link {0} -> {1}'.format(
                    hardlink_src, hardlink_tgt ),
                origin=e )
    # Delete tmp
    if keeptmp is False:
        log.debug( 'unlink tmpfile {0}'.format( tmp_path ) )
        try:
            os.unlink( str( tmp_path ) )
        except ( OSError ) as e:
            # OSError: [Errno 2] No such file or directory
            if e.errno != 2:
                raise SyncError( 
                    'Error attempting to delete tmp {0}'.format( tmp_path ),
                    e
                    )
        #tmp_path.update()
        # TODO - replace rmtree with safer alternative
        #        walk dirs backwards and rmdir each
        #shutil.rmtree( tmpbase ) #this will force delete everything, careful
    if do_checksums and post_checksums:
        # Compare checksums to verify target file was written accurately
        src_checksum = src_path.checksum()
        tgt_checksum = tgt_path.checksum()
        if src_checksum != tgt_checksum:
            reason = 'Checksum mismatch'
            origin = 'src_file={sf}, tgt_file={tf}, '\
                     'src_checksum={sc}, tgt_checksum={tc}'.format(
                        sf=src_path, tf=tgt_path, sc=src_checksum, tc=tgt_checksum )
            raise SyncError( reason, origin )
    return ( tmp_path, sync_action )


def rmdir( path ):
    # could call os.walk() and remove everything
    # faster would be to move path to a known DELETEME dir and delete it later
    raise UserWarning( 'Not Implemented' )


def syncdir( src_path, tgt_path,
             syncowner=False, syncgroup=False, syncperms=False, synctimes=False ):
    """
    lustre stripe aware directory sync
    syncs the directory inode only, does not recurse
    :param src_path FSItem:
    :param tgt_path FSItem:
    :param syncowner bool: sync file owner (default=False)
    :param syncgroup bool: sync file group (default=False)
    :param syncperms bool: sync file permissions (default=False)
    :param synctimes bool: sync file times (default=False)
    :return str: full path to tmpfile (even if keeptmp=False)
    """
    cmd = [ env[ 'PYLUTRSYNCPATH' ] ]
    opts = None
    # strip leaf name from tgtdir to ensure rsync does the right thing
    args = [ '-X', '-A', '--super', '-d' ]
    if synctimes:
        args.append( '-t' )
    if syncperms:
        args.append( '-p' )
    if syncowner:
        args.append( '-o' )
    if syncgroup:
        args.append( '-g' )
    args.append( src_path )
    args.append( "{0}{1}".format( str( tgt_path.parent ), os.sep ) )
    return runcmd( cmd, opts, args )


def _compare_files( f1, f2, syncopts ):
    """
    Compare attributes of f2 to f1 (f1 akin to src, f2 akin to tgt)
    Return tuple of ( data_ok, meta_ok ), where
        data_ok: boolean - True iff size, stripecount, stripesize
                 ( and pre_checksums if specified) all match between both 
                 files; False otherwise
        meta_ok: boolean - True iff remaining attrs, which are specified in 
                 syncopts, match between files; False otherwise
    Also, if synctimes is specified, mtimes must match; otherwise, if f1 is 
    newer than f2, reports data_ok=False
    Meta_ok is True iff relevant parts of syncopts match, False otherwise
    Result is undefined if one or both files don't exist
    """
    data_ok = True
    meta_ok = True
    # Fast check, if f1.ctime older, nothing to do
    if f2.ctime > f1.ctime:
        return( data_ok, meta_ok )
    # Check for data changes
    if f1.size != f2.size:
        data_ok = False
    elif syncopts[ 'synctimes' ] and f1.mtime != f2.mtime:
        data_ok = False
    elif f1.mtime > f2.mtime:
        data_ok = False
    elif syncopts[ 'pre_checksums' ] and f1.checksum() != f2.checksum():
        data_ok = False
    if data_ok == True:
        # Check for metadata changes
        if syncopts[ 'syncowner' ]:
            if f1.uid != f2.uid:
                meta_ok = False
        elif syncopts[ 'syncgroup' ]:
            if f1.gid != f2.gid:
                meta_ok = False
        elif syncopts[ 'synctimes' ] and f1.atime != f2.atime:
            meta_ok = False
    else:
        # data_ok is False, so set meta_ok False as well
        meta_ok = False
    # Lustre stripe info can't change for an existing file, so no need to check it
    return( data_ok, meta_ok )
        

def _pathjoin( *args ):
    """
    Same as os.path.join but implicitly strip leading pathsep chars
    from all but first element.
    """
    return os.path.join( 
        args[0],
        *[ x.lstrip( os.sep ) for x in args[1:] ]
    )


class PylutError( Exception ):
    def __init__( self, reason, origin, *a, **k ):
        super( PylutError, self ).__init__( *a, **k )
        self.reason = reason
        self.origin = origin

    def __repr__( self ):
        return "<{0} (reason={1} origin={2})>".format(
            self.__class__.__name__, self.reason, self.origin )

    __str__ = __repr__

class SyncError( PylutError ): pass

class LustreStripeInfoError( PylutError ): pass


if __name__ == '__main__':
    raise UserWarning( 'cmdling not supported' )
