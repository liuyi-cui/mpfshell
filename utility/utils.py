# -*- coding: utf-8 -*-
import json
import logging
import re
from pathlib import Path


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


def record_str():  # 使用闭包记录传入的字符，并返回拼接结果
    str_val = ''

    def add_str(val: str, refresh=False):
        nonlocal str_val
        if refresh:
            str_val = ''
        str_val += val
        return str_val

    return add_str


def update_state(port, file_name=Path(Path(__file__).parent.parent, 'state_temp.json'), state='mpfshell') -> None:
    """
    针对不同的port,更新其在state_temp.json中的当前状态
    Args:
        port: ser:COM21
        file_name:
        state:

    Returns:
        None
    """
    logging.info(f'update {port}.state to {state}')
    params =port.split(',')
    if len(params) > 1:
        state = {params[0]: state}
    else:
        state = {port: state}
    if file_name.exists():
        with open(file_name, 'r') as fp:
            state_intact = json.load(fp)
        state_intact.update(state)
    else:
        state_intact = state
    with open(file_name, 'w') as fp:
        json.dump(state_intact, fp, indent=4)
