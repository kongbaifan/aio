param(
  [switch]$Docker,
  [switch]$WithNode
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

if ($Docker) {
  Write-Host "启动 Docker Compose 本地 Harness..."
  docker compose -f (Join-Path $projectRoot "compose.yaml") up --build
  exit $LASTEXITCODE
}

$sandboxDir = Join-Path $projectRoot "apps\sandbox-lite"
$harnessDir = Join-Path $projectRoot "apps\local-harness"
$sharedPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pythonPath = if (Test-Path $sharedPython) { $sharedPython } else { (Get-Command python -ErrorAction Stop).Path }
$startedProcesses = [System.Collections.Generic.List[System.Diagnostics.Process]]::new()

# 等待服务就绪，避免 Harness 比 Sandbox 更早启动导致首次健康检查失败。
function Wait-Endpoint([string]$Url, [string]$Name, [System.Diagnostics.Process]$Process) {
  for ($attempt = 0; $attempt -lt 40; $attempt++) {
    if ($Process.HasExited) {
      throw "$Name 启动失败，进程已退出。"
    }
    try {
      $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 1
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
        return
      }
    } catch {
      # 服务尚未监听，继续短暂重试。
    }
    Start-Sleep -Milliseconds 250
  }
  throw "$Name 在等待时间内没有就绪：$Url"
}

try {
  if (-not $env:SANDBOX_HOST) { $env:SANDBOX_HOST = "127.0.0.1" }
  if (-not $env:SANDBOX_PORT) { $env:SANDBOX_PORT = "8081" }
  if (-not $env:SANDBOX_URL) { $env:SANDBOX_URL = "http://${env:SANDBOX_HOST}:$($env:SANDBOX_PORT)" }
  if (-not $env:SANDBOX_TOKEN) { $env:SANDBOX_TOKEN = "local-dev-sandbox" }
  if (-not $env:HARNESS_HOST) { $env:HARNESS_HOST = "127.0.0.1" }
  if (-not $env:HARNESS_PORT) { $env:HARNESS_PORT = "8080" }
  # 环境文件优先级：已设置的 HARNESS_ENV_FILE > 项目根 .env
  # 模型目录固定为项目 config/models.json（可用 HARNESS_MODELS_JSON 覆盖路径，不读取 ~/.pi）
  if (-not $env:HARNESS_ENV_FILE) {
    $projectEnv = Join-Path $projectRoot ".env"
    if (Test-Path $projectEnv) {
      $env:HARNESS_ENV_FILE = $projectEnv
    }
  }

  Write-Host "启动 Sandbox Lite..."
  $sandboxProcess = Start-Process -FilePath $pythonPath -ArgumentList @("start.py") -WorkingDirectory $sandboxDir -PassThru -WindowStyle Hidden
  $startedProcesses.Add($sandboxProcess)
  Wait-Endpoint "$($env:SANDBOX_URL)/v1/healthz" "Sandbox Lite" $sandboxProcess

  if ($WithNode) {
    $nodePath = (Get-Command node -ErrorAction Stop).Path
    $nodeDir = Join-Path $projectRoot "services\node-repl"
    if (-not (Test-Path (Join-Path $nodeDir "node_modules"))) {
      throw "Node REPL 依赖未安装，请先在 services\node-repl 执行 npm install。"
    }
    $env:NODE_REPL_URL = "http://127.0.0.1:8092"
    Write-Host "启动 Node REPL..."
    $nodeProcess = Start-Process -FilePath $nodePath -ArgumentList @("server.js") -WorkingDirectory $nodeDir -PassThru -WindowStyle Hidden
    $startedProcesses.Add($nodeProcess)
    Wait-Endpoint "http://127.0.0.1:8092/health" "Node REPL" $nodeProcess
  }

  Write-Host "启动 Local Harness，访问 http://127.0.0.1:$($env:HARNESS_PORT)"
  & $pythonPath (Join-Path $harnessDir "run.py")
  $harnessExitCode = $LASTEXITCODE
} finally {
  foreach ($process in $startedProcesses) {
    if (-not $process.HasExited) {
      Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
  }
}

if ($null -ne $harnessExitCode) { exit $harnessExitCode }
