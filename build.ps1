# Build DriveUNCConverter into a runnable Windows EXE with PyInstaller.
#
# Interactive:
#   .\build.ps1
#
# Non-interactive (skip menu):
#   .\build.ps1 -Mode 1
#   .\build.ps1 -Mode 2 -Clean
#   .\build.ps1 -Mode 1 -Icon assets\app.ico -SkipInstall

[CmdletBinding()]
param(
    [ValidateSet("", "1", "2", "3", "4", "5", "q", "Q")]
    [string]$Mode = "",

    [switch]$Clean,
    [switch]$SkipInstall,
    [string]$Icon = "",
    [string]$Name = "DriveUNCConverter"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Info {
    param([string]$Message)
    Write-Host $Message -ForegroundColor DarkGray
}

function Get-PythonCommand {
    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }

    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        return $pythonCmd.Source
    }

    throw "Python not found. Create .venv or install Python and ensure it is on PATH."
}

function Assert-FileExists {
    param([string]$Path, [string]$Hint)
    if (-not (Test-Path $Path)) {
        throw "$Hint Not found: $Path"
    }
}

function Resolve-IconPath {
    param([string]$IconInput)

    if ([string]::IsNullOrWhiteSpace($IconInput)) {
        return ""
    }

    $iconPath = if ([System.IO.Path]::IsPathRooted($IconInput)) {
        $IconInput
    }
    else {
        Join-Path $ProjectRoot $IconInput
    }

    Assert-FileExists -Path $iconPath -Hint "Icon file missing."
    return $iconPath
}

function Show-Menu {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Yellow
    Write-Host "  DriveUNCConverter Build Menu" -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  1) Single-file EXE (onefile)          [Recommended]"
    Write-Host "  2) Directory package (onedir)        [Faster startup]"
    Write-Host "  3) Single-file EXE + clean old build"
    Write-Host "  4) Directory package + clean old build"
    Write-Host "  5) Custom options (ask each step)"
    Write-Host "  Q) Quit"
    Write-Host ""
}

function Read-YesNo {
    param(
        [string]$Prompt,
        [bool]$Default = $false
    )

    $suffix = if ($Default) { "[Y/n]" } else { "[y/N]" }
    while ($true) {
        $answer = Read-Host "$Prompt $suffix"
        if ([string]::IsNullOrWhiteSpace($answer)) {
            return $Default
        }
        switch ($answer.Trim().ToLowerInvariant()) {
            "y" { return $true }
            "yes" { return $true }
            "n" { return $false }
            "no" { return $false }
            default { Write-Host "Please enter Y or N." -ForegroundColor DarkYellow }
        }
    }
}

function Get-BuildOptionsFromMode {
    param([string]$SelectedMode)

    $options = [ordered]@{
        Onedir      = $false
        Clean       = $false
        SkipInstall = $false
        Icon        = ""
        Name        = $Name
    }

    switch ($SelectedMode.ToUpperInvariant()) {
        "1" {
            $options.Onedir = $false
            $options.Clean = $false
        }
        "2" {
            $options.Onedir = $true
            $options.Clean = $false
        }
        "3" {
            $options.Onedir = $false
            $options.Clean = $true
        }
        "4" {
            $options.Onedir = $true
            $options.Clean = $true
        }
        "5" {
            Write-Host ""
            Write-Host "Custom options" -ForegroundColor Cyan

            $packageChoice = ""
            while ($packageChoice -notin @("1", "2")) {
                Write-Host "  Package type:"
                Write-Host "    1) Single-file EXE (onefile)"
                Write-Host "    2) Directory package (onedir)"
                $packageChoice = (Read-Host "  Choose [1/2]").Trim()
            }
            $options.Onedir = ($packageChoice -eq "2")

            $options.Clean = Read-YesNo -Prompt "  Clean old build/dist/*.spec first?" -Default $true
            $options.SkipInstall = -not (Read-YesNo -Prompt "  Install/update dependencies from requirements.txt?" -Default $true)

            $useIcon = Read-YesNo -Prompt "  Use a custom .ico icon?" -Default $false
            if ($useIcon) {
                $iconInput = Read-Host "  Icon path (e.g. assets\app.ico)"
                $options.Icon = Resolve-IconPath -IconInput $iconInput
            }

            $customName = Read-Host "  Output name [$Name]"
            if (-not [string]::IsNullOrWhiteSpace($customName)) {
                $options.Name = $customName.Trim()
            }
        }
        default {
            throw "Unknown mode: $SelectedMode"
        }
    }

    return $options
}

function Invoke-Build {
    param(
        [bool]$Onedir,
        [bool]$CleanBuild,
        [bool]$SkipInstallDeps,
        [string]$IconPath,
        [string]$AppName
    )

    Assert-FileExists -Path (Join-Path $ProjectRoot "main.py") -Hint "Project entry point missing."
    Assert-FileExists -Path (Join-Path $ProjectRoot "requirements.txt") -Hint "Dependency list missing."

    $Python = Get-PythonCommand
    Write-Step "Using Python: $Python"
    & $Python --version

    Write-Host ""
    Write-Host "Selected options:" -ForegroundColor Cyan
    Write-Host ("  Mode          : {0}" -f ($(if ($Onedir) { "onedir" } else { "onefile" })))
    Write-Host ("  Clean         : {0}" -f $CleanBuild)
    Write-Host ("  Install deps  : {0}" -f (-not $SkipInstallDeps))
    Write-Host ("  Name          : {0}" -f $AppName)
    Write-Host ("  Icon          : {0}" -f ($(if ($IconPath) { $IconPath } else { "(none)" })))

    if ($CleanBuild) {
        Write-Step "Cleaning previous build outputs"
        foreach ($item in @("build", "dist", "$AppName.spec")) {
            $path = Join-Path $ProjectRoot $item
            if (Test-Path $path) {
                Remove-Item -LiteralPath $path -Recurse -Force
                Write-Host "Removed $item"
            }
        }
    }

    if (-not $SkipInstallDeps) {
        Write-Step "Installing dependencies"
        & $Python -m pip install --upgrade pip
        if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed with exit code $LASTEXITCODE" }

        & $Python -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
        if ($LASTEXITCODE -ne 0) { throw "pip install failed with exit code $LASTEXITCODE" }
    }
    else {
        Write-Step "Skipping dependency installation"
    }

    Write-Step "Verifying importable modules"
    & $Python -c "import customtkinter, win32api, PyInstaller; print('dependencies ok')"
    if ($LASTEXITCODE -ne 0) { throw "Dependency verification failed with exit code $LASTEXITCODE" }

    $pyInstallerArgs = @(
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name", $AppName,
        "--collect-all", "customtkinter",
        "--hidden-import", "win32timezone"
    )

    if ($Onedir) {
        $pyInstallerArgs += "--onedir"
        Write-Step "Building directory package (onedir)"
    }
    else {
        $pyInstallerArgs += "--onefile"
        Write-Step "Building single-file EXE (onefile)"
    }

    if ($IconPath) {
        $pyInstallerArgs += @("--icon", $IconPath)
        Write-Host "Using icon: $IconPath"
    }

    $pyInstallerArgs += (Join-Path $ProjectRoot "main.py")

    Write-Step "Running PyInstaller"
    & $Python -m PyInstaller @pyInstallerArgs
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

    if ($Onedir) {
        $output = Join-Path $ProjectRoot "dist\$AppName\$AppName.exe"
    }
    else {
        $output = Join-Path $ProjectRoot "dist\$AppName.exe"
    }

    if (-not (Test-Path $output)) {
        throw "Build finished but output was not found: $output"
    }

    Write-Step "Build succeeded"
    Write-Host "Output: $output" -ForegroundColor Green
    Write-Host ""
    Write-Host "Run it with:"
    Write-Host "  & `"$output`""
}

# ---- entry ----

$hasCliMode = -not [string]::IsNullOrWhiteSpace($Mode)
$selectedMode = $Mode

if (-not $hasCliMode) {
    Show-Menu
    while ($true) {
        $selectedMode = (Read-Host "Select an option").Trim()
        if ($selectedMode -in @("1", "2", "3", "4", "5", "q", "Q")) {
            break
        }
        Write-Host "Invalid choice. Enter 1-5 or Q." -ForegroundColor DarkYellow
    }
}

if ($selectedMode -in @("q", "Q")) {
    Write-Host "Cancelled."
    exit 0
}

# If user passed switches without -Mode, still honor them after selecting menu.
$options = Get-BuildOptionsFromMode -SelectedMode $selectedMode

if ($hasCliMode) {
    # CLI switches override defaults from mode presets.
    if ($Clean) { $options.Clean = $true }
    if ($SkipInstall) { $options.SkipInstall = $true }
    if ($Icon) { $options.Icon = Resolve-IconPath -IconInput $Icon }
    if ($Name -and $Name -ne "DriveUNCConverter") { $options.Name = $Name }
}
else {
    # Interactive presets can still accept pre-supplied -Icon / -SkipInstall / -Clean.
    if ($Clean) { $options.Clean = $true }
    if ($SkipInstall) { $options.SkipInstall = $true }
    if ($Icon) { $options.Icon = Resolve-IconPath -IconInput $Icon }
}

if ($options.Icon -and -not [System.IO.Path]::IsPathRooted($options.Icon)) {
    $options.Icon = Resolve-IconPath -IconInput $options.Icon
}

try {
    Invoke-Build `
        -Onedir:$options.Onedir `
        -CleanBuild:$options.Clean `
        -SkipInstallDeps:$options.SkipInstall `
        -IconPath $options.Icon `
        -AppName $options.Name
}
catch {
    Write-Host ""
    Write-Host "Build failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
