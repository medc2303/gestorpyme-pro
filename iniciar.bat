@echo off
chcp 65001 >nul
title GestorPyME Pro - Lanzador MVP (Streamlit sin SQL)
cd /d "%~dp0"

echo ============================================================================
echo   INICIANDO GESTORPYME PRO - SISTEMA DE INVENTARIO, VENTAS Y CADUCIDAD
echo ============================================================================
echo.

set "PY_CMD="

if exist ".venv\Scripts\python.exe" (
    set "PY_CMD=.venv\Scripts\python.exe"
)

if not defined PY_CMD (
    where python >nul 2>&1
    if %errorlevel%==0 set "PY_CMD=python"
)

if not defined PY_CMD (
    where py >nul 2>&1
    if %errorlevel%==0 set "PY_CMD=py -3"
)

if not defined PY_CMD (
    echo [ERROR] No se encontro Python instalado en este equipo.
    pause
    exit /b 1
)

echo [1/2] Verificando librerias (Streamlit + Requests)...
"%PY_CMD%" -c "import streamlit, requests" >nul 2>&1
if errorlevel 1 (
    echo       Instalando dependencias necesarias...
    if not exist ".venv\Scripts\python.exe" (
        "%PY_CMD%" -m venv .venv
        set "PY_CMD=.venv\Scripts\python.exe"
    )
    "%PY_CMD%" -m pip install --disable-pip-version-check -r requirements.txt
)

echo [2/2] Abriendo aplicacion web en el navegador...
echo.
"%PY_CMD%" -m streamlit run app.py
pause
