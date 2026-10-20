@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================
echo   估值助手 · 重新打包
echo ============================================
echo.

where pyinstaller >nul 2>nul
if %errorlevel%==0 (
    echo 使用 PATH 中的 PyInstaller
    pyinstaller --noconfirm --clean build.spec
    goto done
)

where python >nul 2>nul
if %errorlevel%==0 (
    echo 使用 python -m PyInstaller
    python -m PyInstaller --noconfirm --clean build.spec
    goto done
)

echo [错误] 未找到 Python 或 PyInstaller。
echo.
echo 请先安装：
echo   python -m pip install pyinstaller
echo.
pause
exit /b 1

:done
echo.
if exist "dist\估值助手.exe" (
    echo 打包完成：dist\估值助手.exe
    for %%A in ("dist\估值助手.exe") do echo 文件大小：%%~zA 字节
) else (
    echo 打包失败，请查看上方日志。
)
echo.
pause
