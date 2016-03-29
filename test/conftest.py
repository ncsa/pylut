import pytest
import pstestdir

@pytest.fixture( scope="module" )
def testdir():
    pstestdir.reset()
    return pstestdir
