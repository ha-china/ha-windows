"""
Home Assistant Windows 客户端主程序入口
作为包入口点，支持 python -m src 运行
"""

import sys
import os

# PyInstaller 打包后的路径设置
if getattr(sys, 'frozen', False):
    # PyInstaller 打包后的环境
    # _MEIPASS 是临时解压目录，src 已经在里面了
    # 需要把 src 目录添加到 sys.path 才能正确导入模块
    import os
    src_path = os.path.join(sys._MEIPASS, 'src')
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

from src.main import main

if __name__ == "__main__":
    main()
