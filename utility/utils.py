# -*- coding: utf-8 -*-


def repeat_inquiry(content):
    ret = input(f'{content}:')
    if ret in ('y', 'Y'):
        return True
    return False
