@echo off
title Multiagent Router PRO Server
cd /d D:\OmniRoute-Agent

echo ===================================================
echo   Multiagent Router PRO is starting...
echo   Web UI will open in your browser shortly.
echo   DO NOT CLOSE THIS WINDOW while using the UI!
echo ===================================================
echo.

:: Запускаем таймер в фоновом потоке, который подождет 3 секунды и откроет браузер
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:8000"

:: Запускаем сервер (консоль будет показывать логи синхронно с браузером)
python api_server.py

:: Если сервер остановился или упал, не закрываем окно сразу, чтобы прочитать ошибку
echo.
echo Server has stopped. Press any key to exit...
pause >nul