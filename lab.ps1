<#
  Windows runner -- the equivalent of `make <target>` for students without make.

  Works in Windows PowerShell 5.1 (powershell.exe) and PowerShell 7+ (pwsh).

      .\lab.ps1                 # list targets
      .\lab.ps1 probe
      .\lab.ps1 setup
      .\lab.ps1 bench
      .\lab.ps1 serve           # leave running, open a second window for the rest
      .\lab.ps1 load-50
      .\lab.ps1 verify

  Every target maps 1:1 to the make target of the same name, so GUIDE.md applies
  as written -- just substitute `.\lab.ps1 x` for `make x`.
#>
param(
    [Parameter(Position = 0)] [string] $Target = "help",
    [Parameter(ValueFromRemainingArguments = $true)] [string[]] $Rest
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$env:HF_HOME = Join-Path $PSScriptRoot '.hf_cache'
$env:HUGGINGFACE_HUB_CACHE = Join-Path $PSScriptRoot '.hf_cache'
$env:PIP_CACHE_DIR = Join-Path $PSScriptRoot '.pip_cache'

function Get-SysPython {
    if (Test-Path "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe") {
        return "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
    }
    if (Test-Path "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe") {
        return "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe"
    }
    if (Get-Command 'py' -ErrorAction SilentlyContinue) {
        return 'py'
    }
    return 'python'
}

function Get-VenvPython {
    $c1 = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    $c2 = Join-Path $PSScriptRoot '.venv\bin\python.exe'
    if (Test-Path $c1) { return $c1 }
    if (Test-Path $c2) { return $c2 }
    return $null
}

function Need-Venv {
    $vpy = Get-VenvPython
    if (-not $vpy) {
        Write-Host "ERROR: no virtualenv found at .venv\" -ForegroundColor Red
        Write-Host "Run this first:  .\lab.ps1 setup"
        exit 1
    }
    return $vpy
}

function Py {
    $vpy = Need-Venv
    & $vpy @args
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

function Locust {
    $vpy = Need-Venv
    & $vpy -m locust @args
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

function Run-SysPy {
    param([string[]]$PyArgs)
    $sysPy = Get-SysPython
    if ($sysPy -eq 'py') {
        & py -3.12 @PyArgs
    } else {
        & $sysPy @PyArgs
    }
}

$Port = if ($env:LAB_SERVER_PORT) { $env:LAB_SERVER_PORT } else { '8080' }

switch ($Target) {
    'help' {
        Write-Host ""
        Write-Host "Day 20 lab -- Windows runner" -ForegroundColor Cyan
        Write-Host "Usage:  .\lab.ps1 <target>"
        Write-Host ""
        Write-Host "Setup (00)"
        Write-Host "  probe          Probe hardware -> hardware.json"
        Write-Host "  setup          Install deps + llama.cpp runtime + Gemma 4 E2B"
        Write-Host "  runtime        Re-fetch just the llama.cpp binaries"
        Write-Host ""
        Write-Host "Measure (01)"
        Write-Host "  bench          TTFT / TPOT / percentiles, both quantizations"
        Write-Host "  tune           Thread sweep -> your before/after speedup"
        Write-Host ""
        Write-Host "Serve (02)"
        Write-Host "  serve          Start llama-server on :8080 (leave running)"
        Write-Host "  serve-embed    Embedding server on :8081 (bonus C9)"
        Write-Host "  smoke          Prove the API + non-zero /metrics"
        Write-Host "  load-10        Load test, 10 users, 60s"
        Write-Host "  load-50        Load test, 50 users, 60s"
        Write-Host "  metrics        Sample /metrics 60s (run WHILE load-50 runs)"
        Write-Host "  load-report    Saturation reading from both load runs"
        Write-Host ""
        Write-Host "Integrate (03)"
        Write-Host "  pipeline       RAG pipeline -> llama-server"
        Write-Host ""
        Write-Host "Submission"
        Write-Host "  verify         Check submission readiness"
        Write-Host ""
        Write-Host "Bonus"
        Write-Host "  sweep-quant | sweep-ctx | sweep-batch | sweep-gpu"
        Write-Host "  compare-builds | build-llama | semantic-cache-offline | embed-demo-offline"
        Write-Host ""
        Write-Host "Housekeeping"
        Write-Host "  clean          Remove generated reports"
        Write-Host "  clean-all      Also remove venv, runtime, models, hardware.json"
        Write-Host ""
        Write-Host "You need 3 windows for the 50-user step: serve / load-50 / metrics." -ForegroundColor Yellow
        Write-Host ""
    }

    'probe'   { Run-SysPy @('labs\00-setup\detect-hardware.py') }
    'setup'   {
        $vpy = Get-VenvPython
        if (-not $vpy) {
            Write-Host "==> Creating virtual environment (.venv)..." -ForegroundColor Cyan
            $sys = Get-SysPython
            if ($sys -eq 'py') {
                & py -3.12 -m venv (Join-Path $PSScriptRoot '.venv')
            } else {
                & $sys -m venv (Join-Path $PSScriptRoot '.venv')
            }
            $vpy = Get-VenvPython
        }
        if (-not $vpy) {
            Write-Host "ERROR: Failed to create virtual environment." -ForegroundColor Red
            exit 1
        }
        Write-Host "==> Upgrading pip and installing requirements..." -ForegroundColor Cyan
        & $vpy -m pip install --upgrade pip wheel
        & $vpy -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
        Write-Host "==> Running setup script (downloading runtime and model)..." -ForegroundColor Cyan
        & $vpy (Join-Path $PSScriptRoot 'labs\00-setup\setup.py')
    }
    'runtime' { Py labs\00-setup\fetch-runtime.py --force }

    'bench'   { Py labs\01-measure\benchmark.py }
    'tune'    { Py labs\01-measure\tune.py @Rest }

    'serve'       { Py labs\02-serve\serve.py @Rest }
    'serve-embed' { Py labs\02-serve\serve.py --embedding @Rest }
    'smoke'       { Py labs\02-serve\smoke-test.py }
    'load-10'     { Locust -f labs\02-serve\load-test.py --headless -u 10 -r 5 -t 1m --host http://localhost:$Port --csv benchmarks\locust-10 --csv-full-history }
    'load-50'     { Locust -f labs\02-serve\load-test.py --headless -u 50 -r 25 -t 1m --host http://localhost:$Port --csv benchmarks\locust-50 --csv-full-history }
    'metrics'     { Py labs\02-serve\record-metrics.py --duration 60 --label u50 }
    'load-report' { Py labs\02-serve\load-report.py }

    'pipeline' { Py labs\03-integrate\pipeline.py @Rest }

    # verify must work with system Python too: the grader has no .venv.
    'verify' { Run-SysPy @('scripts\verify.py'); exit $LASTEXITCODE }

    'sweep-quant' { Py bonus\sweeps\quant-sweep.py @Rest }
    'sweep-ctx'   { Py bonus\sweeps\ctx-len-sweep.py @Rest }
    'sweep-batch' { Py bonus\sweeps\batch-size-sweep.py @Rest }
    'sweep-gpu'   { Py bonus\sweeps\gpu-offload-sweep.py @Rest }
    'compare-builds' { Py bonus\compare-builds.py @Rest }
    'embed-demo'             { Py bonus\serving-regimes\embedding-serving.py @Rest }
    'embed-demo-offline'     { Py bonus\serving-regimes\embedding-serving.py --offline }
    'semantic-cache'         { Py bonus\serving-regimes\semantic-cache-demo.py @Rest }
    'semantic-cache-offline' { Py bonus\serving-regimes\semantic-cache-demo.py --offline --sweep }

    'build-llama' {
        foreach ($t in 'cmake', 'git') {
            if (-not (Get-Command $t -ErrorAction SilentlyContinue)) {
                Write-Host "ERROR: $t not found. Install Visual Studio Build Tools + cmake + git." -ForegroundColor Red
                exit 1
            }
        }
        $build = & $VenvPy -c "import sys;sys.path.insert(0,'lib');import labkit;print(labkit.LLAMA_CPP_BUILD)"
        if (-not (Test-Path 'bonus\llama.cpp')) {
            git clone --depth 1 --branch $build https://github.com/ggml-org/llama.cpp bonus\llama.cpp
        }
        $flags = if ($env:LLAMA_CMAKE_FLAGS) { $env:LLAMA_CMAKE_FLAGS -split ' ' } else { @() }
        cmake -B bonus\llama.cpp\build -S bonus\llama.cpp @flags -DGGML_NATIVE=ON -DCMAKE_BUILD_TYPE=Release
        cmake --build bonus\llama.cpp\build -j --config Release
        Write-Host ""
        Write-Host "Built. Now compare it against the prebuilt binary:  .\lab.ps1 compare-builds"
    }

    'clean' {
        Remove-Item -ErrorAction SilentlyContinue benchmarks\01-*.md, benchmarks\01-*.json,
            benchmarks\02-*.md, benchmarks\02-*.json, benchmarks\02-*.csv,
            benchmarks\03-*.md, benchmarks\03-*.json,
            benchmarks\locust-*.csv, benchmarks\bonus-*.md, benchmarks\bonus-*.json
        Write-Host "Cleaned generated reports. Kept hardware.json, models\, runtime\, submission\."
    }

    'clean-all' {
        Remove-Item -ErrorAction SilentlyContinue benchmarks\01-*.md, benchmarks\01-*.json,
            benchmarks\02-*.md, benchmarks\02-*.json, benchmarks\02-*.csv,
            benchmarks\03-*.md, benchmarks\03-*.json,
            benchmarks\locust-*.csv, benchmarks\bonus-*.md, benchmarks\bonus-*.json
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue .venv, runtime, models,
            bonus\llama.cpp, hardware.json
        Write-Host "Removed venv, runtime, models and hardware.json. Re-run: .\lab.ps1 setup"
    }

    default {
        Write-Host "Unknown target: $Target" -ForegroundColor Red
        Write-Host "Run  .\lab.ps1  with no arguments to list targets."
        exit 1
    }
}
