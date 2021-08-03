##
# The MIT License (MIT)
#
# Copyright (c) 2016 Stefan Wendler
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
##


import os
import posixpath  # force posix-style slashes
import re
import sre_constants
import binascii
import getpass
import logging
import subprocess
import ast
import sys
from pathlib import Path

from pyboard import Pyboard
from pyboard import PyboardError
from conserial import ConSerial
from contelnet import ConTelnet
from conwebsock import ConWebsock
from conbase import ConError
from retry import retry
from utility.file_util import MD5Varifier


def _was_file_not_existing(exception):
    """
    Helper function used to check for ENOENT (file doesn't exist),
    ENODEV (device doesn't exist, but handled in the same way) or
    EINVAL errors in an exception. Treat them all the same for the
    time being. TODO: improve and nuance.

    :param  exception:      exception to examine
    :return:                True if non-existing
    """

    stre = str(exception)
    return any(err in stre for err in ('ENOENT', 'ENODEV', 'EINVAL', 'OSError:'))


class RemoteIOError(IOError):
    pass


class MpFileExplorer(Pyboard):

    BIN_CHUNK_SIZE = 16 * 100
    MAX_TRIES = 3

    def __init__(self, constr, reset=False, os_lib='os'):
        """
        Supports the following connection strings.

            ser:/dev/ttyUSB1,<baudrate>
            tn:192.168.1.101,<login>,<passwd>
            ws:192.168.1.102,<passwd>

        :param constr:      Connection string as defined above.
        """

        logging.info('Init MpFileExplorer')
        self.reset = reset
        self.md5_varifier = MD5Varifier()
        self._os_lib = os_lib

        try:
            Pyboard.__init__(self, self.__con_from_str(constr))
        except Exception as e:
            raise ConError(e)

        self.dir = None
        self.sysname = None
        self.setup()
        self._init_md5_varify()

    def __del__(self):

        try:
            self.exit_raw_repl()
        except:
            pass

        try:
            self.close()
        except:
            pass

    def __con_from_str(self, constr):
        logging.info(f'Build serial connection from {constr}')

        con = None

        proto, target = constr.split(":")
        params = target.split(",")

        if proto.strip(" ") == "ser":
            port = params[0].strip(" ")

            if len(params) > 1:
                baudrate = int(params[1].strip(" "))
            else:
                baudrate = 115200

            con = ConSerial(port=port, baudrate=baudrate, reset=self.reset)

        elif proto.strip(" ") == "tn":

            host = params[0].strip(" ")

            if len(params) > 1:
                login = params[1].strip(" ")
            else:
                print("")
                login = input("telnet login : ")

            if len(params) > 2:
                passwd = params[2].strip(" ")
            else:
                passwd = getpass.getpass("telnet passwd: ")

            # print("telnet connection to: %s, %s, %s" % (host, login, passwd))
            con = ConTelnet(ip=host, user=login, password=passwd)

        elif proto.strip(" ") == "ws":

            host = params[0].strip(" ")

            if len(params) > 1:
                passwd = params[1].strip(" ")
            else:
                passwd = getpass.getpass("webrepl passwd: ")

            con = ConWebsock(host, passwd)

        return con

    def _fqn(self, name):
        # print(name, posixpath.join(self.dir, name).replace("\\","/"))
        return posixpath.join(self.dir, name).replace("\\","/")

    def __set_sysname(self):
        self.sysname = sys.platform
        logging.info(f'Set sysname is {self.sysname}')
        # self.sysname = self.eval("os.uname()[0]").decode('utf-8')

    def close(self):
        logging.info('Close the connection')

        Pyboard.close(self)
        self.dir = None

    def teardown(self):
        logging.info('Teardown')

        self.exit_raw_repl()
        self.sysname = None

    def setup(self):
        logging.info('Set up')

        board_model = self.get_board_info()
        logging.info(f'Get board model is {board_model}')
        self.exit_raw_repl()
        if board_model == 'stm32l401':
            self._os_lib = 'uos'
            logging.info('Set os lib is uos on board')

        self.enter_raw_repl()
        if self._os_lib == 'uos':
            self.exec_("import sys, ubinascii, uos")
            self.dir = posixpath.join("/", self.eval("uos.system('pwd')").decode('utf8'))
        else:
            self.exec_("import os, sys, ubinascii")
            # New version mounts files on /flash so lets set dir based on where we are in
            # filesystem.
            # Using the "path.join" to make sure we get "/" if "os.getcwd" returns "".
            self.dir = posixpath.join("/", self.eval("os.getcwd()").decode('utf8'))
        logging.info(f'Set work dir is {self.dir}')

        self.__set_sysname()

    def _init_md5_varify(self):
        logging.info('Init md5 varify cache')
        remote_sign = self.md5_varifier.cache_file
        cache_data = self._do_read_remote(remote_sign)  # 读取出来的data
        self.md5_varifier.init_cache(cache_data)

    def __list_dir(self, path_):
        logging.info(f'get listdir of {path_}')
        res = None
        try:
            if self._os_lib == 'os':
                res = self.eval("os.listdir('%s')" % path_)
            elif self._os_lib == 'uos':
                res = self.eval(f"[i[0] for i in uos.ilistdir('{path_}')]")
            return res
        except PyboardError as e:
            logging.error(e)
            raise e

    @retry(PyboardError, tries=MAX_TRIES, delay=1, backoff=2, logger=logging.root)
    def ls(self, add_files=True, add_dirs=True, add_details=False):
        logging.info(f'ls {self.dir}')

        files = []

        try:

            res = self.__list_dir(self.dir)
            if res is None:
                return files
            tmp = ast.literal_eval(res.decode('utf-8'))
            if not add_details and add_dirs:
                return tmp
            if add_dirs:
                for f in tmp:
                    try:

                        # if it is a dir, it could be listed with "os.listdir"
                        ret_inner_tmp = self.__list_dir(os.path.join(f))
                        if ret_inner_tmp is None:
                            files.append((f, 'F'))
                        else:
                            ret_inner = ast.literal_eval(ret_inner_tmp.decode('utf-8'))
                            if len(ret_inner) > 0:
                                files.append((f, 'D'))
                            else:
                                files.append((f, 'F'))

                    except PyboardError as e:

                        if _was_file_not_existing(e):
                            # this was not a dir
                            if self.sysname == "WiPy" and self.dir == "/":
                                # for the WiPy, assume that all entries in the root of th FS
                                # are mount-points, and thus treat them as directories
                                if add_details:
                                    files.append((f, 'D'))
                                else:
                                    files.append(f)
                        else:
                            raise e

            if add_files and not (self.sysname == "WiPy" and self.dir == "/"):
                for f in tmp:
                    try:

                        # if it is a file, "os.listdir" must fail
                        if self._os_lib == 'os':
                            self.eval("os.listdir('%s/%s')" % (self.dir.rstrip('/'), f))

                    except PyboardError as e:

                        if _was_file_not_existing(e):
                            if add_details:
                                files.append((f, 'F'))
                            else:
                                files.append(f)
                        else:
                            raise e

        except Exception  as e:
            if _was_file_not_existing(e):
                raise RemoteIOError("No such directory: %s" % self.dir)
            else:
                raise PyboardError(e)

        return files

    @retry(PyboardError, tries=MAX_TRIES, delay=1, backoff=2, logger=logging.root)
    def rm(self, target):
        logging.info(f'rm {target}')

        if self._os_lib == 'uos':
            try:
                self.eval(f"uos.remove('{self._fqn(target)}')")
            except PyboardError as e:
                raise e
            else:
                sign_value = self.md5_varifier.rm_sign(self._fqn(target))
                self._do_write_remote(self.md5_varifier.cache_file, sign_value)
            finally:
                return

        try:
            # 1st try to delete it as a file
            self.eval("os.remove('%s')" % (self._fqn(target)))
        except PyboardError as e:
            try:
                # 2nd see if it is empty dir
                self.eval("os.rmdir('%s')" % (self._fqn(target)))
            except PyboardError as e:
                # 3rd report error if nor successful
                if _was_file_not_existing(e):
                    if self.sysname == "WiPy":
                        raise RemoteIOError("No such file or directory or directory not empty: %s" % target)
                    else:
                        raise RemoteIOError("No such file or directory: %s" % target)
                elif "EACCES" in str(e):
                    raise RemoteIOError("Directory not empty: %s" % target)
                else:
                    raise e
        finally:
            sign_value = self.md5_varifier.rm_sign(self._fqn(target))
            self._do_write_remote(self.md5_varifier.cache_file, sign_value)

    def mrm(self, pat, verbose=False):
        logging.info(f'mrm {pat}')

        files = self.ls(add_dirs=False)
        find = re.compile(pat)

        for f in files:
            if find.match(f):
                if verbose:
                    print(" * rm %s" % f)

                self.rm(f)

    def _do_write_remote(self, dst: str, data: bytes) -> None:
        """
        write operation on remote file
        Args:
            dst: remote file path
            data: fp.read()

        Returns:
            None

        """
        logging.info(f"write data to {dst}")
        try:

            self.exec_("f = open('%s', 'wb')" % self._fqn(dst))

            file_size = len(data)
            while True:
                c = binascii.hexlify(data[:self.BIN_CHUNK_SIZE])
                if not len(c):
                    break

                self.exec_("f.write(ubinascii.unhexlify('%s'))" % c.decode('utf-8'))
                data = data[self.BIN_CHUNK_SIZE:]

                print("\ttransfer %d of %d" % (file_size - len(data), file_size))
            self.exec_("f.close()")

        except PyboardError as e:
            if _was_file_not_existing(e):
                raise RemoteIOError("Failed to create file: %s" % dst)
            elif "EACCES" in str(e):
                raise RemoteIOError("Existing directory: %s" % dst)
            else:
                raise e

    @retry(PyboardError, tries=MAX_TRIES, delay=1, backoff=2, logger=logging.root)
    def put(self, src, dst=None):
        logging.info(f'put {src} to remote {dst}')

        cache_value = self.md5_varifier.varify_sign(src, dst)
        if cache_value:
            self._do_write_remote(self.md5_varifier.cache_file, cache_value)
            f = open(src, "rb")
            data = f.read()
            f.close()

            if dst is None:
                dst = src

            self._do_write_remote(dst, data)

    def mput(self, src_dir, pat, verbose=False):
        logging.info(f'mput {src_dir} {pat}')

        try:

            find = re.compile(pat)
            files = os.listdir(src_dir)

            for f in files:
                if posixpath.isfile(f) and find.match(f):
                    if verbose:
                        print(" * put %s" % f)

                    self.put(posixpath.join(src_dir, f), f)

        except sre_constants.error as e:
            raise RemoteIOError("Error in regular expression: %s" % e)

    def _do_read_remote(self, dst: str) -> bytes:
        """
        read operation on remote file
        Args:
            dst: remote file path

        Returns:
            bytes

        """
        logging.info(f'read remote file {dst}')
        try:

            self.exec_("f = open('%s', 'a')" % self._fqn(dst))
            self.exec_("f.close()")
            self.exec_("f = open('%s', 'rb')" % self._fqn(dst))
            ret = self.exec_(
                "while True:\r\n"
                "  c = ubinascii.hexlify(f.read(%s))\r\n"
                "  if not len(c):\r\n"
                "    break\r\n"
                "  sys.stdout.write(c)\r\n" % self.BIN_CHUNK_SIZE
            )
            self.exec_("f.close()")

        except PyboardError as e:
            if _was_file_not_existing(e):
                raise RemoteIOError("Failed to read file: %s" % dst)
            else:
                raise e
        return ret

    @retry(PyboardError, tries=MAX_TRIES, delay=1, backoff=2, logger=logging.root)
    def get(self, src, dst=None, varify=True):
        logging.info(f'get remote file {src} to local {dst}')

        if varify and src not in self.ls():
            raise RemoteIOError("No such file or directory: '%s'" % self._fqn(src))

        if dst is None:
            dst = src

        ret = self._do_read_remote(src)
        with open(dst, 'wb') as fp:
           fp.write(binascii.unhexlify(ret))

    def mget(self, dst_dir, pat, verbose=False):
        logging.info(f'mget {dst_dir} {pat}')

        try:

            files = self.ls(add_dirs=False)
            find = re.compile(pat)

            for f in files:
                if find.match(f):
                    if verbose:
                        print(" * get %s" % f)

                    self.get(f, dst=posixpath.join(dst_dir, f), varify=False)

        except sre_constants.error as e:
            raise RemoteIOError("Error in regular expression: %s" % e)

    @retry(PyboardError, tries=MAX_TRIES, delay=1, backoff=2, logger=logging.root)
    def gets(self, src):

        try:

            self.exec_("f = open('%s', 'rb')" % self._fqn(src))
            ret = self.exec_(
                "while True:\r\n"
                "  c = ubinascii.hexlify(f.read(%s))\r\n"
                "  if not len(c):\r\n"
                "    break\r\n"
                "  sys.stdout.write(c)\r\n" % self.BIN_CHUNK_SIZE
            )

        except PyboardError as e:
            if _was_file_not_existing(e):
                raise RemoteIOError("Failed to read file: %s" % src)
            else:
                raise e

        try:

            return binascii.unhexlify(ret).decode("utf-8")

        except UnicodeDecodeError:

            s = ret.decode("utf-8")
            fs = "\nBinary file:\n\n"

            while len(s):
                fs += s[:64] + "\n"
                s = s[64:]

            return fs

    @retry(PyboardError, tries=MAX_TRIES, delay=1, backoff=2, logger=logging.root)
    def cd(self, target):
        logging.info(f'cd {target}')

        if target.startswith("/"):
            tmp_dir = target
        elif target == "..":
            tmp_dir, _ = posixpath.split(self.dir)
        else:
            tmp_dir = self._fqn(target)

        # see if the new dir exists
        try:
            self.__list_dir(tmp_dir)
            self.dir = tmp_dir

        except PyboardError as e:
            if _was_file_not_existing(e):
                raise RemoteIOError("No such directory: %s" % target)
            else:
                raise e

    def pwd(self):
        logging.info(f'pwd is {self.dir}')
        return self.dir

    @retry(PyboardError, tries=MAX_TRIES, delay=1, backoff=2, logger=logging.root)
    def md(self, target):
        logging.info(f'mkdir {target}')

        try:

            if self._os_lib == 'uos':
                self.eval("uos.mkdir('%s')" % self._fqn(target))
            else:
                self.eval("os.mkdir('%s')" % self._fqn(target))

        except PyboardError as e:
            if _was_file_not_existing(e):
                raise RemoteIOError("Invalid directory name: %s" % target)
            elif "EEXIST" in str(e):
                raise RemoteIOError("File or directory exists: %s" % target)
            else:
                raise e

    def mpy_cross(self, src, dst=None):
        logging.info('do mpy cross')

        if dst is None:
            return_code = subprocess.call("mpy-cross %s" % (src), shell=True)
        else:
            return_code = subprocess.call("mpy-cross -o %s %s" % (src, dst), shell=True)

        if return_code != 0:
            raise IOError("Filed to compile: %s" % src)


class MpFileExplorerCaching(MpFileExplorer):

    def __init__(self, constr, reset=False):
        MpFileExplorer.__init__(self, constr, reset)

        self.cache = {}

    def __cache(self, path, data):

        logging.debug("caching '%s': %s" % (path, data))
        self.cache[path] = data

    def __cache_hit(self, path):

        return self.cache.get(path)

    def ls(self, add_files=True, add_dirs=True, add_details=False):

        hit = self.__cache_hit(self.dir)

        if hit is not None:

            files = []

            if add_dirs:
                for f in hit:
                    if f[1] == 'D':
                        if add_details:
                            files.append(f)
                        else:
                            files.append(f[0])

            if add_files:
                for f in hit:
                    if f[1] == 'F':
                        if add_details:
                            files.append(f)
                        else:
                            files.append(f[0])

            return files

        files = MpFileExplorer.ls(self, add_files, add_dirs, add_details)

        if add_files and add_dirs and add_details:
            self.__cache(self.dir, files)

        return files

    def put(self, src, dst=None):

        tmp_dirs = Path(src).parts  # 仅使用与windows环境
        if len(tmp_dirs) > 1:  # 绝对路径，需要检查开发板上是否有对应的文件夹
            dirs = tmp_dirs[1:]
            dir_index = 0
            ori_dir = ''
            while dir_index < len(dirs) - 1:
                cur_dir = str(Path(ori_dir, dirs[dir_index]))
                try:
                    self.md(cur_dir)
                except Exception as e:
                    pass
                dir_index += 1
                ori_dir = cur_dir
            dst = str(Path(cur_dir, dirs[-1]))
        MpFileExplorer.put(self, src, dst)

        if dst is None:
            dst = src

        path = posixpath.split(self._fqn(dst))
        newitm = path[-1]
        parent = path[:-1][0]

        hit = self.__cache_hit(parent)

        if hit is not None:
            if not (dst, 'F') in hit:
                self.__cache(parent, hit + [(newitm, 'F')])

    def md(self, dir):

        MpFileExplorer.md(self, dir)

        path = posixpath.split(self._fqn(dir))
        newitm = path[-1]
        parent = path[:-1][0]

        hit = self.__cache_hit(parent)

        if hit is not None:
            if not (dir, 'D') in hit:
                self.__cache(parent, hit + [(newitm, 'D')])

    def rm(self, target):

        MpFileExplorer.rm(self, target)

        path = posixpath.split(self._fqn(target))
        rmitm = path[-1]
        parent = path[:-1][0]

        hit = self.__cache_hit(parent)

        if hit is not None:
            files = []

            for f in hit:
                if f[0] != rmitm:
                    files.append(f)

            self.__cache(parent, files)
