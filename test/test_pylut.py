#!/bin/env python
# vim:fileencoding=utf8

#import unittest
import pytest
import logging
import os
#import itertools
import pylut
import fsitem
import time
import pprint
import random
import stat
from runcmd import runcmd, Run_Cmd_Error

# NOTE: pytest fixture "testdir" has scope level of "module", which means it will
#       only create the test dirs and files once.  This saves time for tests that
#       don't need to have a clean testdir structure.
#       For tests that DO need a clean testdir structure, use testdir.reset()


# @pytest.mark.skip(reason="skipped")


loglvl = logging.DEBUG
#loglvl = logging.INFO
logging.basicConfig( 
    level=loglvl,
    format="%(levelname)s-%(filename)s[%(lineno)d]-%(funcName)s - %(message)s"
    )


# Common variables needed for psync
syncopts_defaults = dict( keeptmp        = True,
                          synctimes      = True,
                          syncperms      = True,
                          syncowner      = True,
                          syncgroup      = True,
                          pre_checksums  = False,
                          post_checksums = True
                        )

def _path2fid( path ):
    output, errput = runcmd( [ 'lfs', 'path2fid' ], opts=None, args=[ path ] )
    if len( errput ) > 0:
        raise UserWarning()
    return output.rstrip()


def _getmountpoint( path ):
    path = os.path.abspath( path )
    while path != os.path.sep:
        if os.path.ismount( path ):
            return path
        path = os.path.abspath( os.path.join( path, os.pardir ) )
    return path


def _mkregfile( f, size=1024, stripeinfo=None ):
    """
    Overwrite contents of file with random data
    If stripeinfo is provided, first attempt to create file with given stripeinfo
    f must be an instance of fsitem
    """
    fn = str( f )
    if stripeinfo:
        if f.exists():
            os.unlink( fn )
        params = dict( count=None, size=None )
        for k in params:
            v = getatts( stripeinfo, k )
            if v > 0:
                params[ k ] = v
        pylut.setstripeinfo( fn, **params )
    if size < 1:
        return _touch( f )
    if size > 1048576:
        raise UserWarning( 'size too big for mkfile {0}'.format( size ) )
    with open( fn, 'wb' ) as fh:
        fh.write( os.urandom( size ) )


def _appendregfile( f ):
    """
    Append data to a file
    f must be an instance of fsitem
    """
    if size < 1:
        return _touch( f )
    if size > 1048576:
        raise UserWarning( 'size too big for mkfile {0}'.format( size ) )
    with open( str( f ), 'ab' ) as fh:
        fh.write( os.urandom( size ) )


def _touch( f, mtime=None ):
    """
    Interface to Linux 'touch'
    """
    cmd = [ 'touch' ]
    opts = None
    args = [ '-h' ]
    if mtime:
        args.extend( [ '-t', mtime.strftime( '%Y%m%d%H%M.%S' ) ] )
    args.append( str( f ) )
    output, errput = runcmd( cmd, opts, args )


def _files_match( f1, f2, incoming_syncopts ):
    """
    Files f1 and f2 match according to rsync
    Return if rsync finds no differences, False otherwise
    f1 and f2 must be instances of FSItem
    """
    rv = True
    syncopts = dict( keeptmp        = False,
                     synctimes      = False,
                     syncperms      = False,
                     syncowner      = False,
                     syncgroup      = False,
                     pre_checksums  = False,
                     post_checksums = True
                   )
    syncopts.update( incoming_syncopts )
    f1.update()
    f2.update()
    cmd = [ os.environ[ 'PYLUTRSYNCPATH' ] ]
    #opts = { '--timeout': 2 }
    opts = None
    args = [ '-nilHA', '--specials' ]
    if syncopts[ 'synctimes' ]:
        args.append( '-t' )
    if syncopts[ 'syncperms' ]:
        args.append( '-p' )
    if syncopts[ 'syncowner' ]:
        args.append( '-o' )
    if syncopts[ 'syncgroup' ]:
        args.append( '-g' )
    args.extend( [ f1.absname, f2.absname ] )
    ( output, errput ) = runcmd( cmd, opts, args )
    if len( errput ) > 0 and len( output ) > 0:
        rv = False
        pprint.pprint( output )
        pprint.pprint( errput )
    # check stripecount and size
    if f1.stripecount != f2.stripecount:
        rv = False
        print( 'stripecount mismatch' )
    if f1.stripesize != f2.stripesize:
        rv = False
        print( 'stripesize mismatch' )
    # verify checksums
    if f1.checksum() != f2.checksum():
        rv = False
        print( 'checksum mismatch' )
    return rv


def _files_equal( f1, f2 ):
    """
    Return True if both FSItem's share the same inode, False otherwise
    """
    rv = False
    f1.update()
    f2.update()
    if f1.checksum() == f2.checksum():
        rv = True
    return rv


def test_path2fid_valid_path( testdir ):
    for inode, flist in testdir.objects.iteritems():
        for f in flist:
            fid = _path2fid( f.path )
            FID = pylut.path2fid( f.path )
            assert FID == fid


def test_path2fid_invalid_path( testdir ):
    """
    Verify that path2fid throws an error for an invalid path
    """
    f = testdir.objects.values()[0][0]
    path = '{0}xyz'.format( f.path )
    with pytest.raises( Run_Cmd_Error ) as einfo:
        FID = pylut.path2fid( path )
    assert einfo.value.code == 2
    assert 'No such file or directory' in einfo.value.reason


def test_fid2path_valid_fids( testdir ):
    """
    Verify that FID's with multiple links return the correct number of paths
    """
    for inode, flist in testdir.objects.iteritems():
        numlinks = len( flist )
        for f in flist:
            mnt = _getmountpoint( f.path )
            fid = _path2fid( f.path )
            paths = pylut.fid2path( mnt, fid )
            assert len( paths ) == numlinks
            abspath = os.path.abspath( f.path )
            assert abspath in paths


def test_fid2path_invalid_fid( testdir ):
    """
    Verify that fid2path throws an error for an invalid path
    """
    invalid_fids = [ '[0xffffffffff:0xfffff:0x0]', '[0xeeeeeeeeee:0xeeeee:0x0]' ]
    mnt = _getmountpoint( testdir.objects.values()[0][0].path )
    for fid in invalid_fids:
        with pytest.raises( Run_Cmd_Error ) as einfo:
            pylut.fid2path( mnt, fid )
        assert einfo.value.code == 2
        assert 'No such file or directory' in einfo.value.reason


def test_getstripe_valid_paths( testdir ):
    """
    Verify stripecount and stripesize match expected values for files and dirs
    """
    testdir.reset()
    for inode, flist in testdir.objects.iteritems():
        for f in flist:
            if f.typ in [ 'd', 'f' ]:
                sinfo = pylut.getstripeinfo( f.path )
                assert sinfo.count == f.stripecount
                assert sinfo.size == f.stripesize
            #else:
            # nothing to do for other file types
            # to be efficient, pylut.getstripeinfo doesn't do any stat checking


def test_getstripe_invalid_path( testdir ):
    """
    Verify that getstripe throws an error for an invalid path
    """
    f = testdir.objects.values()[0][0]
    path = '{0}xyz'.format( f.path )
    with pytest.raises( Run_Cmd_Error ) as einfo:
        sinfo = pylut.getstripeinfo( '{0}xyz'.format( path ) )
    assert einfo.value.code == 2
    assert 'No such file or directory' in einfo.value.reason


def test_setstripe_existing_path( testdir ):
    """
    Setstripe fails only if attempting to change stripe of an existing file
    """
    genr = ( f.path for f in testdir.files if f.typ == 'f' )
    path = genr.next()
    for c in [ None, 2 ]:
        for s in [ None, 1048576 ]:
            for i in [ None, 1 ]:
                with pytest.raises( Run_Cmd_Error ) as einfo:
                    pylut.setstripeinfo( path, count=c, size=s, offset=i )
                assert einfo.value.code == 17
                assert 'stripe already set' in einfo.value.reason


def test_setstripe_files( testdir ):
    """
    Verify resulting files have the correct stripe information
    """
    genr = ( f.path for f in testdir.files if f.typ == 'f' )
    for c in [ 1, 2 ]:
        for s in [ 524288, 1048576, 2097152 ]:
            for i in [ -1, 1, 2 ]:
                newpath = '{0}xyz'.format( genr.next() )
                pylut.setstripeinfo( newpath, count=c, size=s, offset=i )
                sinfo = pylut.getstripeinfo( newpath )
                assert sinfo.count == c
                assert sinfo.size == s
                if i > 0:
                    assert sinfo.offset == i
                else:
                    assert sinfo.offset >= 0


def test_setstripe_dirs( testdir ):
    """
    Verify dirs get updated stripe settings
    """
    dirs = [ d.path for d in testdir.directories ]
    while len(dirs) < 18:
        dirs = dirs*2
    counter = 0
    for c in [ 1, 2 ]:
        for s in [ 524288, 1048576, 2097152 ]:
            for i in [ -1, 1, 2 ]:
                path = dirs[ counter ]
                pylut.setstripeinfo( path, count=c, size=s, offset=i )
                sinfo = pylut.getstripeinfo( path )
                assert sinfo.count == c
                assert sinfo.size == s
                assert sinfo.offset == i
                counter+=1


def test_syncfile_01( testdir ):
    """
    Attempt to sync a source file that doesn't exist
    Should throw an error
    source NO
    """
    testdir.reset()
    syncopts = syncopts_defaults.copy()
    syncopts[ 'tmpbase' ] = os.path.abspath( testdir.psconfig.TMP_DIR )
    f = testdir.objects.values()[0][0]
    src = fsitem.FSItem( '{0}xyz'.format( f.path ) )
    tgt = fsitem.FSItem( src.absname.replace( testdir.source, testdir.target ) )
    with pytest.raises( pylut.SyncError ) as einfo:
        pylut.syncfile( src_path=src, tgt_path=tgt, **syncopts )
    assert 'No such file or directory' in einfo.value.reason
    

def test_syncfile_02( testdir ):
    """
    Initial sync, keep tmp
    tmp NO
    target NO
    keeptmp YES
    test-pair = 03
    """
    testdir.reset()
    testdir.mk_all_tgtdirs()
    syncopts = syncopts_defaults.copy()
    syncopts.update( keeptmp=True,
                     tmpbase=os.path.abspath( testdir.psconfig.TMP_DIR )
                   )
    for f in testdir.files:
        src = fsitem.FSItem( f.path )
        tgt = fsitem.FSItem( src.absname.replace( testdir.source, testdir.target ) )
        pylut.syncfile( src_path=src, tgt_path=tgt, **syncopts )
        assert _files_match( src, tgt, syncopts )


def test_syncfile_04( testdir ):
    """
    Testing existing target ok, keep tmp
    tmp NO
    tgt OK
    expect tmp file hardlink to be created, tgt file should remain untouched
    test-pair = 08
    """
    testdir.reset()
    testdir.mk_all_tgtdirs()
    syncopts = syncopts_defaults.copy()
    syncopts.update( tmpbase=os.path.abspath( testdir.psconfig.TMP_DIR ) )
    for f in testdir.files:
        src = fsitem.FSItem( f.path )
        tgt = fsitem.FSItem( src.absname.replace( testdir.source, testdir.target ) )
        # make initial sync so tgt exists, don't keep tmpfile
        syncopts.update( keeptmp=False )
        tmp, action = pylut.syncfile( src_path=src, tgt_path=tgt, **syncopts )
        # save original tgt FID
        tgt_fid_orig = tgt.inode()
        tgt.update()
        # verify tmp does not exist
        assert os.path.lexists( str( tmp ) ) == False
        # sync again, keep tmpfile this time
        syncopts.update( keeptmp=True )
#        starttime = time.time()
        tmp, action = pylut.syncfile( src_path=src, tgt_path=tgt, **syncopts )
#        endtime = time.time()
#        # check that elapsed time was <1 second
#        elapsedtime = endtime - starttime
#        assert elapsedtime < 1
        # verify tmp and target are the same file
        assert _files_equal( tgt, tmp )
        # verify tgt has same FID as before
        assert tgt_fid_orig == tgt.inode()
        # verify src and tgt are in sync
        assert _files_match( src, tgt, syncopts )


def test_syncfile_05( testdir ):
    """
    Testing existing target mismatch, keep tmp
    tmp NO
    tgt MISMATCH
    test-pair = 09
    """
    testdir.reset()
    testdir.mk_all_tgtdirs()
    syncopts = syncopts_defaults.copy()
    syncopts.update( tmpbase=os.path.abspath( testdir.psconfig.TMP_DIR ) )
    for f in testdir.files:
        src = fsitem.FSItem( f.path )
        tgt = fsitem.FSItem( src.absname.replace( testdir.source, testdir.target ) )
        # initial sync to create tgt, don't keep tmpfile
        syncopts.update( keeptmp=False )
        tmp, action = pylut.syncfile( src_path=src, tgt_path=tgt, **syncopts )
        # verify tmp does not exist
        assert os.path.lexists( str( tmp ) ) == False
        # save current tgt FID
        tgt_fid_orig = tgt.inode()
        # change src file
        if src.is_regular():
            # sleep is long, faster to just change the file data
            change = random.randint( 1, 1024 )
            _mkregfile( src, size=src.size + change )
        else:
            # no choice but sleep for non-regular files
            time.sleep( 1 )
            _touch( src )
        src.update()
        # sync again, keep tmpfile this time
        # sync should delete old tgt and make a new one
        syncopts.update( keeptmp=True )
        tmp, action = pylut.syncfile( src_path=src, tgt_path=tgt, **syncopts )
        # expect tgt is new, so ensure metadata is up to date
        tgt.update()
        # verify src and tgt are in sync
        assert _files_match( src, tgt, syncopts )
        # verify tmp and target are the same file
        assert _files_equal( tgt, tmp )
        # verify tgt has different FID
        assert tgt_fid_orig != tgt.inode()


def test_syncfile_06( testdir ):
    """
    Testing existing tmp ok, keep tmp
    tmp OK
    tgt NO
    expect tgt file hardlink to be created
    tmp file should remain untouched
    test-pair = 10
    """
    testdir.reset()
    testdir.mk_all_tgtdirs()
    syncopts = syncopts_defaults.copy()
    syncopts.update( tmpbase=os.path.abspath( testdir.psconfig.TMP_DIR ) )
    for f in testdir.files:
        src = fsitem.FSItem( f.path )
        tgt = fsitem.FSItem( src.absname.replace( testdir.source, testdir.target ) )
        # initial sync to create tmp
        syncopts.update( keeptmp=True )
        tmp, action = pylut.syncfile( src_path=src, tgt_path=tgt, **syncopts )
        # delete tgt
        os.unlink( str( tgt ) )
        assert os.path.lexists( str( tgt ) ) == False
        tgt.update()
        # save original tmp FID
        tmp_fid_orig = tmp.inode()
        tmp.update()
        # sync again, should be fast since valid tmp already exists
#        starttime = time.time()
        tmp, action = pylut.syncfile( src_path=src, tgt_path=tgt, **syncopts )
#        endtime = time.time()
        # verify src and tgt are in sync
        assert _files_match( src, tgt, syncopts )
        # verify tmp and target are the same file
        assert _files_equal( tgt, tmp )
#        # check that elapsed time was <1 second
#        elapsedtime = endtime - starttime
#        assert elapsedtime < 1
        # verify tmp has same FID as before
        assert tmp_fid_orig == tmp.inode()


def test_syncfile_07( testdir ):
    """
    Testing existing tmp mismatch, keep tmp
    tmp MISMATCH
    tgt NO
    Expect tmp to get unlinked, then test is same as test_syncfile_02
    Verify tmp has new FID
    test-pair = 11
    """
    testdir.reset()
    testdir.mk_all_tgtdirs()
    syncopts = syncopts_defaults.copy()
    syncopts.update( tmpbase=os.path.abspath( testdir.psconfig.TMP_DIR ) )
    for f in testdir.files:
        src = fsitem.FSItem( f.path )
        tgt = fsitem.FSItem( src.absname.replace( testdir.source, testdir.target ) )
        # initial sync to create tmp
        syncopts.update( keeptmp=True )
        tmp, action = pylut.syncfile( src_path=src, tgt_path=tgt, **syncopts )
        # delete tgt
        os.unlink( str( tgt ) )
        assert os.path.lexists( str( tgt ) ) == False
        tgt.update()
        # save current tmp FID
        tmp_fid_orig = tmp.inode()
        # change src file
        if src.is_regular():
            # sleep is long, faster to just change the file data
            change = random.randint( 1, 1024 )
            _mkregfile( src, size=src.size + change )
        else:
            # no choice but sleep for non-regular files
            time.sleep( 1 )
            _touch( src )
        src.update()
        # sync again, expect a new tmp file
        tmp, action = pylut.syncfile( src_path=src, tgt_path=tgt, **syncopts )
        # expect tmp is new, so ensure metadata is up to date
        tmp.update()
        # verify src and tgt are in sync
        assert _files_match( src, tgt, syncopts )
        # verify tmp and target are the same file
        assert _files_equal( tgt, tmp )
        # verify tmp has different FID
        assert tmp_fid_orig != tmp.inode()





#TODO - REQUIRED TESTS: 2, 4, 5, 6, 7






#    def test_syncfile_03( self ):
#        """
#        Testing initial sync, do not keep tmp
#        tmp NO
#        target NO
#        keeptmp NO
#        test-pair = #2
#        """
#        syncopts = self.syncopts_defaults.copy()
#        syncopts.update( keeptmp=False )
#        for d in self._iter_valid_files():
#            src = fsitem.FSItem( d[ 'srcpath' ] )
#            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
#            syncopts.update( tmpbase=d[ 'tmpbase' ] )
#            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
#            failmsg = 'tgt:{0}'.format( tgt )
#            # check tgt exists
#            self.assertTrue( os.path.exists( str( tgt ) ), msg=failmsg )
#            # check src & tgt match
#            self._assert_files_match( src, tgt, syncopts )
#            # check tmp doesn't exist
#            self.assertFalse( os.path.exists( str( tmp ) ) )
#
#
#    def test_syncfile_08( self ):
#        """
#        Testing existing target ok, do not keep tmp
#        tmp NO
#        tgt OK
#        expect tmp file hardlink to be created, tgt file should be untouched
#        """
#        syncopts = self.syncopts_defaults.copy()
#        for d in self._iter_valid_files():
#            src = fsitem.FSItem( d[ 'srcpath' ] )
#            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
#            syncopts.update( keeptmp=False, tmpbase=d[ 'tmpbase' ] )
#            # make initial sync so tgt exists
#            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
#            # verify tmp doesn't exist
#            self.assertFalse( os.path.exists( str( tmp ) ) )
#            # save tgt FID
#            tgt_fid_1 = tgt.inode()
#            tgt.update()
#            # sync again, should be very fast because nothing to do (keeptmp=False)
#            starttime = time.time()
#            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
#            endtime = time.time()
#            # the usual checks
#            self._assert_files_match( src, tgt, syncopts )
#            # check that elapsed time was <1 second
#            elapsedtime = endtime - starttime
#            self.assertLess( elapsedtime, 1 )
#            # verify tmp does not exist
#            self.assertFalse( os.path.exists( str( tmp ) ) )
#            # verify tgt has same FID as before
#            self.assertEqual( tgt_fid_1, tgt.inode() )
#
#
#    def test_syncfile_09( self ):
#        """
#        Testing existing target mismatch, do not keep tmp
#        tmp NO
#        tgt MISMATCH
#        keeptmp NO
#        """
#        syncopts = self.syncopts_defaults.copy()
#        for d in self._iter_valid_files():
#            src = fsitem.FSItem( d[ 'srcpath' ] )
#            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
#            syncopts.update( keeptmp=False, tmpbase=d[ 'tmpbase' ] )
#            # initial sync to create tgt file
#            pylut.syncfile( src, tgt, **syncopts )
#            # change tgt file with random data
#            self.mkfile( tgt )
#            # save tgt FID
#            tgt_fid_1 = tgt.inode()
#            tgt.update()
#            # syncfile should delete old tgt and make a new one
#            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
#            # the usual checks
#            self._assert_files_match( src, tgt, syncopts )
#            # check tgt has different FID
#            self.assertNotEqual( tgt_fid_1, tgt.inode() )
#            # verify tmp does not exist
#            self.assertFalse( os.path.exists( str( tmp ) ) )
#
#
#    def test_syncfile_10( self ):
#        """
#        Testing existing tmp ok, do not keep tmp
#        tmp OK
#        tgt NO
#        expect tgt file hardlink to be created
#        tmp file should be deleted
#        """
#        syncopts = self.syncopts_defaults.copy()
#        for d in self._iter_valid_files():
#            src = fsitem.FSItem( d[ 'srcpath' ] )
#            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
#            syncopts.update( keeptmp=True, tmpbase=d[ 'tmpbase' ] )
#            # make initial sync to create tmp
#            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
#            # delete tgt
#            os.unlink( str( tgt ) )
#            tgt.update()
#            self.assertFalse( os.path.exists( str( tgt ) ) )
#            # save tmp FID
#            tmp_fid_1 = tmp.inode()
#            # sync again, should be very fast because only have to hardlink tgt
#            syncopts.update( keeptmp=False )
#            starttime = time.time()
#            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
#            endtime = time.time()
#            # the usual check
#            self._assert_files_match( src, tgt, syncopts )
#            # check that elapsed time was <1 second
#            elapsedtime = endtime - starttime
#            self.assertLess( elapsedtime, 1 )
#            # verify tmp doesn't exist
#            self.assertFalse( os.path.exists( str( tmp ) ) )
#            # verify tgt_FID matches old tmp FID
#            self.assertEqual( tgt.inode(), tmp_fid_1 )
#
#
#    def test_syncfile_11( self ):
#        """
#        Testing existing tmp mismatch, do not keep tmp
#        tmp MISMATCH
#        tgt NO
#        Expect tmp to get unlinked, then test is same as test_syncfile_02
#        Verify tgt has a different FID than old tmp
#        """
#        syncopts = self.syncopts_defaults.copy()
#        for d in self._iter_valid_files():
#            src = fsitem.FSItem( d[ 'srcpath' ] )
#            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
#            syncopts.update( keeptmp=True, tmpbase=d[ 'tmpbase' ] )
#            # do initial sync to create tmp
#            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
#            # save tmp FID
#            tmp_fid_1 = tmp.inode()
#            # remove tgt file
#            os.unlink( str( tgt ) )
#            tgt.update()
#            # change data (and mtime) of tmpfile
#            self.mkfile( tmp )
#            # syncfile should delete old tmp and make a new tgt
#            syncopts.update( keeptmp=False )
#            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
#            # usual checks
#            self._assert_files_match( src, tgt, syncopts )
#            self.assertFalse( os.path.exists( str( tmp ) ) )
#            # check tgt has different FID than old tmp
#            self.assertNotEqual( tmp_fid_1, tgt.inode() )
#
#    def test_syncfile_12( self ):
#        """
#        Testing synctimes
#        tmp NO
#        tgt OK
#        src older than tgt
#        synctimes NO
#        If synctimes=NO AND tgt is newer than src, leave tgt alone
#        """
#        syncopts = self.syncopts_defaults.copy()
#        for d in self._iter_valid_files():
#            src = fsitem.FSItem( d[ 'srcpath' ] )
#            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
#            syncopts.update( keeptmp=False, tmpbase=d[ 'tmpbase' ] )
#            # initial sync to create tgt
#            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
#            # ensure tgt mtime > src mtime
#            new_mtime = src.mtime + random.randint( 1, 10 )
#            self.touch( tgt, ( new_mtime, new_mtime ) )
#            tgt.update()
#            # sync again, should be very fast because only have to hardlink tgt
#            syncopts.update( keeptmp=True, synctimes=False )
#            starttime = time.time()
#            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
#            endtime = time.time()
#            elapsedtime = endtime - starttime
#            self.assertLess( elapsedtime, 1 )
#            # usual checks
#            self._assert_files_match( src, tgt, syncopts )
#            self._assert_files_equal( tgt, tmp )
#            # Verify tgt mtime hasn't changed
#            self.assertEqual( new_mtime, tgt.mtime )
#
#
#    def test_syncfile_13( self ):
#        """
#        Testing synctimes
#        tmp NO
#        tgt OK
#        src newer than tgt
#        synctimes NO
#        If synctimes=NO AND tgt is older than src, update tgt
#        """
#        syncopts = self.syncopts_defaults.copy()
#        for d in self._iter_valid_files():
#            src = fsitem.FSItem( d[ 'srcpath' ] )
#            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
#            syncopts.update( keeptmp=False, tmpbase=d[ 'tmpbase' ] )
#            # initial sync to create tgt
#            pylut.syncfile( src, tgt, **syncopts )
#            # track old tgt fid
#            tgt_fid_1 = tgt.inode()
#            # ensure tgt_mtime < src_mtime
#            new_mtime = src.mtime - random.randint( 1, 10 )
#            self.touch( tgt, ( new_mtime, new_mtime ) )
#            tgt.update()
#            # new sync
#            syncopts.update( keeptmp=True, synctimes=False )
#            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
#            # the usual checks
#            self._assert_files_match( src, tgt, syncopts )
#            self._assert_files_equal( tgt, tmp )
#            # Check tgt has a new FID
#            self.assertNotEqual( tgt_fid_1, tgt.inode() )
#
#
#    def test_syncfile_14( self ):
#        """
#        Testing synctimes
#        tmp NO
#        tgt OK
#        src older than tgt
#        synctimes YES
#        When synctimes=YES, tgt must match exactly or get a re-sync
#        """
#        syncopts = self.syncopts_defaults.copy()
#        for d in self._iter_valid_files():
#            src = fsitem.FSItem( d[ 'srcpath' ] )
#            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
#            syncopts.update( keeptmp=False, tmpbase=d[ 'tmpbase' ] )
#            # initial sync to create tgt
#            pylut.syncfile( src, tgt, **syncopts )
#            # track old tgt fid
#            tgt_fid_1 = tgt.inode()
#            # ensure tgt mtime > src mtime
#            new_mtime = src.mtime + random.randint( 1, 10 )
#            self.touch( tgt, ( new_mtime, new_mtime ) )
#            tgt.update()
#            # new sync
#            syncopts.update( keeptmp=True, synctimes=True )
#            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
#            # the usual checks
#            self._assert_files_match( src, tgt, syncopts )
#            self._assert_files_equal( tgt, tmp )
#            # Check tgt has a new FID
#            self.assertNotEqual( tgt_fid_1, tgt.inode() )
#
#
#    def test_syncfile_15( self ):
#        """
#        Testing synctimes
#        tmp NO
#        tgt OK
#        src newer than tgt
#        synctimes YES
#        When synctimes=YES, tgt must have exact same time or get a re-sync
#        """
#        syncopts = self.syncopts_defaults.copy()
#        for d in self._iter_valid_files():
#            src= fsitem.FSItem( d[ 'srcpath' ] )
#            tgt= fsitem.FSItem( d[ 'tgtpath' ] )
#            syncopts.update( keeptmp=False, tmpbase=d[ 'tmpbase' ] )
#            # initial sync to create tgt
#            pylut.syncfile( src, tgt, **syncopts )
#            # get existing tgt fid
#            tgt_fid_1 = tgt.inode()
#            # ensure tgt_mtime < src_mtime
#            new_mtime = src.mtime - random.randint( 1, 10 )
#            self.touch( tgt, ( new_mtime, new_mtime ) )
#            tgt.update()
#            # new sync
#            syncopts.update( keeptmp=True, synctimes=True )
#            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
#            # the usual checks
#            self._assert_files_match( src, tgt, syncopts )
#            self._assert_files_equal( tgt, tmp)
#            # check tgt has a new FID
#            self.assertNotEqual( tgt_fid_1, tgt.inode() )
#
#
#    def test_syncfile_16( self ):
#        """
#        Testing pre-checksum
#        tmp NO
#        tgt OK
#        pre_checkums YES
#        Existing tgt size and mtime match, so pre_checksums should run, but no
#            real way to verify.  However, should still run this test for 
#            completeness.
#        """
#        syncopts = self.syncopts_defaults.copy()
#        for d in self._iter_valid_files():
#            src = fsitem.FSItem( d[ 'srcpath' ] )
#            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
#            syncopts.update( keeptmp=False, tmpbase=d[ 'tmpbase' ] )
#            # initial sync to create tgt
#            pylut.syncfile( src, tgt, **syncopts )
#            # get tgt FID
#            tgt_fid_1 = tgt.inode()
#            tgt.update()
#            # sync with pre_checksums enabled
#            syncopts.update( keeptmp=True, pre_checksums=True )
#            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
#            # the usual checks
#            self._assert_files_match( src, tgt, syncopts )
#            self._assert_files_equal( tgt, tmp )
#            # Check tgt FID has not changed
#            self.assertEqual( tgt_fid_1, tgt.inode() )
#
#
#    def test_syncfile_17( self ):
#        """
#        Testing pre-checksum
#        tmp NO
#        tgt META OK
#        tgt DATA MISMATCH
#        pre_checkums YES
#        Existing tgt size and mtime match but data has changed. Only checksum
#            will detect this.
#        """
#        syncopts = self.syncopts_defaults.copy()
#        for d in self._iter_valid_files():
#            src = fsitem.FSItem( d[ 'srcpath' ] )
#            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
#            syncopts.update( keeptmp=False, tmpbase=d[ 'tmpbase' ] )
#            # initial sync to create tgt
#            pylut.syncfile( src, tgt, **syncopts )
#            # change tgt data contents
#            self.mkfile( tgt )
#            # ensure tgt_mtime == src_mtime
#            time_tuple = ( src.atime, src.mtime, )
#            self.touch( tgt, time_tuple )
#            # get tgt FID
#            tgt.update()
#            tgt_fid_1 = tgt.inode()
#            # Verify checksums differ
#            self.assertNotEqual( tgt.checksum(), src.checksum() )
#            # sync with pre_checksums enabled
#            syncopts.update( keeptmp=True, pre_checksums=True )
#            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
#            # the usual checks
#            self._assert_files_match( src, tgt, syncopts )
#            self._assert_files_equal( tgt, tmp )
#            # Check for new tgt FID
#            self.assertNotEqual( tgt_fid_1, tgt.inode() )
#
#
#    def test_syncfile_18( self ):
#        """
#        Testing pre-checksum
#        tmp META OK --- DATA MISMATCH
#        tgt NO
#        pre_checkums YES
#        Existing tmp size and mtime match but data has changed. Only checksum
#            will detect this.
#        """
#        syncopts = self.syncopts_defaults.copy()
#        for d in self._iter_valid_files():
#            src = fsitem.FSItem( d[ 'srcpath' ] )
#            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
#            syncopts.update( keeptmp=True, tmpbase=d[ 'tmpbase' ] )
#            # initial sync to create tmp
#            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
#            # delete tgt
#            os.unlink( str( tgt ) )
#            self.assertFalse( os.path.exists( str( tgt ) ) )
#            tgt.update()
#            # change tmp data contents
#            self.mkfile( tmp )
#            # set mtime of tmp to same as src
#            time_tuple = ( src.atime, src.mtime, )
#            self.touch( tmp, time_tuple )
#            tmp.update()
#            # get tmp FID
#            old_fid = tmp.inode()
#            # Verify checksums differ
#            self.assertNotEqual( tmp.checksum(), src.checksum() )
#            # sync with pre_checksums enabled
#            syncopts.update( keeptmp=True, pre_checksums=True )
#            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
#            # the usual checks
#            self._assert_files_match( src, tgt, syncopts )
#            self._assert_files_equal( tgt, tmp )
#            # Check for new tgt FID
#            self.assertNotEqual( old_fid, tmp.inode() )
#
#
#    def test_syncfile_19( self ):
#        """
#        Testing size comparison
#        tmp NO
#        tgt MISMATCH size
#        Data has changed, so tgt should be recreated and should have a new FID
#        """
#        syncopts = self.syncopts_defaults.copy()
#        for d in self._iter_valid_files():
#            src = fsitem.FSItem( d[ 'srcpath' ] )
#            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
#            syncopts.update( keeptmp=False, tmpbase=d[ 'tmpbase' ] )
#            # initial sync to create tgt
#            pylut.syncfile( src, tgt, **syncopts )
#            # append data to tgt
#            self.appendfile( tgt )
#            # ensure tgt_mtime == src_mtime
#            time_tuple = ( src.atime, src.mtime, )
#            self.touch( tgt, time_tuple )
#            # double check changes
#            tgt.update()
#            self.assertNotEqual( tgt.size, src.size )
#            self.assertEqual( tgt.mtime, src.mtime )
#            # save tgt FID
#            old_fid = tgt.inode()
#            # sync again
#            syncopts.update( keeptmp=True )
#            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
#            # the usual checks
#            self._assert_files_match( src, tgt, syncopts )
#            self._assert_files_equal( tgt, tmp )
#            # check tgt has a new FID
#            self.assertNotEqual( old_fid, tgt.inode() )
#
#
#    def test_syncfile_20( self ):
#        """
#        Testing size comparison
#        tmp MISMATCH size
#        tgt NO
#        Data has changed, so tmp should be recreated and should have a new FID
#        """
#        syncopts = self.syncopts_defaults.copy()
#        for d in self._iter_valid_files():
#            src = fsitem.FSItem( d[ 'srcpath' ] )
#            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
#            syncopts.update( keeptmp=True, tmpbase=d[ 'tmpbase' ] )
#            # initial sync to create tmp
#            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
#            # append data to tmp
#            self.appendfile( tmp )
#            # ensure tmp mtime == src mtime
#            time_tuple = ( src.atime, src.mtime, )
#            self.touch( tmp, time_tuple )
#            # double check changes
#            tmp.update()
#            self.assertNotEqual( tmp.size, src.size )
#            self.assertEqual( tmp.mtime, src.mtime )
#            # save tmp FID
#            old_fid = tmp.inode()
#            # sync again
#            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
#            # the usual checks
#            self._assert_files_match( src, tgt, syncopts )
#            self._assert_files_equal( tgt, tmp )
#            # check tmp has a new FID
#            self.assertNotEqual( old_fid, tmp.inode() )
#
#
#    def test_syncfile_21( self ):
#        """
#        Testing permission comparison
#        tmp NO
#        tgt DATA OK -- MISMATCH perms
#        Only metadata has changed, so sync should be fast and FIDs remain the same
#        """
#        syncopts = self.syncopts_defaults.copy()
#        for d in self._iter_valid_files():
#            src = fsitem.FSItem( d[ 'srcpath' ] )
#            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
#            syncopts.update( keeptmp=False, tmpbase=d[ 'tmpbase' ] )
#            # initial sync to create tgt
#            pylut.syncfile( src, tgt, **syncopts )
#            # change perms
#            os.chmod( str( tgt ), stat.S_IRUSR | stat.S_IWUSR )
#            # double check changes
#            tgt.update()
#            self.assertNotEqual( tgt.mode, src.mode )
#            # save tgt FID
#            old_fid = tgt.inode()
#            # sync again, should be very fast because only have to update metadata
#            syncopts.update( keeptmp=True )
#            starttime = time.time()
#            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
#            endtime = time.time()
#            elapsedtime = endtime - starttime
#            self.assertLess( elapsedtime, 1 )
#            # the usual checks
#            self._assert_files_match( src, tgt, syncopts )
#            self._assert_files_equal( tgt, tmp )
#            # check tgt has the same FID
#            self.assertEqual( old_fid, tgt.inode() )
#
#
#    def test_syncfile_22( self ):
#        """
#        Testing permission comparison
#        tmp DATA OK -- MISMATCH perms
#        tgt NO
#        Only metadata has changed, so sync should be fast and FIDs remain the same
#        """
#        syncopts = self.syncopts_defaults.copy()
#        for d in self._iter_valid_files():
#            src = fsitem.FSItem( d[ 'srcpath' ] )
#            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
#            syncopts.update( keeptmp=True, tmpbase=d[ 'tmpbase' ] )
#            # initial sync to create tmp
#            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
#            # change perms
#            os.chmod( str( tmp ), stat.S_IRUSR | stat.S_IWUSR )
#            # double check changes
#            tmp.update()
#            self.assertNotEqual( tmp.mode, src.mode )
#            # save tmp FID
#            old_fid = tgt.inode()
#            tgt.update()
#            # delete tgt
#            os.unlink( str( tgt ) )
#            # sync again, should be very fast because only have to update metadata
#            starttime = time.time()
#            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
#            endtime = time.time()
#            elapsedtime = endtime - starttime
#            self.assertLess( elapsedtime, 1 )
#            # the usual checks
#            self._assert_files_match( src, tgt, syncopts )
#            self._assert_files_equal( tgt, tmp )
#            # check tmp has the same FID
#            self.assertEqual( old_fid, tmp.inode() )
#
#
#    def test_syncfile_23( self ):
#        """
#        Testing owner comparison
#        tmp NO
#        tgt DATA OK -- MISMATCH owner
#        Only metadata has changed, so sync should be fast and FIDs remain the same
#        """
#        syncopts = self.syncopts_defaults.copy()
#        for d in self._iter_valid_files():
#            src = fsitem.FSItem( d[ 'srcpath' ] )
#            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
#            syncopts.update( keeptmp=False, tmpbase=d[ 'tmpbase' ] )
#            # initial sync to create tgt
#            pylut.syncfile( src, tgt, **syncopts )
#            # change owner
#            os.chown( str( tgt ), 27929, -1 )
#            # double check changes
#            tgt.update()
#            self.assertNotEqual( tgt.uid, src.uid )
#            self.assertEqual( tgt.gid, src.gid )
#            # save tgt FID
#            old_fid = tgt.inode()
#            # sync again, should be very fast because only have to update metadata
#            syncopts.update( keeptmp=True )
#            starttime = time.time()
#            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
#            endtime = time.time()
#            elapsedtime = endtime - starttime
#            self.assertLess( elapsedtime, 1 )
#            # usual checks
#            self._assert_files_match( src, tgt, syncopts )
#            self._assert_files_equal( tgt, tmp )
#            # check tgt has the same FID
#            self.assertEqual( old_fid, tgt.inode() )
#
#
#    def test_syncfile_24( self ):
#        """
#        Testing owner comparison
#        tmp DATA OK -- MISMATCH owner
#        tgt NO
#        Only metadata has changed, so sync should be fast and FIDs remain the same
#        """
#        syncopts = self.syncopts_defaults.copy()
#        for d in self._iter_valid_files():
#            src = fsitem.FSItem( d[ 'srcpath' ] )
#            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
#            syncopts.update( keeptmp=True, tmpbase=d[ 'tmpbase' ] )
#            # initial sync to create tmp
#            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
#            # change owner
#            os.chown( str( tmp ), 27929, -1 )
#            # double check changes
#            tmp.update()
#            self.assertNotEqual( tmp.uid, src.uid )
#            self.assertEqual( tmp.gid, src.gid )
#            # save tmp FID
#            old_fid = tmp.inode()
#            # delete tgt
#            os.unlink( str( tgt ) )
#            tgt.update()
#            # sync again, should be very fast because only have to update metadata
#            starttime = time.time()
#            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
#            endtime = time.time()
#            elapsedtime = endtime - starttime
#            self.assertLess( elapsedtime, 1 )
#            # usual checks
#            self._assert_files_match( src, tgt, syncopts )
#            self._assert_files_equal( tgt, tmp )
#            # check tmp has the same FID
#            self.assertEqual( old_fid, tmp.inode() )
#
#
#    def test_syncfile_25( self ):
#        """
#        Testing group comparison
#        tmp NO
#        tgt DATA OK -- MISMATCH group
#        Only metadata has changed, so sync should be fast and FIDs remain the same
#        """
#        syncopts = self.syncopts_defaults.copy()
#        for d in self._iter_valid_files():
#            src = fsitem.FSItem( d[ 'srcpath' ] )
#            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
#            syncopts.update( keeptmp=False, tmpbase=d[ 'tmpbase' ] )
#            # initial sync to create tgt
#            pylut.syncfile( src, tgt, **syncopts )
#            # change group
#            os.chown( str( tgt ), -1, 14802 )
#            # double check changes
#            tgt.update()
#            self.assertEqual( tgt.uid, src.uid )
#            self.assertNotEqual( tgt.gid, src.gid )
#            # save tgt FID
#            old_fid = tgt.inode()
#            # sync again, should be very fast because only have to update metadata
#            syncopts.update( keeptmp=True )
#            starttime = time.time()
#            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
#            endtime = time.time()
#            elapsedtime = endtime - starttime
#            self.assertLess( elapsedtime, 1 )
#            # usual checks
#            self._assert_files_match( src, tgt, syncopts )
#            self._assert_files_equal( tgt, tmp )
#            # check tgt has the same FID
#            self.assertEqual( old_fid, tgt.inode() )
#
#
#    def test_syncfile_26( self ):
#        """
#        Testing group comparison
#        tmp DATA OK -- MISMATCH group
#        tgt NO
#        Only metadata has changed, so sync should be fast and FIDs remain the same
#        """
#        syncopts = self.syncopts_defaults.copy()
#        for d in self._iter_valid_files():
#            src = fsitem.FSItem( d[ 'srcpath' ] )
#            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
#            syncopts.update( keeptmp=True, tmpbase=d[ 'tmpbase' ] )
#            # initial sync to create tmp
#            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
#            # change group
#            os.chown( str( tmp ), -1, 14802 )
#            # double check changes
#            tmp.update()
#            self.assertEqual( tmp.uid, src.uid )
#            self.assertNotEqual( tmp.gid, src.gid )
#            # save tmp FID
#            old_fid = tmp.inode()
#            # delete tgt
#            os.unlink( str( tgt ) )
#            tgt.update()
#            # sync again, should be very fast because only have to update metadata
#            starttime = time.time()
#            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
#            endtime = time.time()
#            elapsedtime = endtime - starttime
#            self.assertLess( elapsedtime, 1 )
#            # usual checks
#            self._assert_files_match( src, tgt, syncopts )
#            self._assert_files_equal( tgt, tmp )
#            # check tmp has the same FID
#            self.assertEqual( old_fid, tmp.inode() )


#    def _assert_files_equal( self, f1, f2 ):
#        """
#        Assert that both FSItem's share the same inode
#        """
#        f1.update()
#        f2.update()
#        failmsg = 'f1: {0} f2: {1}'.format( f1, f2 )
#        self.assertEqual( f1.inode(), f2.inode(), msg=failmsg )
#
#
#    def test_showvars( self ):
#        logging.debug( pprint.pformat( [ 'valid_dirpaths', self.valid_dirpaths ] ) )
#        logging.debug( pprint.pformat( [ 'valid_filepaths', self.valid_filepaths ] ) )
#        logging.debug( pprint.pformat( [ 'hardlinks', self.hardlinks ] ) )
#        logging.debug( pprint.pformat( [ 'striped_dirs', self.striped_dirs ] ) )
#        logging.debug( pprint.pformat( [ 'striped_files', self.striped_files ] ) )
#
#
#if __name__ == "__main__":
#    loglvl = logging.DEBUG
#    loglvl = logging.INFO
#    logging.basicConfig( 
#        level=loglvl,
#        format="%(levelname)s-%(filename)s[%(lineno)d]-%(funcName)s - %(message)s"
#        )
#
#    # Some tests sometimes fail due to timing taking too long
#    # (think this is due to HSN quiesces during testing, though not confirmed)
#    # test_syncfile_12
#    # test_syncfile_22
#    # test_syncfile_25
#    #
#    # Some tests fail sometimes due to checksum mismatch
#    # (think this is due to HSN quiesces during testing, though not confirmed)
#    # test_syncfile_07
#
#    test_list = [
#        'test_syncfile_09',
#        ]
#    suite = unittest.TestSuite( map( Test_Pylut, test_list ) )
#
#    suite = unittest.TestLoader().loadTestsFromTestCase( Test_Pylut )
#
#    unittest.TextTestRunner( verbosity=2 ).run( suite )
