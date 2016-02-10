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
        

# Encapsulation objects, for function return values
#               0       1              2             3        4      5      6
attr_order = ( 'size', 'stripecount', 'stripesize', 'mtime', 'uid', 'gid', 'mode', )
Attr_Matches = collections.namedtuple( 'Attr_Matches', attr_order )


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
        self.count = 0
        self.size = 0
        self.offset = -1
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
        if lines[0].startswith( 'stripe_count:' ):
            # this is output from a directory
            parts = lines[0].split()
            retval = cls( count=parts[1], size=parts[3], offset=parts[5] )
        elif len( lines ) < 8:
            raise LustreStripeInfoError( 
                reason='too few input lines, expected 8 or more',
                origin=pprint.pformat( lines )
                )
        else:
            # this is a normal file
            found_objidx = False
            info = {}
            del lines[0] #first line is a repeat of the filename
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
        return retval

# $> lfs getstripe -d /u/staff/aloftus
# stripe_count:   1 stripe_size:    1048576 stripe_offset:  -1
# $> lfs getstripe /u/staff/aloftus/junk
# /u/staff/aloftus/junk
# lmm_stripe_count:   1
# lmm_stripe_size:    1048576
# lmm_pattern:        1
# lmm_layout_gen:     0
# lmm_stripe_offset:  106
#         obdidx           objid           objid           group
#            106        20779670      0x13d1296                0


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


def path2fid ( path ):
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


def getstripeinfo( path ):
    """ get lustre stripe information for path
        INPUT: path to file or dir
        OUTPUT: LustreStripeInfo instance
    """
    isdir = False
    cmd = [ env[ 'PYLUTLFSPATH' ], 'getstripe' ]
    opts = None
    args = [ path ]
    if os.path.isdir( path ):
        isdir = True
        args.insert( 0, '-d' )
    ( output, errput ) = runcmd( cmd, opts, args )
    return LustreStripeInfo.from_lfs_getstripe( output.splitlines() )
        

def setstripeinfo( path, count=None, size=None, offset=None ):
    """ set lustre stripe info for path
        returns None
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
    If either the tmp or the target file already exist, it will be checked for
    accuracy by checking size and mtime (and checksums if pre_checksum=True). If 
    synctimes=False, tgt is assumed to be equal if tgt_mtime >= src_mtime; 
    otherwise, if syntimes=True, tgt_mtime must be exactly equal to src_mtime or tgt
    will be assumed to be out of sync.
    If a valid tmp or tgt exist and one or more of synctimes, syncperms, syncowner,
    syncgroup are specified, the specified metadata attributes of tmp and/or tgt 
    file will be checked and updated.
    If both tmp and tgt already exist, both will be checked for accuracy against src.
    If both tmp and tgt are valid (accurate matches), nothing happens.
    If at least one of tmp or tgt are found to exist and be valid, the invalid 
    file will be removed and a hardlink created to point to the valid file, thus
    avoiding a full file copy.
    If keeptmp=False, the tmp file hardlink will be removed.
    When copying a file with multiple hard links, set keeptmp=True
    to keep the tempfile around so the other hard links will not result in
    additional file copies.  It is up to the user of this function to remove the tmp
    files at a later time.
    The tmpbase parameter cannot be None (this requirement may be removed in a
    future version).  tmpbase will be created if necessary.  The tmpbase directory
    structure will not be removed and therefore must be cleaned up manually.
    If post_checksums=True (default), the checksums for src and tgt should be
    immediately available on the same parameters that were passed in 
    (ie: src_path.checksum() and tgt_path.checksum() )
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
    :return three-tuple: 
        1. fsitem.FSItem: full path to tmpfile (even if keeptmp=False)
        2. action_taken: dict with keys of 'data_copy' and 'meta_update' and values
            of True or False depending on the action taken
        3. attrs_affected: namedtuple with boolean values indicating if the file
            attribute in that position was updated or not.  Indices are:
            ( 'size', 'stripecount', 'stripesize', 'mtime', 'uid', 'gid', 'mode' )
    """
    if tmpbase is None:
        #TODO - If tmpbase is None, create one at the mountpoint
        # tmpbase = _pathjoin( 
        #     fsitem.getmountpoint( tgt_path ), 
        #     '.pylutsyncfiletmpbase' )
        raise UserWarning( 'Default tmpbase not yet implemented' )
    # Construct full path to tmpfile: base + <5-char hex value> + <FID>
    try:
        srcfid = src_path.fid()
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
    #attrs_affected = None
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
        tmp_data_ok, tmp_meta_ok, tmp_attrs_affected = _compare_files( 
            src_path, tmp_path, syncopts )
    tgt_exists = tgt_path.exists()
    if tgt_exists:
        log.debug( 'tgt exists, comparing tgt to src' )
        tgt_data_ok, tgt_meta_ok, tgt_attrs_affected = _compare_files( 
            src_path, tgt_path, syncopts )
    if tmp_exists and tgt_exists:
        log.debug( 'tmp and tgt exist' )
        tgt_tmp_are_same_file = tmp_path.fid() == tgt_path.fid()
        if tgt_tmp_are_same_file:
            log.debug( 'tmp and tgt are same file' )
            if tmp_data_ok:
                attrs_affected = tmp_attrs_affected
                if not tmp_meta_ok:
                    log.debug( 'tmp needs metadata update' )
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
                attrs_affected = tmp_attrs_affected
                do_hardlink = True
                hardlink_src = tmp_path
                hardlink_tgt = tgt_path
                if not tmp_meta_ok:
                    log.debug( 'tmp needs meta update' )
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
                attrs_affected = tgt_attrs_affected
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
        attrs_affected = Attr_Matches( True, True, True, 
            synctimes, syncowner, syncgroup, syncperms )
        if keeptmp:
            do_mktmpdir = True
            do_setstripe = True
            setstripe_stripeinfo = src_path.stripeinfo()
            setstripe_tgt = tmp_path
            do_rsync = True
            rsync_src = src_path
            rsync_tgt = tmp_path
            do_hardlink = True
            hardlink_src = tmp_path
            hardlink_tgt = tgt_path
            do_checksums = True
        else:
            log.debug( 'keeptmp is false, skipping tmpfile creation' )
            do_setstripe = True
            setstripe_stripeinfo = src_path.stripeinfo()
            setstripe_tgt = tgt_path
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
        sync_action[ 'data_copy' ] = True
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
        sync_action[ 'meta_update' ] = True
        # Do the rsync
        cmd = [ env[ 'PYLUTRSYNCPATH' ] ]
        opts = { '--compress-level': 0 }
        args = [ '-X', '-A', '--super', '--inplace' ]
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
    return ( tmp_path, sync_action, attrs_affected )


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
    tgt_parent = fsitem.FSItem( os.path.dirname( str( tgt_path ) ) )
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
    args.append( "{0}{1}".format( str( tgt_parent ), os.sep ) )
    return runcmd( cmd, opts, args )


def _compare_files( file1, file2, syncopts ):
    """
    Compare attributes of file2 to file1
    Return tuple of ( data_ok, meta_ok, attrs_affected ), where
        data_ok: boolean - True iff size, stripecount, stripesize
                 ( and pre_checksums if specified) all match between both 
                 files; False otherwise
        meta_ok: boolean - True iff remaining attrs, which are specified in 
                 syncopts, match between files; False otherwise
        attrs_affected: Attr_Matches - Each position in the namedtuple represents a 
                        file attribute; the values are booleans where True indicates
                        that specific file attribute on file2 will be updated 
                        on a sync.  
                        This is different than simply indicating which attributes
                        did or didn't match, because it takes into account the 
                        specific syncronization options that were given (ie: if
                        syncuser wasn't specified in syncopts, then even if uid's 
                        differ, the value in position 4 (uid) will be False because 
                        uid requested for sync).
    Also, if synctimes is specified, mtimes must match; otherwise, if file1 is 
    newer than file2, reports data_ok=False
    Meta_ok is True iff relevant parts of syncopts match, False otherwise
    Result is undefined if one or both files don't exist
    """
#    #          0       1              2             3        4      5      6
#    attrs = ( 'size', 'stripecount', 'stripesize', 'mtime', 'uid', 'gid', 'mode', )
    attr_match_results = file1.compare( file2, attr_order )
    matches = Attr_Matches( *attr_match_results )
    log.debug( 'Match results: {0}'.format( matches ) )
    # mask filters out attributes to be ignored
    mask = [ True, True, True ]
    for k in ( 'synctimes', 'syncowner', 'syncgroup', 'syncperms', ):
        mask.append( syncopts[ k ] )
    affected_attr_list = [ x and not y for x,y in zip( mask, matches ) ]
    # special case: if synctimes not requested, check for file1 newer than file2
    if not syncopts[ 'synctimes' ]:
        if file1.mtime > file2.mtime:
            log.debug( 'file1 has a newer mtime' )
            affected_attr_list[ 3 ] = True
    attrs_affected = Attr_Matches( *affected_attr_list )
    # data is ok only if no updates needed for any of first four attrs
    data_ok = attrs_affected[:4] == ( False, False, False, False, )
    # meta data is okay if none of the remaining attrs need updates
    meta_ok = attrs_affected[4:] == ( False, False, False, )
    if data_ok:
        # don't need to compare checksums if a previous test already failed
        if syncopts[ 'pre_checksums' ]:
            log.debug( 'Comparing checksums...' )
            if file1.checksum() != file2.checksum():
                data_ok = False
                log.debug( 'Checksum mismatch' )
#    meta_ok = True
#    if syncopts[ 'syncowner' ]:
#        if not matches[4]:
#            meta_ok = False
#    if syncopts[ 'syncgroup' ]:
#        if not matches[5]:
#            meta_ok = False
#    if syncopts[ 'syncperms' ]:
#        if not matches[6]:
#            meta_ok = False
    return ( data_ok, meta_ok, attrs_affected )


def _pathjoin( *args ):
    """
    Same as os.path.join but implicitly strip leading pathsep chars
    from all but first element.
    """
#    log.debug( 'args:{0}'.format( args ) )
#    head = args[0]
#    tail = [ x.lstrip( os.sep ) for x in args[1:] ]
#    log.debug( 'head:{0} tail:{1}'.format( head, tail ) )
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
