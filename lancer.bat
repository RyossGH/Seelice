@echo off
cd /d "%~dp0"
title CamHub
where python >nul 2>nul || (echo [!] Python introuvable : installe-le depuis python.org en cochant "Add to PATH". & pause & exit /b)
where ffmpeg >nul 2>nul || echo [!] ffmpeg introuvable : installe-le avec la commande   winget install Gyan.FFmpeg   puis relance ce fichier.
python -m pip install -q -r requirements.txt
python app.py
pause
