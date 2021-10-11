# -*- coding: utf-8 -*_
#!/usr/bin/env python

"""
Pyboard REPL interface
"""

import sys
import re
import time
import logging

try:
    stdout = sys.stdout.buffer
except AttributeError:
    # Python2 doesn't have buffer attr
    stdout = sys.stdout


def stdout_write_bytes(b):
    b = b.replace(b"\x04", b"")
    stdout.write(b)
    stdout.flush()


class PyboardError(BaseException):
    pass


class Pyboard:

    def __init__(self, conbase):
        logging.info('Init Pyboard')

        self.con = conbase
        self._BUFFER_SIZE = 32  # Amount of data to read or write to the serial port at a time.
        # This is kept small because small chips and USB to serial bridges usually have very small buffers

    def close(self):

        if self.con is not None:
            self.con.close()

    def __exec_gc_collect(self):
        """内存回收"""
        command = b'gc.collect()'
        logging.info(f'exec command: {command}')

        # check we have a prompt
        data = self.read_until(1, b'>')

        if not data.endswith(b'>'):
            logging.error(f'data is not endswith >: {data}')
            raise PyboardError('could not enter raw repl, auto try again.')

        # write command
        for i in range(0, len(command), self._BUFFER_SIZE):
            self.con.write(command[i:min(i + self._BUFFER_SIZE, len(command))])
            time.sleep(0.01)
        self.con.write(b'\x04')
        # TODO 是否需要验证回收成功
        logging.info('gc collect success')

    def read_until(self, min_num_bytes, ending, timeout=10, data_consumer=None, max_recv=sys.maxsize):

        data = self.con.read(min_num_bytes)
        if data_consumer:
            data_consumer(data)
        timeout_count = 0
        while len(data) < max_recv:
            # print(len(data), data) # if main.py exist "while True:\r\nprint(1)\r\n lead to recv data error"
    
            if data.endswith(ending):
                break
            elif self.con.inWaiting() > 0:
                new_data = self.con.read(1)
                data = data + new_data
                if data_consumer:
                    data_consumer(new_data)
                timeout_count = 0
            else:
                timeout_count += 1
                if timeout is not None and timeout_count >= 100 * timeout:
                    break
                time.sleep(0.01)
        logging.debug(f"read until {ending} data: {data}")
        return data

    def _exit_mpy(self):
        """
        exit mpy model and enter shell model
        """
        self.con.write(b'\x04')
        time.sleep(0.5)

    def _enter_mpy(self):
        """
        exit shell model and enter mpy model
        """
        self.con.write(b'mpy')
        self.con.write(b'\r\x03\r\n')
        self.con.write(b'\r\x02\r\n')

    def exec_command_in_shell(self, command: str):
        """
        execute command in shell model
        Args:
            command:

        Returns:

        """
        self._exit_mpy()
        self.con.write(command.encode('utf-8'))
        self.con.write(b'\r\n')
        time.sleep(0.5)
        data = b''
        num = 0
        while num < self.con.inWaiting():
            to_read = self.con.inWaiting()
            data += self.con.read(to_read)
            num += to_read
        self._enter_mpy()
        return data

    def get_board_info(self):
        board_model_pattern = r'MicroPython board with (\w+)'
        esp_module_pattern = r'ESP module with (\w+)'
        board_model = None
        for i in range(8):
            time.sleep(0.1)
            self.con.write(b'\x03\x03\x03\x03')
            time.sleep(0.1)
            self.con.write(b'\x02\x02\x02\x02')
            time.sleep(0.1)

            if not self.con.inWaiting():  # 缓冲区没有数据
                return None
            data = self.read_until(1, b'>>>', timeout=5, max_recv=8000)
            if b'mpy: command not found' in data:
                raise TimeoutError('There is no micropython on board')
            elif not data.endswith(b'>>>'):
                # print(data)
                print('Could not enter raw repl, Press Reset key after 10 seconds.')
            else:
                break

        # flush input (without relying on serial.flushInput())
        n = self.con.inWaiting()
        data = self.con.read(n)
        if data:
            ret = re.search(board_model_pattern, data.decode('utf-8'))
            if ret:
                board_model = ret.group(1)
            else:
                ret = re.search(esp_module_pattern, data.decode('utf-8'))
                if ret:
                    board_model = ret.group(1)
        return board_model

    def enter_raw_repl(self):
        # self.con.write(b'\x6D\x70\x79')

        # waiting any board boot start and enter micropython
        for i in range(8):
            time.sleep(0.1)
            self.con.write(b'\x03\x03\x03\x03')
            time.sleep(0.1)
            self.con.write(b'\x02\x02\x02\x02')
            time.sleep(0.1)

            data = self.read_until(1, b'>>>', timeout=5, max_recv=8000)
            if not data.endswith(b'>>>'):
                # print(data)
                print('Could not enter raw repl, Press Reset key after 10 seconds.')
            else:
                break

        # flush input (without relying on serial.flushInput())
        n = self.con.inWaiting()
        while n > 0:
            self.con.read(n)
            n = self.con.inWaiting()
            
        # print('enter_raw_repl')
        self.con.write(b'\r\x01') # ctrl-A: enter raw REPL
        data = self.read_until(1, b'raw REPL; CTRL-B to exit', max_recv=8000)
        if not data.endswith(b'raw REPL; CTRL-B to exit'):
            # print(data)
            raise PyboardError('could not enter raw repl')

    def exit_raw_repl(self):
        self.con.write(b'\r\x02')  # ctrl-B: enter friendly REPL

    def keyboard_interrupt(self):
        self.con.write(b'\x03\x03\x03\x03')  # ctrl-C: KeyboardInterrupt

    def follow(self, timeout, data_consumer=None):

        # wait for normal output
        data = self.read_until(1, b'\x04', timeout=timeout, data_consumer=data_consumer)
        logging.info(f'data: {data}')
        if not data.endswith(b'\x04') and not data.endswith(b'>'):
            raise PyboardError('timeout waiting for first EOF reception')
        data = data[:-1]

        # wait for error output
        data_err = self.read_until(1, b'\x04', timeout=timeout)
        logging.info(f'data_err: {data_err}')
        # print(data_err)
        if not data_err.endswith(b'\x04') and not data.endswith(b'>'):
            raise PyboardError('timeout waiting for second EOF reception')
        data_err = data_err[:-1]

        # return normal and error output
        return data, data_err

    def exec_raw_no_follow(self, command):
        logging.info(f'exec command: {command}')

        if isinstance(command, bytes):
            command_bytes = command
        else:
            command_bytes = bytes(command.encode('utf-8'))

        # check we have a prompt
        data = self.read_until(1, b'>')

        if not data.endswith(b'>'):
            logging.error(f'data is not endswith >: {data}')
            raise PyboardError('could not enter raw repl, auto try again.')

        # write command
        for i in range(0, len(command_bytes), self._BUFFER_SIZE):
            self.con.write(command_bytes[i:min(i + self._BUFFER_SIZE, len(command_bytes))])
            time.sleep(0.01)
        self.con.write(b'\x04')

        # check if we could exec command
        data = self.con.read(2)
        if b'OK' not in data:
            logging.error(f'OK is not in data: {data}')
            data = self.con.read(self.con.inWaiting())
            logging.error(f'OK is not in data: {data}')
            raise PyboardError('could not exec command, auto try again.')
        logging.info('exec command success')

    def exec_raw(self, command, timeout=4, data_consumer=None, gc=False):
        # 总是执行一次内存回收
        if gc:
            self.__exec_gc_collect()
        self.exec_raw_no_follow(command)
        return self.follow(timeout, data_consumer)

    def eval(self, expression, gc=False):
        ret = self.exec_('print({})'.format(expression), gc=gc)
        if 'uos' in expression:
            ret = ret.decode('utf-8').replace('\r\n0', '').encode('utf-8')
        ret = ret.strip()
        return ret

    def exec_(self, command, gc=False):
        logging.debug(f'execute command {command}')
        ret, ret_err = self.exec_raw(command, gc=gc)
        if ret_err:
            raise PyboardError('exception', ret, ret_err)
        return ret

    def get_time(self):
        t = str(self.eval('pyb.RTC().datetime()').encode("utf-8"))[1:-1].split(', ')
        return int(t[4]) * 3600 + int(t[5]) * 60 + int(t[6])


# in Python2 exec is a keyword so one must use "exec_"
# but for Python3 we want to provide the nicer version "exec"
setattr(Pyboard, "exec", Pyboard.exec_)
