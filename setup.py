"""
PyInstaller 打包配置
用于将 Home Assistant Windows 客户端打包成单个 exe 文件
"""

import os
import sys
import io

# 设置标准输出为 UTF-8 编码（修复 Windows 编码问题）
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from PyInstaller.__main__ import run

# 项目信息
APP_NAME = "HomeAssistantWindows"
APP_VERSION = "0.1.0"
APP_AUTHOR = "老王"
APP_DESCRIPTION = "零配置 Home Assistant Windows 原生客户端"

# 主程序入口（使用 __main__.py，这样相对导入才能正常工作）
MAIN_SCRIPT = "src/__main__.py"

# 如果主程序不存在，创建一个临时的
if not os.path.exists(MAIN_SCRIPT):
    print(f"警告: {MAIN_SCRIPT} 不存在，请先创建主程序")
    sys.exit(1)


def build_exe():
    """
    使用 PyInstaller 打包成单个 exe 文件
    """
    # PyInstaller 参数
    pyinstaller_args = [
        MAIN_SCRIPT,
        "--onefile",  # 打包成单个 exe 文件
        "--windowed",  # 无控制台窗口（使用 GUI）
        "--name=" + APP_NAME,  # exe 文件名
        "--icon=assets/icon.ico" if os.path.exists("assets/icon.ico") else "",
        f"--version-file=version_info.txt" if os.path.exists("version_info.txt") else "",
        "--clean",  # 清理临时文件
        "--noconfirm",  # 覆盖输出目录而不询问
        "--distpath=dist",  # 输出目录
        "--workpath=build",  # 构建目录
        "--additional-hooks-dir=hooks",  # 自定义 hooks 目录（修复 webrtcvad 问题）
        # 隐藏导入（这些模块可能无法自动检测）
        "--hidden-import=customtkinter",
        "--hidden-import=aioesphomeapi",
        "--hidden-import=soundcard",
        "--hidden-import=mpv",
        "--hidden-import=numpy",
        "--hidden-import=psutil",
        "--hidden-import=win10toast",
        "--hidden-import=pymicro_wakeword",
        "--hidden-import=webrtcvad",
        "--hidden-import=zeroconf",
        "--hidden-import=pycaw",
        "--hidden-import=PIL",
        "--hidden-import=pystray",
        # src 模块隐藏导入（重要！）
        "--hidden-import=i18n",
        "--hidden-import=core.mdns_discovery",
        "--hidden-import=core.esphome_server",
        "--hidden-import=ui.system_tray_icon",
        "--hidden-import=voice.audio_recorder",
        "--hidden-import=voice.mpv_player",
        "--hidden-import=voice.wake_word",
        "--hidden-import=voice.vad",
        "--hidden-import=voice.voice_assistant",
        "--hidden-import=commands.command_executor",
        "--hidden-import=commands.system_commands",
        "--hidden-import=commands.media_commands",
        "--hidden-import=commands.audio_commands",
        "--hidden-import=sensors.windows_monitor",
        "--hidden-import=sensors.esphome_sensors",
        "--hidden-import=notify.announcement",
        "--hidden-import=ui.main_window",
        "--hidden-import=ui.system_tray",
        # 收集所有子模块
        "--collect-all=customtkinter",
        "--collect-all=aioesphomeapi",
        # 添加 src 目录到 Python 路径
        "--add-data=src;src",
        # 排除不需要的模块（减小体积）
        "--exclude-module=matplotlib",
        "--exclude-module=pandas",
        "--exclude-module=scipy",
        "--exclude-module=pytest",
    ]

    # 过滤空参数
    pyinstaller_args = [arg for arg in pyinstaller_args if arg]

    print(f"开始打包 {APP_NAME} v{APP_VERSION}...")
    print(f"PyInstaller 参数: {' '.join(pyinstaller_args)}")

    # 运行 PyInstaller
    run(pyinstaller_args)

    print(f"\n打包完成！")
    print(f"输出文件: dist/{APP_NAME}.exe")


def create_version_info():
    """
    创建版本信息文件（可选）
    用于 Windows exe 的版本信息
    """
    version_info_content = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({APP_VERSION.replace('.', ',')}, 0),
    prodvers=({APP_VERSION.replace('.', ',')}, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'{APP_AUTHOR}'),
        StringStruct(u'FileDescription', u'{APP_DESCRIPTION}'),
        StringStruct(u'FileVersion', u'{APP_VERSION}'),
        StringStruct(u'InternalName', u'{APP_NAME}'),
        StringStruct(u'LegalCopyright', u'Copyright © 2024'),
        StringStruct(u'OriginalFilename', u'{APP_NAME}.exe'),
        StringStruct(u'ProductName', u'{APP_NAME}'),
        StringStruct(u'ProductVersion', u'{APP_VERSION}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""

    with open("version_info.txt", "w", encoding="utf-8") as f:
        f.write(version_info_content)

    print("版本信息文件已创建: version_info.txt")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Home Assistant Windows 客户端打包脚本")
    parser.add_argument(
        "--version-info",
        action="store_true",
        help="创建版本信息文件",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="构建 exe 文件",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="执行所有步骤（创建版本信息 + 构建）",
    )

    args = parser.parse_args()

    if args.version_info or args.all:
        create_version_info()

    if args.build or args.all:
        build_exe()

    if not any([args.version_info, args.build, args.all]):
        # 默认执行构建
        parser.print_help()
        print("\n未指定参数，执行默认构建...")
        build_exe()


if __name__ == "__main__":
    main()
