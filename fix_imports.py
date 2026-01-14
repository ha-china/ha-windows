"""
批量替换相对导入为绝对导入
把所有 from .. 替换为 from src.
"""

import os
from pathlib import Path
import re

def fix_imports(file_path):
    """修复文件中的导入"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        original = content

        # 替换 from ..module import 为 from src.module import
        content = re.sub(r'from \.\.(\w+)', r'from src.\1', content)

        # 替换 from .module import（同目录）
        rel_path = file_path.relative_to('src')
        module_path = str(rel_path.parent).replace(os.sep, '.')

        if module_path and module_path != '.':
            content = re.sub(r'from \.(\w+)', f'from src.{module_path}.\\1', content)
        else:
            content = re.sub(r'from \.(\w+)', r'from src.\1', content)

        if content != original:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        return False
    except Exception as e:
        print(f"错误 {file_path}: {e}")
        return False

# 遍历所有 src 下的 .py 文件
src_path = Path('src')
count = 0

for py_file in src_path.rglob('*.py'):
    if fix_imports(py_file):
        print(f"OK: {py_file}")
        count += 1

print(f"\n修复了 {count} 个文件")
