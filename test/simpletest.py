import pylut
import fsitem

src_path=fsitem.FSItem( '/u/staff/aloftus/lustre_version.pbs' )
tgt_path=fsitem.FSItem( '/projects/test/psynctest/lustre_version.pbs' )

pylut.syncfile( src_path, tgt_path )
