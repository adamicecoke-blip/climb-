# PyInstaller recipe: `pyinstaller packaging/clipforge.spec` from the repo root.
# Put ffmpeg + ffprobe binaries in packaging/ffmpeg/ first to ship them inside the app
# (the GitHub workflow does this for each platform).
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = Path(SPECPATH).parent
ICONS = ROOT / "clipforge" / "static" / "icons"
FFMPEG = ROOT / "packaging" / "ffmpeg"

datas = [
    (str(ROOT / "clipforge" / "static"), "clipforge/static"),
    (str(ROOT / "clipforge" / "fonts"), "clipforge/fonts"),
]
datas += collect_data_files("faster_whisper")  # voice-activity model
datas += collect_data_files("cv2")              # face detector
datas += collect_data_files("certifi")
binaries = collect_dynamic_libs("ctranslate2") + collect_dynamic_libs("onnxruntime")
if FFMPEG.is_dir():
    binaries += [(str(p), "ffmpeg") for p in FFMPEG.iterdir() if p.is_file()]

hidden = collect_submodules("uvicorn") + collect_submodules("clipforge") + ["webview"]

a = Analysis(
    [str(ROOT / "packaging" / "clipforge_app.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    excludes=["tkinter", "matplotlib", "torch", "pytest", "pandas", "scipy", "IPython"],
)
pyz = PYZ(a.pure)

icon = None
if sys.platform == "win32":
    icon = str(ROOT / "packaging" / "icon.ico")
elif sys.platform == "darwin":
    icon = str(ROOT / "packaging" / "icon.icns")

exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ClipForge",
          console=False, icon=icon if icon and Path(icon).exists() else None)
coll = COLLECT(exe, a.binaries, a.datas, name="ClipForge")

if sys.platform == "darwin":
    app = BUNDLE(coll, name="ClipForge.app", icon=icon if Path(icon).exists() else None,
                 bundle_identifier="app.clipforge.desktop",
                 info_plist={"NSHighResolutionCapable": True, "CFBundleShortVersionString": "0.3.0"})
