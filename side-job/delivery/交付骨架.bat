# 交付骨架.bat —— 给不懂技术的客户用的「一键运行」
# 客户双击这个就行，不用知道 Python 是什么。
#
# 使用前改两件事：
#   1. SCRIPT 改成你的主脚本名
#   2. 让客户把要处理的 Excel 拖到这个 bat 上（拖放会把文件路径变成 %1）

@echo off
chcp 65001 >nul
cd /d "%~dp0"

set SCRIPT=process_excel.py
set PY=C:\Users\pc\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe

echo ============================================
echo   数据处理工具
echo ============================================
echo.

if "%~1"=="" (
    echo 请把要处理的 Excel 文件，拖到本程序图标上。
    echo.
    pause
    exit /b
)

echo 正在处理：%~nx1
echo.

"%PY%" "%SCRIPT%" "%~1" -o "%~dpn1_已处理.xlsx"

if errorlevel 1 (
    echo.
    echo [出错了] 请把上面的提示截图发给我。
) else (
    echo.
    echo [完成] 结果文件：%~dpn1_已处理.xlsx
)

echo.
pause
