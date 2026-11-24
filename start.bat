@echo off
REM EarningsPulse launcher for Windows: double-click this file.
REM First run sets everything up (a few minutes); later runs start in seconds.
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title EarningsPulse

echo.
echo   EarningsPulse - Sentiment ^& health from every quarterly result
echo.

REM ---------------------------------------------------------------- 1. Python 3.10+
if not exist ".venv\Scripts\python.exe" (
  set "PY="
  where py >nul 2>nul && py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul && set "PY=py -3"
  if not defined PY (
    where python >nul 2>nul && python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul && set "PY=python"
  )
  if not defined PY (
    echo   Python 3.10 or newer was not found.
    echo   Install Python 3.12 from https://www.python.org/downloads/windows/
    echo   and tick "Add python.exe to PATH" in the installer, then run this file again.
    pause
    exit /b 1
  )
  echo   Creating a private Python environment in .venv ^(first run only^) ...
  !PY! -m venv .venv || (echo   Could not create the environment. & pause & exit /b 1)
)
set "PYV=.venv\Scripts\python.exe"

REM ---------------------------------------------------------------- 2. packages
if not exist ".venv\.finbert" (
  if defined EARNINGSPULSE_FINBERT (
    set "FB=%EARNINGSPULSE_FINBERT%"
  ) else (
    echo   FinBERT is an AI model that reads every sentence for tone ^(more accurate^).
    echo   It downloads about 600 MB once ^(PyTorch ~130 MB + the model 440 MB^).
    set /p "FB=  Include FinBERT? [Y/n] "
  )
  if /i "!FB:~0,1!"=="n" (echo no> ".venv\.finbert") else (echo yes> ".venv\.finbert")
)
set /p FINBERT=<".venv\.finbert"

if not exist ".venv\.installed" (
  echo.
  echo   [2/5] Installing app packages ^(~150 MB, usually 1-3 minutes^) ...
  "%PYV%" -m pip install --quiet --upgrade pip >nul 2>nul
  "%PYV%" -m pip install --disable-pip-version-check -r requirements.txt || (echo   Package install failed. & pause & exit /b 1)
  if /i "!FINBERT!"=="yes" (
    echo.
    echo   Installing PyTorch + transformers for FinBERT ^(~150 MB^) ...
    "%PYV%" -m pip install --disable-pip-version-check torch --index-url https://download.pytorch.org/whl/cpu || "%PYV%" -m pip install --disable-pip-version-check torch
    "%PYV%" -m pip install --disable-pip-version-check -r requirements-finbert.txt || echo   FinBERT could not be installed; dictionary scoring will be used.
  )
  echo done> ".venv\.installed"
)

REM ---------------------------------------------------------------- 3. FinBERT model (once)
if /i "!FINBERT!"=="yes" if not exist ".venv\.finbert-model" (
  echo.
  echo   [3/5] Downloading the FinBERT model ^(440 MB, one time; progress bars below^) ...
  set "HF_HUB_DISABLE_XET=1"
  "%PYV%" -c "from transformers import AutoModelForSequenceClassification as M, AutoTokenizer as T; T.from_pretrained('ProsusAI/finbert'); M.from_pretrained('ProsusAI/finbert')" && echo done> ".venv\.finbert-model"
  set "HF_HUB_DISABLE_XET="
)

REM ---------------------------------------------------------------- 4. SEC identity
if not defined SEC_USER_AGENT (
  findstr /b /c:"SEC_USER_AGENT=" .env >nul 2>nul || (
    echo.
    echo   The SEC asks apps that download filings for a name and e-mail. It is only sent to sec.gov.
    set "UA="
    set /p "UA=  Your name and e-mail (e.g. Jane Doe jane@example.com), or Enter to skip: "
    if defined UA echo SEC_USER_AGENT="!UA!">> .env
  )
)

REM ---------------------------------------------------------------- 5. launch
if not defined EARNINGSPULSE_PORT set "EARNINGSPULSE_PORT=8501"
set "URL=http://localhost:%EARNINGSPULSE_PORT%"
echo.
echo   [5/5] Starting the dashboard on %URL% ...
echo   The browser opens as soon as it is ready. Keep this window open; close it to stop the app.
echo.
REM Open the browser once the app answers (Streamlit runs headless, so it never shows its own e-mail prompt)
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "for($i=0;$i -lt 240;$i++){try{Invoke-WebRequest -UseBasicParsing '%URL%/_stcore/health' | Out-Null; Start-Process '%URL%'; Write-Host '  EarningsPulse is running at %URL%'; break}catch{Start-Sleep -Milliseconds 500}}"
"%PYV%" -m streamlit run app.py --server.port %EARNINGSPULSE_PORT% --server.headless true --browser.gatherUsageStats false --server.fileWatcherType none
pause
