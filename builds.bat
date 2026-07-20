@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================
echo   USB Redirector - 单文件构建脚本
echo ============================================
echo.

set "PROJECT_DIR=%~dp0"
set "OUT_DIR=%PROJECT_DIR%out"
set "BUILD_DIR=%PROJECT_DIR%build_temp"

cd /d "%PROJECT_DIR%"

:: ========== 检查 PyInstaller ==========
echo [1/3] 检查 PyInstaller...
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo   PyInstaller 未安装，正在安装...
    pip install pyinstaller
    if errorlevel 1 (
        echo   错误: PyInstaller 安装失败
        exit /b 1
    )
)
echo   已就绪

:: ========== 清理旧输出 ==========
echo.
echo [2/3] 清理旧输出目录...
if exist "%OUT_DIR%" (
    rmdir /s /q "%OUT_DIR%" 2>nul
)
if exist "%BUILD_DIR%" (
    rmdir /s /q "%BUILD_DIR%" 2>nul
)
echo   已清理

:: ========== PyInstaller 单文件打包 ==========
echo.
echo [3/3] 打包单文件...

pyinstaller ^
    --onefile ^
    --windowed ^
    --name "USBRedirector" ^
    --add-data "%PROJECT_DIR%etd;etd" ^
    --add-data "%PROJECT_DIR%usb;usb" ^
    --add-data "%PROJECT_DIR%config.ini;." ^
    --add-data "%PROJECT_DIR%icon.png;." ^
    --icon "%PROJECT_DIR%icon.ico" ^
    --manifest "%PROJECT_DIR%app.manifest" ^
    --distpath "%OUT_DIR%" ^
    --workpath "%BUILD_DIR%" ^
    --specpath "%BUILD_DIR%" ^
    "%PROJECT_DIR%main.py"

if errorlevel 1 (
    echo   错误: 打包失败
    exit /b 1
)
echo   打包完成

:: ========== 清理临时文件 ==========
echo.
echo 清理临时文件...
if exist "%BUILD_DIR%" (
    rmdir /s /q "%BUILD_DIR%" 2>nul
)
echo   已清理

:: ========== 完成 ==========
echo.
echo ============================================
echo   构建成功!
echo.
echo   输出: %OUT_DIR%\USBRedirector.exe
echo ============================================

endlocal
