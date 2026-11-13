param([switch]$Cpu)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$composeArgs = @('compose', '-f', (Join-Path $repoRoot 'docker-compose.yml'))
if (-not $Cpu) {
    $composeArgs += @('-f', (Join-Path $repoRoot 'docker-compose.gpu.yml'))
}
$diagnosticDir = Join-Path $repoRoot '.diagnostics'
New-Item -ItemType Directory -Force -Path $diagnosticDir | Out-Null
$fileName = 'attention-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + ([guid]::NewGuid().ToString('N').Substring(0,8)) + '.json'
$captureScript = Join-Path $PSScriptRoot 'diagnose_question.py'
$device = if ($Cpu) { 'cpu' } else { 'cuda' }

$running = & docker @composeArgs ps --status running -q backend
if ($LASTEXITCODE -ne 0) { throw 'Cannot access Docker Compose. Start Docker Desktop first.' }

$diagnosticExit = 1
$restartFailed = $false
try {
    if ($running) {
        Write-Host 'Pausing the backend while the diagnostic uses its GPU/model memory.'
        & docker @composeArgs stop backend
        if ($LASTEXITCODE -ne 0) { throw 'Could not stop the backend.' }
    }
    Write-Host 'Running one question against indexed attention.pdf. This uses your configured Groq key and tokens.'
    & docker @composeArgs run --rm --no-deps -T `
        --volume "${captureScript}:/tmp/diagnose_question.py:ro" `
        --volume "${diagnosticDir}:/diagnostics" `
        -e PYTHONPATH=/app -e "RERANKER_DEVICE=$device" -e "EMBEDDING_DEVICE=$device" `
        --entrypoint python backend /tmp/diagnose_question.py `
        --output "/diagnostics/$fileName"
    $diagnosticExit = $LASTEXITCODE
}
finally {
    if ($running) {
        Write-Host 'Restarting the backend. Allow time for model warmup.'
        & docker @composeArgs start backend
        $restartFailed = $LASTEXITCODE -ne 0
    }
    $artifactPath = Join-Path $diagnosticDir $fileName
    if (Test-Path -LiteralPath $artifactPath) {
        Write-Host "Diagnostic file: $artifactPath"
        Write-Host 'This file contains document excerpts and model replies. Share this JSON for diagnosis.'
    }
}
if ($restartFailed) { throw 'Backend restart failed. Run docker compose -f docker-compose.yml start backend.' }
if ($diagnosticExit -ne 0) { throw 'The diagnostic encountered an error. If a JSON file was created, it contains the partial capture.' }
