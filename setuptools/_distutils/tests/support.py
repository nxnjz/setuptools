"""Support code for distutils test cases."""
import os
import sys
import shutil
import tempfile
import unittest
import sysconfig
import itertools

import pytest

from distutils.log import DEBUG, INFO, WARN, ERROR, FATAL
from distutils.core import Distribution


@pytest.mark.usefixtures('distutils_logging_silencer')
class LoggingSilencer:
    def _log(self, level, msg, args):
        if level not in (DEBUG, INFO, WARN, ERROR, FATAL):
            raise ValueError('%s wrong log level' % str(level))
        if not isinstance(msg, str):
            raise TypeError("msg should be str, not '%.200s'" % (type(msg).__name__))
        self.logs.append((level, msg, args))

    def get_logs(self, *levels):
        return [msg % args for level, msg, args in self.logs if level in levels]

    def clear_logs(self):
        self.logs = []


@pytest.mark.usefixtures('distutils_managed_tempdir')
class TempdirManager:
    """Mix-in class that handles temporary directories for test cases.

    This is intended to be used with unittest.TestCase.
    """

    def mkdtemp(self):
        """Create a temporary directory that will be cleaned up.

        Returns the path of the directory.
        """
        d = tempfile.mkdtemp()
        self.tempdirs.append(d)
        return d

    def write_file(self, path, content='xxx'):
        """Writes a file in the given path.


        path can be a string or a sequence.
        """
        if isinstance(path, (list, tuple)):
            path = os.path.join(*path)
        f = open(path, 'w')
        try:
            f.write(content)
        finally:
            f.close()

    def create_dist(self, pkg_name='foo', **kw):
        """Will generate a test environment.

        This function creates:
         - a Distribution instance using keywords
         - a temporary directory with a package structure

        It returns the package directory and the distribution
        instance.
        """
        tmp_dir = self.mkdtemp()
        pkg_dir = os.path.join(tmp_dir, pkg_name)
        os.mkdir(pkg_dir)
        dist = Distribution(attrs=kw)

        return pkg_dir, dist


class DummyCommand:
    """Class to store options for retrieval via set_undefined_options()."""

    def __init__(self, **kwargs):
        vars(self).update(kwargs)

    def ensure_finalized(self):
        pass


def copy_xxmodule_c(directory):
    """Helper for tests that need the xxmodule.c source file.

    Example use:

        def test_compile(self):
            copy_xxmodule_c(self.tmpdir)
            self.assertIn('xxmodule.c', os.listdir(self.tmpdir))

    If the source file can be found, it will be copied to *directory*.  If not,
    the test will be skipped.  Errors during copy are not caught.
    """
    filename = _get_xxmodule_path()
    if filename is None:
        raise unittest.SkipTest(
            'cannot find xxmodule.c (test must run in ' 'the python build dir)'
        )
    shutil.copy(filename, directory)


def _get_xxmodule_path():
    srcdir = sysconfig.get_config_var('srcdir')
    candidates = [
        # use installed copy if available
        os.path.join(os.path.dirname(__file__), 'xxmodule.c'),
        # otherwise try using copy from build directory
        os.path.join(srcdir, 'Modules', 'xxmodule.c'),
        # srcdir mysteriously can be $srcdir/Lib/distutils/tests when
        # this file is run from its parent directory, so walk up the
        # tree to find the real srcdir
        os.path.join(srcdir, '..', '..', '..', 'Modules', 'xxmodule.c'),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path


def fixup_build_ext(cmd):
    """Function needed to make build_ext tests pass.

    When Python was built with --enable-shared on Unix, -L. is not enough to
    find libpython<blah>.so, because regrtest runs in a tempdir, not in the
    source directory where the .so lives.

    When Python was built with in debug mode on Windows, build_ext commands
    need their debug attribute set, and it is not done automatically for
    some reason.

    This function handles both of these things.  Example use:

        cmd = build_ext(dist)
        support.fixup_build_ext(cmd)
        cmd.ensure_finalized()

    Unlike most other Unix platforms, Mac OS X embeds absolute paths
    to shared libraries into executables, so the fixup is not needed there.
    """
    if os.name == 'nt':
        cmd.debug = sys.executable.endswith('_d.exe')
    elif sysconfig.get_config_var('Py_ENABLE_SHARED'):
        # To further add to the shared builds fun on Unix, we can't just add
        # library_dirs to the Extension() instance because that doesn't get
        # plumbed through to the final compiler command.
        runshared = sysconfig.get_config_var('RUNSHARED')
        if runshared is None:
            cmd.library_dirs = ['.']
        else:
            if sys.platform == 'darwin':
                cmd.library_dirs = []
            else:
                name, equals, value = runshared.partition('=')
                cmd.library_dirs = [d for d in value.split(os.pathsep) if d]


def combine_markers(cls):
    """
    pytest will honor markers as found on the class, but when
    markers are on multiple subclasses, only one appears. Use
    this decorator to combine those markers.
    """
    cls.pytestmark = [
        mark
        for base in itertools.chain([cls], cls.__bases__)
        for mark in getattr(base, 'pytestmark', [])
    ]
    return cls
