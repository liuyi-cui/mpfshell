#### 概述

Shell型的MicroPython文件管理工具，可实现对开发板进行文件上传、下载、删除以及运行脚本功能

#### 前置条件

python 3.5.4 +

requirements

开发板具备MicroPython环境

开发板具备文件系统

开发板上电直接进入`mpy`模式

#### 主要库

| 库名称   | 用途             | 来源     |
| -------- | ---------------- | -------- |
| cmd      | 命令行工具       | 标准库   |
| pyserial | 串口连接工具     | 第三方库 |
| Term     | repl模块         | 自定义   |
| Token    | 解析命令输入参数 | 自定义   |

#### 目录

```python
|-- conbase.py  # 串口连接基类
|-- conserial.py  # 串口连接类
|-- contelnet.py
|-- conwebsock.py
|-- mpfexp.py  # 串口操作类1(基于pyboard.py)
|-- mpfshell.py  # 入口
|-- pyboard.py  # 串口操作类2
|-- README.md
|-- REQUIREMENTS
|-- retry.py  # 异常重试方法，装饰器
|-- tokenizer.py
|-- version.py
|-- __init__.py
|-- log
|   |-- mpfshell.log  # 日志
|-- utility
|   |-- file_util.py  # 操作文件辅助类(签名相关)
|   |-- utils.py  # 辅助方法和类
|   |-- __init__.py
```
#### 使用方法

连接硬件

运行mpfshell.py

执行命令

#### 命令详解

当连上硬件后，运行`mpfshell.py`，得到如下提示：

```python
looking for all port...
serial name : Unisoc Usb Serial Port 0 (COM14)  :  COM14
serial name : Unisoc Usb Serial Port 5 (COM11)  :  COM11
serial name : Unisoc Usb Serial Port 1 (COM13)  :  COM13
input ' open COM15 ' and enter connect your board.
```

证明硬件连接成功。

##### 1.open

> 连接设备
>
> 格式为`open (port)`
>
> 成功后返回`Connected to xxx`
>
> ```python
> Connected to win32
> ```

##### 2.close

> 与open相对，关闭当前设备的连接

##### 3.quit(q) | EOF 

> 退出程序

##### 4.help

> 查看命令的帮助信息
>
> 格式: `help 命令`
>
> ```python
> mpfs [/]> help open  # 输入
> open(o) <TARGET>
>         Open connection to device with given target. TARGET might be:
> 
>         - a serial port, e.g.       ttyUSB0, ser:/dev/ttyUSB0
>         - a telnet host, e.g        tn:192.168.1.1 or tn:192.168.1.1,login,passwd
>         - a websocket host, e.g.    ws:192.168.1.1 or ws:192.168.1.1,passwd
> ```

##### 5.view

> 查看本机连接的串口，和当前的open配置(open连接了的话)
>
> ```python
> mpfs [/]> view  # 输入
> looking for all port...
> serial name : Unisoc Usb Serial Port 3 (COM16)  :  COM16
> serial name : Unisoc Usb Serial Port 4 (COM12)  :  COM12
> serial name : Unisoc Usb Serial Port 0 (COM14)  :  COM14
> serial name : Unisoc Usb Serial Port 5 (COM11)  :  COM11
> serial name : Unisoc Usb Serial Port 1 (COM13)  :  COM13
> serial name : Unisoc Usb Serial Port 6 (COM18)  :  COM18
> serial name : Unisoc Usb Serial Port 2 (COM17)  :  COM17
> serial name : Unisoc Usb Serial Port 7 (COM15)  :  COM15
> current open_args ser:COM11
> ```

##### 6.ls

> 查看开发板当前目录下的所有文件
>
> ```python
> mpfs [/]> ls
> 
> Remote files in '/':
> 
>  <dir> nvm
>  <dir> modemnvm
>  <dir> First
>  <dir> .git
>  <dir> Once
>  <file/empty_dir> mp
>  <file/empty_dir> log
>  <file/empty_dir> utility
>  <file/empty_dir> __pycache__
>  <file/empty_dir> hello.py
>  <file/empty_dir> sms_dm_nv.bin
>  <file/empty_dir> tts.mp3
>  <file/empty_dir> sign
> ```

#####  7.lls

> 与**ls**相对，查看程序当前目录下的所有文件
>
> ```python
> mpfs [/]> lls
> 
> Local files:
> 
>  <dir> .git
>  <dir> .idea
>  <dir> log
>  <dir> remote
>  <dir> utility
>  <dir> __pycache__
>        conbase.py
>        conserial.py
>        contelnet.py
>        conwebsock.py
>        directoryList.md
>        hello.py
>        mpfexp.py
> ```

##### 8.cd

> 修改程序访问开发板的当前工作目录
>
> 格式：`cd ..`或`cd log`
>
> ```python
> mpfs [/]> cd log
> mpfs [/log]> cd ..
> mpfs [/]>
> ```

##### 9.lcd

> 与**cd**相对，修改程序的本地工作路径

> ```python
> mpfs [/log]> lcd log
> mpfs [/log]> lls
> 
> Local files:
> 
>        mpfshell.log
>        mpf_bak - 副本.log
>        mpf_bak.log
> ```

##### 10.pwd

> 返回开发板当前所处的目录
>
> ```python
> mpfs [/log]> pwd
> /log
> ```

##### 11.lpwd

> 返回程序当前所处的目录
>
> ```python
> mpfs [/log]> lpwd
> D:\Projects\python\mp\log
> ```

##### 12.md

> 在开发板的当前目录下新建一个文件夹
>
> 格式：`md 文件夹名`

##### 13. cat(c)

> 查看文件内容
>
> 格式为`cat 文件名`
>
> ```python
> mpfs [/]> cat hello.py
> print('hello world!!!')
> mpfs [/]>
> ```

##### 14.put

> 将本地工作目录下的文件/文件夹推送到开发板，如果为文件夹，则会对该文件夹整个目录树进行操作
>
> 格式为：`put 文件(夹)名称 [本地工作路径] [开发板存储路径]`

##### 15.mput

> 对本地当前目录下的文件(夹)设定匹配规则，符合匹配规则的即进行**put**操作。
>
> 格式为：`mput 正则表达式 [本地工作路径] [开发板存储路径]`

##### 16.get

> 下载开发板当前目录下文件(夹)到本地当前目录
>
> 格式为：`get 文件(夹)名称 [本地存储文件(夹)名] `

##### 17.mget

> 对开发板当前目录下的文件(夹)设定匹配规则，符合匹配规则的即进行**get**操作。
>
> 格式为：`mget 正则表达式 [本地存储文件夹] `

##### 18.rm

> 移除开发板上的文件(夹)。如果删除对象为文件夹，则必须为空文件夹
>
> 格式为：`rm 文件(夹)名称`

##### 19.mrm

> 根据匹配规则，批量删除文件(夹)
>
> 格式为：`mrm 正则表达式`

##### 20.rmrf

> 移除开发板上的文件(夹)。可对非空文件夹操作
>
> 格式为：`rmrf 文件(夹)名称`

##### 21.mrmrf

> 批量移除开发板上的文件(夹)。可对非空文件夹操作
>
> 格式为：`mrmrf 正则表达式`

##### 22.repl

> 进入micropython的repl控制接口，可以直接执行python代码
>
> ```python
> mpfs [/Once]> repl
> 
> *** Exit REPL with Ctrl+Q ***>
> MicroPython ml305_dev-a2687acbb-dirty on 2021-07-22; MicroPython board with ml305
> Type "help()" for more information.
> >>>
> ```

##### 23.exec

> 将输入在python环境中执行
>
> 格式为 ：`exec 命令`
>
> ```python
> mpfs [/Once]> exec print(12)
> 12
> ```

##### 24.execfile

> 执行开发板上的.py脚本
>
> 格式为：`execfile 文件名`
>
> ```python
> mpfs [/]> execfile hello.py
> hello world!!!
> 
> mpfs [/]>
> ```

##### 25.runfile

> **put**和**execfile**的组合
>
> 格式同`put`：`runfile 文件名 [本地工作路径] [开发板存储路径] ` 

##### 26.lexecfile

> 执行本地目录下的.py脚本。同**runfile**命令不同的是，该命令会进入**repl**模式
>
> 格式同`put`：`lexecfile 文件名 [本地工作路径] [开发板存储路径]`

##### 27.synchronize

> 同步本地与开发板上的文件夹
>
> 格式同`put`: `synchronize 文件夹名 [本地工作路径] [开发板存储路径]`







