# -*- coding: utf-8 -*-
import re


def repeat_inquiry(content):
    ret = input(f'{content}:')
    if ret in ('y', 'Y'):
        return True
    return False


def trim_code_block(code_block):
    """
    根据第一行的缩进，每一行都去除这个缩进
    Args:
        code_block:

    Returns:

    """
    pattern = re.compile('[^\n]+(?:\r?\n|$)')
    lines = pattern.findall(code_block)  # regex to split both win and unix style
    count = 0
    if lines:
        while lines[0].startswith(' ', count):
            count += 1
        if count > 0:
            prefix = ' ' * count
            for i in range(len(lines)):
                if lines[i].startswith(prefix):
                    lines[i] = lines[i][count:]
                else:
                    lines[i] = lines[i].strip() + " # <- IndentationError"

        return ''.join(lines)
    return code_block
