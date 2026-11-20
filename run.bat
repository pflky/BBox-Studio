@echo off
cd /d "%~dp0"
py -3 bbox_studio.py
if errorlevel 1 pause