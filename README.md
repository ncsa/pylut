# pylut - Python Lustre Tools

A collection of functions to simplify interaction with the
Lustre filesystem from Python.

## NOTES
+ The following environment variables are expected to be set:
  - PYLUTRSYNCPATH    ( path to rsync )
  - PYLUTLFSPATH      ( path to lfs )
  - PYLUTMAXRSYNCSIZE ( max filesize in bytes to transfer with rsync       )
                      ( files larger than PYLUTMAXRSYNCSIZE will be copied )
                      ( instead with dd before rsync is invoked            )

## Running tests
To run the Python tests:
+ cd /path/to/pylut
+ vi test/runtest (set environment variables, per above, as needed)
+ test/runtest
