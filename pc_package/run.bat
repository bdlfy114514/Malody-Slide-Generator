@echo off
rem ============================================================
rem  Malody Slide 生成器 - PC 版启动脚本
rem  直接双击本文件即可运行。出错时窗口会停住，方便看报错。
rem ============================================================

rem 切到本文件所在目录，避免从别处运行时找不到相对路径
cd /d "%~dp0"

rem 让控制台与 Python 都用 UTF-8，避免中文提示变乱码
chcp 65001 >nul 2>&1
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

set "PYEXE="
where python >nul 2>&1 && set "PYEXE=python"
if not defined PYEXE (
    where py >nul 2>&1 && set "PYEXE=py"
)

if not defined PYEXE (
    echo.
    echo  [错误] 没有找到 Python。
    echo.
    echo  请先安装 Python 3.8 或更高版本：https://www.python.org/downloads/
    echo  安装时务必勾选 "Add Python to PATH"，装完后重新运行本脚本。
    echo.
    pause
    exit /b 1
)

if not exist "slide_core.py" (
    echo.
    echo  [错误] 找不到 slide_core.py。
    echo  它必须和 slide_generator_v1_2.py 放在同一个文件夹里，
    echo  请不要把主程序单独拷出去。
    echo.
    pause
    exit /b 1
)

"%PYEXE%" slide_generator_v1_2.py
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo.
    echo  [程序异常退出，错误码 %RC%]
    echo  上面就是报错信息，可以截图反馈。
    echo.
    pause
)
exit /b %RC%
