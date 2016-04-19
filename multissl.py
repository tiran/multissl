#./python
"""Run Python tests against multiple installations of OpenSSL and LibreSSL

The script

  (1) downloads OpenSSL tar bundle
  (2) extracts it to ../openssl/src/openssl-VERSION/
  (3) compiles OpenSSL
  (4) installs OpenSSL into ../openssl/VERSION/
  (5) forces a recompilation of Python modules using the
      header and library files from ../openssl/VERSION/
  (6) runs Python's test suite

The script must be run with Python's build directory as current working
directory.

The script uses LD_RUN_PATH, LD_LIBRARY_PATH, CPPFLAGS and LDFLAGS to bend
search paths for header files and shared libraries. It's known to work on
Linux with GCC 4.x.

(c) 2013-2016 Christian Heimes <christian@python.org>
"""
import os
from urllib.request import urlopen
import tarfile
import subprocess
import shutil
import logging

log = logging.getLogger("multissl")

#OPENSSL_VERSIONS = ["0.9.7e", "0.9.7m", "0.9.8i", "0.9.8l", "0.9.8k", "0.9.8m", "0.9.8y", "1.0.0k", "1.0.1e", "1.0.2", "1.0.1l"]
OPENSSL_VERSIONS = ["0.9.8zh", "1.0.1s", "1.0.2g", "1.1.0-pre5"]
OPENSSL_URL = "http://www.openssl.org/source/openssl-{}.tar.gz"
LIBRESSL_VERSIONS = ["2.3.3"]
LIBRESSL_URL = "http://ftp.openbsd.org/pub/OpenBSD/LibreSSL/libressl-{}.tar.gz"

HERE = os.path.abspath(os.getcwd())
OPENSSL_DEST_DIR = os.path.abspath(os.path.join(HERE, os.pardir, "openssl"))
LIBRESSL_DEST_DIR = os.path.abspath(os.path.join(HERE, os.pardir, "libressl"))


class BuildOpenSSL:
    url_template = OPENSSL_URL
    src_template = "openssl-{}.tar.gz"
    build_template = "openssl-{}"
    default_destdir = OPENSSL_DEST_DIR

    module_files = ["Modules/_ssl.c",
                    "Modules/socketmodule.c",
                    "Modules/_hashopenssl.c"]
    
    def __init__(self, version, openssl_compile_args=(), destdir=None):
        self._check_python_builddir()
        self.version = version
        self.openssl_compile_args = openssl_compile_args
        if destdir is None:
            destdir = self.default_destdir
        # installation directory
        self.install_dir = os.path.join(destdir, version)
        # source file

        self.src_file = os.path.join(destdir, "src", 
            self.src_template.format(version))
        # build directory (removed after install)
        self.build_dir = os.path.join(destdir, "src", 
            self.build_template.format(version))

    @property
    def openssl_cli(self):
        """openssl CLI binary"""
        return os.path.join(self.install_dir, "bin", "openssl")

    @property
    def openssl_version(self):
       """output of 'bin/openssl version'"""
       cmd= [self.openssl_cli, "version"]
       return self._subprocess_output(cmd)

    @property
    def pyssl_version(self):
        """Value of ssl.OPENSSL_VERSION"""
        cmd = ["./python", "-c", "import ssl; print(ssl.OPENSSL_VERSION)"]
        return self._subprocess_output(cmd)

    @property
    def include_dir(self):
        return os.path.join(self.install_dir, "include")

    @property
    def lib_dir(self):
        return os.path.join(self.install_dir, "lib")

    @property
    def has_openssl(self):
        return os.path.isfile(self.openssl_cli)

    @property
    def has_src(self):
        return os.path.isfile(self.src_file)

    def _subprocess_call(self, cmd, stdout=subprocess.DEVNULL, env=None, **kwargs):
        log.debug("Call '{}'".format(" ".join(cmd)))
        #if env is None:
        #    env = os.environ.copy()
        #    env["LD_RUN_PATH"]= self.lib_dir
        #    env["LD_LIBRARY_PATH"]= self.lib_dir
        return subprocess.check_call(cmd, stdout=stdout, env=env, **kwargs)

    def _subprocess_output(self, cmd, env=None, **kwargs):
        log.debug("Call '{}'".format(" ".join(cmd)))
        if env is None:
            env = os.environ.copy()
            env["LD_LIBRARY_PATH"]= self.lib_dir
        out = subprocess.check_output(cmd, env=env)
        return out.strip().decode("utf-8")

    def _check_python_builddir(self):
        if not os.path.isfile("python") or not os.path.isfile("setup.py"):
            raise ValueError("Script must be run in Python build directory")

    def _download_openssl(self):
        """Download OpenSSL source dist"""
        src_dir = os.path.dirname(self.src_file)
        if not os.path.isdir(src_dir):
            os.makedirs(src_dir)
        url = self.url_template.format(self.version)
        log.info("Downloading from {}".format(url))
        req = urlopen(url)
        # KISS, read all, write all
        data = req.read()
        log.info("Storing {}".format(self.src_file))
        with open(self.src_file, "wb") as f:
            f.write(data)

    def _unpack_openssl(self):
        """Unpack tar.gz bundle"""
        # cleanup
        if os.path.isdir(self.build_dir):
            shutil.rmtree(self.build_dir)
        os.makedirs(self.build_dir)

        tf = tarfile.open(self.src_file)
        base = self.build_template.format(self.version) + '/'
        # force extraction into build dir
        members = tf.getmembers()
        for member in members:
            if not member.name.startswith(base):
                raise ValueError(member.name, base)
            member.name = member.name[len(base):].lstrip('/')
        log.info("Unpacking files to {}".format(self.build_dir))
        tf.extractall(self.build_dir, members)

    def _build_openssl(self):
        """Now build openssl"""
        log.info("Running build in {}".format(self.build_dir))
        cwd = self.build_dir
        cmd = ["./config", "shared", "--prefix={}".format(self.install_dir)]
        cmd.extend(self.openssl_compile_args)
        self._subprocess_call(cmd, cwd=cwd)
        self._subprocess_call(["make", "-j1"], cwd=cwd)

    def _install_openssl(self, remove=True):
        self._subprocess_call(["make", "-j1", "install"], cwd=self.build_dir)
        if remove:
            shutil.rmtree(self.build_dir)

    def install(self):
        log.info(self.openssl_cli)
        if not self.has_openssl:
            if not self.has_src:
                self._download_openssl()
            else:
                log.debug("Already has src {}".format(self.src_file))
            self._unpack_openssl()
            self._build_openssl()
            self._install_openssl()
        else:
            log.info("Already has installation {}".format(self.install_dir))
        # validate installation
        version = self.openssl_version
        if self.version not in version:
            raise ValueError(version)

    def recompile_pymods(self):
        log.warn("Using OpenSSL build from {}".format(self.build_dir))
        # force a rebuild of all modules that use OpenSSL APIs
        for fname in self.module_files:
            os.utime(fname)
        
        # overwrite header and library search paths
        env = os.environ.copy()
        env["CPPFLAGS"]= "-I{}".format(self.include_dir)
        env["LDFLAGS"]= "-L{}".format(self.lib_dir)
        # set rpath
        env["LD_RUN_PATH"]= self.lib_dir

        log.info("Rebuilding Python modules")
        cmd = ["./python", "setup.py", "build"]
        self._subprocess_call(cmd, env=env)

    def check_pyssl(self):
        version = self.pyssl_version
        #if self.version not in version:
        #    raise ValueError(version)

    def run_pytests(self, *args):
        cmd = ["./python", "-m", "test"]
        cmd.extend(args)
        self._subprocess_call(cmd, stdout=None)

    def run_python_tests(self, *args):
        self.recompile_pymods()
        self.check_pyssl()
        self.run_pytests(*args)

class BuildLibreSSL(BuildOpenSSL):
    url_template = LIBRESSL_URL
    src_template = "libressl-{}.tar.gz"
    build_template = "libressl-{}"
    default_destdir = LIBRESSL_DEST_DIR


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="*** %(levelname)s %(message)s")

    builds = []

    for version in OPENSSL_VERSIONS:
        if version in {"0.9.8i", "0.9.8l", "0.9.8k"}:
            openssl_compile_args = ("no-asm",)
        else:
            openssl_compile_args = ()
        build = BuildOpenSSL(version, openssl_compile_args)
        build.install()
        builds.append(build)

    for version in LIBRESSL_VERSIONS:
        build = BuildLibreSSL(version)
        build.install()
        builds.append(build)

    for build in builds:
        build.run_python_tests("-unetwork", "-v", "test_ssl", "test_hashlib")

