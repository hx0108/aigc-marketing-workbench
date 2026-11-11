param([ValidateSet('api','worker','migrate','budget-check')][string]$Action='api')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$env:PYTHONPATH=(Join-Path $projectRoot 'apps/api')+';'+(Join-Path $projectRoot 'apps/worker')
if (-not $env:DATABASE_URL) {
    $configPath=Join-Path $projectRoot '.env'
    if (-not (Test-Path -LiteralPath $configPath)) { throw 'Create .env with POSTGRES_PASSWORD first.' }
    $passwordLine=Get-Content -LiteralPath $configPath | Where-Object { $_ -match '^POSTGRES_PASSWORD=' } | Select-Object -First 1
    if (-not $passwordLine) { throw 'POSTGRES_PASSWORD is missing.' }
    $dbPassword=$passwordLine.Substring('POSTGRES_PASSWORD='.Length)
    if (-not $dbPassword) { throw 'POSTGRES_PASSWORD is empty.' }
    $env:DATABASE_URL='postgresql+psycopg://aigc:'+([Uri]::EscapeDataString($dbPassword))+'@127.0.0.1:54329/aigc'
}
$env:AIGC_STORAGE_ROOT=Join-Path $projectRoot 'runtime/storage'
switch ($Action) {
    'api' { python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log }
    'worker' { python -m marketing_worker }
    'migrate' { python -m app.migrate }
    'budget-check' { $env:TEST_DATABASE_URL=$env:DATABASE_URL; python scripts/verify_postgres_budget.py }
}
exit $LASTEXITCODE
