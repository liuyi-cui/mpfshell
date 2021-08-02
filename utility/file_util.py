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
        if cache_data == b'':
            return
        file_info = binascii.a2b_hex(cache_data).decode('utf-8')  # 字符串

        for line_ in file_info.strip().split('\r\n'):
            self._cache.update(eval(line_))

    def _update_cache_file(self) -> bytes:
        cache_list = [str({_k:_v}) for _k, _v in self._cache.items()]
        cache_str = '\r\n'.join(cache_list)
        cache_str += '\r\n'
        return cache_str.encode('utf-8')

    @staticmethod
    def md5_sign(file_obj):
        tool = hashlib.md5()
        tool.update(file_obj)
        return tool.hexdigest()

    def gen_sign(self, file_path):
        with open(file_path, 'rb') as fp:
            sign = self.md5_sign(fp.read())
        self._cache.update({file_path: sign})
        logging.info(f'add sign: {file_path}:{sign}')
        return self._update_cache_file()

    def varify_sign(self, file_path, file_path_remote):
        logging.info(f'varify file: {file_path_remote}')
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


if __name__ == '__main__':
    file_path = r'D:\Projects\python\mp\sign'
    md5_varifier = MD5Varifier(file_path)
    for file_ in Path(__file__).parent.parent.rglob('*py'):
        print(file_)
        md5_varifier.varify_sign(str(file_.absolute()))
