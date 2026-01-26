# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for directory mode (one-dir)
# Used for creating installer packages
# Goal: Small exe file with all dependencies in directory
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs

# Collect data files from packages (all dependencies)
datas = []
datas += collect_data_files('customtkinter', include_py_files=False)
datas += collect_data_files('aioesphomeapi', include_py_files=False)
datas += collect_data_files('pymicro_wakeword', include_py_files=False)
datas += collect_data_files('soundcard', include_py_files=False)
datas += collect_data_files('pygame', include_py_files=False)
datas += collect_data_files('vlc', include_py_files=False)
datas += collect_data_files('webrtcvad', include_py_files=False)
datas += collect_data_files('zeroconf', include_py_files=False)
datas += collect_data_files('ifaddr', include_py_files=False)
datas += collect_data_files('pydantic', include_py_files=False)
datas += collect_data_files('pydantic_core', include_py_files=False)
datas += collect_data_files('attrs', include_py_files=False)
datas += collect_data_files('comtypes', include_py_files=False)
datas += collect_data_files('PIL', include_py_files=False)
datas += collect_data_files('pystray', include_py_files=False)
datas += collect_data_files('win10toast', include_py_files=False)
datas += collect_data_files('windows_toasts', include_py_files=False)

# Add source files
datas += [('src', 'src')]

# Collect binaries (all DLLs and libraries)
binaries = []
binaries += collect_dynamic_libs('customtkinter')
binaries += collect_dynamic_libs('aioesphomeapi')
binaries += collect_dynamic_libs('pymicro_wakeword')
binaries += collect_dynamic_libs('soundcard')
binaries += collect_dynamic_libs('pygame')
binaries += collect_dynamic_libs('vlc')
binaries += collect_dynamic_libs('webrtcvad')
binaries += collect_dynamic_libs('zeroconf')
binaries += collect_dynamic_libs('ifaddr')
binaries += collect_dynamic_libs('pydantic')
binaries += collect_dynamic_libs('pydantic_core')
binaries += collect_dynamic_libs('attrs')
binaries += collect_dynamic_libs('comtypes')
binaries += collect_dynamic_libs('PIL')
binaries += collect_dynamic_libs('pystray')

# Hidden imports (all necessary modules)
hiddenimports = [
    # Core dependencies
    'customtkinter',
    'aioesphomeapi',
    'soundcard',
    'pygame',
    'vlc',
    'numpy',
    'psutil',
    'win10toast',
    'pymicro_wakeword',
    'webrtcvad',
    'zeroconf',
    'pycaw',
    'PIL',
    'pystray',
    'windows_toasts',
    # Zeroconf modules
    'zeroconf._dns',
    'zeroconf._services',
    'zeroconf._services.info',
    'zeroconf._services.types',
    'zeroconf._cache',
    'zeroconf._core',
    'zeroconf._handlers',
    'zeroconf._protocol',
    'zeroconf._logger',
    'zeroconf._utils',
    'zeroconf._updates',
    'zeroconf._engine',
    'zeroconf._listener',
    'zeroconf._record',
    'zeroconf._transport',
    'zeroconf._resolver',
    'zeroconf._browser',
    'zeroconf._registration',
    'zeroconf._exceptions',
    'zeroconf._const',
    'zeroconf._asyncio',
    'ifaddr',
    # Async and networking
    'asyncio',
    'aiohttp',
    'aiohttp.client',
    'aiohttp.connector',
    'aiohttp.streams',
    'aiohttp.web',
    'aiohttp.http',
    'aiohttp.http_parser',
    'aiohttp.helpers',
    'aiohttp.formdata',
    'aiohttp.multipart',
    'aiohttp.hdrs',
    'aiohttp.log',
    'aiohttp.payload',
    'aiohttp.payload_stream',
    'aiohttp.tcp_helpers',
    'aiohttp.locks',
    'aiohttp.resolver',
    'aiohttp.tracing',
    'aiohttp.web_exceptions',
    'aiohttp.web_fileresponse',
    'aiohttp.web_middlewares',
    'aiohttp.web_protocol',
    'aiohttp.web_request',
    'aiohttp.web_response',
    'aiohttp.web_runner',
    'aiohttp.web_server',
    'aiohttp.web_urldispatcher',
    'aiohttp.web_ws',
    'yarl',
    'yarl._url',
    'yarl._quoting',
    'yarl._quoting_py',
    'yarl._path',
    'yarl._query',
    'multidict',
    'multidict._multidict',
    'multidict._abc',
    'attr',
    'attrs',
    'idna',
    'idna.core',
    'idna.idnadata',
    'idna.intranges',
    'idna.package_data',
    'idna.uts46data',
    # Pydantic
    'pydantic',
    'pydantic.fields',
    'pydantic.main',
    'pydantic.validators',
    'pydantic.parse',
    'pydantic.json',
    'pydantic.utils',
    'pydantic.typing',
    'pydantic.version',
    'pydantic.errors',
    'pydantic.exceptions',
    'pydantic.types',
    'pydantic.dataclasses',
    'pydantic.functional_validators',
    'pydantic.annotated_handlers',
    'pydantic._internal',
    'pydantic_core',
    'pydantic_core.core_schema',
    'pydantic_core.core_utils',
    'pydantic_core.types',
    'pydantic_core.validators',
    'pydantic_core._pydantic_core',
    'annotated_types',
    # COM types
    'comtypes',
    'comtypes.client',
    'comtypes.client._generate',
    'comtypes.client._events',
    'comtypes.client.dynamic',
    'comtypes.client.lazybind',
    'comtypes.client.wrap',
    'comtypes.automation',
    'comtypes.connectionpoints',
    'comtypes.errorinfo',
    'comtypes.gen',
    'comtypes.hresult',
    'comtypes.persist',
    'comtypes.server',
    'comtypes.server.automation',
    'comtypes.server.connectionpoints',
    'comtypes.server.register',
    'comtypes.server.stdmethods',
    'comtypes.typeinfo',
    'comtypes.util',
    # PIL
    'PIL',
    'PIL.Image',
    'PIL.ImageTk',
    'PIL.ImageDraw',
    'PIL.ImageFont',
    'PIL.ImageFilter',
    'PIL.ImageEnhance',
    'PIL.ImageOps',
    'PIL.ImageColor',
    'PIL.ImageSequence',
    'PIL.ImageCms',
    'PIL.ImagePalette',
    'PIL.ImageMode',
    'PIL.ImageStat',
    'PIL.ImageWin',
    # Pystray
    'pystray',
    'pystray._util',
    'pystray._base',
    'pystray._win32',
    'pystray.icons',
    # Win10toast
    'win10toast',
    'win10toast.toast',
    'win10toast.toastWindows',
    # Windows toasts
    'windows_toasts',
    'windows_toasts.windows_toasts',
    'windows_toasts.interop',
    'windows_toasts.audios',
    'windows_toasts.events',
    'windows_toasts.adapters',
    'windows_toasts.sources',
    # PyCaw
    'pycaw',
    'pycaw.pycaw',
    'pycaw.utils',
    'pycaw.constants',
    # Standard library modules
    'ipaddress',
    'socket',
    'selectors',
    'typing',
    'dataclasses',
    'weakref',
    'threading',
    'queue',
    'time',
    'random',
    'hashlib',
    'base64',
    'struct',
    'json',
    're',
    'collections',
    'collections.abc',
    'contextlib',
    'functools',
    'itertools',
    'operator',
    'copy',
    'pickle',
    'uuid',
    'datetime',
    'decimal',
    'fractions',
    'enum',
    'inspect',
    'importlib',
    'importlib.abc',
    'importlib.util',
    'importlib.machinery',
    'pathlib',
    'os',
    'sys',
    'io',
    'warnings',
    'traceback',
    'logging',
    'logging.handlers',
    'logging.config',
    'abc',
    'types',
    'typing_extensions',
    'typing_inspect',
    # src modules
    'src.i18n',
    'src.core.mdns_discovery',
    'src.core.esphome_protocol',
    'src.ui.system_tray_icon',
    'src.voice.audio_recorder',
    'src.voice.mpv_player',
    'src.voice.wake_word',
    'src.voice.vad',
    'src.voice.voice_assistant',
    'src.commands.command_executor',
    'src.commands.system_commands',
    'src.commands.media_commands',
    'src.commands.audio_commands',
    'src.sensors.windows_monitor',
    'src.notify.announcement',
    'src.notify.toast_notification',
    'src.notify.service_entity',
    'src.ui.main_window',
    'src.autostart',
]

# Collect all submodules to ensure nothing is missing
hiddenimports += collect_submodules('customtkinter')
hiddenimports += collect_submodules('aioesphomeapi')
hiddenimports += collect_submodules('pymicro_wakeword')
hiddenimports += collect_submodules('soundcard')
hiddenimports += collect_submodules('pygame')
hiddenimports += collect_submodules('vlc')
hiddenimports += collect_submodules('webrtcvad')
hiddenimports += collect_submodules('zeroconf')
hiddenimports += collect_submodules('ifaddr')
hiddenimports += collect_submodules('pydantic')
hiddenimports += collect_submodules('pydantic_core')
hiddenimports += collect_submodules('attrs')
hiddenimports += collect_submodules('comtypes')
hiddenimports += collect_submodules('PIL')
hiddenimports += collect_submodules('pystray')
hiddenimports += collect_submodules('win10toast')
hiddenimports += collect_submodules('windows_toasts')
hiddenimports += collect_submodules('aiohttp')
hiddenimports += collect_submodules('yarl')
hiddenimports += collect_submodules('multidict')
hiddenimports += collect_submodules('idna')
hiddenimports += collect_submodules('pycaw')

a = Analysis(
    ['src\\__main__.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'pandas', 'scipy', 'pytest', 'tkinter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# EXE configuration - exclude binaries to keep exe small
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # CRITICAL: This keeps binaries separate
    name='HomeAssistantWindows',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # Enable UPX compression
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version_info.txt',
    icon=['src\\logo.ico'],
)

# Collect all files into directory
coll = COLLECT(
    exe,
    a.binaries,  # All DLLs and libraries go here
    a.datas,     # All data files go here
    strip=False,
    upx=True,    # Enable UPX compression for binaries
    upx_exclude=[],
    name='HomeAssistantWindows',
)