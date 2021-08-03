# -*- coding: utf-8 -*-

import binascii
import hashlib
import logging
from pathlib import Path


class MD5Varifier:
    _cache = {}
    cache_file = '/sign'  # 板子的顶级目录

    def __init__(self, cache_file=None):
        logging.info('Init MD5Varifier')
        if cache_file is not None:
            self._cache_file = cache_file

    def init_cache(self, cache_data: bytes):
        """
        Get MD5 signatures from cache_data, and store to self._cache
        Args:
            cache_data: read result of cache_file

        Returns:

        """
        if cache_data == b'':
            return
        file_info = binascii.a2b_hex(cache_data).decode('utf-8')  # 字符串

        for line_ in file_info.strip().split('\r\n'):
            self._cache.update(eval(line_))

    def _update_cache_file(self) -> bytes:
        """
        Rebuild MD5 signatures from self._cache and Processed into bytes that can be written directly
        Returns:
            bytes

        """
        cache_list = [str({_k:_v}) for _k, _v in self._cache.items()]
        cache_str = '\r\n'.join(cache_list)
        cache_str += '\r\n'
        return cache_str.encode('utf-8')

    @staticmethod
    def md5_sign(file_obj):
        """
        Generate signature
        Args:
            file_obj:
            bytes/str, read() on context processer

        Returns:

        """
        tool = hashlib.md5()
        tool.update(file_obj)
        return tool.hexdigest()

    def gen_sign(self, file_path):
        """
        Generate signature of file_path
        Args:
            file_path:
            str/pathlib.Path()

        Returns:

        """
        with open(file_path, 'rb') as fp:
            sign = self.md5_sign(fp.read())
        self._cache.update({file_path: sign})
        logging.info(f'add sign: {file_path}:{sign}')
        return self._update_cache_file()

    def varify_sign(self, file_path, file_path_remote):
        """
        varify sign bettwen file_path and file_path_remote
        Args:
            file_path: new file, get sign by generate
            file_path_remote: old file, get sign from cache_file

        Returns:

        """
        logging.info(f'varify file: {file_path}[local] -- {file_path_remote}[remote]')
        with open(file_path, 'rb') as fp:
            sign = self.md5_sign(fp.read())
        if not self._cache.get(file_path_remote):
            logging.info(f'{file_path_remote}: There is no signatures before')
            print(f'{file_path_remote}: There is no signatures before')
            self._cache.update({file_path_remote: sign})
            return self._update_cache_file()
        sign_ori = self._cache.get(file_path_remote)
        if sign_ori != sign:
            logging.info('The old and new signatures are inconsistent, update')
            print('The old and new signatures are inconsistent, update')
            self._cache.update({file_path_remote: sign})
            return self._update_cache_file()
        else:
            logging.info('The new signatures is same as the old, don`t updte')
            print('The new signatures is same as the old, don`t updte')
            return False

    def rm_sign(self, file_path_remote) -> bytes:
        """
        update sign after remove file
        Args:
            file_path_remote: str

        Returns:

        """
        logging.info(f'remove sign of {file_path_remote}')
        if file_path_remote.startswith('/'):
            file_path_remote = file_path_remote[1:]
        self._cache.pop(file_path_remote)
        return self._update_cache_file()
