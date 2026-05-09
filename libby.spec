# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 6.x spec — builds a single-file Windows exe.
# Run from the project root:  pyinstaller libby.spec

a = Analysis(
    ['launcher.py'],
    # Make backend modules importable as top-level during analysis
    pathex=['backend'],
    binaries=[],
    datas=[
        # Bundle the entire frontend — served at runtime via Flask routes
        ('frontend/public', 'frontend/public'),
        ('frontend/src',    'frontend/src'),
    ],
    hiddenimports=[
        # Flask stack
        'flask',
        'flask.templating',
        'werkzeug',
        'werkzeug.routing',
        'werkzeug.exceptions',
        'werkzeug.serving',
        'jinja2',
        'jinja2.ext',
        'click',
        'itsdangerous',
        'markupsafe',
        # EPUB parsing
        'ebooklib',
        'ebooklib.epub',
        'ebooklib.plugins',
        'ebooklib.plugins.base',
        'ebooklib.utils',
        'lxml',
        'lxml.etree',
        'lxml._elementpath',
        'lxml.html',
        # Image processing
        'PIL',
        'PIL.Image',
        'PIL.ImageFile',
        'PIL.JpegImagePlugin',
        'PIL.PngImagePlugin',
        'PIL.WebPImagePlugin',
        # Device detection
        'psutil',
        'psutil._pswindows',
        # Config
        'dotenv',
        # Folder picker
        'tkinter',
        'tkinter.filedialog',
        'tkinter.ttk',
        # WSGI server
        'waitress',
        'waitress.server',
        'waitress.task',
        'waitress.channel',
        'waitress.buffers',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='Libby',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # console=False — no terminal window; stdout/stderr are redirected to
    # libby.log next to the exe by launcher.py so errors are still capturable.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
