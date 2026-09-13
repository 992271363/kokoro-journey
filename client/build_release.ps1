# Kokoro Journey 发布打包脚本
# Nuitka standalone 双 exe（主程序无控制台 + 日志控制台）+ 时间戳发布目录
# 用法: powershell -ExecutionPolicy Bypass -File build_release.ps1 [-SkipBuild]
param(
    [string]$Python = "E:\program\ANACONDA\envs\bishe\python.exe",
    [string]$OutputRoot = "E:\kokoro计时器历史版本",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$ClientDir = $PSScriptRoot
$ProjectRoot = Split-Path $ClientDir -Parent
$BuildTemp = "E:\kokoro_journey_build_temp"
$Stage = Join-Path $BuildTemp "_stage"
$Stamp = Get-Date -Format "yyyy-MM-dd-HH"
$DistDir = Join-Path $OutputRoot ("kokoro-journey_" + $Stamp)
$ClientDist = Join-Path $ClientDir "dist"
$BuildInfo = Join-Path $ClientDir "_build_info.py"

if (-not (Test-Path $Python)) { throw "Python 不存在: $Python" }

# ---- 版本：v{构建日期}-{version.py 的 X.Y.Z} ----
$VersionFile = Join-Path $ClientDir "version.py"
$VersionText = Get-Content -LiteralPath $VersionFile -Raw -Encoding UTF8
$Semver = $null
if ($VersionText -match '-(\d+\.\d+\.\d+)"') { $Semver = $Matches[1] }
if (-not $Semver) { throw "无法从 version.py 解析语义版本 (X.Y.Z)" }
$BuildDate = (Get-Date).ToString("yyyy.M.d")
$BuildVersion = "v$BuildDate-$Semver"
$FileVersion = "$Semver.0"
Write-Host "构建版本: $BuildVersion  (FileVersion=$FileVersion)" -ForegroundColor Green

if (-not $SkipBuild) {
    New-Item -ItemType Directory -Force $BuildTemp | Out-Null
    Remove-Item $Stage -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force $Stage | Out-Null

    # 生成 _build_info.py（编译后删除，保证源码运行回退 version.py）
    Set-Content -LiteralPath $BuildInfo -Value "BUILD_VERSION = `"$BuildVersion`"" -Encoding ASCII

    try {
        Write-Host "== [1/3] 编译主程序（无控制台，约 10~20 分钟）==" -ForegroundColor Cyan
        Push-Location $ClientDir
        try {
            & $Python -m nuitka --standalone --assume-yes-for-downloads `
                --enable-plugin=pyside6 `
                --windows-console-mode=disable `
                --windows-icon-from-ico=icons\icon.ico `
                --output-filename=kokoro-journey.exe `
                --output-dir=$Stage `
                --company-name="Kokoro Journey" `
                --product-name="Kokoro Journey" `
                --file-version=$FileVersion `
                --product-version=$FileVersion `
                --include-data-dir=icons=icons `
                --include-data-file=.env.example=.env.example `
                --include-libs="E:\program\ANACONDA\envs\bishe\Library\bin\sqlite3.dll" `
                --include-libs="E:\program\ANACONDA\envs\bishe\Library\bin\ffi.dll" `
                main.py
            if ($LASTEXITCODE -ne 0) { throw "主程序编译失败" }
        } finally {
            Pop-Location
        }

        Write-Host "== [2/3] 编译日志控制台（约 2~5 分钟）==" -ForegroundColor Cyan
        Push-Location $ClientDir
        try {
            & $Python -m nuitka --standalone --assume-yes-for-downloads `
                --windows-console-mode=force `
                --windows-icon-from-ico=icons\icon.ico `
                --output-filename=log-console.exe `
                --output-dir=$Stage `
                --company-name="Kokoro Journey" `
                --product-name="Kokoro Journey" `
                --file-version=$FileVersion `
                --product-version=$FileVersion `
                --include-libs="E:\program\ANACONDA\envs\bishe\Library\bin\sqlite3.dll" `
                --include-libs="E:\program\ANACONDA\envs\bishe\Library\bin\ffi.dll" `
                log_console.py
            if ($LASTEXITCODE -ne 0) { throw "日志控制台编译失败" }
        } finally {
            Pop-Location
        }
    } finally {
        Remove-Item -LiteralPath $BuildInfo -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "== [3/3] 组装发布目录 $DistDir ==" -ForegroundColor Cyan
New-Item -ItemType Directory -Force $DistDir | Out-Null
Copy-Item (Join-Path $Stage "main.dist\*") $DistDir -Recurse -Force
Copy-Item (Join-Path $Stage "log_console.dist\log-console.exe") $DistDir -Force

# 同步一份到 client\dist，供 installer/KokoroJourney.iss (SourceDir=..\client\dist) 使用
Remove-Item -LiteralPath $ClientDist -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $ClientDist | Out-Null
Copy-Item (Join-Path $DistDir "*") $ClientDist -Recurse -Force

Write-Host "打包完成: $DistDir" -ForegroundColor Green
Write-Host "  kokoro-journey.exe  主程序（无黑窗，开机自启指向它）"
Write-Host "  log-console.exe     带日志黑窗启动器（关闭黑窗不影响主程序）"
Write-Host "  已同步: $ClientDist"
Write-Host ""
Write-Host "编译安装包（手动执行，脚本不会自动调用 ISCC）:" -ForegroundColor Yellow
Write-Host ("  ISCC.exe /DMyAppVersion=""{0}"" KokoroJourney.iss" -f $BuildVersion)
