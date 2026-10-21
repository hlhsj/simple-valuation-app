# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：单文件 exe，内嵌估值核心包与前端页面。

打包要点
    · pathex=['src'] 让分析器找到 stock_value_estimator，.py 会被收进 PYZ；
    · config 下的 JSON 是**数据文件**，分析器不会自动收，必须 datas 显式声明，
      且目标目录要与 `loader.py` 的 `Path(__file__).parent` 对齐，
      否则运行时报「配置文件缺失」；
    · web 目录同理（app.py 用 BASE/web 找首页）；
    · 不排除 email —— http.client 解析响应头依赖它，排掉会导致所有请求崩溃。
"""
from PyInstaller.utils.hooks import collect_submodules

a = Analysis(
    ['app.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('src/stock_value_estimator/config', 'stock_value_estimator/config'),
        ('data', 'data'),
        ('web', 'web'),
    ],
    hiddenimports=collect_submodules('stock_value_estimator'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'pytest', 'numpy', 'pandas', 'matplotlib', 'PIL'],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='估值助手',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
