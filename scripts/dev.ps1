param(
    [ValidateSet("test", "run", "build", "store", "publish", "dry-run")]
    [string]$Task = "test"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DefaultVenv = "C:\Users\danil\Documents\Codex\2026-10-28\in\work\novoacesso-build\venv\Scripts\python.exe"
$LocalVenv = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Python = if (Test-Path $LocalVenv) { $LocalVenv } elseif (Test-Path $DefaultVenv) { $DefaultVenv } else { "python" }

Push-Location $RepoRoot
try {
    switch ($Task) {
        "test" {
            $env:QT_QPA_PLATFORM = "offscreen"
            $env:NOVOACESSO_OFFLINE = "1"
            $env:DESK_AUTOREADY = "0"
            $env:PYTHONPATH = Join-Path $RepoRoot "src"
            & $Python -m pytest tests -q --disable-warnings
        }
        "run" {
            $env:PYTHONPATH = Join-Path $RepoRoot "src"
            & $Python (Join-Path $RepoRoot "iniciar.py")
        }
        "build" {
            & $Python (Join-Path $RepoRoot "scripts\publish_release.py") --skip-tests --dry-run
        }
        "store" {
            & $Python (Join-Path $RepoRoot "scripts\build_store_msix.py") --build
        }
        "dry-run" {
            & $Python (Join-Path $RepoRoot "scripts\publish_release.py") --dry-run
        }
        "publish" {
            & $Python (Join-Path $RepoRoot "scripts\publish_release.py") --publish
        }
    }
} finally {
    Pop-Location
}
