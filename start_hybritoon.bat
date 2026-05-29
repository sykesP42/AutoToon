@echo off
chcp 65001 >nul
title HybriToon - 一键启动

echo ========================================
echo   HybriToon - AI 实时风格化工具
echo ========================================
echo.

:: 检查 Python 环境
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

:: 检查依赖
echo [1/3] 检查依赖...
cd /d "%~dp0Studio"
python -c "import dearpygui" 2>nul
if %errorlevel% neq 0 (
    echo [提示] 正在安装依赖...
    pip install -r requirements.txt
)

:: 查找 ONNX 模型
set "MODEL_PATH="
if exist "%~dp0training\mooatoon_model.onnx" (
    set "MODEL_PATH=%~dp0training\mooatoon_model.onnx"
)

:: 启动 HybriToon Studio
echo [2/3] 启动 HybriToon Studio...
if defined MODEL_PATH (
    start "HybriToon Studio" python main.py --model "%MODEL_PATH%"
) else (
    echo [提示] 未找到 ONNX 模型，将以无模型模式启动
    start "HybriToon Studio" python main.py
)

:: 提示 UE5
echo [3/3] 请手动打开 UE5 项目
echo.
echo   UE5 项目路径提示：
echo   D:\unreal\MooaToon-Engine-5.5_MooaToonProject\
echo.
echo   插件会自动在 127.0.0.1:8080 启动 HTTP 服务
echo.
echo ========================================
echo   启动完成！请切换到 HybriToon Studio 窗口
echo ========================================
pause
