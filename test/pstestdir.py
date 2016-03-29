# Code to create a randomized directory structure for testing psync
# Intent is to use this in a pytest fixture

from __future__ import print_function
from runcmd import runcmd

import psconfig
import random
import string
import sys
import os
import socket
import shutil
import stat
import pwd
import grp
import logging
import pprint
#import posix1e

objects = {}
files = []
directories = []
source = psconfig.SOURCE_DIR
target = psconfig.DEST_DIR
tmpdir = psconfig.TMP_DIR
uids = [pwd.getpwnam(user).pw_uid for user in psconfig.PERMS_USERS]
gids = [grp.getgrnam(group).gr_gid for group in psconfig.PERMS_GROUPS]

class FileObject( object ):
    def __init__( self, path, typ, tgt ):
        self.path = path
        self.typ  = typ
        self.tgt  = tgt
        self.stat = os.lstat( path )
        self.stripecount = None
        self.stripesize = None

    def set_stripe_info( self, count, size=None ):
       self.stripecount = count
       self.stripesize = size

    def __str__( self ):
        c = 0
        if self.stripecount:
            c = self.stripecount
        s = 0
        if self.stripesize:
            s = self.stripesize
        g = ''
        if self.tgt:
            a = ' => '
            if self.typ == 'l':
                a = ' -> '
            g = '{0}{1}'.format( a, self.tgt )
        return '{t}\t{m} {c} {s:7} {p}{g}'.format( t=self.typ,
                                            m=self.mode(),
                                            c=c,
                                            s=s,
                                            p=self.path,
                                            g=g )
    __repr__ = __str__

    def mode( self ):
        return oct( stat.S_IMODE( self.stat.st_mode ) )

    def inode( self ):
        return self.stat.st_ino


def weighted_picks(sequence, relative_odds):
    table = [ z for x, y in zip(sequence, relative_odds) for z in [x]*y ]
    while True:
        yield random.choice(table)


def rand_newfilepath():
    chars = string.ascii_lowercase + string.ascii_uppercase + string.digits
    dir = random.choice( directories ).path
    filepath = os.path.join(dir, ''.join(random.sample(chars, random.randint(1,10))))

    return filepath if not os.path.exists(filepath) \
                else rand_newfilepath()


def rand_path():
    inode = random.choice( objects.keys() )
    path = random.choice( objects[ inode ] ).path
    return path


def set_rand_stripeinfo( path ):
    cnt = random.choice( psconfig.FILE_STRIPE_COUNTS )
    sz = random.choice( psconfig.FILE_STRIPE_SIZES )
    cmd = [ 'lfs', 'setstripe' ]
    opts = None
    args = [ '-c', cnt, '-S', sz, path ]
    ( out, err ) = runcmd( cmd, opts, args )
    return ( cnt, sz )


def save_path_info( path, typ, tgt=None ):
    f = FileObject( path, typ, tgt )
    inode = f.inode()
    if inode not in objects:
        objects[ inode ] = []
    objects[ inode ].append( f )
    return f


def create_directory():
    path = rand_newfilepath()
    os.makedirs( path )
    d = save_path_info( path, 'd' )
    directories.append( d )
    ( cnt, sz ) = set_rand_stripeinfo( path )
    d.set_stripe_info( cnt, sz )


def create_file():
    path = rand_newfilepath()
    ( stripe_cnt, stripe_sz ) = set_rand_stripeinfo( path )
    filesize = random.randint(0, psconfig.MAX_FILE_SIZE )
    with open( path, 'wb') as f:
        f.write( os.urandom( filesize ) )
    f = save_path_info( path, 'f' )
    files.append( f )
    f.set_stripe_info( stripe_cnt, stripe_sz )


def create_fifo():
    path = rand_newfilepath()
    os.mkfifo( path )
    f = save_path_info( path, 'p' )
    files.append( f )


def create_socket():
    path = rand_newfilepath()
    sock = socket.socket( socket.AF_UNIX, socket.SOCK_STREAM )
    sock.bind( path )
    f = save_path_info( path, 's' )
    files.append( f )


def create_symlink():
    path = rand_newfilepath()    
    target = rand_path()
    os.symlink( target, path )
    f = save_path_info( path, 'l', tgt=target )
    files.append( f )


def create_hardlink():
    path = rand_newfilepath()    
    target = random.choice( files )
    os.link( target.path, path )
    f = save_path_info( path, target.typ )
    files.append( f )
    f.set_stripe_info( target.stripecount, target.stripesize )


def perms_chmod(path, type):
    if type is 'd':
        mode = random.choice( psconfig.CHMOD_DIR_CHOICES )
    else:
        mode = random.choice( psconfig.CHMOD_CHOICES )
    if type is not 'l':
        os.chmod(path, mode)


def perms_chown(path):
    os.lchown(path, random.choice(uids), random.choice(gids))


def perms_acl(path,type):
    if type is 'd':
        return
    acl_users = random.sample( psconfig.PERMS_ACL_USERS, random.randint(0,len(psconfig.PERMS_ACL_USERS)) )
    acl_groups = random.sample( psconfig.PERMS_ACL_GROUPS, random.randint(0,len(psconfig.PERMS_ACL_GROUPS)) )
    ac_u = []
    ac_g = []
    ac = []
    for user in acl_users:
        if type is 'd' and user == pwd.getpwuid(os.getuid()).pw_name:
            ac_u.append("u:" + user + ":r" + random.choice(['w','-']) + "x")
        else:
            ac_u.append("u:" + user + ":r" + random.choice(['w','-']) + random.choice(['x','-']))
    
    for group in acl_groups:
        ac_g.append("g:" + random.choice(psconfig.PERMS_ACL_GROUPS) + ":" + random.choice(['r','-']) + random.choice(['w','-']) + random.choice(['x','-']))
    if len(ac_u) > 0:
        ac.append(','.join(ac_u))
    if len(ac_g) > 0:
        ac.append(','.join(ac_g))
    if random.random() < 0.5:
        ac_o = "o::" + random.choice(['r','-']) + random.choice(['w','-']) + random.choice(['x','-'])
        ac.append(ac_o)
    text=','.join(ac)
#    acl = posix1e.ACL(text=text)
#    path2 = os.path.join(os.getcwd(), path)
#    acl.applyto(path2)


def initialize():
    global objects, directories
    os.makedirs( psconfig.SOURCE_DIR )
    os.makedirs( psconfig.DEST_DIR )
    directories.append( FileObject( psconfig.SOURCE_DIR, 'd', None ) )
    #force create one file first, otherwise a hardlink or softlink first will fail
    create_file()
    parts, weights = zip( ( create_file,       psconfig.FILE_WEIGHT     ),
                          ( create_directory,  psconfig.DIR_WEIGHT      ),
                          ( create_symlink,    psconfig.SYMLINK_WEIGHT  ),
                          ( create_fifo,       psconfig.FIFO_WEIGHT     ),
                          ( create_socket,     psconfig.SOCKET_WEIGHT   ),
                          ( create_hardlink,   psconfig.HARDLINK_WEIGHT )
                        )
    rand_choice = weighted_picks( parts, weights )
    for i in range( psconfig.NUM_OBJECTS - 1 ):
        create = next( rand_choice )
        create()
    #chmod
    for inode, elems in objects.iteritems():
        f = elems[0]
        #logging.debug( 'Change Perms: {0} {1}'.format( f.typ, f.path ) )
        perms_chmod( f.path, f.typ )
        perms_chown( f.path )
#        perms_acl(path, type)
    return ( objects, files )


def mk_all_tgtdirs():
    global objects, files, directories
    for d in directories:
        try:
            tgtpath = d.path.replace( source, target, 1 )
            logging.debug( "Attempting to mkdir '{0}'".format( tgtpath ) )
            os.makedirs( tgtpath )
        except ( OSError ) as e:
            if e.errno == 17:
                pass
            else:
                raise e


def reset():
    global objects, files, directories
    objects = {}
    files = []
    directories = []
    for d in [ source, target, tmpdir ]:
        try:
            shutil.rmtree( d )
        except ( OSError ) as e:
            if e.errno == 2: # OSError: [Errno 2] No such file or directory:
                pass
            else:
                raise e
    initialize()
    

if __name__ == '__main__':
    logging.basicConfig( level=logging.DEBUG )
#    random.seed( a=psconfig.SEED )
        
    reset()
    for inode,elems in objects.iteritems():
        print( inode, end=' ' )
        print( *elems, sep='\n' + ' '*20 )

#    pprint.pprint( objects )
        
# vim:set softtabstop=4 shiftwidth=4 tabstop=4 expandtab:
