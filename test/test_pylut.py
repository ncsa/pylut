#!/bin/env python
# vim:fileencoding=utf8

import unittest
import logging
import os
import itertools
import pylut
import fsitem
import time
import pprint
import random
import stat
from runcmd import runcmd, Run_Cmd_Error


class Test_Pylut( unittest.TestCase ):
    testbases = { '/mnt/a': 'settools/test/pylut_test',
                  '/mnt/b': 'projects/test/pylut_test',
                  '/mnt/c': 'scratch/test/pylut_test',
                }
    invalid_filenames = [ 'invalid_file_1', 'invalid_file_2' ]
    invalid_fids = [ '[0xffffffffff:0xfffff:0x0]', '[0xeeeeeeeeee:0xeeeee:0x0]' ]
    valid_filenames = dict( a = [ '4'                ],
                            b = [ '4', '3'           ],
                            c = [ '4', '3', '2'      ],
                            d = [ '4', '3', '2', '1' ]
                          )
    stripe_counts = range( 1, 4 )
    stripe_sizes = ( 2**19, 2**20, 2**21, 2**22 )
    sync_tmp_dirname = 'TESTPYLUT_TMPDIR'
    sync_tgt_dirname = 'TESTPYLUT_SYNCTGTDIR'

    syncopts_defaults = dict( keeptmp        = True,
                              synctimes      = True,
                              syncperms      = True,
                              syncowner      = True,
                              syncgroup      = True,
                              pre_checksums  = False,
                              post_checksums = True
                            )

    # these should match defaults in pylut.syncfile
    pylut_syncopts_defaults = dict( keeptmp        = False,
                                    synctimes      = False,
                                    syncperms      = False,
                                    syncowner      = False,
                                    syncgroup      = False,
                                    pre_checksums  = False,
                                    post_checksums = True
                                  )

    def touch( self, filename, times=None ):
        fn = str( filename )
        with open( fn, 'a' ):
            os.utime( fn, times )


    def mkfile( self, filename, size=1024, stripeinfo=None ):
        """
            Overwrite contents of file with random data
            If stripeinfo is provided:
                first attempt to create file with the given stripeinfo
        """
        fn = str( filename )
        if stripeinfo:
            if os.path.exists( fn ):
                os.unlink( fn )
            params = dict( count=None, size=None )
            for k in params:
                v = getattr( stripeinfo, k )
                if v > 0:
                    params[ k ] = v
            pylut.setstripeinfo( fn, **params )
        if size < 1:
            return Test_Pylut.touch( filename )
        if size > 1048576:
            raise UserWarning( 'size too big for mkfile {0}'.format( size ) )
        with open( fn, 'wb' ) as f:
            f.write( os.urandom( size ) )
                

    def appendfile( self, filename, size=1024 ):
        """
            Append random data to a file
        """
        if size < 1:
            return Test_Pylut.touch( filename )
        if size > 1048576:
            raise UserWarning( 'size too big for appendfile {0}'.format( size ) )
        with open( str( filename ), 'ab' ) as f:
            f.write( os.urandom( 1024 ) )


    def setUp( self ):
        """
        For each mountpoint, set up test files and directory structure
        /mnt/c/scratch/test/pylut_test/
        ├── a
        │   └── 4     (hardlink 4)
        ├── b
        │   ├── 3     (hardlink 3)
        │   └── 4       (hardlink 4)
        ├── c
        │   ├── 2     (hardlink 2)
        │   ├── 3       (hardlink 3)
        │   └── 4         (hardlink 4)
        ├── d
        │   ├── 1
        │   ├── 2     (hardlink 2)
        │   ├── 3       (hardlink 3)
        │   └── 4         (hardlink 4)
        ├── dir_c1s1048576
        ├── dir_c1s2097152
        ├── dir_c1s4194304
        ├── dir_c1s524288
        ├── dir_c2s1048576
        ├── dir_c2s2097152
        ├── dir_c2s4194304
        ├── dir_c2s524288
        ├── dir_c3s1048576
        ├── dir_c3s2097152
        ├── dir_c3s4194304
        ├── dir_c3s524288
        ├── file_c1s1048576
        ├── file_c1s2097152
        ├── file_c1s4194304
        ├── file_c1s524288
        ├── file_c2s1048576
        ├── file_c2s2097152
        ├── file_c2s4194304
        ├── file_c2s524288
        ├── file_c3s1048576
        ├── file_c3s2097152
        ├── file_c3s4194304
        ├── file_c3s524288
        └── TESTPYLUT_SYNCTGTDIR
        17 directories, 23 files

        If tearDown fails, clear it with:
        for dir in /mnt/a/settools /mnt/b/projects /mnt/c/scratch; do find $dir/test/pylut_test -delete; done
        """
#        # time setup step
#        tick = time.time()
        # disable debug logging inside setup
        logger = logging.getLogger()
        log_lvl_orig = logger.getEffectiveLevel()
        logger.setLevel( logging.WARNING )

        self.fid_path = {}
        self.path_fid = {}
        self.valid_filepaths = []
        self.valid_dirpaths = []
        self.invalid_filepaths = []
        self.hardlinks = {}
        self.striped_dirs = {}
        self.striped_files = {}
        for ( mnt, path ) in self.testbases.iteritems():
            top = os.path.join( mnt, path )
            # ensure top level test dir exists
            try:
                os.mkdir( top )
            except ( OSError ) as e:
                if e.errno != 17:
                    raise e
            # create file paths for this mountpoint
            for ( dn, flist ) in self.valid_filenames.iteritems():
                # make dir
                dirpath = os.path.join( mnt, path, dn )
                dirpath = dirpath.rstrip( os.sep )
                try:
                    os.makedirs( dirpath )
                except ( OSError ) as e:
                    if e.errno != 17:
                        raise e
                # add dir to list
                self.valid_dirpaths.append( dirpath )
                # track dir FID
                ( output, errput ) = runcmd( [ "lfs", "path2fid" ], opts=None, args=[ dirpath ] )
                fid = output.rstrip()
                self.path_fid[ dirpath ] = fid
                if fid in self.fid_path:
                    raise UserWarning( "Duplicate fid found for dir '{0}'".format( 
                        dirpath ) )
                self.fid_path[ fid ] = [ dirpath ]
                # isolate hardlink filenames per mountpoint
                if mnt not in self.hardlinks:
                    self.hardlinks[ mnt ] = {}
                # create files
                for fn in flist:
                    fullpath = os.path.join( dirpath, fn )
                    if fn not in self.hardlinks[ mnt ]:
                        self.hardlinks[ mnt ][ fn ] = [ fullpath ]
                        self.mkfile( fullpath )
                    else:
                        logging.debug( 'Attempting to hardlink {0} -> {1}'.format(
                            self.hardlinks[ mnt ][ fn ][ 0 ], fullpath ) )
                        os.link( self.hardlinks[ mnt ][ fn ][ 0 ], fullpath )
                        self.hardlinks[ mnt ][ fn ].append( fullpath )
                    # add file to list
                    self.valid_filepaths.append( fullpath )
                    # track file FID
                    ( output, errput ) = runcmd( [ "lfs", "path2fid" ], opts=None, args=[ fullpath ] )
                    fid = output.rstrip()
                    if fid in self.fid_path:
                        self.fid_path[ fid ].append( fullpath )
                    else:
                        self.fid_path[ fid ] = [ fullpath ]
                    self.path_fid[ fullpath ] = fid
#                    logging.debug( fullpath )
            # ensure invalid filenames do not exist
            for fn in self.invalid_filenames:
                invalidpath = os.path.join( mnt, path, fn )
                if os.path.exists( invalidpath ):
                    os.unlink( invalidpath )
                self.invalid_filepaths.append( invalidpath )
            # Create names for dirs and files with varying stripe counts & sizes
            # dirs are created, files only get names generated
            for ( count, size ) in itertools.product( self.stripe_counts, self.stripe_sizes ):
                dirname = 'dir_c{0}s{1}'.format( count, size )
                fulldirpath = os.path.join( mnt, path, dirname )
                os.mkdir( fulldirpath )
                self.striped_dirs[ fulldirpath ] = { 'stripe_count': count, 'stripe_size': size }
                self.valid_dirpaths.append( fulldirpath )
                filename = 'file_c{0}s{1}'.format( count, size )
                fullfilepath = os.path.join( mnt, path, filename )
                self.striped_files[ fullfilepath ] = { 'stripe_count': count, 'stripe_size': size }
                self.valid_filepaths.append( fullfilepath )
            # Create synctgtdirs
            os.mkdir( pylut._pathjoin( mnt, path, self.sync_tgt_dirname ) )
        # Set stripe details for striped dirs; create striped files
        for fullpath, details in itertools.chain( self.striped_dirs.items(), self.striped_files.items() ):
            cmd = [ "lfs", "setstripe" ]
            opts=None
            args=[ '-c', details[ 'stripe_count' ], '-S', details[ 'stripe_size' ], fullpath ]
            runcmd( cmd, opts=opts,  args=args )
            # track FID
            ( output, errput ) = runcmd( [ "lfs", "path2fid" ], opts=None, args=[ fullpath ] )
            fid = output.rstrip()
            self.fid_path[ fid ] = [ fullpath ]
            self.path_fid[ fullpath ] = fid
        #restore original logging level
        logger.setLevel( log_lvl_orig )
#        tock = time.time()
#        setuptime = tock - tick
#        print( '\n{0:.4f} setuptime'.format( setuptime ) )
#        # start timer
#        self.tick = time.time()


    def tearDown( self ):
        """
        clean up test area after every test
        """
#        # stop time
#        self.tock = time.time()
#        runtime = self.tock - self.tick
#        print( '{0:.4f} runtime'.format( runtime ) )
#        return
#        tick = time.time()
        # delete everything under the test area
        for ( mnt, path ) in self.testbases.iteritems():
            top = pylut._pathjoin( mnt, path )
            for root, dirs, files in os.walk( top, topdown=False ):
                for name in files:
                    os.remove( os.path.join( root, name ) )
                for name in dirs:
                    os.rmdir( os.path.join( root, name ) )
#        tock = time.time()
#        teardowntime = tock - tick
#        print( '{0:.4f} teardowntime'.format( teardowntime ) )


    def _iter_valid_files( self ):
        for ( srcmnt, tgtmnt ) in itertools.combinations( self.testbases.keys(), 2 ):
            srcbase = self.testbases[ srcmnt ]
            tgtbase = self.testbases[ tgtmnt ]
            for srcpath in self.valid_filepaths:
                if not srcpath.startswith( srcmnt ): 
                    continue
                # create target filename by stripping srcmnt and srcbase
                #make tgtfn unique using from_mnt to avoid collisions, ie:
                #when copying from /mnt/a -> /mnt/b vs. /mnt/c -> /mnt/b
                idx = len( os.path.join( srcmnt, srcbase ) ) + 1
                tgtfn = '{0}{1}'.format( srcpath[idx:], srcmnt ).replace( os.sep, '_' )
                tgtpath = pylut._pathjoin( 
                    tgtmnt, tgtbase, self.sync_tgt_dirname, tgtfn )
                tmpbase = pylut._pathjoin( tgtmnt, tgtbase, self.sync_tmp_dirname )
                yield { 'srcmnt':  srcmnt,
                       'srcbase': srcbase,
                       'srcpath': srcpath,
                        'tgtmnt':  tgtmnt,
                       'tgtbase': tgtbase,
                       'tgtpath': tgtpath,
                       'tmpbase': tmpbase }


    def test_path2fid_valid_path( self ):
        for ( path, fid ) in self.path_fid.iteritems():
            FID = pylut.path2fid( path )
            self.assertEqual( FID, fid )


    def test_path2fid_invalid_path( self ):
        for fullpath in self.invalid_filepaths:
            with self.assertRaises( Run_Cmd_Error ) as cm:
                FID = pylut.path2fid( fullpath )
            self.assertEqual( cm.exception.code, 2 )
            self.assertIn( 'No such file or directory', cm.exception.reason )


    def test_fid2path_valid_fids( self ):
        """
        Verify that FID's with multiple links return the correct number of paths
        """
        # foreach mountpoint:
        #   foreach [ file in validfile that startswith mountpoint ]:
        #     actual hardlinks should equal length of hardlinks[ mnt ][ fn ]
        for mnt in self.testbases:
            for fullpath in itertools.chain( self.valid_filepaths,
                                             self.valid_dirpaths ):
                if not fullpath.startswith( mnt ):
                    continue
                basename = os.path.basename( fullpath )
                numlinks = 1
                if basename in self.hardlinks[ mnt ]:
                    numlinks = len( self.hardlinks[ mnt ][ basename ] )
                logging.debug( 'lookup path_fid[ {0} ]'.format( fullpath ) )
                fid = self.path_fid[ fullpath ]
                paths = pylut.fid2path( mnt, fid )
#                logging.debug( "RESULT from fid2path ... {0}".format( paths ) )
                self.assertEqual( len( paths ), numlinks )
                self.assertIn( fullpath, paths )


    def test_fid2path_invalid_fid( self ):
        for ( mnt, path ) in self.testbases.iteritems():
            for fid in self.invalid_fids:
                with self.assertRaises( Run_Cmd_Error ) as cm:
                    pylut.fid2path( mnt, fid )
                self.assertEqual( cm.exception.code, 2 )
                self.assertIn( 'No such file or directory', cm.exception.reason )


    def test_getstripe_valid_paths( self ):
        for fullpath in itertools.chain( self.valid_dirpaths, self.valid_filepaths ):
            #TODO - get actual defaults from filesystem
            expected_count = 1
            expected_size = 1048576
            if fullpath in self.striped_dirs:
                expected_count = self.striped_dirs[ fullpath ][ 'stripe_count' ]
                expected_size = self.striped_dirs[ fullpath ][ 'stripe_size' ]
            elif fullpath in self.striped_files:
                expected_count = self.striped_files[ fullpath ][ 'stripe_count' ]
                expected_size = self.striped_files[ fullpath ][ 'stripe_size' ]
#            logging.debug( 'getstripeinfo( {0} )'.format( fullpath ) )
            sinfo = pylut.getstripeinfo( fullpath )
#            logging.debug( 'getstripeinfo results {0} )'.format( sinfo ) )
            self.assertEqual( sinfo.count, expected_count )
            self.assertEqual( sinfo.size, expected_size )
            if os.path.basename( fullpath ).startswith( 'file_c' ):
                num_obj_indexes = len( sinfo.index_info )
                self.assertEqual( num_obj_indexes, expected_count )


    def test_getstripe_invalid_paths( self ):
        for fullpath in self.invalid_filepaths:
            with self.assertRaises( Run_Cmd_Error ) as cm:
                pylut.getstripeinfo( fullpath )
            self.assertEqual( cm.exception.code, 2 )
            self.assertIn( 'No such file or directory', cm.exception.reason )


    def test_setstripe_valid_files( self ):
        for fullpath in self.invalid_filepaths:
            expected_count = 1
            expected_size = 1048576
            pylut.setstripeinfo( fullpath )
            sinfo = pylut.getstripeinfo( fullpath )
            self.assertEqual( sinfo.count, expected_count )
            self.assertEqual( sinfo.size, expected_size )
            for count in self.stripe_counts:
                expected_count = count
                expected_size = 1048576
                newpath = '{0}-1_c{1}s{2}'.format( fullpath, expected_count, expected_size )
                kw = { 'count': count }
                pylut.setstripeinfo( newpath, **kw )
                sinfo = pylut.getstripeinfo( newpath )
                self.assertEqual( sinfo.count, expected_count )
                self.assertEqual( sinfo.size, expected_size )
            for size in self.stripe_sizes:
                expected_count = 1
                expected_size = size
                newpath = '{0}-2_c{1}s{2}'.format( fullpath, expected_count, expected_size )
                kw = { 'size': size }
                pylut.setstripeinfo( newpath, **kw )
                sinfo = pylut.getstripeinfo( newpath )
                self.assertEqual( sinfo.count, expected_count )
                self.assertEqual( sinfo.size, expected_size )
            for ( count, size ) in itertools.product( self.stripe_counts, self.stripe_sizes ):
                expected_count = count
                expected_size = size
                newpath = '{0}-3_c{1}s{2}'.format( fullpath, expected_count, expected_size )
                kw = { 'count': count,
                       'size':  size,
                }
                pylut.setstripeinfo( newpath, **kw )
                sinfo = pylut.getstripeinfo( newpath )
                self.assertEqual( sinfo.count, expected_count )
                self.assertEqual( sinfo.size, expected_size )


    def test_setstripe_valid_dirs( self ):
        for fullpath in self.valid_dirpaths:
            expected_count = 2
            expected_size = 2097152
            if fullpath in self.striped_dirs:
                expected_count = self.striped_dirs[ fullpath ][ 'stripe_count' ] + 1
                expected_size = self.striped_dirs[ fullpath ][ 'stripe_size' ] * 2
            kw = { 'count': expected_count,
                   'size':  expected_size,
            }
            pylut.setstripeinfo( fullpath, **kw )
            sinfo = pylut.getstripeinfo( fullpath )
            self.assertEqual( sinfo.count, expected_count )
            self.assertEqual( sinfo.size, expected_size )



    def test_setstripe_invalid_paths( self ):
        """ setstripe fails only if attempt to change stripe of existing file
        """
        for fullpath in self.valid_filepaths:
            with self.assertRaises( Run_Cmd_Error ) as cm:
                pylut.setstripeinfo( fullpath )
            self.assertEqual( cm.exception.code, 17 )
            self.assertIn( 'stripe already set', cm.exception.reason )
            for count in self.stripe_counts:
                kw = { 'count': count }
                with self.assertRaises( Run_Cmd_Error ) as cm:
                    pylut.setstripeinfo( fullpath, **kw )
                self.assertEqual( cm.exception.code, 17 )
                self.assertIn( 'stripe already set', cm.exception.reason )
            for size in self.stripe_sizes:
                kw = { 'size': size }
                with self.assertRaises( Run_Cmd_Error ) as cm:
                    pylut.setstripeinfo( fullpath, **kw )
                self.assertEqual( cm.exception.code, 17 )
                self.assertIn( 'stripe already set', cm.exception.reason )
            for ( count, size ) in itertools.product( self.stripe_counts, self.stripe_sizes ):
                kw = { 'count': count,
                       'size':  size,
                }
                with self.assertRaises( Run_Cmd_Error ) as cm:
                    pylut.setstripeinfo( fullpath, **kw )
                self.assertEqual( cm.exception.code, 17 )
                self.assertIn( 'stripe already set', cm.exception.reason )


    def test_syncfile_01( self ):
        """
        source NO
        """
        syncopts = self.syncopts_defaults.copy()
        for ( srcmnt, tgtmnt ) in itertools.combinations( self.testbases.keys(), 2 ):
            srcbase = self.testbases[ srcmnt ]
            tgtbase = self.testbases[ tgtmnt ]
            tmpbase = pylut._pathjoin( tgtmnt, tgtbase, self.sync_tmp_dirname )
            syncopts[ 'tmpbase' ] = tmpbase
            for fn in self.invalid_filenames:
                src = fsitem.FSItem( os.path.join( srcmnt, srcbase, fn ) )
                tgt = fsitem.FSItem( os.path.join( tgtmnt, tgtbase, fn ) )
                with self.assertRaises( pylut.SyncError ) as cm:
                    pylut.syncfile(
                        src_path = src,
                        tgt_path = tgt,
                        **syncopts
                        )
                self.assertIn( 'No such file or directory', cm.exception.reason )


    def test_syncfile_02( self ):
        """
        Testing initial sync, keep tmp
        tmp NO
        target NO
        keeptmp YES
        """
        syncopts = self.syncopts_defaults.copy()
        syncopts.update( keeptmp=True )
        for d in self._iter_valid_files():
            src = fsitem.FSItem( d[ 'srcpath' ] )
            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
            syncopts.update( tmpbase=d[ 'tmpbase' ] )
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            failmsg = 'tgt:{0}'.format( tgt )
            # check tgt exists
            self.assertTrue( os.path.exists( str( tgt ) ), msg=failmsg )
            # check src & tgt match
            self._assert_files_match( src, tgt, syncopts )
            # check tmp & tgt point to same file
            self._assert_files_equal( tgt, tmp )


    def test_syncfile_03( self ):
        """
        Testing initial sync, do not keep tmp
        tmp NO
        target NO
        keeptmp NO
        """
        syncopts = self.syncopts_defaults.copy()
        syncopts.update( keeptmp=False )
        for d in self._iter_valid_files():
            src = fsitem.FSItem( d[ 'srcpath' ] )
            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
            syncopts.update( tmpbase=d[ 'tmpbase' ] )
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            failmsg = 'tgt:{0}'.format( tgt )
            # check tgt exists
            self.assertTrue( os.path.exists( str( tgt ) ), msg=failmsg )
            # check src & tgt match
            self._assert_files_match( src, tgt, syncopts )
            # check tmp doesn't exist
            self.assertFalse( os.path.exists( str( tmp ) ) )


    def test_syncfile_04( self ):
        """
        Testing existing target ok, keep tmp
        tmp NO
        tgt OK
        expect tmp file hardlink to be created, tgt file should remain untouched
        """
        syncopts = self.syncopts_defaults.copy()
        for d in self._iter_valid_files():
            src = fsitem.FSItem( d[ 'srcpath' ] )
            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
            syncopts.update( keeptmp=False, tmpbase=d[ 'tmpbase' ] )
            # make initial sync so tgt exists
            pylut.syncfile( src, tgt, **syncopts )
            # save tgt FID
            tgt_fid_1 = tgt.fid()
            tgt.update()
            # sync again, should be very fast because only have to hardlink tmp
            syncopts.update( keeptmp=True )
            starttime = time.time()
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            endtime = time.time()
            # check that elapsed time was <1 second
            elapsedtime = endtime - starttime
            self.assertLess( elapsedtime, 1 )
            # verify tmp and tgt are same file
            self._assert_files_equal( tgt, tmp )
            # verify tgt has same FID as before
            self.assertEqual( tgt_fid_1, tgt.fid() )


    @unittest.skip( 'skipped as redundant' )
    def test_syncfile_05( self ):
        """
        Testing existing target mismatch, keep tmp
        tmp NO
        tgt MISMATCH
        """
        syncopts = self.syncopts_defaults.copy()
        for d in self._iter_valid_files():
            src = fsitem.FSItem( d[ 'srcpath' ] )
            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
            # initial sync to create tgt
            syncopts.update( keeptmp=False, tmpbase=d[ 'tmpbase' ] )
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            self.assertFalse( os.path.exists( str( tmp ) ) )
            # change tgt file with random data
            self.mkfile( tgt )
            tgt.update()
            # verify tgt differs from src
            # save tgt FID
            tgt_fid_1 = tgt.fid()
            # syncfile should delete old tgt and make a new one
            syncopts.update( keeptmp=True )
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            # all the usual checks
            self._assert_files_match( src, tgt, syncopts )
            self._assert_files_equal( tgt, tmp )
            # check tgt has different FID
            self.assertNotEqual( tgt_fid_1, tgt.fid() )


    def test_syncfile_08( self ):
        """
        Testing existing target ok, do not keep tmp
        tmp NO
        tgt OK
        expect tmp file hardlink to be created, tgt file should be untouched
        """
        syncopts = self.syncopts_defaults.copy()
        for d in self._iter_valid_files():
            src = fsitem.FSItem( d[ 'srcpath' ] )
            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
            syncopts.update( keeptmp=False, tmpbase=d[ 'tmpbase' ] )
            # make initial sync so tgt exists
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            # verify tmp doesn't exist
            self.assertFalse( os.path.exists( str( tmp ) ) )
            # save tgt FID
            tgt_fid_1 = tgt.fid()
            tgt.update()
            # sync again, should be very fast because nothing to do (keeptmp=False)
            starttime = time.time()
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            endtime = time.time()
            # the usual checks
            self._assert_files_match( src, tgt, syncopts )
            # check that elapsed time was <1 second
            elapsedtime = endtime - starttime
            self.assertLess( elapsedtime, 1 )
            # verify tmp does not exist
            self.assertFalse( os.path.exists( str( tmp ) ) )
            # verify tgt has same FID as before
            self.assertEqual( tgt_fid_1, tgt.fid() )


    def test_syncfile_09( self ):
        """
        Testing existing target mismatch, do not keep tmp
        tmp NO
        tgt MISMATCH
        keeptmp NO
        """
        syncopts = self.syncopts_defaults.copy()
        for d in self._iter_valid_files():
            src = fsitem.FSItem( d[ 'srcpath' ] )
            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
            syncopts.update( keeptmp=False, tmpbase=d[ 'tmpbase' ] )
            # initial sync to create tgt file
            pylut.syncfile( src, tgt, **syncopts )
            # change tgt file with random data
            self.mkfile( tgt )
            # save tgt FID
            tgt_fid_1 = tgt.fid()
            tgt.update()
            # syncfile should delete old tgt and make a new one
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            # the usual checks
            self._assert_files_match( src, tgt, syncopts )
            # check tgt has different FID
            self.assertNotEqual( tgt_fid_1, tgt.fid() )
            # verify tmp does not exist
            self.assertFalse( os.path.exists( str( tmp ) ) )


    def test_syncfile_06( self ):
        """
        Testing existing tmp ok, keep tmp
        tmp OK
        tgt NO
        expect tgt file hardlink to be created
        tmp file should remain untouched
        """
        syncopts = self.syncopts_defaults.copy()
        for d in self._iter_valid_files():
            src = fsitem.FSItem( d[ 'srcpath' ] )
            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
            syncopts.update( keeptmp=True, tmpbase=d[ 'tmpbase' ] )
            # make initial sync so tmp exists
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            # delete tgt
            os.unlink( str( tgt ) )
            self.assertFalse( os.path.exists( str( tgt ) ) )
            tgt.update()
            # save tmp FID
            tmp_fid_1 = tmp.fid()
            # sync again, should be very fast because only have to hardlink tgt
            starttime = time.time()
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            endtime = time.time()
            # the usual checks
            self._assert_files_match( src, tgt, syncopts )
            self._assert_files_equal( tgt, tmp )
            # check that elapsed time was <1 second
            elapsedtime = endtime - starttime
            self.assertLess( elapsedtime, 1 )
            # verify tmp has same FID as before
            self.assertEqual( tmp_fid_1, tmp.fid() )


    def test_syncfile_10( self ):
        """
        Testing existing tmp ok, do not keep tmp
        tmp OK
        tgt NO
        expect tgt file hardlink to be created
        tmp file should be deleted
        """
        syncopts = self.syncopts_defaults.copy()
        for d in self._iter_valid_files():
            src = fsitem.FSItem( d[ 'srcpath' ] )
            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
            syncopts.update( keeptmp=True, tmpbase=d[ 'tmpbase' ] )
            # make initial sync to create tmp
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            # delete tgt
            os.unlink( str( tgt ) )
            tgt.update()
            self.assertFalse( os.path.exists( str( tgt ) ) )
            # save tmp FID
            tmp_fid_1 = tmp.fid()
            # sync again, should be very fast because only have to hardlink tgt
            syncopts.update( keeptmp=False )
            starttime = time.time()
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            endtime = time.time()
            # the usual check
            self._assert_files_match( src, tgt, syncopts )
            # check that elapsed time was <1 second
            elapsedtime = endtime - starttime
            self.assertLess( elapsedtime, 1 )
            # verify tmp doesn't exist
            self.assertFalse( os.path.exists( str( tmp ) ) )
            # verify tgt_FID matches old tmp FID
            self.assertEqual( tgt.fid(), tmp_fid_1 )


    def test_syncfile_07( self ):
        """
        Testing existing tmp mismatch, keep tmp
        tmp MISMATCH
        tgt NO
        Expect tmp to get unlinked, then test is same as test_syncfile_02
        Verify tmp has new FID
        """
        syncopts = self.syncopts_defaults.copy()
        for d in self._iter_valid_files():
            src = fsitem.FSItem( d[ 'srcpath' ] )
            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
            syncopts.update( tmpbase=d[ 'tmpbase' ] )
            # do initial sync to get tmppath
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            # save tmp FID
            tmp_fid_1 = tmp.fid()
            # remove tgt file
            os.unlink( str( tgt ) )
            self.assertFalse( os.path.exists( str( tgt ) ) )
            tgt.update()
            # change data (and mtime) of tmpfile
            self.mkfile( tmp )
            # syncfile should delete old tmp and make a new one
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            # all the usual checks
            self._assert_files_match( src, tgt, syncopts )
            self._assert_files_equal( tgt, tmp )
            # check tmp has different FID
            self.assertNotEqual( tmp_fid_1, tmp.fid() )


    def test_syncfile_11( self ):
        """
        Testing existing tmp mismatch, do not keep tmp
        tmp MISMATCH
        tgt NO
        Expect tmp to get unlinked, then test is same as test_syncfile_02
        Verify tgt has a different FID than old tmp
        """
        syncopts = self.syncopts_defaults.copy()
        for d in self._iter_valid_files():
            src = fsitem.FSItem( d[ 'srcpath' ] )
            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
            syncopts.update( keeptmp=True, tmpbase=d[ 'tmpbase' ] )
            # do initial sync to create tmp
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            # save tmp FID
            tmp_fid_1 = tmp.fid()
            # remove tgt file
            os.unlink( str( tgt ) )
            tgt.update()
            # change data (and mtime) of tmpfile
            self.mkfile( tmp )
            # syncfile should delete old tmp and make a new tgt
            syncopts.update( keeptmp=False )
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            # usual checks
            self._assert_files_match( src, tgt, syncopts )
            self.assertFalse( os.path.exists( str( tmp ) ) )
            # check tgt has different FID than old tmp
            self.assertNotEqual( tmp_fid_1, tgt.fid() )

    def test_syncfile_12( self ):
        """
        Testing synctimes
        tmp NO
        tgt OK
        src older than tgt
        synctimes NO
        If synctimes=NO AND tgt is newer than src, leave tgt alone
        """
        syncopts = self.syncopts_defaults.copy()
        for d in self._iter_valid_files():
            src = fsitem.FSItem( d[ 'srcpath' ] )
            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
            syncopts.update( keeptmp=False, tmpbase=d[ 'tmpbase' ] )
            # initial sync to create tgt
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            # ensure tgt mtime > src mtime
            new_mtime = src.mtime + random.randint( 1, 10 )
            self.touch( tgt, ( new_mtime, new_mtime ) )
            tgt.update()
            # sync again, should be very fast because only have to hardlink tgt
            syncopts.update( keeptmp=True, synctimes=False )
            starttime = time.time()
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            endtime = time.time()
            elapsedtime = endtime - starttime
            self.assertLess( elapsedtime, 1 )
            # usual checks
            self._assert_files_match( src, tgt, syncopts )
            self._assert_files_equal( tgt, tmp )
            # Verify tgt mtime hasn't changed
            self.assertEqual( new_mtime, tgt.mtime )


    def test_syncfile_13( self ):
        """
        Testing synctimes
        tmp NO
        tgt OK
        src newer than tgt
        synctimes NO
        If synctimes=NO AND tgt is older than src, update tgt
        """
        syncopts = self.syncopts_defaults.copy()
        for d in self._iter_valid_files():
            src = fsitem.FSItem( d[ 'srcpath' ] )
            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
            syncopts.update( keeptmp=False, tmpbase=d[ 'tmpbase' ] )
            # initial sync to create tgt
            pylut.syncfile( src, tgt, **syncopts )
            # track old tgt fid
            tgt_fid_1 = tgt.fid()
            # ensure tgt_mtime < src_mtime
            new_mtime = src.mtime - random.randint( 1, 10 )
            self.touch( tgt, ( new_mtime, new_mtime ) )
            tgt.update()
            # new sync
            syncopts.update( keeptmp=True, synctimes=False )
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            # the usual checks
            self._assert_files_match( src, tgt, syncopts )
            self._assert_files_equal( tgt, tmp )
            # Check tgt has a new FID
            self.assertNotEqual( tgt_fid_1, tgt.fid() )


    def test_syncfile_14( self ):
        """
        Testing synctimes
        tmp NO
        tgt OK
        src older than tgt
        synctimes YES
        When synctimes=YES, tgt must match exactly or get a re-sync
        """
        syncopts = self.syncopts_defaults.copy()
        for d in self._iter_valid_files():
            src = fsitem.FSItem( d[ 'srcpath' ] )
            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
            syncopts.update( keeptmp=False, tmpbase=d[ 'tmpbase' ] )
            # initial sync to create tgt
            pylut.syncfile( src, tgt, **syncopts )
            # track old tgt fid
            tgt_fid_1 = tgt.fid()
            # ensure tgt mtime > src mtime
            new_mtime = src.mtime + random.randint( 1, 10 )
            self.touch( tgt, ( new_mtime, new_mtime ) )
            tgt.update()
            # new sync
            syncopts.update( keeptmp=True, synctimes=True )
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            # the usual checks
            self._assert_files_match( src, tgt, syncopts )
            self._assert_files_equal( tgt, tmp )
            # Check tgt has a new FID
            self.assertNotEqual( tgt_fid_1, tgt.fid() )


    def test_syncfile_15( self ):
        """
        Testing synctimes
        tmp NO
        tgt OK
        src newer than tgt
        synctimes YES
        When synctimes=YES, tgt must have exact same time or get a re-sync
        """
        syncopts = self.syncopts_defaults.copy()
        for d in self._iter_valid_files():
            src= fsitem.FSItem( d[ 'srcpath' ] )
            tgt= fsitem.FSItem( d[ 'tgtpath' ] )
            syncopts.update( keeptmp=False, tmpbase=d[ 'tmpbase' ] )
            # initial sync to create tgt
            pylut.syncfile( src, tgt, **syncopts )
            # get existing tgt fid
            tgt_fid_1 = tgt.fid()
            # ensure tgt_mtime < src_mtime
            new_mtime = src.mtime - random.randint( 1, 10 )
            self.touch( tgt, ( new_mtime, new_mtime ) )
            tgt.update()
            # new sync
            syncopts.update( keeptmp=True, synctimes=True )
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            # the usual checks
            self._assert_files_match( src, tgt, syncopts )
            self._assert_files_equal( tgt, tmp)
            # check tgt has a new FID
            self.assertNotEqual( tgt_fid_1, tgt.fid() )


    def test_syncfile_16( self ):
        """
        Testing pre-checksum
        tmp NO
        tgt OK
        pre_checkums YES
        Existing tgt size and mtime match, so pre_checksums should run, but no
            real way to verify.  However, should still run this test for 
            completeness.
        """
        syncopts = self.syncopts_defaults.copy()
        for d in self._iter_valid_files():
            src = fsitem.FSItem( d[ 'srcpath' ] )
            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
            syncopts.update( keeptmp=False, tmpbase=d[ 'tmpbase' ] )
            # initial sync to create tgt
            pylut.syncfile( src, tgt, **syncopts )
            # get tgt FID
            tgt_fid_1 = tgt.fid()
            tgt.update()
            # sync with pre_checksums enabled
            syncopts.update( keeptmp=True, pre_checksums=True )
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            # the usual checks
            self._assert_files_match( src, tgt, syncopts )
            self._assert_files_equal( tgt, tmp )
            # Check tgt FID has not changed
            self.assertEqual( tgt_fid_1, tgt.fid() )


    def test_syncfile_17( self ):
        """
        Testing pre-checksum
        tmp NO
        tgt META OK
        tgt DATA MISMATCH
        pre_checkums YES
        Existing tgt size and mtime match but data has changed. Only checksum
            will detect this.
        """
        syncopts = self.syncopts_defaults.copy()
        for d in self._iter_valid_files():
            src = fsitem.FSItem( d[ 'srcpath' ] )
            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
            syncopts.update( keeptmp=False, tmpbase=d[ 'tmpbase' ] )
            # initial sync to create tgt
            pylut.syncfile( src, tgt, **syncopts )
            # change tgt data contents
            self.mkfile( tgt )
            # ensure tgt_mtime == src_mtime
            time_tuple = ( src.atime, src.mtime, )
            self.touch( tgt, time_tuple )
            # get tgt FID
            tgt.update()
            tgt_fid_1 = tgt.fid()
            # Verify checksums differ
            self.assertNotEqual( tgt.checksum(), src.checksum() )
            # sync with pre_checksums enabled
            syncopts.update( keeptmp=True, pre_checksums=True )
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            # the usual checks
            self._assert_files_match( src, tgt, syncopts )
            self._assert_files_equal( tgt, tmp )
            # Check for new tgt FID
            self.assertNotEqual( tgt_fid_1, tgt.fid() )


    def test_syncfile_18( self ):
        """
        Testing pre-checksum
        tmp META OK --- DATA MISMATCH
        tgt NO
        pre_checkums YES
        Existing tmp size and mtime match but data has changed. Only checksum
            will detect this.
        """
        syncopts = self.syncopts_defaults.copy()
        for d in self._iter_valid_files():
            src = fsitem.FSItem( d[ 'srcpath' ] )
            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
            syncopts.update( keeptmp=True, tmpbase=d[ 'tmpbase' ] )
            # initial sync to create tmp
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            # delete tgt
            os.unlink( str( tgt ) )
            self.assertFalse( os.path.exists( str( tgt ) ) )
            tgt.update()
            # change tmp data contents
            self.mkfile( tmp )
            # set mtime of tmp to same as src
            time_tuple = ( src.atime, src.mtime, )
            self.touch( tmp, time_tuple )
            tmp.update()
            # get tmp FID
            old_fid = tmp.fid()
            # Verify checksums differ
            self.assertNotEqual( tmp.checksum(), src.checksum() )
            # sync with pre_checksums enabled
            syncopts.update( keeptmp=True, pre_checksums=True )
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            # the usual checks
            self._assert_files_match( src, tgt, syncopts )
            self._assert_files_equal( tgt, tmp )
            # Check for new tgt FID
            self.assertNotEqual( old_fid, tmp.fid() )


    def test_syncfile_19( self ):
        """
        Testing size comparison
        tmp NO
        tgt MISMATCH size
        Data has changed, so tgt should be recreated and should have a new FID
        """
        syncopts = self.syncopts_defaults.copy()
        for d in self._iter_valid_files():
            src = fsitem.FSItem( d[ 'srcpath' ] )
            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
            syncopts.update( keeptmp=False, tmpbase=d[ 'tmpbase' ] )
            # initial sync to create tgt
            pylut.syncfile( src, tgt, **syncopts )
            # append data to tgt
            self.appendfile( tgt )
            # ensure tgt_mtime == src_mtime
            time_tuple = ( src.atime, src.mtime, )
            self.touch( tgt, time_tuple )
            # double check changes
            tgt.update()
            self.assertNotEqual( tgt.size, src.size )
            self.assertEqual( tgt.mtime, src.mtime )
            # save tgt FID
            old_fid = tgt.fid()
            # sync again
            syncopts.update( keeptmp=True )
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            # the usual checks
            self._assert_files_match( src, tgt, syncopts )
            self._assert_files_equal( tgt, tmp )
            # check tgt has a new FID
            self.assertNotEqual( old_fid, tgt.fid() )


    def test_syncfile_20( self ):
        """
        Testing size comparison
        tmp MISMATCH size
        tgt NO
        Data has changed, so tmp should be recreated and should have a new FID
        """
        syncopts = self.syncopts_defaults.copy()
        for d in self._iter_valid_files():
            src = fsitem.FSItem( d[ 'srcpath' ] )
            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
            syncopts.update( keeptmp=True, tmpbase=d[ 'tmpbase' ] )
            # initial sync to create tmp
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            # append data to tmp
            self.appendfile( tmp )
            # ensure tmp mtime == src mtime
            time_tuple = ( src.atime, src.mtime, )
            self.touch( tmp, time_tuple )
            # double check changes
            tmp.update()
            self.assertNotEqual( tmp.size, src.size )
            self.assertEqual( tmp.mtime, src.mtime )
            # save tmp FID
            old_fid = tmp.fid()
            # sync again
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            # the usual checks
            self._assert_files_match( src, tgt, syncopts )
            self._assert_files_equal( tgt, tmp )
            # check tmp has a new FID
            self.assertNotEqual( old_fid, tmp.fid() )


    def test_syncfile_21( self ):
        """
        Testing permission comparison
        tmp NO
        tgt DATA OK -- MISMATCH perms
        Only metadata has changed, so sync should be fast and FIDs remain the same
        """
        syncopts = self.syncopts_defaults.copy()
        for d in self._iter_valid_files():
            src = fsitem.FSItem( d[ 'srcpath' ] )
            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
            syncopts.update( keeptmp=False, tmpbase=d[ 'tmpbase' ] )
            # initial sync to create tgt
            pylut.syncfile( src, tgt, **syncopts )
            # change perms
            os.chmod( str( tgt ), stat.S_IRUSR | stat.S_IWUSR )
            # double check changes
            tgt.update()
            self.assertNotEqual( tgt.mode, src.mode )
            # save tgt FID
            old_fid = tgt.fid()
            # sync again, should be very fast because only have to update metadata
            syncopts.update( keeptmp=True )
            starttime = time.time()
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            endtime = time.time()
            elapsedtime = endtime - starttime
            self.assertLess( elapsedtime, 1 )
            # the usual checks
            self._assert_files_match( src, tgt, syncopts )
            self._assert_files_equal( tgt, tmp )
            # check tgt has the same FID
            self.assertEqual( old_fid, tgt.fid() )


    def test_syncfile_22( self ):
        """
        Testing permission comparison
        tmp DATA OK -- MISMATCH perms
        tgt NO
        Only metadata has changed, so sync should be fast and FIDs remain the same
        """
        syncopts = self.syncopts_defaults.copy()
        for d in self._iter_valid_files():
            src = fsitem.FSItem( d[ 'srcpath' ] )
            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
            syncopts.update( keeptmp=True, tmpbase=d[ 'tmpbase' ] )
            # initial sync to create tmp
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            # change perms
            os.chmod( str( tmp ), stat.S_IRUSR | stat.S_IWUSR )
            # double check changes
            tmp.update()
            self.assertNotEqual( tmp.mode, src.mode )
            # save tmp FID
            old_fid = tgt.fid()
            tgt.update()
            # delete tgt
            os.unlink( str( tgt ) )
            # sync again, should be very fast because only have to update metadata
            starttime = time.time()
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            endtime = time.time()
            elapsedtime = endtime - starttime
            self.assertLess( elapsedtime, 1 )
            # the usual checks
            self._assert_files_match( src, tgt, syncopts )
            self._assert_files_equal( tgt, tmp )
            # check tmp has the same FID
            self.assertEqual( old_fid, tmp.fid() )


    def test_syncfile_23( self ):
        """
        Testing owner comparison
        tmp NO
        tgt DATA OK -- MISMATCH owner
        Only metadata has changed, so sync should be fast and FIDs remain the same
        """
        syncopts = self.syncopts_defaults.copy()
        for d in self._iter_valid_files():
            src = fsitem.FSItem( d[ 'srcpath' ] )
            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
            syncopts.update( keeptmp=False, tmpbase=d[ 'tmpbase' ] )
            # initial sync to create tgt
            pylut.syncfile( src, tgt, **syncopts )
            # change owner
            os.chown( str( tgt ), 27929, -1 )
            # double check changes
            tgt.update()
            self.assertNotEqual( tgt.uid, src.uid )
            self.assertEqual( tgt.gid, src.gid )
            # save tgt FID
            old_fid = tgt.fid()
            # sync again, should be very fast because only have to update metadata
            syncopts.update( keeptmp=True )
            starttime = time.time()
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            endtime = time.time()
            elapsedtime = endtime - starttime
            self.assertLess( elapsedtime, 1 )
            # usual checks
            self._assert_files_match( src, tgt, syncopts )
            self._assert_files_equal( tgt, tmp )
            # check tgt has the same FID
            self.assertEqual( old_fid, tgt.fid() )


    def test_syncfile_24( self ):
        """
        Testing owner comparison
        tmp DATA OK -- MISMATCH owner
        tgt NO
        Only metadata has changed, so sync should be fast and FIDs remain the same
        """
        syncopts = self.syncopts_defaults.copy()
        for d in self._iter_valid_files():
            src = fsitem.FSItem( d[ 'srcpath' ] )
            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
            syncopts.update( keeptmp=True, tmpbase=d[ 'tmpbase' ] )
            # initial sync to create tmp
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            # change owner
            os.chown( str( tmp ), 27929, -1 )
            # double check changes
            tmp.update()
            self.assertNotEqual( tmp.uid, src.uid )
            self.assertEqual( tmp.gid, src.gid )
            # save tmp FID
            old_fid = tmp.fid()
            # delete tgt
            os.unlink( str( tgt ) )
            tgt.update()
            # sync again, should be very fast because only have to update metadata
            starttime = time.time()
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            endtime = time.time()
            elapsedtime = endtime - starttime
            self.assertLess( elapsedtime, 1 )
            # usual checks
            self._assert_files_match( src, tgt, syncopts )
            self._assert_files_equal( tgt, tmp )
            # check tmp has the same FID
            self.assertEqual( old_fid, tmp.fid() )


    def test_syncfile_25( self ):
        """
        Testing group comparison
        tmp NO
        tgt DATA OK -- MISMATCH group
        Only metadata has changed, so sync should be fast and FIDs remain the same
        """
        syncopts = self.syncopts_defaults.copy()
        for d in self._iter_valid_files():
            src = fsitem.FSItem( d[ 'srcpath' ] )
            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
            syncopts.update( keeptmp=False, tmpbase=d[ 'tmpbase' ] )
            # initial sync to create tgt
            pylut.syncfile( src, tgt, **syncopts )
            # change group
            os.chown( str( tgt ), -1, 14802 )
            # double check changes
            tgt.update()
            self.assertEqual( tgt.uid, src.uid )
            self.assertNotEqual( tgt.gid, src.gid )
            # save tgt FID
            old_fid = tgt.fid()
            # sync again, should be very fast because only have to update metadata
            syncopts.update( keeptmp=True )
            starttime = time.time()
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            endtime = time.time()
            elapsedtime = endtime - starttime
            self.assertLess( elapsedtime, 1 )
            # usual checks
            self._assert_files_match( src, tgt, syncopts )
            self._assert_files_equal( tgt, tmp )
            # check tgt has the same FID
            self.assertEqual( old_fid, tgt.fid() )


    def test_syncfile_26( self ):
        """
        Testing group comparison
        tmp DATA OK -- MISMATCH group
        tgt NO
        Only metadata has changed, so sync should be fast and FIDs remain the same
        """
        syncopts = self.syncopts_defaults.copy()
        for d in self._iter_valid_files():
            src = fsitem.FSItem( d[ 'srcpath' ] )
            tgt = fsitem.FSItem( d[ 'tgtpath' ] )
            syncopts.update( keeptmp=True, tmpbase=d[ 'tmpbase' ] )
            # initial sync to create tmp
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            # change group
            os.chown( str( tmp ), -1, 14802 )
            # double check changes
            tmp.update()
            self.assertEqual( tmp.uid, src.uid )
            self.assertNotEqual( tmp.gid, src.gid )
            # save tmp FID
            old_fid = tmp.fid()
            # delete tgt
            os.unlink( str( tgt ) )
            tgt.update()
            # sync again, should be very fast because only have to update metadata
            starttime = time.time()
            tmp, action, attrs = pylut.syncfile( src, tgt, **syncopts )
            endtime = time.time()
            elapsedtime = endtime - starttime
            self.assertLess( elapsedtime, 1 )
            # usual checks
            self._assert_files_match( src, tgt, syncopts )
            self._assert_files_equal( tgt, tmp )
            # check tmp has the same FID
            self.assertEqual( old_fid, tmp.fid() )


    def _assert_files_match( self, f1, f2, incoming_syncopts ):
        """
        Compare two FSItem's size, mtime, mode, uid, gid, stripecount, checksum
        f1 = src, f2 = tgt or tmp
        """
        syncopts = self.pylut_syncopts_defaults.copy()
        syncopts.update( incoming_syncopts )
        f1.update()
        f2.update()
        failmsg = 'f1: {0} f2: {1} {{0}}'.format( f1, f2 )
        # check for matching perms, uid, gid, size, times
        self.assertEqual( f1.size, f2.size, msg=failmsg.format( 
            'sizes dont match {0} {1}'.format( 
                f1.size, f2.size ) ) )
        if syncopts[ 'synctimes' ]:
            self.assertEqual( f1.mtime, f2.mtime, 
                msg=failmsg.format( 'mtimes not equal {0} {1}'.format( 
                    f1.mtime, f2.mtime ) ) )
        else:
            self.assertLessEqual( f1.mtime, f2.mtime, 
                msg=failmsg.format( 'mtimes not lessOrEqual {0} {1}'.format( 
                    f1.mtime, f2.mtime ) ) )
        if syncopts[ 'syncperms' ]:
            self.assertEqual( f1.mode, f2.mode, msg=failmsg.format( 
                'perms dont match {0} {1}'.format( 
                    f1.mode, f2.mode ) ) )
        if syncopts[ 'syncowner' ]:
            self.assertEqual( f1.uid, f2.uid, msg=failmsg.format( 
                'owners dont match {0} {1}'.format( 
                    f1.uid, f2.uid ) ) )
        if syncopts[ 'syncgroup' ]:
            self.assertEqual( f1.gid, f2.gid, msg=failmsg.format( 
                'groups dont match {0} {1}'.format( 
                    f1.gid, f2.gid ) ) )
        # check for matching stripe info
        self.assertEqual( f1.stripeinfo().count, f2.stripeinfo().count, 
            msg=failmsg.format( 'stripecount' ) )
        self.assertEqual( f1.stripeinfo().size, f2.stripeinfo().size, 
            msg=failmsg.format( 'stripesize' ) )
        # verify matching checksums
        if syncopts[ 'post_checksums' ]:
            self.assertEqual( f1.checksum(), f2.checksum(),
                msg=failmsg.format( 'checksums dont match {0} {1}'.format( 
                    f1.checksum(), f2.checksum() ) ) )


    def _assert_files_equal( self, f1, f2 ):
        """
        Assert that both FSItem's share the same inode
        """
        f1.update()
        f2.update()
        failmsg = 'f1: {0} f2: {1}'.format( f1, f2 )
        self.assertEqual( f1.fid(), f2.fid(), msg=failmsg )


    def test_showvars( self ):
        logging.debug( pprint.pformat( [ 'valid_dirpaths', self.valid_dirpaths ] ) )
        logging.debug( pprint.pformat( [ 'valid_filepaths', self.valid_filepaths ] ) )
        logging.debug( pprint.pformat( [ 'hardlinks', self.hardlinks ] ) )
        logging.debug( pprint.pformat( [ 'striped_dirs', self.striped_dirs ] ) )
        logging.debug( pprint.pformat( [ 'striped_files', self.striped_files ] ) )


if __name__ == "__main__":
    loglvl = logging.DEBUG
    loglvl = logging.INFO
    logging.basicConfig( 
        level=loglvl,
        format="%(levelname)s-%(filename)s[%(lineno)d]-%(funcName)s - %(message)s"
        )

    # Some tests sometimes fail due to timing taking too long
    # (think this is due to HSN quiesces during testing, though not confirmed)
    # test_syncfile_12
    # test_syncfile_22
    # test_syncfile_25
    #
    # Some tests fail sometimes due to checksum mismatch
    # (think this is due to HSN quiesces during testing, though not confirmed)
    # test_syncfile_07

    test_list = [
        'test_syncfile_22',
        ]
    suite = unittest.TestSuite( map( Test_Pylut, test_list ) )

    suite = unittest.TestLoader().loadTestsFromTestCase( Test_Pylut )

    unittest.TextTestRunner( verbosity=2 ).run( suite )
