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


import io
import cmd
import os
import argparse
import glob
import sys
import serial
import logging
import platform
import re
import time
import json
from pathlib import Path

import version
from mpfexp import MpFileExplorer
from mpfexp import MpFileExplorerCaching
from mpfexp import RemoteIOError
from pyboard import PyboardError
from conbase import ConError
from tokenizer import Tokenizer
from utility.file_util import get_file_size, init_log_path
from utility.utils import trim_code_block


class MpFileShell(cmd.Cmd):

    STATE_FILE = 'state_temp.json'

    def __init__(self, color=False, caching=False, reset=False, help=False):
        cmd.Cmd.__init__(self)

        self.color = color
        self.caching = caching
        self.reset = reset
        self.open_args = None
        self.fe = None
        self.repl = None
        self.tokenizer = Tokenizer()
        self.port = None  # 记录端口号

        if platform.system() == 'Windows':
            self.use_rawinput = False

        if platform.system() == 'Darwin':
            self.reset = True

        self.__intro()
        self.__set_prompt_path()

        if help is True:
            self.do_help(None)
            print("can input help ls or other command if you don't know how to use it.")

            plist = self.all_serial()
            if len(plist) <= 0:
                print("serial not found!")
                logging.error("serial not found")
            else:
                for serial in plist:
                    print("serial name :", serial[1], " : ", serial[0].split('/')[-1])
                print("input ' open", plist[len(plist) - 1][0].split('/')[-1], "' and enter connect your board.")
            

    def __del__(self):
        self.__disconnect()

    def __intro(self):

        # self.intro = '\n** Micropython File Shell v%s, sw@kaltpost.de & junhuanchen@qq.com **\n' % version.FULL

        self.intro = '-- Running on Python %d.%d using PySerial %s --\n' \
                      % (sys.version_info[0], sys.version_info[1], serial.VERSION)

    def __set_prompt_path(self):

        if self.fe is not None:
            pwd = self.fe.pwd()
        else:
            pwd = "/"

        self.prompt = "mpfs [" + pwd + "]> "

    def __error(self, msg):

        print('\n' + msg + '\n')

    def __connect(self, port, reconnect=False):

        try:
            self.__disconnect()
            if (port is None):
                port = self.open_args
            # if self.reset:
            #     print("Hard resetting device ...")
            if self.caching:
                self.fe = MpFileExplorerCaching(port, self.reset)
            else:
                self.fe = MpFileExplorer(port, self.reset)
            if not reconnect:
                print("Connected to %s" % self.fe.sysname)
            self.__set_prompt_path()
        except PyboardError as e:
            logging.error(e)
            self.__error(str(e))
        except ConError as e:
            logging.error(e)
            self.__error("Failed to open: %s" % port)
        except AttributeError as e:
            logging.error(e)
            self.__error("Failed to open: %s" % port)
        except Exception as e:
            print(e)

        if reconnect and self.__is_open() == False:
            time.sleep(3)
            self.__connect(None, reconnect=reconnect)

    def __reconnect(self):
        import time
        for a in range(3):
            self.__connect(None, reconnect=True)
            if self.__is_open():
                break
            print('try reconnect... ')
            time.sleep(3)

    def __disconnect(self):

        if self.fe is not None:
            try:
                self.fe.close()
                self.fe = None
                self.__set_prompt_path()
            except RemoteIOError as e:
                self.__error(str(e))
            except Exception as e:
                print(e)

    def __is_open(self):

        if self.fe is None:
            self.__error("Not connected to device. Use 'open' first.")
            return False

        return True

    def __parse_file_names(self, args):

        tokens, rest = self.tokenizer.tokenize(args)

        if rest != '':
            self.__error("Invalid filename given: %s" % rest)
        else:
            return [token.value for token in tokens]

        return None

    def __update_state(self, file_name=STATE_FILE, state='mpfshell'):
        state = {self.port: state}
        if os.path.exists(file_name):
            with open(file_name, 'r') as fp:
                state_intact = json.load(fp)
            state_intact.update(state)
        else:
            state_intact = state
        with open(file_name, 'w') as fp:
            json.dump(state_intact, fp, indent=4)

    def __parse_put_args(self, args):
        if not len(args):
            self.__error("Missing arguments: <LOCAL FILE> [<LOCAL WORKPATH>] [<REMOTE FILE>]")

        elif self.__is_open():

            s_args = self.__parse_file_names(args)
            if not s_args:
                return
            elif len(s_args) > 3:
                self.__error("Only one ore two or three arguments allowed: <LOCAL FILE> [<LOCAL WORKPATH>]"
                             "[<REMOTE FILE>]")
                return

            if len(s_args) == 3:  # 需要约定好，put携带的路径参数，文件为相对路径，工作路径为绝对路径
                rfile_name = s_args[2]
                work_path = s_args[1]
                if not s_args[0].startswith(work_path):
                    lfile_name = os.path.join(work_path, s_args[0])
                else:
                    lfile_name = s_args[0]
            elif len(s_args) == 2:
                rfile_name = s_args[0]
                work_path = s_args[1]
                if not rfile_name.startswith(work_path):
                    lfile_name = os.path.join(work_path, s_args[0])
                else:
                    lfile_name = s_args[0]
            else:
                lfile_name, rfile_name = s_args[0], s_args[0]
                work_path = None
                if not lfile_name.startswith(os.getcwd()):
                    lfile_name = os.path.join(os.getcwd(), lfile_name)
            return lfile_name, work_path, rfile_name

    def onecmd(self, line):
        """Interpret the argument as though it had been typed in response
        to the prompt.

        This may be overridden, but should not normally need to be;
        see the precmd() and postcmd() methods for useful execution hooks.
        The return value is a flag indicating whether interpretation of
        commands by the interpreter should stop.

        """
        cmd, arg, line = self.parseline(line)
        if not line:
            return self.emptyline()
        if cmd is None:
            return self.default(line)
        # self.lastcmd = line
        if line == 'EOF' :
            self.lastcmd = ''
        if cmd == '':
            return self.default(line)
        else:
            try:
                func = getattr(self, 'do_' + cmd)
            except AttributeError:
                return self.default(line)
            return func(arg)

    def all_serial(self):
        import serial.tools.list_ports
        print("looking for all port...")
        plist = list(serial.tools.list_ports.comports())
        return plist
        
    def do_view(self, args):
        """view(v)
        view all serial.
        """
        plist = self.all_serial()
        if len(plist) <= 0:
            print("serial not found!")
        else:
            for serial in plist:
                print("serial name :", serial[1], " : ", serial[0].split('/')[-1])

        if self.open_args:
            print("current open_args", self.open_args)


    def do_v(self, args):
        return self.do_view(args)

    def do_q(self, args):
        return self.do_quit(args)

    def do_quit(self, args):
        """quit(q)
        Exit this shell.
        """
        self.__disconnect()

        return True

    do_EOF = do_quit

    def do_o(self, args):
        return self.do_open(args)

    def do_open(self, args):
        """open(o) <TARGET>
        Open connection to device with given target. TARGET might be:

        - a serial port, e.g.       ttyUSB0, ser:/dev/ttyUSB0
        - a telnet host, e.g        tn:192.168.1.1 or tn:192.168.1.1,login,passwd
        - a websocket host, e.g.    ws:192.168.1.1 or ws:192.168.1.1,passwd
        """

        if not len(args):
            plist = self.all_serial()
            if len(plist) != 0:
                args = plist[0][0].split('/')[-1]

        if not len(args):
            self.__error("Missing argument: <PORT>")
        else:
            if not args.startswith("ser:/dev/") \
                    and not args.startswith("ser:COM") \
                    and not args.startswith("tn:") \
                    and not args.startswith("ws:"):

                if platform.system() == "Windows":
                    args = "ser:" + args
                elif '/dev' in args:
                    args = "ser:" + args
                else:
                    args = "ser:/dev/" + args

            self.open_args = args
            self.port = args

            self.__connect(args)
            self.__update_state()

    def complete_open(self, *args):
        ports = glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*')
        return [i[5:] for i in ports if i[5:].startswith(args[0])]

    def do_close(self, args):
        """close
        Close connection to device.
        """

        self.__disconnect()

    def __sort_files(self, file_):
        if isinstance(file_, tuple):
            if file_[1].startswith(" "):
                return float('inf')
            return file_[1]
        return file_

    def do_ls(self, args):
        """ls
        List remote files.
        """

        if self.__is_open():
            try:
                files = list(self.fe.ls(add_details=True))
                files.sort(key=self.__sort_files)

                if self.fe.pwd() != "/":
                    files = [("..", "D")] + files

                print("\nRemote files in '%s':\n" % self.fe.pwd())

                for elem, type in files:
                    if type == 'D':
                        print(" <dir> %s" % elem)
                    else:
                        print(" <file/empty_dir> %s" % elem)

                print("")

            except IOError as e:
                self.__error(str(e))
            except Exception as e:
                print(e)

    def do_pwd(self, args):
        """pwd
         Print current remote directory.
         """
        if self.__is_open():
            print(self.fe.pwd())

    def do_cd(self, args):
        """cd <TARGET DIR>
        Change current remote directory to given target.
        """
        if not len(args):
            self.__error("Missing argument: <REMOTE DIR>")
        elif self.__is_open():
            try:
                s_args = self.__parse_file_names(args)
                if not s_args:
                    return
                elif len(s_args) > 1:
                    self.__error("Only one argument allowed: <REMOTE DIR>")
                    return

                self.fe.cd(s_args[0])
                self.__set_prompt_path()
            except IOError as e:
                self.__error(str(e))
            except Exception as e:
                print(e)

    def complete_cd(self, *args):

        try:
            files = self.fe.ls(add_files=False)
        except Exception:
            files = []

        return [i for i in files if i.startswith(args[0])]

    def do_md(self, args):
        """md <TARGET DIR>
        Create new remote directory.
        """
        if not len(args):
            self.__error("Missing argument: <REMOTE DIR>")
        elif self.__is_open():
            try:
                s_args = self.__parse_file_names(args)
                if not s_args:
                    return
                elif len(s_args) > 1:
                    self.__error("Only one argument allowed: <REMOTE DIR>")
                    return

                self.fe.md(s_args[0])
            except IOError as e:
                self.__error(str(e))
            except Exception as e:
                print(e)

    def do_lls(self, args):
        """lls
        List files in current local directory.
        """

        files = os.listdir(".")

        print("\nLocal files:\n")

        for f in files:
            if os.path.isdir(f):
                print(" <dir> %s" % f)
        for f in files:
            if os.path.isfile(f):
                print("       %s" % f)
        print("")

    def do_lcd(self, args):
        """lcd <TARGET DIR>
        Change current local directory to given target.
        """

        if not len(args):
            self.__error("Missing argument: <LOCAL DIR>")
        else:
            try:
                s_args = self.__parse_file_names(args)
                if not s_args:
                    return
                elif len(s_args) > 1:
                    self.__error("Only one argument allowed: <LOCAL DIR>")
                    return

                os.chdir(s_args[0])
            except OSError as e:
                self.__error(str(e).split("] ")[-1])
            except Exception as e:
                print(e)

    def complete_lcd(self, *args):
        dirs = [o for o in os.listdir(".") if os.path.isdir(os.path.join(".", o))]
        return [i for i in dirs if i.startswith(args[0])]

    def do_lpwd(self, args):
        """lpwd
        Print current local directory.
        """

        print(os.getcwd())

    def __put_dir(self, src, dst, varify=True):
        remote = self.fe.pwd()
        try:
            try:
                self.fe.md(dst, varify=varify)
            except Exception as e:
                pass
            self.fe.cd(dst)
        except Exception as e:
            logging.error(e)
        for f in Path(src).rglob('*'):
            if f.is_dir():
                self.fe.md(str(f.absolute())[len(src)+1:], varify=False)
        self.fe.cd(remote)

    def _do_put(self, lfile_name, work_path, rfile_name, varify=True, verbose=True):
        """

        Args:
            lfile_name: local absolute path
            work_path: local absolute path
            rfile_name: remote relative path

        Returns:

        """
        logging.warning(f'do put {lfile_name} {work_path} {rfile_name}')
        try:
            if os.path.isdir(lfile_name):
                self.__put_dir(lfile_name, rfile_name, varify=varify)
                files = [str(f.absolute()) for f in Path(lfile_name).rglob('*') if f.is_file()]
                nums = len(files)
                num_cur = 1
                for file in files:
                    relative_path = file[len(work_path) + 1:]
                    remote_relative_path = relative_path.replace(lfile_name[len(work_path) + 1:], rfile_name)
                    file_size = get_file_size(file)
                    if verbose:
                        print(f'[{num_cur}/{nums}] Writing file {relative_path}({file_size // 1024 + 1}kb)')
                    self.fe.put(str(file), remote_relative_path, verbose=not verbose)
                    num_cur += 1
                if verbose:
                    print('Upload done')
            elif os.path.isfile(lfile_name):
                file_size = get_file_size(lfile_name)
                if verbose:
                    print(f'[1/1] Writing file {lfile_name[len(work_path) + 1:]}({file_size // 1024 + 1}kb)')
                self.fe.put(lfile_name, rfile_name, verbose=not verbose)
                if verbose:
                    print('Upload done')
            else:
                print(f'There is no file or path {lfile_name}')
        except IOError as e:
            self.__error(str(e))
        except Exception as e:
            print(e)

    def do_put(self, args, verbose=True):
        """put <LOCAL FILE> [<LOCAL WORKPATH>] [<REMOTE FILE>]
        Upload local file. If the second parameter is given,
        its value is used for local work path.
        If the third parameter is given,
        its value is used for the remote file name. Otherwise the
        remote file will be named the same as the local file.
        """

        put_args = self.__parse_put_args(args)
        if put_args:
            lfile_name, work_path, rfile_name = put_args
            self._do_put(lfile_name, work_path, rfile_name, verbose=verbose)

    def complete_put(self, *args):
        files = [o for o in os.listdir(".") if os.path.isfile(os.path.join(".", o))]
        return [i for i in files if i.startswith(args[0])]

    def do_mput(self, args):
        """mput <SELECTION REGEX>
        Upload all local files that match the given regular expression.
        The remote files will be named the same as the local files.

        "mput" does not get directories, and it is not recursive.
        """

        if not args:
            self.__error("MISSING arguments: <SELECTION REGEX> <WORKPATH> <REMOTE PATH>")
        s_args = self.__parse_file_names(args)

        if self.__is_open():
            pattern = s_args[0]
            work_path = os.getcwd()
            remote_path = None
            if len(s_args) >= 2:
                work_path = s_args[1]
            if len(s_args) >= 3:
                remote_path = s_args[2]

            files = Path(work_path).glob('*')
            compiler = re.compile(pattern)
            for file in files:
                if compiler.match(str(file)):
                    if remote_path is None:
                        rfile_name = file.name
                    else:
                        rfile_name = remote_path
                        rfile_name = f'{rfile_name}/{file.name}'
                    self._do_put(str(file.absolute()), work_path, rfile_name, varify=False)

    def do_get(self, args):
        """get <REMOTE FILE> [<LOCAL FILE>]
        Download remote file. If the second parameter is given,
        its value is used for the local file name. Otherwise the
        locale file will be named the same as the remote file.
        """

        if not len(args):
            self.__error("Missing arguments: <REMOTE FILE> [<LOCAL FILE>]")

        elif self.__is_open():

            s_args = self.__parse_file_names(args)
            if not s_args:
                return
            elif len(s_args) > 2:
                self.__error("Only one ore two arguments allowed: <REMOTE FILE> [<LOCAL FILE>]")
                return

            rfile_name = s_args[0]

            if len(s_args) > 1:
                lfile_name = s_args[1]
            else:
                lfile_name = rfile_name

            try:
                self.fe.get(rfile_name, lfile_name)
            except IOError as e:
                self.__error(str(e))
            except Exception as e:
                print(e)

    def do_mget(self, args):
        """mget <SELECTION REGEX>
        Download all remote files that match the given regular expression.
        The local files will be named the same as the remote files.

        "mget" does not get directories, and it is not recursive.
        """

        if not len(args):
            self.__error("Missing argument: <SELECTION REGEX> [<LOCAL PATH>]")

        elif self.__is_open():
            s_args = self.__parse_file_names(args)
            if len(s_args) >= 1:
                pattern = s_args[0]
                local_path = os.getcwd()
            if len(s_args) >= 2:
                local_path = s_args[1]

            try:
                self.fe.mget(local_path, pattern, True)
            except IOError as e:
                self.__error(str(e))
            except Exception as e:
                print(e)

    def complete_get(self, *args):

        try:
            files = self.fe.ls(add_dirs=False)
        except Exception:
            files = []

        return [i for i in files if i.startswith(args[0])]

    def do_rm(self, args):
        """rm <REMOTE FILE or DIR>
        Delete a remote file or directory.

        Note: only empty directories could be removed.
        """

        if not len(args):
            self.__error("Missing argument: <REMOTE FILE>")
        elif self.__is_open():

            s_args = self.__parse_file_names(args)
            if not s_args:
                return
            elif len(s_args) > 1:
                self.__error("Only one argument allowed: <REMOTE FILE>")
                return

            try:
                self.fe.rm(s_args[0])
            except IOError as e:
                self.__error(str(e))
            except PyboardError:
                self.__error("Unable to send request to %s" % self.fe.sysname)
            except Exception as e:
                print(e)

    def do_mrm(self, args):
        """mrm <SELECTION REGEX>
        Delete all remote files that match the given regular expression.

        "mrm" does not delete directories, and it is not recursive.
        """

        if not len(args):
            self.__error("Missing argument: <SELECTION REGEX>")

        elif self.__is_open():

            try:
                self.fe.mrm(args)
            except IOError as e:
                self.__error(str(e))
            except Exception as e:
                print(e)

    def complete_rm(self, *args):

        try:
            files = self.fe.ls()
        except Exception:
            files = []

        return [i for i in files if i.startswith(args[0])]

    def do_c(self, args):
        self.do_cat(args)

    def do_cat(self, args):
        """cat(c) <REMOTE FILE>
        Print the contents of a remote file.
        """

        if not len(args):
            self.__error("Missing argument: <REMOTE FILE>")
        elif self.__is_open():

            s_args = self.__parse_file_names(args)
            if not s_args:
                return
            elif len(s_args) > 1:
                self.__error("Only one argument allowed: <REMOTE FILE>")
                return

            try:
                print(self.fe.gets(s_args[0]))
            except IOError as e:
                self.__error(str(e))
            except Exception as e:
                print(e)

    complete_cat = complete_get

    def do_rf(self, args):
        self.do_runfile(args)

    def do_runfile(self, args):
        """runfile(rf) <LOCAL FILE>
        download and running local file in board.
        """

        if not len(args):
            self.__error("Missing arguments: <LOCAL FILE>")

        elif self.__is_open():

            try:
                put_args = self.__parse_put_args(args)
                if put_args:
                    lfile_name, work_path, rfile_name = put_args
                    self._do_put(lfile_name, work_path, rfile_name, verbose=False)
                    self.do_ef(rfile_name)
            except IOError as e:
                self.__error(str(e))
            except Exception as e:
                print(e)

    def do_ef(self, args):
        self.do_execfile(args)

    def do_execfile(self, args):
        """execfile(ef) <REMOTE FILE>
        Execute a Python filename on remote.
        """
        if not args:
            self.__error("Missing arguments: <REMOTE .PY FILE>")
        if not args.endswith('.py'):
            self.__error("Remote file must be a python executable file")
        if self.fe._exec_tool == 'repl':
            try:
                self.do_repl("exec(open('{0}').read())\r\n".format(args))
            except Exception as e:
                raise e
            else:
                return

        command = f'mpy {args}'
        try:
            command_data = self.fe.exec_command_in_shell(command)
            command_data = command_data.decode('utf-8')
            data = ''.join(re.split('sh[\s/>]+', command_data)[1:])
            data.strip()
            print(data)
            logging.info(f'{command_data} result: {data}')
        except Exception as e:
            logging.error(e)
            print(e)
        self.__reconnect()

    def do_lef(self, args):
        self.do_lexecfile(args)

    def do_lexecfile(self, args):
        """execfile(ef) <LOCAL FILE>
        Execute a Python filename on local.
        """
        if self.__is_open():

            try:
                put_args = self.__parse_put_args(args)
                if put_args:
                    lfile_name, work_path, rfile_name = put_args
                    self._do_put(lfile_name, work_path, rfile_name)
                    self.do_repl("exec(open('{0}').read())\r\n".format(rfile_name))

            except IOError as e:
                self.__error(str(e))
            except Exception as e:
                print(e)

    def do_e(self, args):
        self.do_exec(args)

    def do_exec(self, args):
        """exec(e) <Python CODE>
        Execute a Python CODE on remote.
        """

        def data_consumer(data):
            data = str(data.decode('utf-8'))
            sys.stdout.write(data.strip("\x04"))

        if not len(args):
            self.__error("Missing argument: <Python CODE>")
        elif self.__is_open():
            ret = trim_code_block(args)
            ret = ret.replace('\\n', '\n')
            code_block = ret + '\r\nimport time'
            code_block += '\r\ntime.sleep(0.1)'


            try:
                self.fe.exec_raw_no_follow(code_block + "\n")
                ret = self.fe.follow(1, data_consumer)

                if len(ret[-1]):
                    self.__error(str(ret[-1].decode('utf-8')))
                    
            except IOError as e:
                self.__error(str(e))
            except PyboardError as e:
                self.__error(str(e))
            except Exception as e:
                logging.error(e)

    def do_r(self, args):
        self.do_repl(args)

    def do_repl(self, args):
        """repl(r)
        Enter Micropython REPL.
        """

        import serial

        ver = serial.VERSION.split(".")

        if int(ver[0]) < 2 or (int(ver[0]) == 2 and int(ver[1]) < 7):
            self.__error("REPL needs PySerial version >= 2.7, found %s" % serial.VERSION)
            return

        if self.__is_open():

            if self.repl is None:

                from term import Term
                self.repl = Term(self.fe.con)

                if platform.system() == "Windows":
                    self.repl.exit_character = chr(0x11)
                else:
                    self.repl.exit_character = chr(0x1d)

                self.repl.raw = True
                self.repl.set_rx_encoding('UTF-8')
                self.repl.set_tx_encoding('UTF-8')

            else:
                self.repl.serial = self.fe.con

            self.fe.teardown()
            self.repl.start()
            self.__update_state(state='repl')

            if self.repl.exit_character == chr(0x11):
                print("\n*** Exit REPL with Ctrl+Q ***")
            else:
                print("\n*** Exit REPL with Ctrl+] ***")

            try:
                if args != None:
                    self.fe.con.write(bytes(args, encoding="utf8"))
                self.repl.join(True)
            except Exception as e:
                # print(e)
                pass

            self.repl.console.cleanup()

            self.fe.setup()
            self.__update_state(state='mpfshell')
            print("")

    def do_mpyc(self, args):
        """mpyc <LOCAL PYTHON FILE>
        Compile a Python file into byte-code by using mpy-cross (which needs to be in the path).
        The compiled file has the same name as the original file but with extension '.mpy'.
        """

        if not len(args):
            self.__error("Missing argument: <LOCAL FILE>")
        else:

            s_args = self.__parse_file_names(args)
            if not s_args:
                return
            elif len(s_args) > 1:
                self.__error("Only one argument allowed: <LOCAL FILE>")
                return

            try:
                self.fe.mpy_cross(s_args[0])
            except IOError as e:
                self.__error(str(e))
            except Exception as e:
                print(e)

    def complete_mpyc(self, *args):
        files = [o for o in os.listdir(".") if (os.path.isfile(os.path.join(".", o)) and o.endswith(".py"))]
        return [i for i in files if i.startswith(args[0])]

    def do_rmrf(self, target):
        """
        删除目录树
        Args:
            target: 文件名或文件夹名称

        Returns:

        """
        if not len(target):
            self.__error("Missing argument: <REMOTE DIR>")

        elif self.__is_open():

            try:
                self.fe.rmrf(target)
            except IOError as e:
                self.__error(str(e))
            except Exception as e:
                print(e)

    def do_mrmrf(self, args):
        """
        批量删除目录树
        Args:
            args: 目变文件(夹)名称的正则表达式

        Returns:

        """
        if not len(args):
            self.__error("Missing argument: <SELECT REGEX>")

        elif self.__is_open():

            try:
                self.fe.mrmrf(args)
            except IOError as e:
                self.__error(str(e))
            except Exception as e:
                print(e)

    def do_synchronize(self, args):
        """
        同步目录
        Args:
            args: 同do_put

        Returns:

        """
        put_args = self.__parse_put_args(args)
        if put_args:
            lfile_name, work_path, rfile_name = put_args
            self._do_put(lfile_name, work_path, rfile_name, verbose=False)
            self.fe.synchronize(lfile_name, rfile_name)
            print('Synchronize done\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--command", help="execute given commands (separated by ;)", default=None, nargs="*")
    parser.add_argument("-s", "--script", help="execute commands from file", default=None)
    parser.add_argument("-n", "--noninteractive", help="non interactive mode (don't enter shell)",
                        action="store_true", default=False)

    parser.add_argument("--nocolor", help="disable color", action="store_true", default=False)
    parser.add_argument("--nocache", help="disable cache", action="store_true", default=False)
    parser.add_argument("--nohelp", help="disable help", action="store_true", default=False)

    parser.add_argument("--logfile", help="write log to file", default=None)
    parser.add_argument("--loglevel", help="loglevel (CRITICAL, ERROR, WARNING, INFO, DEBUG)", default="INFO")

    parser.add_argument("--reset", help="hard reset device via DTR (serial connection only)", action="store_true",
                        default=False)

    parser.add_argument("-o", "--open", help="directly opens board", metavar="BOARD", action="store", default=None)
    parser.add_argument("board", help="directly opens board", nargs="?", action="store", default=None)

    args = parser.parse_args()

    format='%(asctime)s %(thread)d %(threadName)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s'

    if args.logfile is not None:
        logging.basicConfig(format=format, filename=args.logfile, level=args.loglevel)
    else:
        logging.basicConfig(filename=init_log_path(), format=format, level=logging.DEBUG)

    logging.info('Micropython File Shell v%s started' % version.FULL)
    logging.info('Running on Python %d.%d using PySerial %s' \
                 % (sys.version_info[0], sys.version_info[1], serial.VERSION))

    mpfs = MpFileShell(not args.nocolor, not args.nocache, args.reset, args.nohelp)

    if args.open is not None:
        if args.board is None:
            mpfs.do_open(args.open)
        else:
            print("Positional argument ({}) takes precedence over --open.".format(args.board))
    if args.board is not None:
        mpfs.do_open(args.board)

    if args.command is not None:

        for cmd in ' '.join(args.command).split(';'):
            scmd = cmd.strip()
            if len(scmd) > 0 and not scmd.startswith('#'):
                mpfs.onecmd(scmd)

    elif args.script is not None:

        f = open(args.script, 'r')
        script = ""

        for line in f:

            sline = line.strip()

            if len(sline) > 0 and not sline.startswith('#'):
                script += sline + '\n'

        if sys.version_info < (3, 0):
            sys.stdin = io.StringIO(script.decode('utf-8'))
        else:
            sys.stdin = io.StringIO(script)

        mpfs.intro = ''
        mpfs.prompt = ''

    if not args.noninteractive:

        try:
            mpfs.cmdloop()
        except KeyboardInterrupt:
            print("")
        except Exception as e:
            print(e)


if __name__ == '__main__':
    main()
