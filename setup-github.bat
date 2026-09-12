@echo off
chcp 65001
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-github.ps1" %*
