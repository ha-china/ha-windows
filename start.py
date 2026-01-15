"""
Home Assistant Windows 客户端启动脚本
解决 Python 模块导入路径问题
"""

import sys
import os

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入并运行主程序
if __name__ == "__main__":
    from src.main import main
    main()