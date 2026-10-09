@echo off
setlocal
uv run --project "%~dp0.." --locked --no-sync douyin-transcript %*
exit /b %errorlevel%
