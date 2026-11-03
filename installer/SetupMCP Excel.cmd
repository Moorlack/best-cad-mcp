@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "AECMB_PRODUCT=Excel"
set "AECMB_TITLE=ExcelMcp setup"
if /i "%~1"=="--self-updated" set "AECMB_SELF_UPDATED=1"
title %AECMB_TITLE% v2026.11.03.03

echo.
echo %AECMB_TITLE% v2026.11.03.03
echo This script installs only the ExcelMcp bridge and preserves unrelated MCP servers.
echo.

net session >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Administrator rights are required. Requesting elevation...
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
      "Start-Process -FilePath $env:ComSpec -ArgumentList @('/d','/c','"""%~f0"""') -Verb RunAs"
    exit /b
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$lines = Get-Content -LiteralPath '%~f0' -Encoding UTF8;" ^
  "$marker = [Array]::IndexOf($lines, '# POWERSHELL_PAYLOAD');" ^
  "if ($marker -lt 0) { throw 'PowerShell payload marker was not found.' };" ^
  "$code = $lines[($marker + 1)..($lines.Length - 1)] -join [Environment]::NewLine;" ^
  "$tokens = $null; $parseErrors = $null; [void][System.Management.Automation.Language.Parser]::ParseInput($code, [ref]$tokens, [ref]$parseErrors);" ^
  "if ($parseErrors.Count -gt 0) { foreach ($e in $parseErrors) { Write-Host ('Line {0}: {1}' -f $e.Extent.StartLineNumber, $e.Message) -ForegroundColor Red }; exit 1 };" ^
  "& ([ScriptBlock]::Create($code))"

set "EXIT_CODE=%ERRORLEVEL%"

rem Exit code 75: the payload downloaded and validated a newer installer.
rem The whole block is parsed before it runs, so replacing this file here is safe.
if "%EXIT_CODE%"=="75" if exist "%TEMP%\SetupMCP_%AECMB_PRODUCT%_selfupdate.cmd" (
    copy /y "%TEMP%\SetupMCP_%AECMB_PRODUCT%_selfupdate.cmd" "%~f0" >nul && (
        echo [OK] Installer was updated. Restarting the new version...
        start "" "%~f0" --self-updated
    ) || (
        echo [WARNING] This installer file could not be replaced. Starting the downloaded copy instead...
        start "" "%TEMP%\SetupMCP_%AECMB_PRODUCT%_selfupdate.cmd" --self-updated
    )
    exit /b 0
)

echo.
if "%EXIT_CODE%"=="0" (echo [OK] Setup finished.) else (echo [ERROR] Setup finished with exit code %EXIT_CODE%.)
echo.
pause
exit /b %EXIT_CODE%

# POWERSHELL_PAYLOAD
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$StepNumber = 0
# Keep in sync with the title/echo lines above; self-update compares this value.
$script:InstallerVersion = '2026.11.03.03'
# Published in the Moorlack/Excel-mcp-server fork (installer only; the server comes from kousunh/excel-mcp-server).
$script:InstallerUpdateUrl = 'https://raw.githubusercontent.com/Moorlack/Excel-mcp-server/main/installer/SetupMCP%20Excel.cmd'
$BridgeName = 'excel-mcp'
$InstallRoot = Join-Path $env:ProgramData 'ExcelMcp'
$SourceRoot = Join-Path $InstallRoot 'source'
$VenvRoot = Join-Path $InstallRoot 'venv'
$VenvPython = Join-Path $VenvRoot 'Scripts\python.exe'
$ServerEntry = Join-Path $SourceRoot 'src\index.js'
$RepoUrl = 'https://github.com/kousunh/excel-mcp-server.git'
$RepoBranch = 'main'
# Logs live outside InstallRoot so a complete removal can still write its log.
$LogDirectory = Join-Path $env:ProgramData 'ExcelMcp-logs'

function Write-Ok([string]$Message) { Write-Host "[OK] $Message" -ForegroundColor Green }
function Write-Info([string]$Message) { Write-Host "[INFO] $Message" -ForegroundColor Cyan }
function Write-WarningMessage([string]$Message) { Write-Host "[WARNING] $Message" -ForegroundColor Yellow }
function Write-ErrorMessage([string]$Message) { Write-Host "[ERROR] $Message" -ForegroundColor Red }
function Start-Step([string]$Title, [string]$Explanation) {
    $script:StepNumber++
    Write-Host ''; Write-Host ('=' * 72) -ForegroundColor DarkGray
    Write-Host "[$script:StepNumber] $Title" -ForegroundColor Cyan
    Write-Host $Explanation -ForegroundColor Gray
    Write-Host ('-' * 72) -ForegroundColor DarkGray
}
function Refresh-ProcessPath {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machine;$user"
}
function Get-CommandPath([string]$Name) { try { (Get-Command $Name -ErrorAction Stop).Source } catch { $null } }
function Backup-File([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $backup = "$Path.bak_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    Copy-Item -LiteralPath $Path -Destination $backup -Force
    Write-Info "Existing configuration was backed up to $backup"
}
function Join-NativeArguments([string[]]$Arguments) {
    ($Arguments | ForEach-Object {
        if ($_ -eq '') { '""' }
        elseif ($_ -match '[\s"]') { '"' + ($_ -replace '(\\*)"', '$1$1\"' -replace '(\\+)$', '$1$1') + '"' }
        else { $_ }
    }) -join ' '
}
function Invoke-Quiet {
    # Runs a native command without printing; returns its exit code and output (timeout-safe).
    param([Parameter(Mandatory)][string]$FilePath, [string[]]$Arguments, [int]$TimeoutMs = 60000, [string]$WorkingDirectory)
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new($FilePath)
    $startInfo.Arguments = Join-NativeArguments $Arguments
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true
    $startInfo.EnvironmentVariables['GIT_TERMINAL_PROMPT'] = '0'
    if ($WorkingDirectory) { $startInfo.WorkingDirectory = $WorkingDirectory }
    try { $process = [System.Diagnostics.Process]::Start($startInfo) }
    catch { return [pscustomobject]@{ ExitCode = -1; Output = ''; Error = $_.Exception.Message } }
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit($TimeoutMs)) {
        try { $process.Kill() } catch {}
        return [pscustomobject]@{ ExitCode = -1; Output = ''; Error = 'timed out' }
    }
    $process.WaitForExit()
    [pscustomobject]@{ ExitCode = $process.ExitCode; Output = $stdout.Result.Trim(); Error = $stderr.Result.Trim() }
}
function Invoke-CheckedProcess {
    param([string]$FilePath, [string[]]$Arguments, [string]$Description, [string]$WorkingDirectory, [int]$TimeoutMs = 1800000)
    Write-Host "  > $Description" -ForegroundColor White
    $result = Invoke-Quiet -FilePath $FilePath -Arguments $Arguments -TimeoutMs $TimeoutMs -WorkingDirectory $WorkingDirectory
    if ($script:LogPath) {
        Add-Content -LiteralPath $script:LogPath -Value "`r`n--- $Description (exit $($result.ExitCode)) ---`r`n$($result.Output)`r`n$($result.Error)" -ErrorAction SilentlyContinue
    }
    if ($result.ExitCode -ne 0) {
        $details = @($result.Error, $result.Output) | Where-Object { $_ } | Select-Object -First 1
        if ($details) { ($details -split "`r?`n" | Select-Object -Last 12) | ForEach-Object { Write-Host "  $_" -ForegroundColor Red } }
        throw "$Description failed with exit code $($result.ExitCode)."
    }
}

function Get-InstallerVersionFromText([string]$Text) {
    $match = [regex]::Match($Text, "(?m)^\`$script:InstallerVersion = '(\d{4}\.\d{2}\.\d{2}\.\d{2})'")
    if ($match.Success) { return $match.Groups[1].Value }
    return $null
}
function Test-InstallerText([string]$Text) {
    if ($Text -notmatch '(?m)^set "AECMB_PRODUCT=Excel"') { return 'it is not the ExcelMcp installer' }
    $lines = $Text -split "`r?`n"
    $marker = [Array]::IndexOf($lines, '# POWERSHELL_PAYLOAD')
    if ($marker -lt 0) { return 'the PowerShell payload marker is missing' }
    $parseErrors = $null
    [void][System.Management.Automation.Language.Parser]::ParseInput(($lines[($marker + 1)..($lines.Length - 1)] -join [Environment]::NewLine), [ref]$null, [ref]$parseErrors)
    if ($parseErrors.Count -gt 0) { return 'its PowerShell payload does not parse' }
    return $null
}
function Update-InstallerIfNewer {
    # Returns $true when a validated newer installer was saved and a restart is needed.
    if ($env:AECMB_SELF_UPDATED -eq '1' -or $env:AECMB_SKIP_SELF_UPDATE -eq '1') { Write-Info "Installer version $($script:InstallerVersion)."; return $false }
    Write-Info "Installer version $($script:InstallerVersion). Checking for a newer installer..."
    $url = if ($env:AECMB_INSTALLER_UPDATE_URL) { $env:AECMB_INSTALLER_UPDATE_URL } else { $script:InstallerUpdateUrl }
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        $content = (Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 15 -ErrorAction Stop).Content
        if ($content -is [byte[]]) { $content = [System.Text.Encoding]::UTF8.GetString($content) }
    }
    catch { Write-WarningMessage "Could not check for a newer installer: $($_.Exception.Message). Continuing with this version."; return $false }
    $remoteVersion = Get-InstallerVersionFromText $content
    if (-not $remoteVersion) { Write-WarningMessage 'The published installer has no readable version. Continuing with this version.'; return $false }
    if ([version]$remoteVersion -le [version]$script:InstallerVersion) { Write-Ok "Installer is up to date ($($script:InstallerVersion))."; return $false }
    $problem = Test-InstallerText $content
    if ($problem) { Write-WarningMessage "Installer $remoteVersion was found but not used because $problem. Continuing with this version."; return $false }
    [System.IO.File]::WriteAllText((Join-Path $env:TEMP 'SetupMCP_Excel_selfupdate.cmd'), $content, [System.Text.UTF8Encoding]::new($false))
    Write-Ok "Installer $remoteVersion was downloaded (current $($script:InstallerVersion)). This window will restart it."
    return $true
}

function Get-ClaudeConfigPaths {
    $paths = [System.Collections.Generic.List[string]]::new()
    # Traditional Win32 installation.
    $paths.Add((Join-Path $env:APPDATA 'Claude\claude_desktop_config.json'))
    # Microsoft Store / MSIX installation (package suffix can change).
    $packagesRoot = Join-Path $env:LOCALAPPDATA 'Packages'
    if (Test-Path -LiteralPath $packagesRoot) {
        Get-ChildItem -LiteralPath $packagesRoot -Directory -Filter 'Claude_*' -ErrorAction SilentlyContinue | ForEach-Object {
            $paths.Add((Join-Path $_.FullName 'LocalCache\Roaming\Claude\claude_desktop_config.json'))
        }
    }
    # Claude Desktop 4.x keeps the config it actually reads in %LOCALAPPDATA%\Claude-Data\claude_<package id>.
    $claudeDataRoot = Join-Path $env:LOCALAPPDATA 'Claude-Data'
    if (Test-Path -LiteralPath $claudeDataRoot) {
        Get-ChildItem -LiteralPath $claudeDataRoot -Directory -Filter 'claude_*' -ErrorAction SilentlyContinue | ForEach-Object {
            $paths.Add((Join-Path $_.FullName 'claude_desktop_config.json'))
        }
    }
    @($paths | Sort-Object -Unique)
}
function Get-ActiveClaudeConfigPaths {
    # An existing config or an existing profile folder marks a location Claude uses.
    $active = @(Get-ClaudeConfigPaths | Where-Object { (Test-Path -LiteralPath $_) -or (Test-Path -LiteralPath (Split-Path $_ -Parent)) })
    if ($active.Count -gt 0) { return $active }
    return @(Join-Path $env:APPDATA 'Claude\claude_desktop_config.json')
}
function Test-ExcelInstalled {
    $excel = $null
    try {
        $excel = New-Object -ComObject Excel.Application -ErrorAction Stop
        return $true
    } catch { return $false }
    finally {
        if ($excel) { try { $excel.Quit() } catch {}; [void][Runtime.InteropServices.Marshal]::ReleaseComObject($excel) }
    }
}
function Get-CodexCli { $codex = Get-CommandPath 'codex.cmd'; if (-not $codex) { $codex = Get-CommandPath 'codex.exe' }; $codex }
function Test-CodexBridgeConfigured {
    $codex = Get-CodexCli
    if ($codex) { try { $list = & $codex mcp list 2>$null | Out-String; return $list -match '(?m)^excel-mcp\b' } catch {} }
    $path = Join-Path $env:USERPROFILE '.codex\config.toml'
    return (Test-Path -LiteralPath $path) -and ((Get-Content -LiteralPath $path -Raw) -match '(?m)^\[mcp_servers\.excel-mcp\]')
}
function Test-ClaudeBridgeConfigured {
    foreach ($path in @(Get-ClaudeConfigPaths)) {
        if (-not (Test-Path -LiteralPath $path)) { continue }
        try { if ((Get-Content -LiteralPath $path -Raw | ConvertFrom-Json).mcpServers.PSObject.Properties[$BridgeName]) { return $true } } catch {}
    }
    return $false
}
function Test-AntigravityBridgeConfigured {
    $path = Join-Path $env:USERPROFILE '.gemini\config\mcp_config.json'
    if (-not (Test-Path -LiteralPath $path)) { return $false }
    try { return $null -ne (Get-Content -LiteralPath $path -Raw | ConvertFrom-Json).mcpServers.PSObject.Properties[$BridgeName] } catch { return $false }
}
function Test-CodexDesktopInstalled {
    if (Test-Path (Join-Path $env:LOCALAPPDATA 'Programs\Codex\Codex.exe')) { return $true }
    try { return $null -ne (Get-AppxPackage -ErrorAction SilentlyContinue | Where-Object { $_.Publisher -match 'OpenAI' -and $_.Name -match 'ChatGPT|Codex' } | Select-Object -First 1) } catch { return $false }
}
function Test-ClaudeDesktopInstalled {
    if ((Test-Path (Join-Path $env:LOCALAPPDATA 'Programs\Claude\Claude.exe')) -or (Test-Path (Join-Path $env:LOCALAPPDATA 'AnthropicClaude\Claude.exe'))) { return $true }
    try { return $null -ne (Get-AppxPackage -Name 'Claude*' -ErrorAction SilentlyContinue | Select-Object -First 1) } catch { return $false }
}
function Test-AntigravityDesktopInstalled {
    try { if (Get-AppxPackage -Name 'Google.Antigravity' -ErrorAction SilentlyContinue) { return $true } } catch {}
    return $false
}
function Ensure-WinGetPackage([string]$Id, [string]$Name, [string]$Source) {
    $winget = Get-CommandPath 'winget.exe'; if (-not $winget) { $winget = Get-CommandPath 'winget' }
    if (-not $winget) { throw "WinGet is required to install $Name automatically, but was not found." }
    $arguments = @('install','--id',$Id,'--exact','--silent','--accept-package-agreements','--accept-source-agreements','--disable-interactivity')
    if ($Source) { $arguments += @('--source',$Source) }
    try { Invoke-CheckedProcess -FilePath $winget -Arguments $arguments -Description "Install or update $Name" }
    catch {
        # WinGet (notably the Microsoft Store source) exits non-zero when the package
        # is already installed and has no newer version.
        $listed = Invoke-Quiet -FilePath $winget -Arguments @('list','--id',$Id,'--exact','--accept-source-agreements','--disable-interactivity') -TimeoutMs 120000
        if ($listed.ExitCode -ne 0) { throw }
        Write-Info "$Name is already installed and has no available update."
    }
    Refresh-ProcessPath
}
function Ensure-Codex {
    if (-not (Test-CodexDesktopInstalled)) { Ensure-WinGetPackage -Id '9PLM9XGG6VKS' -Name 'ChatGPT desktop app with Codex' -Source 'msstore' }
    if (-not (Get-CodexCli)) {
        if (-not (Get-CommandPath 'npm.cmd')) { Ensure-WinGetPackage -Id 'OpenJS.NodeJS.LTS' -Name 'Node.js LTS' }
        Refresh-ProcessPath
        Invoke-CheckedProcess -FilePath (Get-CommandPath 'npm.cmd') -Arguments @('install','-g','@openai/codex') -Description 'Installing OpenAI Codex CLI'
        Refresh-ProcessPath
    }
}
function Ensure-Node {
    if (-not (Get-CommandPath 'node.exe') -or -not (Get-CommandPath 'npm.cmd')) { Ensure-WinGetPackage -Id 'OpenJS.NodeJS.LTS' -Name 'Node.js LTS' }
    Refresh-ProcessPath
    if (-not (Get-CommandPath 'node.exe') -or -not (Get-CommandPath 'npm.cmd')) { throw 'Node.js is unavailable after installation.' }
}
function Ensure-Python {
    if (-not (Get-CommandPath 'python.exe')) { Ensure-WinGetPackage -Id 'Python.Python.3.12' -Name 'Python 3.12' }
    Refresh-ProcessPath
    $python = Get-CommandPath 'python.exe'
    if (-not $python) { throw 'Python is unavailable after installation.' }
    return $python
}
function Ensure-Git {
    if (-not (Get-CommandPath 'git.exe')) { Ensure-WinGetPackage -Id 'Git.Git' -Name 'Git' }
    Refresh-ProcessPath
    $git = Get-CommandPath 'git.exe'
    if (-not $git) { throw 'Git is unavailable after installation.' }
    return $git
}
function Ensure-Claude { if (-not (Test-ClaudeDesktopInstalled)) { Ensure-WinGetPackage -Id 'Anthropic.Claude' -Name 'Claude Desktop' } }
function Ensure-Antigravity {
    if (-not (Test-AntigravityDesktopInstalled)) { Ensure-WinGetPackage -Id 'Google.Antigravity' -Name 'Google Antigravity desktop app' }
    if (-not (Get-CommandPath 'agy.cmd') -and -not (Get-CommandPath 'agy.exe')) { Ensure-WinGetPackage -Id 'Google.AntigravityCLI' -Name 'Google Antigravity CLI' }
    Refresh-ProcessPath
}
function Get-JsonSettings([string]$Path, [string]$Description) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path) | Out-Null
    if (Test-Path -LiteralPath $Path) {
        Backup-File $Path
        try { $root = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json } catch { throw "The existing $Description is invalid JSON and was not changed: $Path" }
        if (-not $root) { $root = [pscustomobject]@{} }
    } else { $root = [pscustomobject]@{} }
    [pscustomobject]@{Path=$Path;Root=$root}
}
function Save-JsonSettings($Settings) { [IO.File]::WriteAllText($Settings.Path, ($Settings.Root | ConvertTo-Json -Depth 100), [Text.UTF8Encoding]::new($false)) }

function Get-ExcelUpdateStatus {
    # Compares the installed source with the official repository without changing files.
    $status = [pscustomobject]@{ State = 'Unknown'; Local = ''; Remote = ''; Detail = '' }
    if (-not (Test-Path -LiteralPath (Join-Path $SourceRoot '.git'))) { $status.State = 'NotInstalled'; return $status }
    $git = Get-CommandPath 'git.exe'
    if (-not $git) { $status.Detail = 'Git was not found'; return $status }
    $safe = 'safe.directory=' + ($SourceRoot -replace '\\', '/')
    $local = Invoke-Quiet -FilePath $git -Arguments @('-c', $safe, '-C', $SourceRoot, 'rev-parse', 'HEAD') -TimeoutMs 20000
    if ($local.ExitCode -ne 0 -or $local.Output -notmatch '^[0-9a-f]{40}$') { $status.Detail = 'the installed version could not be read'; return $status }
    $status.Local = $local.Output
    $remote = Invoke-Quiet -FilePath $git -Arguments @('ls-remote', $RepoUrl, "refs/heads/$RepoBranch") -TimeoutMs 20000
    $remoteSha = (($remote.Output -split '\s+') | Select-Object -First 1)
    if ($remote.ExitCode -ne 0 -or $remoteSha -notmatch '^[0-9a-f]{40}$') { $status.Detail = "the latest version could not be checked ($($remote.Error))"; return $status }
    $status.Remote = $remoteSha
    if ($remoteSha -eq $status.Local) { $status.State = 'UpToDate' }
    else {
        $ancestor = Invoke-Quiet -FilePath $git -Arguments @('-c', $safe, '-C', $SourceRoot, 'merge-base', '--is-ancestor', $remoteSha, 'HEAD') -TimeoutMs 20000
        $status.State = if ($ancestor.ExitCode -eq 0) { 'LocalAhead' } else { 'UpdateAvailable' }
    }
    return $status
}
function Get-UpdateNote($Status) {
    $short = { param($sha) if ($sha) { $sha.Substring(0, 7) } else { '?' } }
    switch ($Status.State) {
        'UpdateAvailable' { return [pscustomobject]@{ Text = "Updates found: $(& $short $Status.Local) -> $(& $short $Status.Remote)"; Color = 'Magenta' } }
        'UpToDate' { return [pscustomobject]@{ Text = 'Updates not found'; Color = 'DarkGray' } }
        'LocalAhead' { return [pscustomobject]@{ Text = 'Updates not found'; Color = 'DarkGray' } }
        'Unknown' { return [pscustomobject]@{ Text = "Update check unavailable ($($Status.Detail)); the latest version is still pulled"; Color = 'Yellow' } }
        default { return $null }
    }
}
function Write-MenuOption([string]$Number, [string]$Label, [string]$Color, $Note) {
    Write-Host "$Number - $Label" -ForegroundColor $Color
    if ($Note) { Write-Host "    $($Note.Text)" -ForegroundColor $Note.Color }
}

function Sync-ExcelSource([string]$Git) {
    $safe = 'safe.directory=' + ($SourceRoot -replace '\\', '/')
    if (Test-Path -LiteralPath (Join-Path $SourceRoot '.git')) {
        Invoke-CheckedProcess -FilePath $Git -Arguments @('-c', $safe, '-C', $SourceRoot, 'remote', 'set-url', 'origin', $RepoUrl) -Description 'Selecting the official Excel Live MCP repository'
        $changes = Invoke-Quiet -FilePath $Git -Arguments @('-c', $safe, '-C', $SourceRoot, 'status', '--porcelain') -TimeoutMs 60000
        if ($changes.ExitCode -eq 0 -and $changes.Output) {
            $stashMessage = "ExcelMcp setup backup $(Get-Date -Format 'yyyyMMdd_HHmmss')"
            Write-WarningMessage 'Local ExcelMcp source changes were found. Saving them to Git stash before update.'
            Invoke-CheckedProcess -FilePath $Git -Arguments @('-c', $safe, '-C', $SourceRoot, 'stash', 'push', '--include-untracked', '-m', $stashMessage) -Description 'Saving local ExcelMcp changes'
        }
        Write-Host '  > Updating Excel Live MCP source' -ForegroundColor White
        $pull = Invoke-Quiet -FilePath $Git -Arguments @('-c', $safe, '-C', $SourceRoot, 'pull', '--ff-only', 'origin', $RepoBranch) -TimeoutMs 600000
        if ($script:LogPath) { Add-Content -LiteralPath $script:LogPath -Value "`r`n--- git pull (exit $($pull.ExitCode)) ---`r`n$($pull.Output)`r`n$($pull.Error)" -ErrorAction SilentlyContinue }
        if ($pull.ExitCode -eq 0) { Write-Ok 'Excel Live MCP source was updated.'; return }
        # A copy whose history diverged ("Not possible to fast-forward") is kept as a backup and downloaded again.
        $reach = Invoke-Quiet -FilePath $Git -Arguments @('ls-remote', '--heads', $RepoUrl) -TimeoutMs 60000
        if ($reach.ExitCode -ne 0) { throw "Updating the Excel Live MCP source failed (git exit code $($pull.ExitCode)) and $RepoUrl is not reachable. Check the internet connection, proxy or firewall. $($pull.Error)" }
        $backup = "$SourceRoot.backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
        Write-WarningMessage "The existing ExcelMcp source cannot be fast-forwarded. Keeping it as $backup and downloading a fresh copy."
        try { Move-Item -LiteralPath $SourceRoot -Destination $backup -ErrorAction Stop }
        catch { throw "Could not move $SourceRoot to $backup. Close the AI clients using ExcelMcp, then run setup again. Details: $($_.Exception.Message)" }
    }
    elseif (Test-Path -LiteralPath $SourceRoot) {
        $backup = "$SourceRoot.backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
        Write-WarningMessage "A non-Git ExcelMcp source folder exists and will be moved to $backup."
        Move-Item -LiteralPath $SourceRoot -Destination $backup -ErrorAction Stop
    }
    Invoke-CheckedProcess -FilePath $Git -Arguments @('clone','--branch',$RepoBranch,'--depth','1',$RepoUrl,$SourceRoot) -Description 'Downloading Excel Live MCP source'
}
function Get-RunningExcelMcpProcesses {
    @(Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -and $_.CommandLine -like "*$ServerEntry*" })
}
function Confirm-NoRunningExcelMcp {
    # Running clients keep the old server until they are fully restarted.
    $running = Get-RunningExcelMcpProcesses
    if (-not $running.Count) { Write-Ok 'No running Excel Live MCP server processes were found.'; return $true }
    Write-WarningMessage "$($running.Count) Excel Live MCP server process(es) are still running. Clients keep the old version until they are fully closed (including the tray)."
    $answer = Read-Host 'Close Claude, Codex and Antigravity first. Continue the update anyway? [Y/N]'
    return ($answer -match '^(?i)y(?:es)?$')
}
function Test-ExcelMcpStartup {
    # Starts the server like a client does (stdin open); alive after 5 seconds passes.
    $node = Get-CommandPath 'node.exe'
    $psi = [System.Diagnostics.ProcessStartInfo]::new($node)
    $psi.Arguments = Join-NativeArguments @($ServerEntry)
    $psi.WorkingDirectory = $SourceRoot
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $psi.EnvironmentVariables['EXCEL_MCP_PYTHON'] = $VenvPython
    $process = [System.Diagnostics.Process]::Start($psi)
    $stderr = $process.StandardError.ReadToEndAsync()
    $exited = $process.WaitForExit(5000)
    if (-not $exited) { try { $process.Kill() } catch {}; $process.WaitForExit(3000) | Out-Null }
    if ($exited) {
        ($stderr.Result -split "`r?`n" | Where-Object { $_ } | Select-Object -Last 12) | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
        throw "The Excel Live MCP server exited during startup with code $($process.ExitCode)."
    }
    Write-Ok 'Excel Live MCP server startup test passed.'
}

function Set-CodexApproval {
    $path = Join-Path $env:USERPROFILE '.codex\config.toml'
    if (-not (Test-Path -LiteralPath $path)) { return }
    Backup-File $path
    $content = Get-Content -LiteralPath $path -Raw
    $pattern = '(?ms)(^\[mcp_servers\.excel-mcp\]\s*\r?\n)(.*?)(?=^\[|\z)'
    $updated = [regex]::Replace($content, $pattern, { param($m)
        $body=$m.Groups[2].Value
        if ($body -match '(?m)^default_tools_approval_mode\s*=') { $body=[regex]::Replace($body,'(?m)^default_tools_approval_mode\s*=.*$','default_tools_approval_mode = "approve"') }
        else { $body='default_tools_approval_mode = "approve"' + "`r`n" + $body }
        $m.Groups[1].Value+$body
    })
    if ($updated -ne $content) { [IO.File]::WriteAllText($path,$updated,[Text.UTF8Encoding]::new($false)); Write-Ok 'Codex Excel Live MCP tools were set to approve without prompts.' }
}
function Configure-Codex {
    Ensure-Codex
    $codex = Get-CodexCli; if (-not $codex) { throw 'Codex CLI is unavailable after installation.' }
    try { & $codex mcp remove $BridgeName *> $null } catch {}
    $node = Get-CommandPath 'node.exe'
    Invoke-CheckedProcess -FilePath $codex -Arguments @('mcp','add',$BridgeName,'--env',"EXCEL_MCP_PYTHON=$VenvPython",'--',$node,$ServerEntry) -Description 'Adding Excel Live MCP to Codex'
    if (-not (Test-CodexBridgeConfigured)) { throw 'Codex configuration verification failed.' }
    Set-CodexApproval; Write-Ok 'Excel Live MCP was configured for Codex.'
}
function Configure-Claude {
    Ensure-Claude
    foreach ($path in @(Get-ActiveClaudeConfigPaths)) {
        $settings = Get-JsonSettings -Path $path -Description 'Claude configuration'
        if (-not $settings.Root.PSObject.Properties['mcpServers'] -or -not $settings.Root.mcpServers) { $settings.Root | Add-Member NoteProperty mcpServers ([pscustomobject]@{}) -Force }
        $settings.Root.mcpServers | Add-Member NoteProperty $BridgeName ([pscustomobject]@{command=(Get-CommandPath 'node.exe');args=[object[]]@($ServerEntry);env=[pscustomobject]@{EXCEL_MCP_PYTHON=$VenvPython}}) -Force
        Save-JsonSettings $settings
        Write-Ok "Excel Live MCP was configured for Claude: $path"
    }
    Write-Info 'Fully close Claude Desktop (including the tray icon) and reopen it before using ExcelMcp.'
}
function Configure-Antigravity {
    Ensure-Antigravity
    $settings=Get-JsonSettings -Path (Join-Path $env:USERPROFILE '.gemini\config\mcp_config.json') -Description 'Google Antigravity MCP configuration'
    if (-not $settings.Root.PSObject.Properties['mcpServers'] -or -not $settings.Root.mcpServers) { $settings.Root | Add-Member NoteProperty mcpServers ([pscustomobject]@{}) -Force }
    $settings.Root.mcpServers | Add-Member NoteProperty $BridgeName ([pscustomobject]@{command=(Get-CommandPath 'node.exe');args=[object[]]@($ServerEntry);env=[pscustomobject]@{EXCEL_MCP_PYTHON=$VenvPython}}) -Force
    Save-JsonSettings $settings
    $policy=Get-JsonSettings -Path (Join-Path $env:USERPROFILE '.gemini\antigravity-cli\settings.json') -Description 'Google Antigravity permissions'
    if (-not $policy.Root.PSObject.Properties['permissions'] -or -not $policy.Root.permissions) { $policy.Root | Add-Member NoteProperty permissions ([pscustomobject]@{}) -Force }
    $existing=@(); if ($policy.Root.permissions.PSObject.Properties['allow']) { $existing=@($policy.Root.permissions.allow) }
    $policy.Root.permissions | Add-Member NoteProperty allow ([object[]]@($existing + "mcp($BridgeName/*)" | Select-Object -Unique)) -Force
    Save-JsonSettings $policy; Write-Ok 'Excel Live MCP was configured for Google Antigravity.'
}
function Stop-ExcelMcpProcesses {
    foreach ($process in (Get-RunningExcelMcpProcesses)) {
        try { Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop; Write-Info "Stopped Excel Live MCP process PID $($process.ProcessId)." }
        catch { Write-WarningMessage "Could not stop Excel Live MCP process PID $($process.ProcessId): $($_.Exception.Message)" }
    }
}
function Remove-Codex {
    $codex = Get-CodexCli
    if ($codex) { try { & $codex mcp remove $BridgeName *> $null; Write-Ok 'ExcelMcp was removed from Codex.'; return } catch { Write-WarningMessage "Codex CLI removal failed; removing its configuration entry directly." } }
    $path=Join-Path $env:USERPROFILE '.codex\config.toml'
    if (-not (Test-Path -LiteralPath $path)) { return }
    Backup-File $path
    $content=Get-Content -LiteralPath $path -Raw
    $updated=[regex]::Replace($content,'(?ms)^\[mcp_servers\.excel-mcp(\.[^\]]*)?\]\s*\r?\n.*?(?=^\[|\z)','')
    if ($updated -ne $content) { [IO.File]::WriteAllText($path,$updated,[Text.UTF8Encoding]::new($false)); Write-Ok 'ExcelMcp was removed from Codex configuration.' }
}
function Remove-JsonBridge([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $settings=Get-JsonSettings -Path $Path -Description $Label
    if ($settings.Root.mcpServers -and $settings.Root.mcpServers.PSObject.Properties[$BridgeName]) { [void]$settings.Root.mcpServers.PSObject.Properties.Remove($BridgeName); Save-JsonSettings $settings; Write-Ok "ExcelMcp was removed from $Label ($Path)." }
}
function Remove-All {
    Start-Step -Title 'Remove ExcelMcp completely' -Explanation 'Only ExcelMcp registrations and its files are removed. Other bridges, apps, and dependencies remain installed.'
    Stop-ExcelMcpProcesses
    Remove-Codex
    foreach ($path in @(Get-ClaudeConfigPaths)) { Remove-JsonBridge -Path $path -Label 'Claude' }
    Remove-JsonBridge -Path (Join-Path $env:USERPROFILE '.gemini\config\mcp_config.json') -Label 'Google Antigravity'
    $policyPath=Join-Path $env:USERPROFILE '.gemini\antigravity-cli\settings.json'
    if (Test-Path -LiteralPath $policyPath) {
        $policy=Get-JsonSettings -Path $policyPath -Description 'Google Antigravity permissions'
        if ($policy.Root.permissions -and $policy.Root.permissions.PSObject.Properties['allow']) {
            $policy.Root.permissions | Add-Member NoteProperty allow ([object[]]@($policy.Root.permissions.allow | Where-Object { $_ -ne "mcp($BridgeName/*)" })) -Force; Save-JsonSettings $policy
        }
    }
    if (Test-Path -LiteralPath $InstallRoot) { Remove-Item -LiteralPath $InstallRoot -Recurse -Force; Write-Ok "Removed $InstallRoot" }
    Write-Ok 'ExcelMcp cleanup is complete. Excel, AI clients, Node.js, and Codex CLI remain installed.'
}
function Install-ExcelMcp {
    Start-Step -Title 'Check Microsoft Excel' -Explanation 'Excel Live MCP connects to the workbook that is already open in desktop Excel through xlwings.'
    if (-not (Test-ExcelInstalled)) { throw 'Microsoft Excel 2016 or later was not detected. Install and activate desktop Excel, then run this script again.' }
    Write-Ok 'Microsoft Excel COM automation is available.'
    Start-Step -Title 'Download or update Excel Live MCP' -Explanation 'The open-workbook bridge is installed from its official source with isolated Python dependencies.'
    $git=Ensure-Git; $python=Ensure-Python; Ensure-Node
    New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
    Sync-ExcelSource -Git $git
    if (-not (Test-Path -LiteralPath $VenvPython)) { Invoke-CheckedProcess -FilePath $python -Arguments @('-m','venv',$VenvRoot) -Description 'Creating Excel Live MCP virtual environment' }
    Invoke-CheckedProcess -FilePath $VenvPython -Arguments @('-m','pip','install','--disable-pip-version-check','--progress-bar','off','--upgrade','pip') -Description 'Updating pip inside the virtual environment'
    Invoke-CheckedProcess -FilePath $VenvPython -Arguments @('-m','pip','install','--disable-pip-version-check','--progress-bar','off','-r',(Join-Path $SourceRoot 'scripts\requirements.txt')) -Description 'Installing xlwings and Excel Live MCP dependencies'
    Invoke-CheckedProcess -FilePath (Get-CommandPath 'npm.cmd') -Arguments @('install','--no-audit','--no-fund','--loglevel=error') -Description 'Installing Excel Live MCP Node.js dependencies' -WorkingDirectory $SourceRoot
    if (-not (Test-Path -LiteralPath $ServerEntry)) { throw 'Excel Live MCP entry point was not found after installation.' }
    Start-Step -Title 'Test the Excel Live MCP server' -Explanation 'Immediate startup errors are printed. A server that stays alive for 5 seconds is stopped and passes.'
    Test-ExcelMcpStartup
    $installed = Invoke-Quiet -FilePath $git -Arguments @('-c', ('safe.directory=' + ($SourceRoot -replace '\\', '/')), '-C', $SourceRoot, 'log', '-1', '--format=%h %s') -TimeoutMs 20000
    if ($installed.ExitCode -eq 0 -and $installed.Output) { Write-Ok "Installed Excel Live MCP version: $($installed.Output)" }
}

$logPath = $null
try {
    New-Item -ItemType Directory -Path $LogDirectory -Force -ErrorAction SilentlyContinue | Out-Null
    $logPath = Join-Path $LogDirectory ("setup_{0}.log" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
    $script:LogPath = $logPath
    Start-Transcript -LiteralPath $logPath -Force | Out-Null

    Write-Host 'Excel Live MCP - Microsoft Excel bridge' -ForegroundColor White
    Write-Host 'Windows 10+ / Microsoft Excel 2016+ / Codex / Claude / Google Antigravity' -ForegroundColor Gray
    Write-Info "Log file: $logPath"

    if (Update-InstallerIfNewer) {
        try { Stop-Transcript | Out-Null } catch {}
        exit 75
    }

    Write-Info 'Checking the installed Excel Live MCP version against the official repository...'
    $status = Get-ExcelUpdateStatus
    $note = Get-UpdateNote $status
    $noUpdates = $status.State -in @('UpToDate', 'LocalAhead')
    $verb = if ($noUpdates) { 'Repair' } else { 'Repair or update' }
    $installed = $status.State -ne 'NotInstalled'
    Write-Host ''
    Write-Host 'Available actions:'
    Write-MenuOption '1' $(if (Test-CodexBridgeConfigured) { "$verb ExcelMcp for Codex" } else { 'Install ExcelMcp for Codex' }) 'Green' $note
    Write-MenuOption '2' $(if (Test-ClaudeBridgeConfigured) { "$verb ExcelMcp for Claude" } else { 'Install ExcelMcp for Claude' }) 'Green' $note
    Write-MenuOption '3' $(if (Test-AntigravityBridgeConfigured) { "$verb ExcelMcp for Google Antigravity" } else { 'Install ExcelMcp for Google Antigravity' }) 'Green' $note
    $choices = @('1', '2', '3', '4', '5')
    if ($installed) {
        Write-MenuOption '4' $(if ($noUpdates) { 'Repair the shared ExcelMcp server (all clients; client settings unchanged)' } else { 'Update only the shared ExcelMcp server (all clients; client settings unchanged)' }) 'Cyan' $note
    } else { $choices = @('1', '2', '3', '5') }
    Write-Host '5 - Completely remove ExcelMcp and all of its registrations' -ForegroundColor Yellow
    Write-Host '6 - Cancel'
    do { $choice = Read-Host 'Select an action' } until ($choice -in ($choices + '6'))

    if ($choice -eq '6') { Write-Info 'No changes were made.'; try { Stop-Transcript | Out-Null } catch {}; exit 0 }
    if ($choice -eq '5') {
        $answer=Read-Host "Remove ExcelMcp from all AI clients and delete $InstallRoot? [Y/N]"
        if ($answer -notmatch '^(?i)y(?:es)?$') { Write-Info 'Cleanup cancelled.'; try { Stop-Transcript | Out-Null } catch {}; exit 0 }
        Remove-All
        Write-Info "Full log file: $logPath"
        try { Stop-Transcript | Out-Null } catch {}
        exit 0
    }
    if ($choice -eq '4') {
        Start-Step -Title 'Check running ExcelMcp clients' -Explanation 'The code is shared by every AI client. Clients started before the update keep using the previous version.'
        if (-not (Confirm-NoRunningExcelMcp)) { Write-WarningMessage 'Update was cancelled. No changes were made.'; try { Stop-Transcript | Out-Null } catch {}; exit 0 }
    }

    Install-ExcelMcp

    if ($choice -eq '4') {
        $clients = @()
        if (Test-CodexBridgeConfigured) { $clients += 'ChatGPT/Codex' }
        if (Test-ClaudeBridgeConfigured) { $clients += 'Claude' }
        if (Test-AntigravityBridgeConfigured) { $clients += 'Google Antigravity' }
        Write-Host ''
        Write-Ok 'Done. The shared ExcelMcp server was updated; client registrations were not changed.'
        if ($clients) { Write-Info "Fully restart (including the tray): $($clients -join ', ')." }
        else { Write-WarningMessage 'No configured AI client was detected. Use Install/Repair for a client to register the server.' }
    }
    else {
        Start-Step -Title 'Configure the selected AI client' -Explanation 'Only ExcelMcp is registered; unrelated MCP servers remain untouched.'
        switch ($choice) { '1' { Configure-Codex } '2' { Configure-Claude } '3' { Configure-Antigravity } }
        Write-Host ''; Write-Ok 'Done. ExcelMcp is configured.'
        Write-Info 'Open the target workbook in Excel first, then ask the AI to use that open workbook by its file name.'
    }
    Write-Info "Full log file: $logPath"
    try { Stop-Transcript | Out-Null } catch {}
    exit 0
}
catch {
    Write-Host ''
    Write-Host 'DETAILED ERROR REPORT' -ForegroundColor Red
    Write-ErrorMessage "Current step number: $StepNumber"
    Write-ErrorMessage $_.Exception.Message
    Write-Host $_.ScriptStackTrace -ForegroundColor DarkRed
    if ($logPath) { Write-ErrorMessage "Full log file: $logPath" }
    try { Stop-Transcript | Out-Null } catch {}
    exit 1
}
