# PyInstaller hook for webrtcvad
# 这个SB hook 是为了绕过 webrtcvad-wheels 的兼容性问题

from PyInstaller.utils.hooks import is_module_satisfies
import os

# 获取 webrtcvad 的位置
import webrtcvad

# 添加 webrtcvad 的二进制文件
binaries = []
datas = []

# 收集 webrtcvad 模块
hiddenimports = ['webrtcvad']
