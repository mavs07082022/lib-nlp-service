@echo off
echo ========================================
echo 📚 Library NLP Search Service
echo ========================================
cd /d "%~dp0"

echo Installing/Updating dependencies...
pip install -r requirements.txt

echo.
echo Starting NLP Service...
echo This window will show the service logs.
echo To run in background, use start_nlp.bat instead.
echo ========================================
echo.
python app.py

pause