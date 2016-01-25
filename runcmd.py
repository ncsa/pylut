#!/bin/env python

import subprocess
import logging

log = logging.getLogger( __name__ )


class Run_Cmd_Error( Exception ):
    def __init__( self, code, reason, cmd, *a, **k ):
        super( Run_Cmd_Error, self ).__init__( *a, **k )
        self.code = code
        self.reason = reason
        self.cmd = cmd

    def __repr__( self ):
        return "<{0} (code={1} msg={2} cmd={3})>".format(
            self.__class__.__name__, self.code, self.reason, self.cmd )

    __str__ = __repr__


def runcmd( cmdlist, opts=None, args=None ):
    """ Run a command on the linux command line.
        INPUTS:
          cmdlist   = list - command to run
                             (if the command requires one or more
                             subcommands, they go here)
          opts      = dict - converted to key=value args
          args      = list - converted to cmdline args
        OUTPUTS:
          tuple = ( stdout, stderr )
        NOTES:
          opts and args are used as-is, if elements are expected to be
          prefixed with a dash or multiple dashes, you must add them
          yourself.
    """
    if opts is not None:
        cmdlist.extend( [ "{0}={1}".format( k, v ) for k, v in opts.items() ] )
    if args is not None:
        cmdlist.extend( map( str, args ) )
    log.debug( "cmdlist: {0}".format( cmdlist ) )
    subp = subprocess.Popen( cmdlist, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE )
    log.debug( "about to call subp.communicate..." )
    ( output, errput ) = subp.communicate()
    log.debug( "finished" )
    rc = subp.returncode
    log.debug( "got returncode '{0}'".format( rc ) )
    if rc != 0:
        raise( Run_Cmd_Error( code=rc, reason=errput, cmd=' '.join( cmdlist ) ) )
    return ( output, errput )
