param(
    [string]$StateFile,
    [switch]$DeleteData
)

# ============================================================================
# Kokoro Journey 卸载数据处理器
# 由 Inno Setup [Code] 调用，隐藏运行
# 功能：接收 -DeleteData 参数 → 安全删除用户数据
# ============================================================================

$ErrorActionPreference = "Stop"

# 未请求删除：直接退出
if (-not $DeleteData) {
    exit 0
}

# --- 读取状态文件 ---
if (-not (Test-Path $StateFile)) {
    exit 1
}

try {
    $state = Get-Content $StateFile -Raw | ConvertFrom-Json
} catch {
    exit 1
}

$dataDir = $state.dataDirectory
$settingsDir = $state.settingsDirectory

if (-not $dataDir) {
    exit 1
}

# --- 用户选择删除（Inno Setup 复选框已确认） ---
$deletionIssues = $false

try {
    # 安全检查：危险目录列表
    $systemDirs = @(
        $env:USERPROFILE,
        $env:LOCALAPPDATA,
        $env:APPDATA,
        $env:PROGRAMFILES,
        [Environment]::GetEnvironmentVariable("PROGRAMFILES(X86)"),
        $env:ProgramData,
        $env:WINDIR,
        $env:TEMP
    )

    $isDangerous = {
        param($target)
        if (-not $target) { return $true }
        $targetNorm = $target.TrimEnd('\')

        # 盘根目录：仅精确匹配
        foreach ($drive in (Get-PSDrive -PSProvider FileSystem)) {
            if ($targetNorm -eq $drive.Root.TrimEnd('\')) { return $true }
        }

        # 系统目录：精确 / 父级（不含子级，避免误判用户数据目录）
        foreach ($sysDir in $script:systemDirs) {
            if (-not $sysDir) { continue }
            $sysNorm = $sysDir.TrimEnd('\')
            if ($targetNorm -eq $sysNorm) { return $true }
            if ($sysNorm.StartsWith($targetNorm + "\")) { return $true }
        }

        return $false
    }

    # --- 处理数据目录 ---
    if ((Test-Path $dataDir) -and (-not (& $isDangerous $dataDir))) {
        $kokoroPatterns = @(
            "local_client.db",
            "local_client.db-*",          # sqlite 事务/WAL 附属文件
            "local_client.db.Back*",      # 迁移时的备份 (local_client.db.Back1 ...)
            "failed_sessions.json",
            "failed_sessions_dead.json",
            "local_client_*.bak"
        )

        foreach ($pattern in $kokoroPatterns) {
            $kokoroMatches = Get-ChildItem $dataDir -Force -Filter $pattern
            foreach ($match in $kokoroMatches) {
                if ($match.PSIsContainer) {
                    Remove-Item $match.FullName -Recurse -Force
                } else {
                    Remove-Item $match.FullName -Force
                }
            }
        }
        if (Test-Path $dataDir) {
            $remaining = Get-ChildItem $dataDir -Force
            if ($remaining.Count -eq 0) {
                Remove-Item $dataDir -Force
            }
        }
    }
    elseif (Test-Path $dataDir) {
        $deletionIssues = $true
    }

    # --- 处理设置目录 ---
    if ($settingsDir -and $settingsDir -ne $dataDir) {
        if ((Test-Path $settingsDir) -and (-not (& $isDangerous $settingsDir))) {
            $settingsPatterns = @(".env", "settings.json", "uninstall_state.json")

            foreach ($pattern in $settingsPatterns) {
                $settingsMatches = Get-ChildItem $settingsDir -Force -Filter $pattern
                foreach ($match in $settingsMatches) {
                    Remove-Item $match.FullName -Force
                }
            }
            if (Test-Path $settingsDir) {
                $remaining = Get-ChildItem $settingsDir -Force
                if ($remaining.Count -eq 0) {
                    Remove-Item $settingsDir -Force
                }
            }
        }
        elseif (Test-Path $settingsDir) {
            $deletionIssues = $true
        }
    }
} catch {
    # 任何异常：中止删除，保留数据
    exit 1
}

if ($deletionIssues) {
    exit 1
}

exit 0
