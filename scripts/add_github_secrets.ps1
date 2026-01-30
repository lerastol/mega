# Добавить секреты Yandex (и при необходимости OpenAI) в репозиторий GitHub.
# Запуск: из корня проекта (d:\itmo\mega) выполните:
#   .\scripts\add_github_secrets.ps1
# или из любой папки:
#   powershell -NoProfile -ExecutionPolicy Bypass -File "d:\itmo\mega\scripts\add_github_secrets.ps1"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path (Join-Path $ProjectRoot ".env"))) {
    Write-Error "Файл .env не найден в $ProjectRoot. Заполните .env (GITHUB_TOKEN, YANDEX_API_KEY, YANDEX_FOLDER_ID) и запустите снова."
    exit 1
}
Set-Location $ProjectRoot
python scripts/setup_github_repo.py
exit $LASTEXITCODE
