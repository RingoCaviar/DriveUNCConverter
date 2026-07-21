# DriveUNCConverter 编译脚本（Windows PowerShell / ANSI）
#
# 默认中文：.\build.ps1
# 无交互编译：.\build.ps1 -Mode 1 -SkipInstall
# 保留编译缓存：.\build.ps1 -Mode 1 -KeepCache

[CmdletBinding()]
param(
    [ValidateSet("", "1", "2", "3", "4", "5", "q", "Q")]
    [string]$Mode = "",

    [switch]$Clean,
    [switch]$SkipInstall,
    [switch]$KeepCache,
    [string]$Icon = "",
    [string]$Name = "DriveUNCConverter"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$L = @{
        MenuTitle = "DriveUNCConverter 编译菜单"
        Mode1 = "单文件 EXE（推荐）"
        Mode2 = "目录版（启动更快）"
        Mode3 = "清理旧产物后编译单文件 EXE"
        Mode4 = "清理旧产物后编译目录版"
        Mode5 = "自定义选项"
        Quit = "退出"
        Choose = "请选择"
        Invalid = "输入无效，请输入 1-5 或 Q。"
        Package = "输出类型"
        OneFile = "单文件 EXE"
        OneDir = "目录版"
        CleanPrompt = "编译前清理该名称的旧产物？"
        InstallPrompt = "安装/更新 requirements.txt 中的依赖？"
        CachePrompt = "编译完成后保留 build 和 spec 缓存？"
        IconPrompt = "使用自定义 .ico 图标？"
        IconPath = "图标路径"
        NamePrompt = "输出名称"
        UsingPython = "使用 Python"
        Selected = "当前选项"
        CleaningOld = "正在清理旧产物"
        Installing = "正在安装依赖"
        SkipInstalling = "已跳过依赖安装"
        Verifying = "正在验证依赖"
        BuildingOne = "正在编译单文件 EXE"
        BuildingDir = "正在编译目录版"
        Running = "正在运行 PyInstaller"
        CleaningCache = "正在删除编译缓存"
        CacheRemoved = "已删除本次编译产生的 build 缓存和 spec 文件"
        CacheKept = "已保留编译缓存"
        Success = "编译成功"
        Output = "编译结果"
        RunWith = "运行命令"
        Failed = "编译失败"
        Cancelled = "已取消"
        Missing = "文件不存在"
}

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Ask-YesNo([string]$Prompt, [bool]$Default = $false) {
    $suffix = if ($Default) { "[Y/n]" } else { "[y/N]" }
    while ($true) {
        $answer = Read-Host "$Prompt $suffix"
        if ([string]::IsNullOrWhiteSpace($answer)) { return $Default }
        switch ($answer.Trim().ToLowerInvariant()) {
            "y" { return $true }
            "yes" { return $true }
            "n" { return $false }
            "no" { return $false }
        }
    }
}

function Initialize-VirtualEnvironment {
    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython) { return $venvPython }

    Write-Step "$($L.Installing): .venv"
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        & $pyLauncher.Source -3 -m venv (Join-Path $ProjectRoot ".venv")
    } else {
        $command = Get-Command python -ErrorAction SilentlyContinue
        if (-not $command) { throw "$($L.Missing): Python 3" }
        & $command.Source -m venv (Join-Path $ProjectRoot ".venv")
    }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPython)) {
        throw "$($L.Failed): .venv ($LASTEXITCODE)"
    }
    return $venvPython
}

function Resolve-Icon([string]$InputPath) {
    if ([string]::IsNullOrWhiteSpace($InputPath)) { return "" }
    $path = if ([IO.Path]::IsPathRooted($InputPath)) { $InputPath } else { Join-Path $ProjectRoot $InputPath }
    if (-not (Test-Path -LiteralPath $path)) { throw "$($L.Missing): $path" }
    return (Resolve-Path -LiteralPath $path).Path
}

function Remove-SelectedOutput([string]$AppName, [bool]$IncludeDist) {
    $targets = @(
        (Join-Path $ProjectRoot "build\$AppName"),
        (Join-Path $ProjectRoot "$AppName.spec")
    )
    if ($IncludeDist) {
        $targets += (Join-Path $ProjectRoot "dist\$AppName.exe")
        $targets += (Join-Path $ProjectRoot "dist\$AppName")
    }
    foreach ($target in $targets) {
        if (Test-Path -LiteralPath $target) {
            Remove-Item -LiteralPath $target -Recurse -Force
        }
    }
}

function Show-Menu {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Yellow
    Write-Host "  $($L.MenuTitle)" -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Yellow
    Write-Host "  1) $($L.Mode1)"
    Write-Host "  2) $($L.Mode2)"
    Write-Host "  3) $($L.Mode3)"
    Write-Host "  4) $($L.Mode4)"
    Write-Host "  5) $($L.Mode5)"
    Write-Host "  Q) $($L.Quit)"
    Write-Host ""
}

$selectedMode = $Mode
if ([string]::IsNullOrWhiteSpace($selectedMode)) {
    Show-Menu
    while ($true) {
        $selectedMode = (Read-Host "$($L.Choose) [1-5/Q]").Trim()
        if ($selectedMode -in @("1", "2", "3", "4", "5", "q", "Q")) { break }
        Write-Host $L.Invalid -ForegroundColor DarkYellow
    }
}
if ($selectedMode -in @("q", "Q")) {
    Write-Host $L.Cancelled
    exit 0
}

$Onedir = $selectedMode -in @("2", "4")
$CleanOld = $Clean -or $selectedMode -in @("3", "4")
$InstallDeps = -not $SkipInstall
$KeepBuildCache = [bool]$KeepCache
$AppName = $Name
$IconPath = Resolve-Icon $Icon

if ($selectedMode -eq "5") {
    Write-Host ""
    Write-Host "$($L.Package): 1) $($L.OneFile)  2) $($L.OneDir)"
    $packageChoice = ""
    while ($packageChoice -notin @("1", "2")) { $packageChoice = (Read-Host "$($L.Choose) [1/2]").Trim() }
    $Onedir = $packageChoice -eq "2"
    $CleanOld = Ask-YesNo $L.CleanPrompt $true
    $InstallDeps = Ask-YesNo $L.InstallPrompt $true
    $KeepBuildCache = Ask-YesNo $L.CachePrompt $false
    if (Ask-YesNo $L.IconPrompt $false) { $IconPath = Resolve-Icon (Read-Host $L.IconPath) }
    $customName = Read-Host "$($L.NamePrompt) [$Name]"
    if (-not [string]::IsNullOrWhiteSpace($customName)) { $AppName = $customName.Trim() }
}

try {
    foreach ($required in @("main.py", "requirements.txt")) {
        $requiredPath = Join-Path $ProjectRoot $required
        if (-not (Test-Path -LiteralPath $requiredPath)) { throw "$($L.Missing): $requiredPath" }
    }

    $Python = Initialize-VirtualEnvironment
    Write-Step "$($L.UsingPython): $Python"
    & $Python --version

    Write-Host ""
    Write-Host "$($L.Selected):" -ForegroundColor Cyan
    Write-Host "  $($L.Package): $(if ($Onedir) { $L.OneDir } else { $L.OneFile })"
    Write-Host "  $($L.NamePrompt): $AppName"
    Write-Host "  Cache: $(if ($KeepBuildCache) { 'Keep' } else { 'Auto cleanup' })"

    if ($CleanOld) {
        Write-Step $L.CleaningOld
        Remove-SelectedOutput $AppName $true
    }

    if ($InstallDeps) {
        Write-Step $L.Installing
        & $Python -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
        if ($LASTEXITCODE -ne 0) { throw "pip failed: $LASTEXITCODE" }
    } else {
        Write-Step $L.SkipInstalling
    }

    Write-Step $L.Verifying
    & $Python -c "import customtkinter, win32api, PyInstaller; print('dependencies ok')"
    if ($LASTEXITCODE -ne 0) { throw "dependency check failed: $LASTEXITCODE" }

    $PyInstallerArgs = @(
        "--noconfirm", "--clean", "--windowed", "--name", $AppName,
        "--collect-all", "customtkinter", "--hidden-import", "win32timezone"
    )
    if ($Onedir) {
        $PyInstallerArgs += "--onedir"
        Write-Step $L.BuildingDir
    } else {
        $PyInstallerArgs += "--onefile"
        Write-Step $L.BuildingOne
    }
    if ($IconPath) { $PyInstallerArgs += @("--icon", $IconPath) }
    $PyInstallerArgs += (Join-Path $ProjectRoot "main.py")

    Write-Step $L.Running
    & $Python -m PyInstaller @PyInstallerArgs
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed: $LASTEXITCODE" }

    $output = if ($Onedir) {
        Join-Path $ProjectRoot "dist\$AppName\$AppName.exe"
    } else {
        Join-Path $ProjectRoot "dist\$AppName.exe"
    }
    if (-not (Test-Path -LiteralPath $output)) { throw "$($L.Missing): $output" }

    if ($KeepBuildCache) {
        Write-Step $L.CacheKept
    } else {
        Write-Step $L.CleaningCache
        Remove-SelectedOutput $AppName $false
        Write-Host $L.CacheRemoved -ForegroundColor DarkGray
    }

    Write-Step $L.Success
    Write-Host "$($L.Output): $output" -ForegroundColor Green
    Write-Host "$($L.RunWith): & `"$output`""
}
catch {
    Write-Host ""
    Write-Host "$($L.Failed): $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
