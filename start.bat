@echo off
cd /d "%~dp0"
echo Starting NotebookLM Manager on http://localhost:7860 ...
python -m uvicorn server:app --host 0.0.0.0 --port 7860 --reload
