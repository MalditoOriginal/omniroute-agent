# setup.ps1 - Автоматическая настройка OmniRoute + Aider для Windows 11
Write-Host "🚀 Настройка мультиагентной системы..." -ForegroundColor Cyan

# 1. Проверка Node.js
try {
    $nodeVersion = node --version
    Write-Host "[✓] Node.js установлен: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "[X] Node.js не найден! Скачайте с https://nodejs.org и установите." -ForegroundColor Red
    exit
}

# 2. Установка OmniRoute
Write-Host "Установка OmniRoute..." -ForegroundColor Cyan
npm install -g omniroute

# 3. Запуск OmniRoute
Write-Host "Запуск дашборда OmniRoute..." -ForegroundColor Cyan
Start-Process omniroute
Start-Sleep -Seconds 5 # Ждем запуска

Write-Host "==================================================" -ForegroundColor Yellow
Write-Host "ВНИМАНИЕ:" -ForegroundColor Yellow
Write-Host "1. Откройте дашборд OmniRoute (http://localhost:20128)"
Write-Host "2. Создайте 4 Combo: TerminalAgent, CodingAgent, MediaAgent, RouterAgent"
Write-Host "3. Перейдите в Settings -> API Keys и скопируйте ваш ключ"
Write-Host "==================================================" -ForegroundColor Yellow

# 4. Ввод API ключа
 $apiKey = Read-Host "Введите ваш API ключ из OmniRoute дашборда"

# 5. Настройка переменных окружения
Write-Host "Настройка переменных окружения..." -ForegroundColor Cyan
[System.Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $apiKey, 'User')
[System.Environment]::SetEnvironmentVariable('OPENAI_API_BASE', 'http://localhost:20128/v1', 'User')

# Применяем для текущей сессии
 $env:OPENAI_API_KEY = $apiKey
 $env:OPENAI_API_BASE = 'http://localhost:20128/v1'

# 6. Установка Python-зависимостей
Write-Host "Установка Python-зависимостей..." -ForegroundColor Cyan
pip install -r requirements.txt

Write-Host "==================================================" -ForegroundColor Green
Write-Host "✅ Настройка завершена!" -ForegroundColor Green
Write-Host "ПЕРЕЗАПУСТИТЕ этот терминал, чтобы переменные окружения вступили в силу." -ForegroundColor Yellow
Write-Host "Затем запустите систему командой: python multiagent_router_pro.py" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green