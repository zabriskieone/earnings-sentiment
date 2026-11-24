# PyInstaller recipe for the EarningsPulse engine (run from the repository root):
#   pyinstaller packaging/engine.spec --distpath engine-dist --workpath build/engine --noconfirm
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

SRC = os.path.abspath(os.path.join(SPECPATH, "..", "src"))  # SPECPATH = folder of this file
sys.path.insert(0, SRC)

datas = []
datas += collect_data_files("pysentiment2")          # Loughran-McDonald word lists
datas += collect_data_files("plotly")                # chart templates + plotly.js for offline HTML reports
datas += collect_data_files("earnings_sentiment")

hiddenimports = []
hiddenimports += collect_submodules("uvicorn")       # uvicorn picks protocol/loop modules at run time
hiddenimports += collect_submodules("earnings_sentiment")
hiddenimports += ["plotly.validators", "onnxruntime", "tokenizers"]

a = Analysis(
    [os.path.join(SPECPATH, "engine_main.py")],
    pathex=[SRC],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["torch", "transformers", "streamlit", "pyarrow", "fastparquet", "scipy", "sqlalchemy", "openpyxl", "numba", "tkinter", "IPython", "pytest", "notebook",
              "matplotlib.backends.backend_qtagg", "matplotlib.backends.backend_tkagg", "PyQt5", "PySide6"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="earningspulse-engine", console=True,
          upx=False, strip=False, codesign_identity=None)
coll = COLLECT(exe, a.binaries, a.datas, name="earningspulse-engine", upx=False, strip=False)
