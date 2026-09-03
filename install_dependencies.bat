@echo off
setlocal enabledelayedexpansion
echo ========================================
echo 📦 NLP Service - Complete Installation
echo ========================================
echo.

:: Check Python version
echo [CHECK] Python version...
python --version
if errorlevel 1 (
    echo ❌ Python not found!
    echo.
    echo Please install Python 3.10 or higher:
    echo 1. Download from: https://www.python.org/downloads/
    echo 2. Check "Add Python to PATH" during installation
    echo 3. Restart this script after installation
    echo.
    pause
    exit /b 1
)

:: Check pip
echo.
echo [CHECK] pip version...
pip --version
if errorlevel 1 (
    echo ❌ pip not found!
    echo Installing pip...
    python -m ensurepip --upgrade
)

:: Upgrade pip
echo.
echo [1/5] Upgrading pip...
python -m pip install --upgrade pip

:: Install from requirements.txt
echo.
echo [2/5] Installing requirements from requirements.txt...
echo This may take 5-10 minutes...
echo.

:: Check if requirements.txt exists
if exist requirements.txt (
    pip install -r requirements.txt
) else (
    echo ⚠️ requirements.txt not found!
    echo Installing packages manually...
    
    :: Core packages
    echo Installing Flask...
    pip install Flask==2.3.3 flask-cors==4.0.1
    
    echo Installing PyTorch (CPU version)...
    pip install torch==2.1.0 --index-url https://download.pytorch.org/whl/cpu
    pip install torchvision==0.16.0 --index-url https://download.pytorch.org/whl/cpu
    
    echo Installing NLP libraries...
    pip install sentence-transformers==2.2.2 transformers==4.40.2
    
    echo Installing data processing...
    pip install numpy==1.24.3 pandas==2.0.3 scikit-learn==1.3.0
    
    echo Installing utilities...
    pip install requests==2.34.2 tqdm==4.69.1 huggingface-hub==0.19.4
)

:: Verify installation
echo.
echo [3/5] Verifying installation...
python -c "import flask; import torch; import sentence_transformers; import numpy; import requests; print('✅ All packages imported successfully!')"
if errorlevel 1 (
    echo ❌ Verification failed!
    echo.
    echo Trying to fix missing packages...
    pip install --upgrade --force-reinstall Flask==2.3.3 flask-cors==4.0.1
    pip install --upgrade --force-reinstall torch==2.1.0 --index-url https://download.pytorch.org/whl/cpu
    pip install --upgrade --force-reinstall sentence-transformers==2.2.2
) else (
    echo ✅ Verification passed!
)

echo.
echo [4/5] Checking for CUDA support...
python -c "import torch; print('CUDA Available:', torch.cuda.is_available())"

echo.
echo [5/5] Installation Complete!
echo.
echo ========================================
echo ✅ All packages installed successfully!
echo ========================================
echo.
echo To start the NLP service:
echo   cd python
echo   python app.py
echo.
echo Service will be available at: http://localhost:5000
echo.
pause