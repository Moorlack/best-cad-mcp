@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "AECMB_PRODUCT=AutoCAD"
if /i "%~1"=="--self-updated" set "AECMB_SELF_UPDATED=1"
title AutoCAD MCP setup v2026.09.29.03

echo.
echo AutoCAD MCP setup v2026.09.29.03
echo This script configures only the selected product without removing or replacing unrelated MCP servers.
echo.

net session >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Administrator rights are required. Requesting elevation...
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
      "Start-Process -FilePath $env:ComSpec -ArgumentList @('/d','/c','"""%~f0"""') -Verb RunAs"
    exit /b
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$lines = Get-Content -LiteralPath '%~f0';" ^
  "$marker = [Array]::IndexOf($lines, '# POWERSHELL_PAYLOAD');" ^
  "if ($marker -lt 0) { throw 'PowerShell payload marker was not found.' };" ^
  "$code = $lines[($marker + 1)..($lines.Length - 1)] -join [Environment]::NewLine;" ^
  "$tokens = $null; $parseErrors = $null;" ^
  "[void][System.Management.Automation.Language.Parser]::ParseInput($code, [ref]$tokens, [ref]$parseErrors);" ^
  "if ($parseErrors.Count -gt 0) {" ^
  "  Write-Host 'POWERSHELL PAYLOAD PARSE ERRORS' -ForegroundColor Red;" ^
  "  foreach ($e in $parseErrors) {" ^
  "    Write-Host ('Line {0}, Column {1}: {2}' -f $e.Extent.StartLineNumber, $e.Extent.StartColumnNumber, $e.Message) -ForegroundColor Red;" ^
  "    Write-Host $e.Extent.Text -ForegroundColor DarkRed;" ^
  "  };" ^
  "  exit 1;" ^
  "};" ^
  "& ([ScriptBlock]::Create($code))"

set "EXIT_CODE=%ERRORLEVEL%"

rem Exit code 75: the payload downloaded and validated a newer installer.
rem The whole block is parsed before it runs, so replacing this file here is safe.
if "%EXIT_CODE%"=="75" if exist "%TEMP%\SetupMCP_AutoCAD_selfupdate.cmd" (
    copy /y "%TEMP%\SetupMCP_AutoCAD_selfupdate.cmd" "%~f0" >nul && (
        echo [OK] Installer was updated. Restarting the new version...
        start "" "%~f0" --self-updated
    ) || (
        echo [WARNING] This installer file could not be replaced. Starting the downloaded copy instead...
        start "" "%TEMP%\SetupMCP_AutoCAD_selfupdate.cmd" --self-updated
    )
    exit /b 0
)

echo.
if "%EXIT_CODE%"=="0" (
    echo [OK] Setup finished.
) else (
    echo [ERROR] Setup finished with exit code %EXIT_CODE%.
)
echo.
pause
exit /b %EXIT_CODE%

# POWERSHELL_PAYLOAD
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$StepNumber = 0
$script:BridgeProduct = 'AutoCAD'
$script:BridgeProductLabel = 'AutoCAD'
# Keep in sync with the title/echo lines above; self-update compares this value.
$script:InstallerVersion = '2026.09.29.03'
$script:InstallerUpdateUrl = 'https://raw.githubusercontent.com/Moorlack/best-cad-mcp/master/installer/SetupMCP%20AutoCAD.cmd'

function Write-Ok([string]$Message) {
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-WarningMessage([string]$Message) {
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

function Write-ErrorMessage([string]$Message) {
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Write-Info([string]$Message) {
    Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

function ConvertTo-Hashtable {
    param([Parameter(ValueFromPipeline = $true)]$InputObject)

    process {
        if ($null -eq $InputObject) {
            return $null
        }

        if ($InputObject -is [System.Collections.IDictionary]) {
            $result = [ordered]@{}
            foreach ($key in $InputObject.Keys) {
                $result[$key] = ConvertTo-Hashtable $InputObject[$key]
            }
            return $result
        }

        if (
            $InputObject -is [System.Collections.IEnumerable] -and
            -not ($InputObject -is [string])
        ) {
            $items = @()
            foreach ($item in $InputObject) {
                $items += ,(ConvertTo-Hashtable $item)
            }
            return $items
        }

        if ($InputObject -is [pscustomobject]) {
            $result = [ordered]@{}
            foreach ($property in $InputObject.PSObject.Properties) {
                $result[$property.Name] = ConvertTo-Hashtable $property.Value
            }
            return $result
        }

        return $InputObject
    }
}

function Test-DictionaryKey {
    param(
        [Parameter(Mandatory)]$Dictionary,
        [Parameter(Mandatory)][string]$Key
    )

    if ($null -eq $Dictionary) {
        return $false
    }

    if ($Dictionary -is [System.Collections.IDictionary]) {
        return $Dictionary.Contains($Key)
    }

    $property = $Dictionary.PSObject.Properties[$Key]
    return $null -ne $property
}


function Start-Step([string]$Title, [string]$Explanation) {
    $script:StepNumber++
    Write-Host ''
    Write-Host ('=' * 72) -ForegroundColor DarkGray
    Write-Host "[$script:StepNumber] $Title" -ForegroundColor Cyan
    Write-Host $Explanation -ForegroundColor Gray
    Write-Host ('-' * 72) -ForegroundColor DarkGray
}

function Wait-ProcessWithProgress {
    param(
        [Parameter(Mandatory)][System.Diagnostics.Process]$Process,
        [Parameter(Mandatory)][string]$StdoutFile,
        [Parameter(Mandatory)][string]$StderrFile
    )

    $started = Get-Date
    $lastLineCount = 0
    $activityCount = 0
    $spinner = @('|', '/', '-', '\')
    $spinnerIndex = 0

    while (-not $Process.HasExited) {
        $elapsed = [int]((Get-Date) - $started).TotalSeconds

        $stdoutLines = 0
        $stderrLines = 0
        $stdoutBytes = 0
        $stderrBytes = 0

        if (Test-Path -LiteralPath $StdoutFile) {
            try {
                $stdoutInfo = Get-Item -LiteralPath $StdoutFile -ErrorAction Stop
                $stdoutBytes = $stdoutInfo.Length
                $stdoutLines = @(Get-Content -LiteralPath $StdoutFile -ErrorAction SilentlyContinue).Count
            }
            catch {}
        }

        if (Test-Path -LiteralPath $StderrFile) {
            try {
                $stderrInfo = Get-Item -LiteralPath $StderrFile -ErrorAction Stop
                $stderrBytes = $stderrInfo.Length
                $stderrLines = @(Get-Content -LiteralPath $StderrFile -ErrorAction SilentlyContinue).Count
            }
            catch {}
        }

        $lineCount = $stdoutLines + $stderrLines
        if ($lineCount -gt $lastLineCount) {
            $activityCount += ($lineCount - $lastLineCount)
            $lastLineCount = $lineCount
        }

        $totalKb = [math]::Round(($stdoutBytes + $stderrBytes) / 1KB, 1)
        $indicator = $spinner[$spinnerIndex % $spinner.Count]
        $spinnerIndex++

        Write-Host (
            "`r    {0} Elapsed: {1}s | Activity: {2} events | Output: {3} KB     " -f
            $indicator,
            $elapsed,
            $activityCount,
            $totalKb
        ) -NoNewline -ForegroundColor Yellow

        Start-Sleep -Milliseconds 400
        $Process.Refresh()
    }

    $elapsed = [int]((Get-Date) - $started).TotalSeconds
    Write-Host (
        "`r    Done | Elapsed: {0}s | Activity: {1} events                    " -f
        $elapsed,
        $activityCount
    ) -ForegroundColor Green
}

function Refresh-ProcessPath {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machine;$user"
}

function Get-CommandPath([string]$Name) {
    try {
        return (Get-Command $Name -ErrorAction Stop).Source
    }
    catch {
        return $null
    }
}

function Test-CodexBridgeConfigured {

    $serverPattern = if ($script:BridgeProduct -eq 'AutoCAD') {
        'best-cad-mcp-autocad'
    }
    else {
        'aec-model-bridge(?:-revit-(?:2024|2025|2026|2027))?'
    }

    $codex = Get-CommandPath 'codex.cmd'
    if (-not $codex) {
        $codex = Get-CommandPath 'codex.exe'
    }

    if ($codex) {
        try {
            $output = & $codex mcp list 2>&1 | Out-String
            if ($LASTEXITCODE -eq 0 -and $output -match "(?im)^\s*(?:$serverPattern)(?:\s|$)") {
                return $true
            }
        }
        catch {
            Write-WarningMessage "Codex MCP list could not be queried: $($_.Exception.Message)"
        }
    }

    $configPath = Join-Path $env:USERPROFILE '.codex\config.toml'
    if (-not (Test-Path -LiteralPath $configPath)) {
        return $false
    }

    try {
        $content = Get-Content -LiteralPath $configPath -Raw

        # Accept both normal and quoted TOML table names.
        $tomlPattern = if ($script:BridgeProduct -eq 'AutoCAD') {
            '(?im)^\s*\[\s*mcp_servers\.(?:"best-cad-mcp-autocad"|''best-cad-mcp-autocad''|best-cad-mcp-autocad)\s*\]\s*$'
        }
        else {
            '(?im)^\s*\[\s*mcp_servers\.(?:"aec-model-bridge(?:-revit-(?:2024|2025|2026|2027))?"|''aec-model-bridge(?:-revit-(?:2024|2025|2026|2027))?''|aec-model-bridge(?:-revit-(?:2024|2025|2026|2027))?)\s*\]\s*$'
        }
        if ($content -match $tomlPattern) {
            return $true
        }

        # Also detect newer/alternate TOML layouts that contain the server key.
        $keyPattern = if ($script:BridgeProduct -eq 'AutoCAD') {
            '(?im)^\s*(?:"best-cad-mcp-autocad"|''best-cad-mcp-autocad''|best-cad-mcp-autocad)\s*='
        }
        else {
            '(?im)^\s*(?:"aec-model-bridge(?:-revit-(?:2024|2025|2026|2027))?"|''aec-model-bridge(?:-revit-(?:2024|2025|2026|2027))?''|aec-model-bridge(?:-revit-(?:2024|2025|2026|2027))?)\s*='
        }
        if ($content -match $keyPattern) {
            return $true
        }

        return $false
    }
    catch {
        Write-WarningMessage "Codex configuration could not be read: $($_.Exception.Message)"
        return $false
    }
}

function Get-ClaudeConfigPaths {
    $paths = [System.Collections.Generic.List[string]]::new()

    # Traditional Win32 installation.
    $standardPath = Join-Path $env:APPDATA 'Claude\claude_desktop_config.json'
    $paths.Add($standardPath)

    # Microsoft Store / MSIX installation. The package suffix can change,
    # so every Claude_* package is inspected instead of using a fixed name.
    $packagesRoot = Join-Path $env:LOCALAPPDATA 'Packages'
    if (Test-Path -LiteralPath $packagesRoot) {
        Get-ChildItem -LiteralPath $packagesRoot -Directory -Filter 'Claude_*' -ErrorAction SilentlyContinue |
            ForEach-Object {
                $paths.Add(
                    (Join-Path $_.FullName 'LocalCache\Roaming\Claude\claude_desktop_config.json')
                )
            }
    }

    return @($paths | Sort-Object -Unique)
}

function Get-ActiveClaudeConfigPaths {
    $allPaths = @(Get-ClaudeConfigPaths)
    $active = [System.Collections.Generic.List[string]]::new()

    foreach ($path in $allPaths) {
        $parent = Split-Path $path -Parent

        # Existing config or existing package/profile directory indicates a usable target.
        if ((Test-Path -LiteralPath $path) -or (Test-Path -LiteralPath $parent)) {
            $active.Add($path)
        }
    }

    # If no installation-specific path exists yet, keep the standard path as fallback.
    if ($active.Count -eq 0) {
        $active.Add((Join-Path $env:APPDATA 'Claude\claude_desktop_config.json'))
    }

    return @($active | Sort-Object -Unique)
}

function Test-ClaudeBridgeConfigured {
    $paths = @(Get-ActiveClaudeConfigPaths)
    $found = $false

    foreach ($configPath in $paths) {
        if (-not (Test-Path -LiteralPath $configPath)) {
            continue
        }

        try {
            $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
            $mcpServersProperty = $config.PSObject.Properties['mcpServers']

            if ($mcpServersProperty -and $mcpServersProperty.Value) {
                $matchingEntries = @(
                    $mcpServersProperty.Value.PSObject.Properties |
                        Where-Object {
                            if ($script:BridgeProduct -eq 'AutoCAD') {
                                $_.Name -eq 'best-cad-mcp-autocad'
                            }
                            else {
                                $_.Name -eq 'aec-model-bridge' -or $_.Name -match '^aec-model-bridge-revit-(2024|2025|2026|2027)$'
                            }
                        }
                )

                if ($matchingEntries.Count -gt 0) {
                    $found = $true
                }
            }
        }
        catch {
            Write-WarningMessage "Claude configuration could not be parsed: $configPath"
        }
    }

    return $found
}

function Test-AntigravityBridgeConfigured {
    foreach ($configPath in @(
        (Join-Path $env:USERPROFILE '.gemini\config\mcp_config.json'),
        (Join-Path $env:USERPROFILE '.gemini\settings.json')
    )) {
        if (-not (Test-Path -LiteralPath $configPath)) { continue }
        try {
            $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
            $servers = $config.PSObject.Properties['mcpServers']
            if ($servers -and $servers.Value -and @($servers.Value.PSObject.Properties | Where-Object {
                if ($script:BridgeProduct -eq 'AutoCAD') { $_.Name -eq 'best-cad-mcp-autocad' }
                else { $_.Name -match '^aec-model-bridge-revit-(2024|2025|2026|2027)$' }
            }).Count -gt 0) { return $true }
        }
        catch { Write-WarningMessage "MCP configuration could not be parsed: $configPath" }
    }
    return $false
}

function Get-InstallerVersionFromText([string]$Text) {
    $match = [regex]::Match($Text, "(?m)^\`$script:InstallerVersion = '(\d{4}\.\d{2}\.\d{2}\.\d{2})'")
    if ($match.Success) { return $match.Groups[1].Value }
    return $null
}

function Test-InstallerText([string]$Text) {
    # A downloaded installer must be a complete AutoCAD setup whose payload parses.
    if ($Text -notmatch '(?m)^set "AECMB_PRODUCT=AutoCAD"') { return 'it is not the AutoCAD installer' }
    $lines = $Text -split "`r?`n"
    $marker = [Array]::IndexOf($lines, '# POWERSHELL_PAYLOAD')
    if ($marker -lt 0) { return 'the PowerShell payload marker is missing' }
    $code = $lines[($marker + 1)..($lines.Length - 1)] -join [Environment]::NewLine
    $parseErrors = $null
    [void][System.Management.Automation.Language.Parser]::ParseInput($code, [ref]$null, [ref]$parseErrors)
    if ($parseErrors.Count -gt 0) { return 'its PowerShell payload does not parse' }
    return $null
}

function Update-InstallerIfNewer {
    # Returns $true when a validated newer installer was saved and a restart is needed.
    if ($env:AECMB_SELF_UPDATED -eq '1' -or $env:AECMB_SKIP_SELF_UPDATE -eq '1') {
        Write-Info "Installer version $($script:InstallerVersion)."
        return $false
    }
    Write-Info "Installer version $($script:InstallerVersion). Checking for a newer installer..."
    $url = if ($env:AECMB_INSTALLER_UPDATE_URL) { $env:AECMB_INSTALLER_UPDATE_URL } else { $script:InstallerUpdateUrl }
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 15 -ErrorAction Stop
        $content = $response.Content
        if ($content -is [byte[]]) { $content = [System.Text.Encoding]::UTF8.GetString($content) }
    }
    catch {
        Write-WarningMessage "Could not check for a newer installer: $($_.Exception.Message). Continuing with this version."
        return $false
    }

    $remoteVersion = Get-InstallerVersionFromText $content
    if (-not $remoteVersion) {
        Write-WarningMessage 'The published installer has no readable version. Continuing with this version.'
        return $false
    }
    if ([version]$remoteVersion -le [version]$script:InstallerVersion) {
        Write-Ok "Installer is up to date ($($script:InstallerVersion))."
        return $false
    }
    $problem = Test-InstallerText $content
    if ($problem) {
        Write-WarningMessage "Installer $remoteVersion was found but not used because $problem. Continuing with this version."
        return $false
    }

    $target = Join-Path $env:TEMP 'SetupMCP_AutoCAD_selfupdate.cmd'
    [System.IO.File]::WriteAllText($target, $content, [System.Text.UTF8Encoding]::new($false))
    Write-Ok "Installer $remoteVersion was downloaded (current $($script:InstallerVersion)). This window will restart it."
    return $true
}

function Invoke-GitQuery {
    param(
        [Parameter(Mandatory)][string]$GitExe,
        [Parameter(Mandatory)][string[]]$Arguments,
        [int]$TimeoutMs = 20000
    )

    # Read-only query with a timeout so an offline network cannot block the menu.
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new($GitExe)
    $startInfo.Arguments = Join-NativeArguments $Arguments
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true
    $startInfo.EnvironmentVariables['GIT_TERMINAL_PROMPT'] = '0'
    try {
        $process = [System.Diagnostics.Process]::Start($startInfo)
    }
    catch {
        return [pscustomobject]@{ ExitCode = -1; Output = ''; Error = $_.Exception.Message }
    }
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit($TimeoutMs)) {
        try { $process.Kill() } catch {}
        return [pscustomobject]@{ ExitCode = -1; Output = ''; Error = 'timed out' }
    }
    $process.WaitForExit()
    return [pscustomobject]@{
        ExitCode = $process.ExitCode
        Output = $stdout.Result.Trim()
        Error = $stderr.Result.Trim()
    }
}

function Get-AutoCadUpdateStatus {
    # Compares the installed checkout with fork/master without fetching or changing files.
    $root = Join-Path $env:ProgramData 'AECModelBridge\autocad'
    $repoUrl = 'https://github.com/Moorlack/best-cad-mcp.git'
    $status = [pscustomobject]@{ State = 'Unknown'; Local = ''; Remote = ''; Detail = '' }
    if (-not (Test-Path -LiteralPath (Join-Path $root '.git'))) {
        $status.State = 'NotInstalled'
        return $status
    }

    $git = Get-CommandPath 'git.exe'
    if (-not $git) {
        $status.Detail = 'Git was not found'
        return $status
    }

    $safeDirectory = 'safe.directory=' + ($root -replace '\\', '/')
    $local = Invoke-GitQuery -GitExe $git -Arguments @('-c', $safeDirectory, '-C', $root, 'rev-parse', 'HEAD')
    if ($local.ExitCode -ne 0 -or $local.Output -notmatch '^[0-9a-f]{40}$') {
        $status.Detail = 'the installed version could not be read'
        return $status
    }
    $status.Local = $local.Output

    $remote = Invoke-GitQuery -GitExe $git -Arguments @('ls-remote', $repoUrl, 'refs/heads/master')
    $remoteSha = (($remote.Output -split '\s+') | Select-Object -First 1)
    if ($remote.ExitCode -ne 0 -or $remoteSha -notmatch '^[0-9a-f]{40}$') {
        $status.Detail = "the latest version could not be checked ($($remote.Error))"
        return $status
    }
    $status.Remote = $remoteSha

    if ($remoteSha -eq $status.Local) {
        $status.State = 'UpToDate'
    }
    else {
        # Unknown remote commits exit with an error, which also means an update exists.
        $ancestor = Invoke-GitQuery -GitExe $git -Arguments @('-c', $safeDirectory, '-C', $root, 'merge-base', '--is-ancestor', $remoteSha, 'HEAD')
        $status.State = if ($ancestor.ExitCode -eq 0) { 'LocalAhead' } else { 'UpdateAvailable' }
    }

    $changes = Invoke-GitQuery -GitExe $git -Arguments @('-c', $safeDirectory, '-C', $root, 'status', '--porcelain')
    if ($changes.ExitCode -eq 0 -and $changes.Output) {
        $status.Detail = 'local source changes will be saved to Git stash before an update'
    }
    return $status
}

function Write-AutoCadUpdateStatus($Status) {
    $short = { param($sha) if ($sha) { $sha.Substring(0, 7) } else { '?' } }
    switch ($Status.State) {
        'UpToDate' { Write-Ok "No updates found: installed AutoCAD MCP $(& $short $Status.Local) is the latest fork/master. Every action below only repairs and re-verifies." }
        'UpdateAvailable' { Write-Host "[UPDATE] AutoCAD MCP update available: installed $(& $short $Status.Local) -> latest $(& $short $Status.Remote). Any Install/Repair action or the server-only update applies it." -ForegroundColor Cyan }
        'LocalAhead' { Write-WarningMessage "Installed AutoCAD MCP $(& $short $Status.Local) is newer than fork/master $(& $short $Status.Remote). No update will be downloaded; actions only repair." }
        'NotInstalled' { Write-Info 'AutoCAD MCP is not installed yet; an Install action downloads the latest fork/master.' }
        default { Write-WarningMessage "Could not check for AutoCAD MCP updates: $($Status.Detail). Actions still try to update." }
    }
    if ($Status.State -ne 'Unknown' -and $Status.Detail) { Write-Info "Note: $($Status.Detail)." }
}

function Get-UpdateSuffix($Status) {
    switch ($Status.State) {
        'UpToDate' { return ' [no updates found: repair only]' }
        'LocalAhead' { return ' [no updates found: repair only]' }
        'UpdateAvailable' { return ' [includes update]' }
        default { return '' }
    }
}

function Select-TargetClient {
    Start-Step `
        -Title 'Detect existing MCP configuration' `
        -Explanation 'The script checks Codex, Claude, and Google Antigravity configuration. Selecting an already configured client safely repairs and extends its bridge entries; unrelated MCP servers remain untouched. Complete cleanup is always available.'

    $script:SelectedAction = 'Install'

    $codexConfigured = Test-CodexBridgeConfigured
    $claudeConfigured = Test-ClaudeBridgeConfigured
    $antigravityConfigured = Test-AntigravityBridgeConfigured

    $updateSuffix = ''
    $installSuffix = ''
    if ($script:BridgeProduct -eq 'AutoCAD') {
        Write-Info 'Checking the installed AutoCAD MCP version against fork/master...'
        $script:AutoCadUpdateStatus = Get-AutoCadUpdateStatus
        Write-AutoCadUpdateStatus $script:AutoCadUpdateStatus
        $updateSuffix = Get-UpdateSuffix $script:AutoCadUpdateStatus
        # A new client registration reuses the shared server code.
        $installSuffix = if ($script:AutoCadUpdateStatus.State -in @('UpToDate', 'LocalAhead')) { ' [no code updates: registers this client only]' } else { $updateSuffix }
    }

    Write-Host ''
    Write-Host 'Available actions:'

    $options = [System.Collections.Generic.List[object]]::new()
    $nextNumber = 1

    $codexLabel = if ($codexConfigured) { "Repair or extend $($script:BridgeProductLabel) bridge for Codex$updateSuffix" } else { "Install $($script:BridgeProductLabel) bridge for Codex$installSuffix" }
    Write-Host "$nextNumber - $codexLabel" -ForegroundColor Green
    $options.Add([pscustomobject]@{
        Number = [string]$nextNumber
        Client = 'Codex'
        Action = 'Install'
    })
    $nextNumber++

    $antigravityLabel = if ($antigravityConfigured) { "Repair or extend $($script:BridgeProductLabel) bridge for Google Antigravity$updateSuffix" } else { "Install $($script:BridgeProductLabel) bridge for Google Antigravity$installSuffix" }
    Write-Host "$nextNumber - $antigravityLabel" -ForegroundColor Green
    $options.Add([pscustomobject]@{
        Number = [string]$nextNumber
        Client = 'Antigravity'
        Action = 'Install'
    })
    $nextNumber++

    $claudeLabel = if ($claudeConfigured) { "Repair or extend $($script:BridgeProductLabel) bridge for Claude$updateSuffix" } else { "Install $($script:BridgeProductLabel) bridge for Claude$installSuffix" }
    Write-Host "$nextNumber - $claudeLabel" -ForegroundColor Green
    $options.Add([pscustomobject]@{
        Number = [string]$nextNumber
        Client = 'Claude'
        Action = 'Install'
    })
    $nextNumber++

    # All AI clients start the same installed AutoCAD MCP code, so a code-only
    # update does not need to rewrite any client registration.
    $autoCadInstalled = ($script:BridgeProduct -eq 'AutoCAD') -and
        (Test-Path -LiteralPath (Join-Path $env:ProgramData 'AECModelBridge\autocad\.git'))
    if ($autoCadInstalled) {
        $serverLabel = if ($script:AutoCadUpdateStatus.State -in @('UpToDate', 'LocalAhead')) {
            'Re-verify the shared AutoCAD MCP server (no updates found: repair only; client settings unchanged)'
        }
        else {
            "Update only the shared AutoCAD MCP server (all clients; client settings unchanged)$updateSuffix"
        }
        Write-Host "$nextNumber - $serverLabel" -ForegroundColor Cyan
        $options.Add([pscustomobject]@{
            Number = [string]$nextNumber
            Client = $null
            Action = 'UpdateServer'
        })
        $nextNumber++
    }

    Write-Host "$nextNumber - Completely remove the $($script:BridgeProductLabel) MCP bridge and its remaining files from this computer" -ForegroundColor Yellow
    $options.Add([pscustomobject]@{
        Number = [string]$nextNumber
        Client = $null
        Action = 'FullRemove'
    })
    $nextNumber++

    Write-Host "$nextNumber - Cancel"
    $cancelNumber = [string]$nextNumber

    do {
        $selection = Read-Host "Select an action"
        $selectedOption = $options | Where-Object { $_.Number -eq $selection } | Select-Object -First 1
        $valid = ($selection -eq $cancelNumber) -or ($null -ne $selectedOption)
    } until ($valid)

    if ($selection -eq $cancelNumber) {
        Write-WarningMessage 'Operation was cancelled.'
        return $null
    }

    if ($selectedOption.Action -eq 'FullRemove') {
        Write-Host ''
        Write-WarningMessage "This performs a cleanup even when no AI client registration is detected. It removes only $($script:BridgeProductLabel) registrations and files; the other product's bridge remains untouched."
        Write-Info 'Git, Python, Node.js, Codex CLI, .NET SDKs, and .NET Framework Developer Pack will remain installed.'

        $answer = Read-Host "Are you sure you want to remove the $($script:BridgeProductLabel) bridge from this computer? [Y/N]"
        if ($answer -notmatch '^(?i)y(?:es)?$') {
            Write-WarningMessage 'Complete removal was cancelled.'
            return $null
        }

        $script:SelectedAction = 'FullRemove'
        Write-WarningMessage "Complete $($script:BridgeProductLabel) bridge removal was selected."
        return $script:BridgeProduct
    }

    if ($selectedOption.Action -eq 'UpdateServer') {
        $script:SelectedAction = 'UpdateServer'
        Write-Ok 'Shared AutoCAD MCP server update was selected. Client registrations will not be changed.'
        return 'Server'
    }

    $script:SelectedAction = 'Install'
    Write-Ok "$($selectedOption.Client) was selected."
    return $selectedOption.Client
}

function Get-RunningAutoCadMcpProcesses([string]$AutoCadRoot) {
    $prefix = [System.IO.Path]::GetFullPath($AutoCadRoot).TrimEnd('\') + '\'
    @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object {
        $_.ExecutablePath -and $_.CommandLine -and
        $_.ExecutablePath.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase) -and
        $_.CommandLine -match 'src\.server'
    })
}

function Confirm-NoRunningAutoCadMcp([string]$AutoCadRoot) {
    # Running clients keep the old server code and tool list until restarted.
    $running = Get-RunningAutoCadMcpProcesses $AutoCadRoot
    if (-not $running.Count) {
        Write-Ok 'No running AutoCAD MCP server processes were found.'
        return $true
    }
    Write-WarningMessage "$($running.Count) AutoCAD MCP server process(es) are still running. Clients keep the old tools until they are fully closed (including the tray)."
    $running | ForEach-Object { Write-Info ("PID {0}, started {1}" -f $_.ProcessId, $_.CreationDate) }
    $answer = Read-Host 'Close Claude, Codex and Antigravity first. Continue the update anyway? [Y/N]'
    return ($answer -match '^(?i)y(?:es)?$')
}

function Ensure-WinGet {
    Write-Info "Checking whether WinGet is available. WinGet is used to install missing dependencies silently."

    if (Get-CommandPath 'winget.exe') {
        Write-Ok "WinGet is available."
        return
    }

    Write-WarningMessage "WinGet is missing. Attempting to install Microsoft App Installer."
    $bundle = Join-Path $env:TEMP 'Microsoft.DesktopAppInstaller.msixbundle'

    try {
        Invoke-WebRequest -Uri 'https://aka.ms/getwinget' -OutFile $bundle -UseBasicParsing
        Add-AppxPackage -Path $bundle
        Refresh-ProcessPath
    }
    catch {
        Write-ErrorMessage "Unable to install WinGet automatically: $($_.Exception.Message)"
        Write-ErrorMessage "Install Microsoft App Installer from Microsoft Store, then run this script again."
        throw
    }

    if (-not (Get-CommandPath 'winget.exe')) {
        throw 'WinGet installation completed, but winget.exe is still unavailable. Sign out or restart Windows and run the script again.'
    }

    Write-Ok "WinGet was installed."
}

function Install-WinGetPackage {
    param(
        [Parameter(Mandatory)][string]$Id,
        [Parameter(Mandatory)][string]$DisplayName,
        [string]$Version,
        [string]$Source
    )

    $arguments = @(
        'install',
        '--exact',
        '--id', $Id,
        '--silent',
        '--accept-package-agreements',
        '--accept-source-agreements',
        '--disable-interactivity'
    )

    if ($Version) {
        $arguments += @('--version', $Version)
    }
    if ($Source) {
        $arguments += @('--source', $Source)
    }

    Invoke-CheckedProcess `
        -FilePath 'winget.exe' `
        -Arguments $arguments `
        -Description "Install or update $DisplayName"

    Refresh-ProcessPath
}

function Test-CodexDesktopInstalled {
    $appx = @(Get-AppxPackage -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -eq 'OpenAI.ChatGPT' -or
        ($_.Publisher -match 'OpenAI' -and $_.Name -match 'ChatGPT|Codex')
    })
    if ($appx) { return $true }

    $paths = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\ChatGPT\ChatGPT.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Codex\Codex.exe'),
        (Join-Path $env:ProgramFiles 'ChatGPT\ChatGPT.exe')
    )
    return [bool]($paths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1)
}

function Ensure-CodexDesktop {
    if (Test-CodexDesktopInstalled) {
        Write-Ok 'ChatGPT desktop app with Codex is installed.'
        return
    }

    Write-WarningMessage 'ChatGPT desktop app with Codex was not found. Installing it from Microsoft Store through WinGet.'
    Install-WinGetPackage -Id '9PLM9XGG6VKS' -DisplayName 'ChatGPT desktop app with Codex' -Source 'msstore'

    if (-not (Test-CodexDesktopInstalled)) {
        Write-WarningMessage 'The ChatGPT desktop app installation was handed to Microsoft Store but could not yet be detected. Complete any Store prompt, then open ChatGPT and choose Codex.'
        return
    }

    Write-Ok 'ChatGPT desktop app with Codex is ready. Sign in with the same OpenAI account, then choose Codex in the app.'
}

function Test-DotNetSdk([string]$Major) {
    $dotnet = Get-CommandPath 'dotnet.exe'
    if (-not $dotnet) {
        return $false
    }

    try {
        $sdks = & $dotnet --list-sdks 2>$null
        return [bool]($sdks | Where-Object { $_ -match "^$([regex]::Escape($Major))\." })
    }
    catch {
        return $false
    }
}

function Get-PythonExecutable {
    Refresh-ProcessPath

    $py = Get-CommandPath 'py.exe'
    if ($py) {
        foreach ($selector in @('-3.14', '-3.13', '-3.12', '-3.11')) {
            try {
                $candidate = & $py $selector -c "import sys; print(sys.executable)" 2>$null
                if ($LASTEXITCODE -eq 0 -and $candidate) {
                    return ($candidate | Select-Object -First 1).Trim()
                }
            }
            catch {}
        }
    }

    $python = Get-CommandPath 'python.exe'
    if ($python) {
        try {
            $versionOk = & $python -c "import sys; print(int(sys.version_info >= (3,11)))" 2>$null
            if ($LASTEXITCODE -eq 0 -and ($versionOk | Select-Object -First 1).Trim() -eq '1') {
                return $python
            }
        }
        catch {}
    }

    return $null
}

function Get-RevitVersions {
    $versions = [System.Collections.Generic.HashSet[string]]::new()

    Write-Info "Scanning standard Autodesk folders and Windows uninstall records for Revit 2024-2027."

    foreach ($year in 2024..2027) {
        $exe = "C:\Program Files\Autodesk\Revit $year\Revit.exe"
        if (Test-Path -LiteralPath $exe) {
            [void]$versions.Add([string]$year)
        }
    }

    $uninstallRoots = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
    )

    foreach ($root in $uninstallRoots) {
        try {
            Get-ItemProperty $root -ErrorAction SilentlyContinue |
                Where-Object { $_.DisplayName -match '^Autodesk Revit (2024|2025|2026|2027)' } |
                ForEach-Object {
                    if ($_.DisplayName -match '(2024|2025|2026|2027)') {
                        [void]$versions.Add($Matches[1])
                    }
                }
        }
        catch {}
    }

    return @($versions | Sort-Object)
}

function Get-AutoCadVersions {
    $versions = [System.Collections.Generic.HashSet[string]]::new()

    Write-Info 'Scanning standard Autodesk folders and Windows uninstall records for full AutoCAD 2020 and later.'

    foreach ($year in 2020..2035) {
        $exe = "C:\Program Files\Autodesk\AutoCAD $year\acad.exe"
        if (Test-Path -LiteralPath $exe) {
            [void]$versions.Add([string]$year)
        }
    }

    $uninstallRoots = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
    )

    foreach ($root in $uninstallRoots) {
        try {
            Get-ItemProperty $root -ErrorAction SilentlyContinue |
                Where-Object {
                    $_.DisplayName -match '^(?:Autodesk )?AutoCAD (20[2-9][0-9])' -and
                    $_.DisplayName -notmatch '(?i)\bLT\b'
                } |
                ForEach-Object {
                    if ($_.DisplayName -match '(20[2-9][0-9])') {
                        [void]$versions.Add($Matches[1])
                    }
                }
        }
        catch {}
    }

    return @($versions | Sort-Object)
}

function Get-AllowedDirectories {
    Write-Info "Collecting every available local, removable, and mapped network drive root."

    $items = [System.Collections.Generic.List[string]]::new()

    foreach ($drive in [System.IO.DriveInfo]::GetDrives()) {
        try {
            if ($drive.IsReady -and $drive.DriveType -in @(
                [System.IO.DriveType]::Fixed,
                [System.IO.DriveType]::Removable,
                [System.IO.DriveType]::Network
            )) {
                $items.Add($drive.RootDirectory.FullName)
            }
        }
        catch {}
    }

    try {
        Get-CimInstance Win32_LogicalDisk -Filter "DriveType=4" -ErrorAction SilentlyContinue |
            ForEach-Object {
                if ($_.ProviderName) {
                    $items.Add($_.ProviderName.TrimEnd('\'))
                }
            }
    }
    catch {}

    $unique = @($items | Where-Object { $_ } | Sort-Object -Unique)
    if (-not $unique) {
        $unique = @("$env:SystemDrive\")
    }

    return $unique
}

function Set-PersistentBridgeEnvironment {
    param(
        [Parameter(Mandatory)][string]$Workspace,
        [Parameter(Mandatory)][string]$Allowed
    )

    Write-Info "Saving MCP_REVIT environment variables in the current user profile so they remain available after sign-out and restart."

    # Contract v2 discovers the active Revit instance, its dynamic port,
    # and its per-session bearer token through the local discovery registry.
    # A persisted fixed URL forces the obsolete legacy path and breaks v2.
    [Environment]::SetEnvironmentVariable('MCP_REVIT_BRIDGE_URL', $null, 'User')
    Remove-Item Env:MCP_REVIT_BRIDGE_URL -ErrorAction SilentlyContinue
    Write-Info 'Removed obsolete fixed MCP_REVIT_BRIDGE_URL override.'

    $values = @{
        MCP_REVIT_MODE                = 'bridge'
        MCP_REVIT_APPROVAL_MODE        = 'auto'
        MCP_REVIT_ALLOW_PYTHON_HOST    = 'true'
        MCP_REVIT_ENABLE_USER_MODULES  = 'true'
        MCP_REVIT_WORKSPACE_DIR        = $Workspace
        MCP_REVIT_ALLOWED_DIRECTORIES  = $Allowed
    }

    foreach ($pair in $values.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable($pair.Key, $pair.Value, 'User')
        Set-Item -Path "Env:$($pair.Key)" -Value $pair.Value
        Write-Info "$($pair.Key) = $($pair.Value)"
    }

    Write-Ok "Persistent MCP environment variables were configured."
}

function Quote-NativeArgument([string]$Value) {
    if ($null -eq $Value) {
        return '""'
    }

    if ($Value -notmatch '[\s"]') {
        return $Value
    }

    $escaped = $Value -replace '(\\*)"', '$1$1\"'
    $escaped = $escaped -replace '(\\+)$', '$1$1'
    return '"' + $escaped + '"'
}

function Join-NativeArguments([string[]]$Values) {
    return (($Values | ForEach-Object { Quote-NativeArgument ([string]$_) }) -join ' ')
}

function Invoke-CheckedProcess {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$Arguments,
        [Parameter(Mandatory)][string]$Description,
        [string]$WorkingDirectory
    )

    if ([string]::IsNullOrWhiteSpace($FilePath)) {
        throw "Executable path is empty for step: $Description"
    }

    Write-Host "  > $Description" -ForegroundColor White

    $stdoutFile = Join-Path $env:TEMP ("aecmb_stdout_{0}.log" -f ([guid]::NewGuid().ToString('N')))
    $stderrFile = Join-Path $env:TEMP ("aecmb_stderr_{0}.log" -f ([guid]::NewGuid().ToString('N')))
    $oldLocation = Get-Location

    try {
        if ($WorkingDirectory) {
            Set-Location -LiteralPath $WorkingDirectory
        }

        $argumentLine = Join-NativeArguments $Arguments

        $process = Start-Process `
            -FilePath $FilePath `
            -ArgumentList $argumentLine `
            -WorkingDirectory $(if ($WorkingDirectory) { $WorkingDirectory } else { (Get-Location).Path }) `
            -PassThru `
            -NoNewWindow `
            -RedirectStandardOutput $stdoutFile `
            -RedirectStandardError $stderrFile `
            -ErrorAction Stop

        Wait-ProcessWithProgress `
            -Process $process `
            -StdoutFile $stdoutFile `
            -StderrFile $stderrFile

        $process.WaitForExit()
        $process.Refresh()
        $exitCode = [int]$process.ExitCode

        $stdout = if (Test-Path -LiteralPath $stdoutFile) {
            Get-Content -LiteralPath $stdoutFile -Raw -ErrorAction SilentlyContinue
        } else { '' }

        $stderr = if (Test-Path -LiteralPath $stderrFile) {
            Get-Content -LiteralPath $stderrFile -Raw -ErrorAction SilentlyContinue
        } else { '' }

        if ($script:LogPath) {
            Add-Content -LiteralPath $script:LogPath -Value "`r`n--- $Description ---" -ErrorAction SilentlyContinue
            if ($stdout) { Add-Content -LiteralPath $script:LogPath -Value $stdout -ErrorAction SilentlyContinue }
            if ($stderr) { Add-Content -LiteralPath $script:LogPath -Value $stderr -ErrorAction SilentlyContinue }
        }

        if ($exitCode -ne 0) {
            Write-ErrorMessage "$Description failed with exit code $exitCode."

            $details = @($stderr, $stdout) |
                Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
                Select-Object -First 1

            if ($details) {
                Write-Host ''
                Write-Host 'Last output:' -ForegroundColor DarkGray
                $details.Trim().Split([Environment]::NewLine) |
                    Select-Object -Last 12 |
                    ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
            }

            if ($script:LogPath) {
                Write-Info "Full details were saved to: $script:LogPath"
            }

            throw "$Description returned exit code $exitCode."
        }

        Write-Ok $Description
    }
    finally {
        Set-Location -LiteralPath $oldLocation
        Remove-Item -LiteralPath $stdoutFile, $stderrFile -Force -ErrorAction SilentlyContinue
    }
}

function Test-McpServerStartup {
    param(
        [Parameter(Mandatory)][string]$PythonExe,
        [Parameter(Mandatory)][string]$WorkingDirectory
    )

    Write-Host '  > Starting the Python MCP server for a short self-test...' -ForegroundColor White

    $stdoutFile = Join-Path $env:TEMP ("aecmb_mcp_stdout_{0}.log" -f ([guid]::NewGuid().ToString('N')))
    $stderrFile = Join-Path $env:TEMP ("aecmb_mcp_stderr_{0}.log" -f ([guid]::NewGuid().ToString('N')))

    try {
        $process = Start-Process `
            -FilePath $PythonExe `
            -ArgumentList '-m revit_mcp_server.mcp_server' `
            -WorkingDirectory $WorkingDirectory `
            -PassThru `
            -NoNewWindow `
            -RedirectStandardOutput $stdoutFile `
            -RedirectStandardError $stderrFile `
            -ErrorAction Stop

        if ($process.WaitForExit(5000)) {
            $stdout = if (Test-Path -LiteralPath $stdoutFile) {
                Get-Content -LiteralPath $stdoutFile -Raw -ErrorAction SilentlyContinue
            } else { '' }

            $stderr = if (Test-Path -LiteralPath $stderrFile) {
                Get-Content -LiteralPath $stderrFile -Raw -ErrorAction SilentlyContinue
            } else { '' }

            if ($script:LogPath) {
                Add-Content -LiteralPath $script:LogPath -Value "`r`n--- Python MCP startup test ---" -ErrorAction SilentlyContinue
                if ($stdout) { Add-Content -LiteralPath $script:LogPath -Value $stdout -ErrorAction SilentlyContinue }
                if ($stderr) { Add-Content -LiteralPath $script:LogPath -Value $stderr -ErrorAction SilentlyContinue }
            }

            Write-ErrorMessage "The Python MCP server stopped during startup."
            $details = @($stderr, $stdout) |
                Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
                Select-Object -First 1

            if ($details) {
                $details.Trim().Split([Environment]::NewLine) |
                    Select-Object -Last 12 |
                    ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
            }

            throw "The MCP server exited during startup with code $($process.ExitCode)."
        }

        & taskkill.exe /PID $process.Id /T /F *> $null
        try { $process.WaitForExit(3000) | Out-Null } catch {}

        Write-Ok 'Python MCP server startup test passed.'
    }
    finally {
        Remove-Item -LiteralPath $stdoutFile, $stderrFile -Force -ErrorAction SilentlyContinue
    }
}

function Backup-File([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }

    $backup = "$Path.bak_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    Copy-Item -LiteralPath $Path -Destination $backup -Force
    Write-Info "Existing configuration was backed up to $backup."
    return $backup
}

function Set-CodexBridgeApprovalModes {
    $configPath = Join-Path $env:USERPROFILE '.codex\config.toml'
    if (-not (Test-Path -LiteralPath $configPath)) { return }
    Backup-File $configPath | Out-Null
    $content = Get-Content -LiteralPath $configPath -Raw
    $script:CodexApprovalChanged = $false

    foreach ($name in @('aec-model-bridge-revit-2024','aec-model-bridge-revit-2025','aec-model-bridge-revit-2026','aec-model-bridge-revit-2027','best-cad-mcp-autocad')) {
        $escapedName = [regex]::Escape($name)
        $pattern = "(?ms)(^\[mcp_servers\.$escapedName\]\s*\r?\n)(.*?)(?=^\[|\z)"
        $content = [regex]::Replace($content, $pattern, {
            param($match)
            $header = $match.Groups[1].Value
            $body = $match.Groups[2].Value
            if ($body -match '(?m)^default_tools_approval_mode\s*=') {
                $body = [regex]::Replace($body, '(?m)^default_tools_approval_mode\s*=.*$', 'default_tools_approval_mode = "approve"')
            }
            else {
                $body = 'default_tools_approval_mode = "approve"' + "`r`n" + $body
            }
            $script:CodexApprovalChanged = $true
            return $header + $body
        })
    }

    if ($script:CodexApprovalChanged) {
        [System.IO.File]::WriteAllText($configPath, $content, [System.Text.UTF8Encoding]::new($false))
        Write-Ok 'Codex MCP bridge tools were set to approve without prompts.'
    }
}

function Install-AecRevitBimSkill {
    param(
        [Parameter(Mandatory)][string]$SourceRoot
    )

    $skillNames = @(
        'aec-revit-bim',
        'aec-revit-design-building',
        'aec-revit-create-element',
        'aec-revit-modify-model',
        'aec-revit-query-model',
        'aec-revit-analyze-model'
    )
    $skillsRoot = Join-Path $SourceRoot 'skills'
    $codexSkillsRoot = Join-Path $env:USERPROFILE '.codex\skills'

    foreach ($skillName in $skillNames) {
        $sourceSkillRoot = Join-Path $skillsRoot $skillName
        $sourceSkill = Join-Path $sourceSkillRoot 'SKILL.md'
        if (-not (Test-Path -LiteralPath $sourceSkill)) {
            throw "AEC Revit BIM skill package was not found in the bridge source: $sourceSkill"
        }

        $skillRoot = Join-Path $codexSkillsRoot $skillName
        if (Test-Path -LiteralPath $skillRoot) {
            Remove-Item -LiteralPath $skillRoot -Recurse -Force -ErrorAction Stop
        }
        Copy-Item -LiteralPath $sourceSkillRoot -Destination $skillRoot -Recurse -Force -ErrorAction Stop
    }

    Write-Ok "Six AEC Revit BIM skills were installed for Codex: $codexSkillsRoot"
}

function Remove-AecRevitBimSkill {
    $removed = $false
    foreach ($skillName in @(
        'aec-revit-bim',
        'aec-revit-design-building',
        'aec-revit-create-element',
        'aec-revit-modify-model',
        'aec-revit-query-model',
        'aec-revit-analyze-model'
    )) {
        $skillRoot = Join-Path $env:USERPROFILE ".codex\skills\$skillName"
        if (Test-Path -LiteralPath $skillRoot) {
            Remove-Item -LiteralPath $skillRoot -Recurse -Force -ErrorAction Stop
            $removed = $true
        }
    }
    if ($removed) { Write-Ok 'AEC Revit BIM skills were removed from Codex.' }
}

function Assert-MaintainedAecFork {
    param(
        [Parameter(Mandatory)][string]$SourceRoot
    )

    $requiredSource = @(
        @{
            Path = 'packages\revit-bridge-addin\src\Bridge\BridgeCommandFactory.cs'
            Pattern = 'return new Transaction\(doc, txName\);'
            Feature = 'the Revit transaction recursion fix'
        },
        @{
            Path = 'packages\revit-bridge-addin\src\Bridge\App.cs'
            Pattern = 'Disabled AEC Model Bridge WebView2 dockable pane for Revit 2025 Manage Links stability'
            Feature = 'the Revit 2025 Manage Links stability fix'
        },
        @{
            Path = 'packages\mcp-server-revit\src\revit_mcp_server\config.py'
            Pattern = 'target_version:\s*str\s*\|\s*None'
            Feature = 'version-specific Revit routing configuration'
        },
        @{
            Path = 'packages\mcp-server-revit\src\revit_mcp_server\bridge\discovery.py'
            Pattern = 'version_key\s*=\s*f"\{info\.provider_id\}-\{info\.host_version\}"'
            Feature = 'simultaneous Revit version discovery'
        },
        @{
            Path = 'packages\mcp-server-revit\src\revit_mcp_server\providers\revit.py'
            Pattern = 'def _refresh_bridge_from_registry\(self\)'
            Feature = 'dynamic Revit bridge discovery'
        }
    )

    foreach ($required in $requiredSource) {
        $path = Join-Path $SourceRoot $required.Path
        if (-not (Test-Path -LiteralPath $path)) {
            throw "The maintained fork is incomplete; missing source file: $path"
        }
        if ((Get-Content -LiteralPath $path -Raw -ErrorAction Stop) -notmatch $required.Pattern) {
            throw "The maintained fork does not contain $($required.Feature): $path"
        }
    }

    $requiredSkillFiles = @(
        'skills\aec-revit-bim\SKILL.md',
        'skills\aec-revit-bim\commands\design-building.md',
        'skills\aec-revit-bim\commands\create-element.md',
        'skills\aec-revit-bim\commands\modify-model.md',
        'skills\aec-revit-bim\commands\query-model.md',
        'skills\aec-revit-bim\commands\analyze-model.md',
        'skills\aec-revit-bim\references\tool-routing.md',
        'skills\aec-revit-bim\references\unit-and-coordinate-handling.md',
        'skills\aec-revit-bim\references\building-design-sequence.md',
        'skills\aec-revit-bim\references\mep-workflows.md',
        'skills\aec-revit-bim\references\structural-workflows.md',
        'skills\aec-revit-bim\references\documentation-workflows.md',
        'skills\aec-revit-design-building\SKILL.md',
        'skills\aec-revit-create-element\SKILL.md',
        'skills\aec-revit-modify-model\SKILL.md',
        'skills\aec-revit-query-model\SKILL.md',
        'skills\aec-revit-analyze-model\SKILL.md'
    )

    foreach ($skillFile in $requiredSkillFiles) {
        $skillPath = Join-Path $SourceRoot $skillFile
        if (-not (Test-Path -LiteralPath $skillPath)) {
            throw "The maintained fork does not contain the complete Codex BIM skill package: $skillPath"
        }
    }

    foreach ($claudePluginFile in @(
        '.claude-plugin\marketplace.json',
        'plugins\aec-revit-bim\.claude-plugin\plugin.json',
        'plugins\aec-revit-bim\skills\revit-bim\SKILL.md',
        'plugins\aec-revit-bim\commands\design-building.md',
        'plugins\aec-revit-bim\commands\create-element.md',
        'plugins\aec-revit-bim\commands\modify-model.md',
        'plugins\aec-revit-bim\commands\query-model.md',
        'plugins\aec-revit-bim\commands\analyze-model.md'
    )) {
        $pluginPath = Join-Path $SourceRoot $claudePluginFile
        if (-not (Test-Path -LiteralPath $pluginPath)) {
            throw "The maintained fork does not contain the complete AEC Revit BIM Claude Desktop plugin: $pluginPath"
        }
    }

    foreach ($antigravityPluginFile in @(
        'plugins\aec-revit-bim-antigravity\plugin.json',
        'plugins\aec-revit-bim-antigravity\skills\revit-bim\SKILL.md',
        'plugins\aec-revit-bim-antigravity\skills\design-building\SKILL.md',
        'plugins\aec-revit-bim-antigravity\skills\create-element\SKILL.md',
        'plugins\aec-revit-bim-antigravity\skills\modify-model\SKILL.md',
        'plugins\aec-revit-bim-antigravity\skills\query-model\SKILL.md',
        'plugins\aec-revit-bim-antigravity\skills\analyze-model\SKILL.md'
    )) {
        $pluginPath = Join-Path $SourceRoot $antigravityPluginFile
        if (-not (Test-Path -LiteralPath $pluginPath)) {
            throw "The maintained fork does not contain the complete AEC Revit BIM Antigravity plugin: $pluginPath"
        }
    }

    Write-Ok 'The maintained AEC fork, Revit fixes, Codex skill package, Claude Desktop plugin, and Antigravity plugin were verified.'
}

function Remove-CodexBridge {
    Write-Info "Removing $($script:BridgeProductLabel) MCP entries from Codex."
    Write-Info 'Other MCP servers and all installed dependencies will be preserved.'

    $codex = Get-CommandPath 'codex.cmd'
    if (-not $codex) {
        $codex = Get-CommandPath 'codex.exe'
    }

    if (-not $codex) {
        throw 'Codex CLI is required to remove the MCP registrations, but the codex command was not found.'
    }

    $configPath = Join-Path $env:USERPROFILE '.codex\config.toml'
    Backup-File $configPath | Out-Null

    $namesToRemove = if ($script:BridgeProduct -eq 'AutoCAD') {
        @('best-cad-mcp-autocad')
    }
    else {
        @('aec-model-bridge', 'aec-model-bridge-revit-2024', 'aec-model-bridge-revit-2025', 'aec-model-bridge-revit-2026', 'aec-model-bridge-revit-2027')
    }
    foreach ($name in $namesToRemove) {
        try { & $codex mcp remove $name *> $null } catch {}
    }

    if (Test-CodexBridgeConfigured) {
        throw "Codex still reports a $($script:BridgeProductLabel) MCP entry after removal."
    }

    Write-Ok "$($script:BridgeProductLabel) MCP entries were removed from Codex."
}

function Remove-ClaudeBridge {
    Write-Info "Removing $($script:BridgeProductLabel) MCP entries from every detected Claude configuration."
    Write-Info 'Other MCP servers and all installed dependencies will be preserved.'

    $configPaths = @(Get-ActiveClaudeConfigPaths)
    $utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
    $changed = $false

    foreach ($claudeConfigPath in $configPaths) {
        if (-not (Test-Path -LiteralPath $claudeConfigPath)) {
            continue
        }

        Backup-File $claudeConfigPath | Out-Null

        try {
            $root = Get-Content -LiteralPath $claudeConfigPath -Raw | ConvertFrom-Json
        }
        catch {
            throw "The Claude configuration is invalid JSON and was not changed: $claudeConfigPath. $($_.Exception.Message)"
        }

        $mcpServersProperty = $root.PSObject.Properties['mcpServers']
        if ($mcpServersProperty -and $mcpServersProperty.Value) {
            $namesToRemove = @(
                $mcpServersProperty.Value.PSObject.Properties |
                    Where-Object {
                        if ($script:BridgeProduct -eq 'AutoCAD') { $_.Name -eq 'best-cad-mcp-autocad' }
                        else { $_.Name -eq 'aec-model-bridge' -or $_.Name -match '^aec-model-bridge-revit-(2024|2025|2026|2027)$' }
                    } |
                    Select-Object -ExpandProperty Name
            )

            foreach ($name in $namesToRemove) {
                [void]$mcpServersProperty.Value.PSObject.Properties.Remove($name)
                $changed = $true
            }

            if ($namesToRemove.Count -gt 0) {
                $json = $root | ConvertTo-Json -Depth 100
                [System.IO.File]::WriteAllText($claudeConfigPath, $json, $utf8WithoutBom)
                Write-Ok "$($script:BridgeProductLabel) MCP entries were removed from Claude: $claudeConfigPath"
            }
        }
    }

    if (-not $changed) {
        Write-WarningMessage "No $($script:BridgeProductLabel) bridge registration was found."
    }
}

function Remove-AntigravityBridge {
    $changed = $false
    foreach ($configPath in @(
        (Join-Path $env:USERPROFILE '.gemini\config\mcp_config.json'),
        (Join-Path $env:USERPROFILE '.gemini\settings.json')
    )) {
        if (-not (Test-Path -LiteralPath $configPath)) { continue }
        Backup-File $configPath | Out-Null
        try { $root = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json }
        catch { throw "The MCP configuration is invalid JSON and was not changed: $configPath. $($_.Exception.Message)" }
        $servers = $root.PSObject.Properties['mcpServers']
        if (-not $servers -or -not $servers.Value) { continue }
        $names = @($servers.Value.PSObject.Properties | Where-Object {
            if ($script:BridgeProduct -eq 'AutoCAD') { $_.Name -eq 'best-cad-mcp-autocad' }
            else { $_.Name -match '^aec-model-bridge-revit-(2024|2025|2026|2027)$' }
        } | Select-Object -ExpandProperty Name)
        foreach ($name in $names) { [void]$servers.Value.PSObject.Properties.Remove($name) }
        if ($names.Count -gt 0) {
            [System.IO.File]::WriteAllText($configPath, ($root | ConvertTo-Json -Depth 100), [System.Text.UTF8Encoding]::new($false))
            $changed = $true
        }
    }
    $policyPath = Join-Path $env:USERPROFILE '.gemini\antigravity-cli\settings.json'
    if (Test-Path -LiteralPath $policyPath) {
        Backup-File $policyPath | Out-Null
        try { $policyRoot = Get-Content -LiteralPath $policyPath -Raw | ConvertFrom-Json }
        catch { throw "Google Antigravity permission settings are invalid JSON and were not changed: $policyPath. $($_.Exception.Message)" }
        if ($policyRoot.permissions -and $policyRoot.permissions.PSObject.Properties['allow']) {
            $before = @($policyRoot.permissions.allow)
            $selectedAllow = if ($script:BridgeProduct -eq 'AutoCAD') { @('mcp(best-cad-mcp-autocad/*)') } else { @('mcp(aec-model-bridge-revit-2024/*)', 'mcp(aec-model-bridge-revit-2025/*)', 'mcp(aec-model-bridge-revit-2026/*)', 'mcp(aec-model-bridge-revit-2027/*)') }
            $after = @($before | Where-Object { $_ -notin $selectedAllow })
            if ($before.Count -ne $after.Count) {
                $policyRoot.permissions | Add-Member -MemberType NoteProperty -Name 'allow' -Value ([object[]]$after) -Force
                [System.IO.File]::WriteAllText($policyPath, ($policyRoot | ConvertTo-Json -Depth 100), [System.Text.UTF8Encoding]::new($false))
                $changed = $true
            }
        }
    }
    if ($changed) { Write-Ok "$($script:BridgeProductLabel) MCP entries were removed from Google Antigravity and legacy Gemini CLI configuration." }
    else { Write-Info "$($script:BridgeProductLabel) MCP bridge is not registered in Google Antigravity." }
}

function Get-AntigravityPluginRoots {
    return @(
        (Join-Path $env:USERPROFILE '.gemini\config\plugins'),
        (Join-Path $env:USERPROFILE '.gemini\antigravity-cli\plugins')
    )
}

function Install-AecRevitBimAntigravityPlugin {
    param(
        [Parameter(Mandatory)][string]$SourceRoot
    )

    $sourcePlugin = Join-Path $SourceRoot 'plugins\aec-revit-bim-antigravity'
    $manifest = Join-Path $sourcePlugin 'plugin.json'
    if (-not (Test-Path -LiteralPath $manifest)) {
        throw "The maintained fork does not contain the AEC Revit BIM Antigravity plugin: $manifest"
    }

    foreach ($pluginsRoot in (Get-AntigravityPluginRoots)) {
        $targetPlugin = Join-Path $pluginsRoot 'aec-revit-bim'
        if (Test-Path -LiteralPath $targetPlugin) {
            Remove-Item -LiteralPath $targetPlugin -Recurse -Force -ErrorAction Stop
        }
        New-Item -ItemType Directory -Path $pluginsRoot -Force -ErrorAction Stop | Out-Null
        Copy-Item -LiteralPath $sourcePlugin -Destination $targetPlugin -Recurse -Force -ErrorAction Stop
    }

    Write-Ok 'AEC Revit BIM skill plugin was installed for Google Antigravity.'
}

function Remove-AecRevitBimAntigravityPlugin {
    $removed = $false
    foreach ($pluginsRoot in (Get-AntigravityPluginRoots)) {
        $targetPlugin = Join-Path $pluginsRoot 'aec-revit-bim'
        if (Test-Path -LiteralPath $targetPlugin) {
            Remove-Item -LiteralPath $targetPlugin -Recurse -Force -ErrorAction Stop
            $removed = $true
        }
    }
    if ($removed) { Write-Ok 'AEC Revit BIM skill plugin was removed from Google Antigravity.' }
}

function Remove-RevitBridgeAddins {
    Write-Info 'Searching Revit 2024-2027 add-in folders for AEC Model Bridge manifests.'

    $removed = $false
    $roots = @(
        (Join-Path $env:ProgramData 'Autodesk\Revit\Addins'),
        (Join-Path $env:APPDATA 'Autodesk\Revit\Addins')
    )

    foreach ($root in $roots) {
        foreach ($year in 2024..2027) {
            $folder = Join-Path $root ([string]$year)
            if (-not (Test-Path -LiteralPath $folder)) {
                continue
            }

            Get-ChildItem -LiteralPath $folder -Filter '*.addin' -File -ErrorAction SilentlyContinue |
                ForEach-Object {
                    $isBridgeManifest = $false

                    if ($_.Name -match '(?i)AEC.*Model.*Bridge|AECModelBridge') {
                        $isBridgeManifest = $true
                    }
                    else {
                        try {
                            $content = Get-Content -LiteralPath $_.FullName -Raw -ErrorAction Stop
                            if ($content -match '(?i)AEC\s*Model\s*Bridge|AECModelBridge|ProgramData\\AECModelBridge') {
                                $isBridgeManifest = $true
                            }
                        }
                        catch {}
                    }

                    if ($isBridgeManifest) {
                        Write-Info "Removing Revit add-in manifest: $($_.FullName)"
                        Remove-Item -LiteralPath $_.FullName -Force -ErrorAction Stop
                        $script:RemovedAnyRevitManifest = $true
                    }
                }
        }
    }

    if ($script:RemovedAnyRevitManifest) {
        Write-Ok 'AEC Model Bridge Revit add-in manifests were removed.'
    }
    else {
        Write-WarningMessage 'No AEC Model Bridge .addin manifests were found.'
    }
}

function Stop-AECModelBridgeProcesses {
    Write-Info "Searching for running $($script:BridgeProductLabel) bridge Python processes that may lock bridge files."

    $bridgeRoot = Join-Path $env:ProgramData 'AECModelBridge'
    $productRoot = if ($script:BridgeProduct -eq 'AutoCAD') { Join-Path $bridgeRoot 'autocad' } else { Join-Path $bridgeRoot 'source' }
    $processCommandPattern = if ($script:BridgeProduct -eq 'AutoCAD') { '(?i)(?:best-cad-mcp|src\.server)' } else { '(?i)revit_mcp_server\.mcp_server' }
    $matched = @()

    try {
        $matched = @(
            Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
                Where-Object {
                    ($_.Name -match '^(?i)python(?:w)?\.exe$') -and (
                        ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($productRoot, [System.StringComparison]::OrdinalIgnoreCase)) -or
                        ($_.CommandLine -and $_.CommandLine -match $processCommandPattern)
                    )
                }
        )
    }
    catch {
        Write-WarningMessage "Unable to query running processes through CIM: $($_.Exception.Message)"
    }

    if (-not $matched) {
        Write-Ok "No running $($script:BridgeProductLabel) bridge Python processes were found."
        return
    }

    foreach ($process in $matched) {
        Write-Info "Stopping bridge process PID $($process.ProcessId): $($process.Name)"
        try {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
            Write-Ok "Stopped bridge process PID $($process.ProcessId)."
        }
        catch {
            Write-WarningMessage "Unable to stop bridge process PID $($process.ProcessId): $($_.Exception.Message)"
        }
    }

    Start-Sleep -Seconds 2
}

function Remove-BridgeProgramData {
    $bridgeRoot = Join-Path $env:ProgramData 'AECModelBridge'
    $productRoot = if ($script:BridgeProduct -eq 'AutoCAD') { Join-Path $bridgeRoot 'autocad' } else { Join-Path $bridgeRoot 'source' }

    if (-not (Test-Path -LiteralPath $productRoot)) {
        Write-WarningMessage "$($script:BridgeProductLabel) bridge data folder does not exist: $productRoot"
        return
    }

    Stop-AECModelBridgeProcesses

    Write-Info "Removing only $($script:BridgeProductLabel) bridge files: $productRoot"

    $removed = $false
    $lastRemovalError = $null

    for ($attempt = 1; $attempt -le 5; $attempt++) {
        try {
            Write-Info "Removal attempt $attempt of 5."
            Remove-Item -LiteralPath $productRoot -Recurse -Force -ErrorAction Stop
            $removed = -not (Test-Path -LiteralPath $productRoot)

            if ($removed) {
                break
            }
        }
        catch {
            $lastRemovalError = $_
            Write-WarningMessage "Removal attempt $attempt failed: $($_.Exception.Message)"

            Stop-AECModelBridgeProcesses
            Start-Sleep -Seconds 2
        }
    }

    if (-not $removed) {
        if ($lastRemovalError) {
            throw "$($script:BridgeProductLabel) bridge files could not be removed after 5 attempts. Last error: $($lastRemovalError.Exception.Message)"
        }

        throw "$($script:BridgeProductLabel) bridge folder still exists after removal attempts: $productRoot"
    }

    Write-Ok "$($script:BridgeProductLabel) bridge ProgramData files were removed."
}


function Remove-BridgeEnvironmentVariables {
    Write-Info 'Removing persistent MCP_REVIT environment variables created for AEC Model Bridge.'

    foreach ($name in @(
        'MCP_REVIT_MODE',
        'MCP_REVIT_BRIDGE_URL',
        'MCP_REVIT_APPROVAL_MODE',
        'MCP_REVIT_ALLOW_PYTHON_HOST',
        'MCP_REVIT_ENABLE_USER_MODULES',
        'MCP_REVIT_TARGET_VERSION',
        'MCP_REVIT_WORKSPACE_DIR',
        'MCP_REVIT_ALLOWED_DIRECTORIES'
    )) {
        [Environment]::SetEnvironmentVariable($name, $null, 'User')
        Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue
    }

    Write-Ok 'AEC Model Bridge environment variables were removed.'
}

function Remove-AECModelBridgeCompletely {
    Write-WarningMessage "Performing complete $($script:BridgeProductLabel) bridge cleanup, including residual files from incomplete removals."
    Write-Info "This removes only $($script:BridgeProductLabel) registrations and files; the other product's bridge is preserved."
    Write-Info 'Shared dependencies are not removed.'

    # Remove from Codex when present. Absence of Codex CLI must not prevent cleanup of other components.
    if (Test-CodexBridgeConfigured) {
        try {
            Remove-CodexBridge
        }
        catch {
            Write-ErrorMessage "Codex bridge removal failed: $($_.Exception.Message)"
            throw
        }
    }
    else {
        Write-Info "$($script:BridgeProductLabel) bridge is not registered in Codex."
    }

    # Remove from every detected Claude configuration.
    if (Test-ClaudeBridgeConfigured) {
        Remove-ClaudeBridge
    }
    else {
        Write-Info "$($script:BridgeProductLabel) bridge is not registered in Claude."
    }

    Remove-AntigravityBridge
    if ($script:BridgeProduct -eq 'Revit') {
        Remove-AecRevitBimAntigravityPlugin
        Remove-AecRevitBimSkill
        Remove-RevitBridgeAddins
        Remove-BridgeEnvironmentVariables
    }
    Remove-BridgeProgramData
}

function Configure-Codex {
    param(
        [Parameter(Mandatory)][string]$PythonExe,
        [Parameter(Mandatory)][string]$Workspace,
        [Parameter(Mandatory)][string]$Allowed,
        [Parameter(Mandatory)][string[]]$RevitVersions
    )

    Write-Info 'Codex receives one independent MCP entry for every detected supported Revit version.'

    Ensure-CodexDesktop

    if (-not (Get-CommandPath 'node.exe') -or -not (Get-CommandPath 'npm.cmd')) {
        Install-WinGetPackage -Id 'OpenJS.NodeJS.LTS' -DisplayName 'Node.js LTS'
    }
    else {
        Write-Ok 'Node.js and npm are available.'
    }

    Refresh-ProcessPath

    if (-not (Get-CommandPath 'codex.cmd') -and -not (Get-CommandPath 'codex.exe')) {
        Invoke-CheckedProcess `
            -FilePath 'npm.cmd' `
            -Arguments @('install', '-g', '@openai/codex') `
            -Description 'Installing OpenAI Codex CLI'
        Refresh-ProcessPath
    }
    else {
        Write-Ok 'Codex CLI is available.'
    }

    $codex = Get-CommandPath 'codex.cmd'
    if (-not $codex) {
        $codex = Get-CommandPath 'codex.exe'
    }
    if (-not $codex) {
        throw 'Codex CLI is not available in PATH.'
    }

    $configPath = Join-Path $env:USERPROFILE '.codex\config.toml'
    Backup-File $configPath | Out-Null

    # Remove the legacy single-instance entry and stale version-specific entries.
    foreach ($name in @(
        'aec-model-bridge',
        'aec-model-bridge-revit-2024',
        'aec-model-bridge-revit-2025',
        'aec-model-bridge-revit-2026',
        'aec-model-bridge-revit-2027'
    )) {
        try { & $codex mcp remove $name *> $null } catch {}
    }

    foreach ($version in $RevitVersions) {
        $entryName = "aec-model-bridge-revit-$version"

        Invoke-CheckedProcess `
            -FilePath $codex `
            -Arguments @(
                'mcp',
                'add',
                $entryName,
                '--env', 'MCP_REVIT_MODE=bridge',
                '--env', 'MCP_REVIT_APPROVAL_MODE=auto',
                '--env', 'MCP_REVIT_ALLOW_PYTHON_HOST=true',
                '--env', 'MCP_REVIT_ENABLE_USER_MODULES=true',
                '--env', "MCP_REVIT_TARGET_VERSION=$version",
                '--env', "MCP_REVIT_WORKSPACE_DIR=$Workspace",
                '--env', "MCP_REVIT_ALLOWED_DIRECTORIES=$Allowed",
                '--',
                $PythonExe,
                '-m',
                'revit_mcp_server.mcp_server'
            ) `
            -Description "Adding AEC Model Bridge for Revit $version to Codex"
    }

    if (-not (Test-CodexBridgeConfigured)) {
        throw 'Codex did not report any version-specific AEC Model Bridge registration.'
    }

    Write-Ok ('Codex was configured for Revit versions: ' + ($RevitVersions -join ', '))
    Set-CodexBridgeApprovalModes
}

function Test-AntigravityDesktopInstalled {
    if (Get-AppxPackage -Name 'Google.Antigravity' -ErrorAction SilentlyContinue) { return $true }
    foreach ($uninstallKey in @(
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
    )) {
        if (Get-ItemProperty $uninstallKey -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -eq 'Antigravity' -and $_.Publisher -match 'Google' } | Select-Object -First 1) { return $true }
    }
    return $false
}

function Ensure-Antigravity {
    Write-Info 'Installing Google Antigravity desktop app and CLI when they are missing.'
    if (-not (Test-AntigravityDesktopInstalled)) {
        Install-WinGetPackage -Id 'Google.Antigravity' -DisplayName 'Google Antigravity desktop app'
    }
    else { Write-Ok 'Google Antigravity desktop app is available.' }
    if (-not (Get-CommandPath 'agy.exe') -and -not (Get-CommandPath 'agy.cmd')) {
        Install-WinGetPackage -Id 'Google.AntigravityCLI' -DisplayName 'Google Antigravity CLI'
    }
    else { Write-Ok 'Google Antigravity CLI is available.' }
    Refresh-ProcessPath
    if (-not (Get-CommandPath 'agy.exe') -and -not (Get-CommandPath 'agy.cmd')) {
        throw 'Google Antigravity CLI is not available in PATH after installation.'
    }
}

function Get-AntigravityJsonRoot {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string]$Description)
    New-Item -ItemType Directory -Path (Split-Path $Path -Parent) -Force | Out-Null
    if (Test-Path -LiteralPath $Path) {
        Backup-File $Path | Out-Null
        try { $root = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json }
        catch { throw "The existing $Description is invalid JSON and was not overwritten: $Path. $($_.Exception.Message)" }
    }
    else { $root = [pscustomobject]@{} }
    return [pscustomobject]@{ Root = $root; Path = $Path }
}

function Save-AntigravityJson($Settings) {
    [System.IO.File]::WriteAllText($Settings.Path, ($Settings.Root | ConvertTo-Json -Depth 100), [System.Text.UTF8Encoding]::new($false))
}

function Get-AntigravityMcpSettings {
    $settings = Get-AntigravityJsonRoot -Path (Join-Path $env:USERPROFILE '.gemini\config\mcp_config.json') -Description 'Google Antigravity MCP configuration'
    if (-not $settings.Root.PSObject.Properties['mcpServers'] -or -not $settings.Root.mcpServers) {
        $settings.Root | Add-Member -MemberType NoteProperty -Name 'mcpServers' -Value ([pscustomobject]@{}) -Force
    }
    return $settings
}

function Set-AntigravityBridgePermissions {
    param([Parameter(Mandatory)][string[]]$ServerNames)
    $settings = Get-AntigravityJsonRoot -Path (Join-Path $env:USERPROFILE '.gemini\antigravity-cli\settings.json') -Description 'Google Antigravity permission settings'
    if (-not $settings.Root.PSObject.Properties['permissions'] -or -not $settings.Root.permissions) {
        $settings.Root | Add-Member -MemberType NoteProperty -Name 'permissions' -Value ([pscustomobject]@{}) -Force
    }
    $existing = @()
    if ($settings.Root.permissions.PSObject.Properties['allow'] -and $settings.Root.permissions.allow) { $existing = @($settings.Root.permissions.allow) }
    $required = @($ServerNames | ForEach-Object { "mcp($_/*)" })
    $settings.Root.permissions | Add-Member -MemberType NoteProperty -Name 'allow' -Value ([object[]]@($existing + $required | Select-Object -Unique)) -Force
    Save-AntigravityJson $settings
}

function Configure-Antigravity {
    param(
        [Parameter(Mandatory)][string]$PythonExe,
        [Parameter(Mandatory)][string]$Workspace,
        [Parameter(Mandatory)][string]$Allowed,
        [Parameter(Mandatory)][string[]]$RevitVersions
    )

    Ensure-Antigravity
    $settings = Get-AntigravityMcpSettings
    foreach ($name in @('aec-model-bridge-revit-2024','aec-model-bridge-revit-2025','aec-model-bridge-revit-2026','aec-model-bridge-revit-2027')) {
        if ($settings.Root.mcpServers.PSObject.Properties[$name]) { [void]$settings.Root.mcpServers.PSObject.Properties.Remove($name) }
    }
    foreach ($version in $RevitVersions) {
        $settings.Root.mcpServers | Add-Member -MemberType NoteProperty -Name "aec-model-bridge-revit-$version" -Value ([pscustomobject]@{
            command = $PythonExe
            args = [object[]]@('-m', 'revit_mcp_server.mcp_server')
            env = [pscustomobject]@{
                MCP_REVIT_MODE = 'bridge'; MCP_REVIT_APPROVAL_MODE = 'auto'; MCP_REVIT_ALLOW_PYTHON_HOST = 'true'; MCP_REVIT_ENABLE_USER_MODULES = 'true'; MCP_REVIT_TARGET_VERSION = $version; MCP_REVIT_WORKSPACE_DIR = $Workspace; MCP_REVIT_ALLOWED_DIRECTORIES = $Allowed
            }
        }) -Force
    }
    Save-AntigravityJson $settings
    Set-AntigravityBridgePermissions -ServerNames @($RevitVersions | ForEach-Object { "aec-model-bridge-revit-$_" })
    Write-Ok ('Google Antigravity was configured for Revit versions: ' + ($RevitVersions -join ', '))
}

function Repair-ClaudeArraySettings {
    param([Parameter(Mandatory)]$Root)

    $preferencesProperty = $Root.PSObject.Properties['preferences']
    if (-not $preferencesProperty -or -not $preferencesProperty.Value) {
        return
    }

    foreach ($property in @($preferencesProperty.Value.PSObject.Properties)) {
        if ($property.Name -notmatch '^launchPreview') {
            continue
        }

        $value = $property.Value
        if ($value -is [System.Array]) {
            continue
        }

        if ($null -eq $value) {
            $arrayValue = [object[]]@()
        }
        else {
            $arrayValue = [object[]]@($value)
        }

        $preferencesProperty.Value |
            Add-Member -MemberType NoteProperty -Name $property.Name -Value $arrayValue -Force

        Write-WarningMessage "Repaired Claude setting as an array: preferences.$($property.Name)"
    }
}

function Test-ClaudeDesktopInstalled {
    try {
        if (Get-AppxPackage -Name 'Claude*' -ErrorAction SilentlyContinue) { return $true }
    }
    catch {}

    foreach ($path in @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Claude\Claude.exe'),
        (Join-Path $env:LOCALAPPDATA 'AnthropicClaude\Claude.exe')
    )) {
        if (Test-Path -LiteralPath $path) { return $true }
    }

    foreach ($root in @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*'
    )) {
        try {
            if (Get-ItemProperty $root -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -match '(?i)^Claude(?: Desktop)?$' } | Select-Object -First 1) {
                return $true
            }
        }
        catch {}
    }

    return $false
}

function Ensure-ClaudeDesktop {
    if (Test-ClaudeDesktopInstalled) {
        Write-Ok 'Claude Desktop is installed.'
        return
    }

    Write-WarningMessage 'Claude Desktop was not found. Installing it through WinGet.'
    Install-WinGetPackage -Id 'Anthropic.Claude' -DisplayName 'Claude Desktop'

    if (-not (Test-ClaudeDesktopInstalled)) {
        throw 'Claude Desktop installation completed, but the application could not be detected. Restart Windows if the installer requests it, then run this script again.'
    }

    Write-Ok 'Claude Desktop was installed.'
}

function Configure-Claude {
    param(
        [Parameter(Mandatory)][string]$PythonExe,
        [Parameter(Mandatory)][string]$Workspace,
        [Parameter(Mandatory)][string]$Allowed,
        [Parameter(Mandatory)][string[]]$RevitVersions
    )

    Write-Info 'Claude receives one independent MCP entry for every detected supported Revit version.'
    Ensure-ClaudeDesktop

    $configPaths = @(Get-ActiveClaudeConfigPaths)
    $writtenPaths = [System.Collections.Generic.List[string]]::new()
    $utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)

    foreach ($claudeConfigPath in $configPaths) {
        $claudeConfigDirectory = Split-Path $claudeConfigPath -Parent
        New-Item -ItemType Directory -Path $claudeConfigDirectory -Force | Out-Null

        if (Test-Path -LiteralPath $claudeConfigPath) {
            Backup-File $claudeConfigPath | Out-Null
            try {
                $root = Get-Content -LiteralPath $claudeConfigPath -Raw | ConvertFrom-Json
            }
            catch {
                throw "The existing Claude configuration is invalid JSON and was not overwritten: $claudeConfigPath. $($_.Exception.Message)"
            }
        }
        else {
            $root = [pscustomobject]@{}
        }

        Repair-ClaudeArraySettings -Root $root

        $mcpServersProperty = $root.PSObject.Properties['mcpServers']
        if (-not $mcpServersProperty -or -not $mcpServersProperty.Value) {
            $mcpServers = [pscustomobject]@{}
            $root | Add-Member -MemberType NoteProperty -Name 'mcpServers' -Value $mcpServers -Force
        }
        else {
            $mcpServers = $mcpServersProperty.Value
        }

        foreach ($name in @(
            'aec-model-bridge',
            'aec-model-bridge-revit-2024',
            'aec-model-bridge-revit-2025',
            'aec-model-bridge-revit-2026',
            'aec-model-bridge-revit-2027'
        )) {
            if ($mcpServers.PSObject.Properties[$name]) {
                [void]$mcpServers.PSObject.Properties.Remove($name)
            }
        }

        foreach ($version in $RevitVersions) {
            $entryName = "aec-model-bridge-revit-$version"
            $bridgeEntry = [pscustomobject]@{
                command = $PythonExe
                args = [object[]]@('-m', 'revit_mcp_server.mcp_server')
                env = [pscustomobject]@{
                    MCP_REVIT_MODE = 'bridge'
                    MCP_REVIT_APPROVAL_MODE = 'auto'
                    MCP_REVIT_ALLOW_PYTHON_HOST = 'true'
                    MCP_REVIT_ENABLE_USER_MODULES = 'true'
                    MCP_REVIT_TARGET_VERSION = $version
                    MCP_REVIT_WORKSPACE_DIR = $Workspace
                    MCP_REVIT_ALLOWED_DIRECTORIES = $Allowed
                }
            }

            $mcpServers |
                Add-Member -MemberType NoteProperty -Name $entryName -Value $bridgeEntry -Force
        }

        $json = $root | ConvertTo-Json -Depth 100
        [System.IO.File]::WriteAllText($claudeConfigPath, $json, $utf8WithoutBom)

        $verified = Get-Content -LiteralPath $claudeConfigPath -Raw | ConvertFrom-Json
        $verifiedMcp = $verified.PSObject.Properties['mcpServers']
        foreach ($version in $RevitVersions) {
            $entryName = "aec-model-bridge-revit-$version"
            if (-not $verifiedMcp -or -not $verifiedMcp.Value.PSObject.Properties[$entryName]) {
                throw "Claude configuration verification failed for $entryName in $claudeConfigPath"
            }
        }

        $writtenPaths.Add($claudeConfigPath)
        Write-Ok "Claude was configured for Revit versions $($RevitVersions -join ', '): $claudeConfigPath"
    }

    if ($writtenPaths.Count -eq 0) {
        throw 'No writable Claude Desktop configuration path was detected.'
    }

    Write-Info 'Claude Desktop must be fully closed and reopened before the MCP entries appear.'
}

function Test-AutoCadMcpServerStartup {
    param(
        [Parameter(Mandatory)][string]$PythonExe,
        [Parameter(Mandatory)][string]$WorkingDirectory
    )

    Write-Host '  > Starting the AutoCAD MCP server for a short self-test...' -ForegroundColor White
    $process = $null
    $stdoutFile = Join-Path $env:TEMP ("aecmb_autocad_stdout_{0}.log" -f ([guid]::NewGuid().ToString('N')))
    $stderrFile = Join-Path $env:TEMP ("aecmb_autocad_stderr_{0}.log" -f ([guid]::NewGuid().ToString('N')))

    try {
        $process = Start-Process `
            -FilePath $PythonExe `
            -ArgumentList '-m src.server' `
            -WorkingDirectory $WorkingDirectory `
            -PassThru `
            -NoNewWindow `
            -RedirectStandardOutput $stdoutFile `
            -RedirectStandardError $stderrFile `
            -ErrorAction Stop

        if ($process.WaitForExit(5000)) {
            $process.Refresh()
            $stderr = if (Test-Path -LiteralPath $stderrFile) { Get-Content -LiteralPath $stderrFile -Raw -ErrorAction SilentlyContinue } else { '' }
            $stdout = if (Test-Path -LiteralPath $stdoutFile) { Get-Content -LiteralPath $stdoutFile -Raw -ErrorAction SilentlyContinue } else { '' }
            $details = @($stderr, $stdout) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -First 1
            if ($details) {
                $details.Trim().Split([Environment]::NewLine) | Select-Object -Last 12 | ForEach-Object {
                    Write-Host "  $_" -ForegroundColor Red
                }
            }
            throw "The AutoCAD MCP server exited during startup with code $($process.ExitCode)."
        }

        Write-Ok 'AutoCAD MCP server startup test passed.'
    }
    finally {
        if ($process -and -not $process.HasExited) {
            & taskkill.exe /PID $process.Id /T /F *> $null
        }
        Remove-Item -LiteralPath $stdoutFile, $stderrFile -Force -ErrorAction SilentlyContinue
    }
}

function Configure-AutoCadCodex {
    param(
        [Parameter(Mandatory)][string]$PythonExe,
        [Parameter(Mandatory)][string]$SourceRoot,
        [Parameter(Mandatory)][string]$Workspace
    )

    if (-not (Get-CommandPath 'node.exe') -or -not (Get-CommandPath 'npm.cmd')) {
        Install-WinGetPackage -Id 'OpenJS.NodeJS.LTS' -DisplayName 'Node.js LTS'
    }
    Refresh-ProcessPath

    if (-not (Get-CommandPath 'codex.cmd') -and -not (Get-CommandPath 'codex.exe')) {
        Invoke-CheckedProcess -FilePath 'npm.cmd' -Arguments @('install', '-g', '@openai/codex') -Description 'Installing OpenAI Codex CLI'
        Refresh-ProcessPath
    }

    $codex = Get-CommandPath 'codex.cmd'
    if (-not $codex) { $codex = Get-CommandPath 'codex.exe' }
    if (-not $codex) { throw 'Codex CLI is not available in PATH.' }

    $configPath = Join-Path $env:USERPROFILE '.codex\config.toml'
    Backup-File $configPath | Out-Null
    try { & $codex mcp remove 'best-cad-mcp-autocad' *> $null } catch {}
    $logDirectory = Join-Path $env:LOCALAPPDATA 'AECModelBridge\logs'
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    $logPath = Join-Path $logDirectory 'best-cad-mcp.log'

    Invoke-CheckedProcess `
        -FilePath $codex `
        -Arguments @(
            'mcp', 'add', 'best-cad-mcp-autocad',
            '--env', "CAD_MCP_WORKSPACE_ROOT=$Workspace",
            '--env', 'CAD_MCP_TOOL_PROFILE=core',
            '--env', "PYTHONPATH=$SourceRoot",
            '--env', "CAD_MCP_LOG_PATH=$logPath",
            '--env', 'CAD_MCP_LOG_LEVEL=WARNING',
            '--env', 'CAD_MCP_MCP_LOG_LEVEL=WARNING',
            '--', $PythonExe, '-m', 'src.server'
        ) `
        -Description 'Adding best-cad-mcp for AutoCAD to Codex'

    Write-Ok 'AutoCAD MCP was configured for Codex.'
    Set-CodexBridgeApprovalModes
}

function Configure-AutoCadAntigravity {
    param(
        [Parameter(Mandatory)][string]$PythonExe,
        [Parameter(Mandatory)][string]$SourceRoot,
        [Parameter(Mandatory)][string]$Workspace
    )

    Ensure-Antigravity
    $settings = Get-AntigravityMcpSettings
    if ($settings.Root.mcpServers.PSObject.Properties['best-cad-mcp-autocad']) {
        [void]$settings.Root.mcpServers.PSObject.Properties.Remove('best-cad-mcp-autocad')
    }
    $logDirectory = Join-Path $env:LOCALAPPDATA 'AECModelBridge\logs'
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    $logPath = Join-Path $logDirectory 'best-cad-mcp.log'
    $settings.Root.mcpServers | Add-Member -MemberType NoteProperty -Name 'best-cad-mcp-autocad' -Value ([pscustomobject]@{
        command = $PythonExe
        args = [object[]]@('-m', 'src.server')
        cwd = $SourceRoot
        env = [pscustomobject]@{
            CAD_MCP_WORKSPACE_ROOT = $Workspace; CAD_MCP_TOOL_PROFILE = 'core'; PYTHONPATH = $SourceRoot; CAD_MCP_LOG_PATH = $logPath; CAD_MCP_LOG_LEVEL = 'WARNING'; CAD_MCP_MCP_LOG_LEVEL = 'WARNING'
        }
    }) -Force
    Save-AntigravityJson $settings
    Set-AntigravityBridgePermissions -ServerNames @('best-cad-mcp-autocad')
    Write-Ok 'AutoCAD MCP was configured for Google Antigravity.'
}

function Configure-AutoCadClaude {
    param(
        [Parameter(Mandatory)][string]$PythonExe,
        [Parameter(Mandatory)][string]$SourceRoot,
        [Parameter(Mandatory)][string]$Workspace
    )

    Ensure-ClaudeDesktop
    $configPaths = @(Get-ActiveClaudeConfigPaths)
    $utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
    $logDirectory = Join-Path $env:LOCALAPPDATA 'AECModelBridge\logs'
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    $logPath = Join-Path $logDirectory 'best-cad-mcp.log'

    foreach ($claudeConfigPath in $configPaths) {
        $directory = Split-Path $claudeConfigPath -Parent
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
        if (Test-Path -LiteralPath $claudeConfigPath) {
            Backup-File $claudeConfigPath | Out-Null
            try { $root = Get-Content -LiteralPath $claudeConfigPath -Raw | ConvertFrom-Json }
            catch { throw "The existing Claude configuration is invalid JSON and was not overwritten: $claudeConfigPath. $($_.Exception.Message)" }
        }
        else { $root = [pscustomobject]@{} }

        Repair-ClaudeArraySettings -Root $root
        $mcpProperty = $root.PSObject.Properties['mcpServers']
        if (-not $mcpProperty -or -not $mcpProperty.Value) {
            $mcpServers = [pscustomobject]@{}
            $root | Add-Member -MemberType NoteProperty -Name 'mcpServers' -Value $mcpServers -Force
        }
        else { $mcpServers = $mcpProperty.Value }

        if ($mcpServers.PSObject.Properties['best-cad-mcp-autocad']) {
            [void]$mcpServers.PSObject.Properties.Remove('best-cad-mcp-autocad')
        }

        $entry = [pscustomobject]@{
            command = $PythonExe
            args = [object[]]@('-m', 'src.server')
            env = [pscustomobject]@{
                CAD_MCP_WORKSPACE_ROOT = $Workspace
                CAD_MCP_TOOL_PROFILE = 'core'
                PYTHONPATH = $SourceRoot
                CAD_MCP_LOG_PATH = $logPath
                CAD_MCP_LOG_LEVEL = 'WARNING'
                CAD_MCP_MCP_LOG_LEVEL = 'WARNING'
            }
        }
        $mcpServers | Add-Member -MemberType NoteProperty -Name 'best-cad-mcp-autocad' -Value $entry -Force
        [System.IO.File]::WriteAllText($claudeConfigPath, ($root | ConvertTo-Json -Depth 100), $utf8WithoutBom)
        Write-Ok "AutoCAD MCP was configured for Claude: $claudeConfigPath"
    }
}

function Wait-ForBridgeHealth {
    param([int]$TimeoutSeconds = 60)

    Write-Info 'Reading the Contract v2 discovery registry for the active Revit bridge.'
    Write-Info 'The bridge uses a dynamic port and a per-session token.'

    $registryDirectory = Join-Path $env:LOCALAPPDATA 'AECModelBridge\registry'
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastError = $null

    while ((Get-Date) -lt $deadline) {
        try {
            if (-not (Test-Path -LiteralPath $registryDirectory)) {
                $lastError = "Discovery registry not found yet: $registryDirectory"
                Start-Sleep -Seconds 2
                continue
            }

            $entries = @(
                Get-ChildItem -LiteralPath $registryDirectory -Filter '*.json' -File -ErrorAction SilentlyContinue |
                    ForEach-Object {
                        try {
                            $entry = Get-Content -LiteralPath $_.FullName -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
                            if (
                                [string]$entry.provider_id -eq 'revit' -and
                                $entry.endpoint -and
                                $entry.pid -and
                                (Get-Process -Id ([int]$entry.pid) -ErrorAction SilentlyContinue)
                            ) {
                                [PSCustomObject]@{
                                    Entry        = $entry
                                    RegistryFile = $_.FullName
                                    StartedAt    = try { [datetime]$entry.started_at } catch { $_.LastWriteTime }
                                }
                            }
                        }
                        catch {
                            $script:lastError = "Invalid discovery entry $($_.FullName): $($_.Exception.Message)"
                        }
                    } |
                    Sort-Object StartedAt -Descending
            )

            if (-not $entries) {
                $lastError = 'No live Revit entry was found in the Contract v2 discovery registry.'
                Start-Sleep -Seconds 2
                continue
            }

            foreach ($item in $entries) {
                $entry = $item.Entry
                $endpoint = ([string]$entry.endpoint).TrimEnd('/')
                $healthUri = "$endpoint/health"

                try {
                    $headers = @{}
                    if ($entry.session_token) {
                        $headers['Authorization'] = "Bearer $($entry.session_token)"
                    }

                    $response = Invoke-RestMethod `
                        -Uri $healthUri `
                        -Headers $headers `
                        -TimeoutSec 3 `
                        -ErrorAction Stop

                    if ([string]$response.status -eq 'healthy') {
                        Write-Ok "The Revit bridge is healthy: $endpoint"
                        Write-Info "Revit version: $($response.revit_version); PID: $($entry.pid)"
                        return $true
                    }

                    $lastError = "The discovered endpoint responded without healthy status: $healthUri"
                }
                catch {
                    $lastError = "${healthUri}: $($_.Exception.Message)"
                }
            }
        }
        catch {
            $lastError = $_.Exception.Message
        }

        Start-Sleep -Seconds 2
    }

    Write-ErrorMessage "The Revit bridge was not verified within $TimeoutSeconds seconds."
    if ($lastError) {
        Write-ErrorMessage $lastError
    }
    return $false
}

try {
    $logDirectory = Join-Path $env:ProgramData 'AECModelBridge\logs'
    New-Item -ItemType Directory -Path $logDirectory -Force -ErrorAction SilentlyContinue | Out-Null
    $logPath = Join-Path $logDirectory ("setup_{0}.log" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
    $script:LogPath = $logPath
    Start-Transcript -LiteralPath $logPath -Force | Out-Null

    Clear-Host
    Write-Host ('=' * 72) -ForegroundColor DarkGray
    Write-Host 'AUTOCAD MCP SETUP' -ForegroundColor Cyan
    Write-Host 'AutoCAD 2020+ / Codex / Claude / Google Antigravity' -ForegroundColor Gray
    Write-Host ('=' * 72) -ForegroundColor DarkGray
    Write-Host ''
    Write-Host 'The installer will show only the current action and its result.'
    Write-Host 'Detailed command output is written to the log file.'
    Write-Info "Log file: $logPath"

    if (Update-InstallerIfNewer) {
        try { Stop-Transcript | Out-Null } catch {}
        exit 75
    }

    $client = Select-TargetClient
    if (-not $client) {
        Write-Info "No changes were made."
        try { Stop-Transcript | Out-Null } catch {}
        exit 0
    }

    if ($script:SelectedAction -eq 'FullRemove') {
        Start-Step `
            -Title "Remove the $($script:BridgeProductLabel) bridge completely" `
            -Explanation "Only $($script:BridgeProductLabel) MCP registrations and its files are removed. The other product's bridge and shared dependencies remain installed."

        Remove-AECModelBridgeCompletely

        Write-Host ''
        Write-Ok "$($script:BridgeProductLabel) MCP bridge was completely removed from this computer."
        Write-Info 'Git, Python, Node.js, Codex CLI, .NET SDKs, and .NET Framework Developer Pack remain installed.'
        Write-Info "Restart Codex, Claude, Google Antigravity, and $($script:BridgeProductLabel) if they were open."
        exit 0
    }

    Start-Step `
        -Title 'Check package manager' `
        -Explanation 'The script checks WinGet first because missing dependencies may need to be installed automatically.'
    Ensure-WinGet

    Start-Step `
        -Title 'Check base development tools' `
        -Explanation 'Git downloads the bridge source. Python runs the MCP server. Missing tools are installed automatically.'

    $gitExe = Get-CommandPath 'git.exe'
    if (-not $gitExe) {
        Install-WinGetPackage -Id 'Git.Git' -DisplayName 'Git'
        Refresh-ProcessPath
        $gitExe = Get-CommandPath 'git.exe'
    }
    else {
        Write-Ok "Git is available at $gitExe."
    }

    if ([string]::IsNullOrWhiteSpace($gitExe)) {
        throw 'Git was installed, but git.exe could not be located.'
    }


    $pythonExe = Get-PythonExecutable
    if (-not $pythonExe) {
        Install-WinGetPackage -Id 'Python.Python.3.12' -DisplayName 'Python 3.12'
        $pythonExe = Get-PythonExecutable
    }
    if (-not $pythonExe) {
        throw 'Python 3.11 or later could not be located after installation.'
    }
    Write-Ok "Python is available."

    Start-Step `
        -Title "Detect supported $($script:BridgeProductLabel) versions" `
        -Explanation 'The script detects full AutoCAD 2020 and later. AutoCAD LT is not supported by the COM bridge.'

    $revitVersions = @()
    $autoCadVersions = @()
    if ($script:BridgeProduct -eq 'AutoCAD') {
        $autoCadVersions = Get-AutoCadVersions
        if ($autoCadVersions) { Write-Ok "Detected AutoCAD versions: $($autoCadVersions -join ', ')" }
        else { throw 'No supported full AutoCAD 2020+ installation was detected. AutoCAD LT is not supported by the selected COM bridge.' }
    }
    else {
        $revitVersions = Get-RevitVersions
        if ($revitVersions) { Write-Ok "Detected Revit versions: $($revitVersions -join ', ')" }
        else { throw 'No supported Revit 2024-2027 installation was detected.' }
    }

    if ($script:BridgeProduct -eq 'Revit') {

    Start-Step `
        -Title 'Check Revit build dependencies' `
        -Explanation 'Each detected Revit version requires the matching .NET build environment. Only missing components are installed.'

    if (($revitVersions | Where-Object { $_ -in @('2024', '2025', '2026') }) -and -not (Test-DotNetSdk '8')) {
        Install-WinGetPackage -Id 'Microsoft.DotNet.SDK.8' -DisplayName '.NET 8 SDK'
    }
    elseif ($revitVersions | Where-Object { $_ -in @('2024', '2025', '2026') }) {
        Write-Ok ".NET 8 SDK is available."
    }

    if ($revitVersions -contains '2027') {
        if (-not (Test-DotNetSdk '10')) {
            Install-WinGetPackage -Id 'Microsoft.DotNet.SDK.10' -DisplayName '.NET 10 SDK'
        }
        else {
            Write-Ok ".NET 10 SDK is available."
        }
    }

    if ($revitVersions -contains '2024') {
        $net48Reference = 'C:\Program Files (x86)\Reference Assemblies\Microsoft\Framework\.NETFramework\v4.8\mscorlib.dll'
        if (-not (Test-Path -LiteralPath $net48Reference)) {
            Install-WinGetPackage `
                -Id 'Microsoft.DotNet.Framework.DeveloperPack_4' `
                -DisplayName '.NET Framework 4.8 Developer Pack' `
                -Version '4.8'
        }
        else {
            Write-Ok ".NET Framework 4.8 Developer Pack is available."
        }
    }

    Start-Step `
        -Title 'Download or update AEC Model Bridge' `
        -Explanation 'The source is stored in ProgramData. An existing repository is updated instead of being deleted.'

    $sourceRoot = Join-Path $env:ProgramData 'AECModelBridge\source'
    $repoUrl = 'https://github.com/Moorlack/aec-model-bridge.git'

    Write-Info "Repository path: $sourceRoot"
    Write-Info "Repository URL: $repoUrl"
    Write-Info "Git executable: $gitExe"

    $gitMetadataPath = Join-Path -Path $sourceRoot -ChildPath '.git'
    $repositoryExists = Test-Path -LiteralPath $gitMetadataPath

    if ($repositoryExists) {
        Write-Info "An existing Git repository was found."

        # Adopt the maintained fork so existing installations receive the tested
        # fixes and bundled Codex skill on their next repair/extend run.
        & $gitExe -C $sourceRoot remote set-url origin $repoUrl
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to point the AEC Model Bridge repository at the maintained fork (git exit code $LASTEXITCODE)."
        }

        # The maintained fork already contains our fixes. Preserve user changes
        # before the update instead of failing with unstaged local files.
        $repositoryStatus = & $gitExe -C $sourceRoot status --porcelain 2>$null
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to inspect local changes in the AEC Model Bridge repository (git exit code $LASTEXITCODE)."
        }
        if ($repositoryStatus) {
            $stashMessage = "AEC Model Bridge setup backup $(Get-Date -Format 'yyyyMMdd_HHmmss')"
            Write-WarningMessage 'Local AEC Model Bridge source changes were found. Saving them to Git stash before update.'
            & $gitExe -C $sourceRoot stash push --include-untracked -m $stashMessage
            $stashExitCode = $LASTEXITCODE
            if ($stashExitCode -ne 0) {
                throw "AEC Model Bridge local-change backup failed with git exit code $stashExitCode."
            }
            Write-Info "Saved local source changes to Git stash: $stashMessage"
            Write-Info 'The maintained fork will be restored on update. Other saved changes remain recoverable with: git -C <source path> stash list / stash pop'
        }

        Write-Info ("Command: {0} -C {1} pull --ff-only" -f $gitExe, $sourceRoot)

        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            & $gitExe -C $sourceRoot pull --ff-only
            $gitExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }

        Write-Info "git pull exit code: $gitExitCode"
        if ($gitExitCode -ne 0) {
            throw "AEC Model Bridge repository update failed with git exit code $gitExitCode."
        }

        Write-Ok "AEC Model Bridge repository was updated."
    }
    else {
        if (Test-Path -LiteralPath $sourceRoot) {
            $backupFolder = "$sourceRoot.backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
            Write-WarningMessage "A non-Git source folder exists and will be moved to $backupFolder."
            Move-Item -LiteralPath $sourceRoot -Destination $backupFolder -ErrorAction Stop
        }

        $sourceParent = Split-Path $sourceRoot -Parent
        New-Item -ItemType Directory -Path $sourceParent -Force -ErrorAction Stop | Out-Null

        Write-Info "Downloading the AEC Model Bridge repository."
        Write-Info ("Command: {0} clone --depth 1 {1} {2}" -f $gitExe, $repoUrl, $sourceRoot)

        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            & $gitExe clone --depth 1 $repoUrl $sourceRoot
            $gitExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }

        Write-Info "git clone exit code: $gitExitCode"
        if ($gitExitCode -ne 0) {
            throw "AEC Model Bridge repository download failed with git exit code $gitExitCode."
        }

        if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot '.git'))) {
            throw "git clone reported success, but the repository was not created at $sourceRoot."
        }

        Write-Ok "AEC Model Bridge repository was downloaded."
    }

    Start-Step `
        -Title 'Verify the Revit transaction fix' `
        -Explanation 'The maintained fork replaces the recursive transaction factory that can freeze Revit during a modifying tool call.'

    $factoryFile = Join-Path $sourceRoot 'packages\revit-bridge-addin\src\Bridge\BridgeCommandFactory.cs'
    if (-not (Test-Path -LiteralPath $factoryFile)) {
        throw "BridgeCommandFactory.cs was not found: $factoryFile"
    }

    $factorySource = Get-Content -LiteralPath $factoryFile -Raw -ErrorAction Stop
    $brokenLine = 'return BridgeCommandFactory.CreateTransaction(doc, txName);'
    $fixedLine = 'return new Transaction(doc, txName);'

    if ($factorySource.Contains($brokenLine)) {
        $factorySource = $factorySource.Replace($brokenLine, $fixedLine)
        [System.IO.File]::WriteAllText(
            $factoryFile,
            $factorySource,
            [System.Text.UTF8Encoding]::new($false)
        )
        Write-Ok 'The recursive transaction factory was fixed.'
    }
    elseif ($factorySource.Contains($fixedLine)) {
        Write-Ok 'The transaction factory is already fixed.'
    }
    else {
        throw 'The expected transaction factory code was not found. The upstream source has changed and must be reviewed.'
    }

    $appFile = Join-Path $sourceRoot 'packages\revit-bridge-addin\src\Bridge\App.cs'
    if (-not (Test-Path -LiteralPath $appFile)) {
        throw "App.cs was not found: $appFile"
    }

    $appSource = Get-Content -LiteralPath $appFile -Raw -ErrorAction Stop

    # Revit 2025.4 can crash when Manage Links opens after the bridge WebView2
    # pane has initialized. The MCP server and ExternalEvent do not need this UI;
    # keep them active but do not register/load the WebView2 pane in Revit 2025.
    $panelRegistrationPattern = '(?ms)^\s{16}try\s*\{\s*BridgePanelProvider\.Register\(application\);\s*\}\s*catch \(Exception ex\)\s*\{\s*Log\.Error\(ex, "Bridge started, but the AEC Model Bridge dockable pane could not be registered"\);\s*\}'
    $panelRegistrationReplacement = @'
                if (string.Equals(RevitVersion, "2025", StringComparison.Ordinal))
                {
                    Log.Information("Disabled AEC Model Bridge WebView2 dockable pane for Revit 2025 Manage Links stability");
                }
                else
                {
                    try
                    {
                        BridgePanelProvider.Register(application);
                    }
                    catch (Exception ex)
                    {
                        Log.Error(ex, "Bridge started, but the AEC Model Bridge dockable pane could not be registered");
                    }
                }
'@
    $panelHubPattern = '(?ms)^\s{16}try\s*\{\s*// Fire-and-forget: checks/launches in the background, never blocks startup\.\s*_hubLauncher = new PanelHubLauncher\(\);\s*_hubLauncher\.EnsureRunning\(\);\s*\}\s*catch \(Exception ex\)\s*\{\s*Log\.Error\(ex, "Bridge started, but the panel hub could not be launched"\);\s*\}'
    $panelHubReplacement = @'
                if (!string.Equals(RevitVersion, "2025", StringComparison.Ordinal))
                {
                    try
                    {
                        // Fire-and-forget: checks/launches in the background, never blocks startup.
                        _hubLauncher = new PanelHubLauncher();
                        _hubLauncher.EnsureRunning();
                    }
                    catch (Exception ex)
                    {
                        Log.Error(ex, "Bridge started, but the panel hub could not be launched");
                    }
                }
'@

    if ($appSource -match $panelRegistrationPattern) {
        $appSource = [regex]::Replace($appSource, $panelRegistrationPattern, $panelRegistrationReplacement, 1)
    }
    elseif ($appSource -notmatch 'Disabled AEC Model Bridge WebView2 dockable pane for Revit 2025 Manage Links stability') {
        throw 'The dockable-pane implementation changed and the Revit 2025 UI isolation hotfix could not be applied safely.'
    }

    if ($appSource -match $panelHubPattern) {
        $appSource = [regex]::Replace($appSource, $panelHubPattern, $panelHubReplacement, 1)
    }
    elseif ($appSource -notmatch 'if \(!string\.Equals\(RevitVersion, "2025", StringComparison\.Ordinal\)\)') {
        throw 'The panel-hub implementation changed and the Revit 2025 UI isolation hotfix could not be applied safely.'
    }
    [System.IO.File]::WriteAllText($appFile, $appSource, [System.Text.UTF8Encoding]::new($false))
    Write-Ok 'The Revit 2025 WebView2 panel was isolated from Manage Links.'

    Start-Step `
        -Title 'Verify simultaneous Revit versions' `
        -Explanation 'The maintained fork resolves the Contract v2 registry entry for each selected Revit version instead of overwriting another running connection.'

    $configFile = Join-Path $sourceRoot 'packages\mcp-server-revit\src\revit_mcp_server\config.py'
    $discoveryFile = Join-Path $sourceRoot 'packages\mcp-server-revit\src\revit_mcp_server\bridge\discovery.py'
    $providerFile = Join-Path $sourceRoot 'packages\mcp-server-revit\src\revit_mcp_server\providers\revit.py'

    foreach ($requiredFile in @($configFile, $discoveryFile, $providerFile)) {
        if (-not (Test-Path -LiteralPath $requiredFile)) {
            throw "Required multi-version source file was not found: $requiredFile"
        }
    }

    $configSource = Get-Content -LiteralPath $configFile -Raw -ErrorAction Stop
    if ($configSource -notmatch 'target_version:\s*str\s*\|\s*None') {
        $configSource = $configSource.Replace(
            '    bridge_url: str | None = Field(default=None)',
            "    bridge_url: str | None = Field(default=None)`r`n    target_version: str | None = Field(default=None)"
        )
        [System.IO.File]::WriteAllText($configFile, $configSource, [System.Text.UTF8Encoding]::new($false))
    }

    $discoverySource = Get-Content -LiteralPath $discoveryFile -Raw -ErrorAction Stop
    $oldDiscoveryBlock = @'
            # Prefer the most recently started switch for a given provider
            if info.provider_id in switches:
                existing = switches[info.provider_id]
                try:
                    existing_start = datetime.fromisoformat(existing.started_at.replace('Z', '+00:00'))
                    new_start = datetime.fromisoformat(info.started_at.replace('Z', '+00:00'))
                    if new_start > existing_start:
                        switches[info.provider_id] = info
                except ValueError:
                    switches[info.provider_id] = info
            else:
                switches[info.provider_id] = info
'@
    $newDiscoveryBlock = @'
            # Keep one entry per host version so multiple Revit versions can run
            # simultaneously. Preserve the provider-only key as the latest instance
            # for backward compatibility with clients that do not select a version.
            version_key = f"{info.provider_id}-{info.host_version}"

            if version_key in switches:
                existing = switches[version_key]
                try:
                    existing_start = datetime.fromisoformat(existing.started_at.replace('Z', '+00:00'))
                    new_start = datetime.fromisoformat(info.started_at.replace('Z', '+00:00'))
                    if new_start > existing_start:
                        switches[version_key] = info
                except ValueError:
                    switches[version_key] = info
            else:
                switches[version_key] = info

            if info.provider_id in switches:
                existing = switches[info.provider_id]
                try:
                    existing_start = datetime.fromisoformat(existing.started_at.replace('Z', '+00:00'))
                    new_start = datetime.fromisoformat(info.started_at.replace('Z', '+00:00'))
                    if new_start > existing_start:
                        switches[info.provider_id] = info
                except ValueError:
                    switches[info.provider_id] = info
            else:
                switches[info.provider_id] = info
'@

    if ($discoverySource.Contains($oldDiscoveryBlock)) {
        $discoverySource = $discoverySource.Replace($oldDiscoveryBlock, $newDiscoveryBlock)
        [System.IO.File]::WriteAllText($discoveryFile, $discoverySource, [System.Text.UTF8Encoding]::new($false))
    }
    elseif ($discoverySource -notmatch 'version_key\s*=\s*f"\{info\.provider_id\}-\{info\.host_version\}"') {
        throw 'The discovery implementation changed and the multi-version patch could not be applied safely.'
    }

    $providerSource = Get-Content -LiteralPath $providerFile -Raw -ErrorAction Stop
    $oldProviderBlock = @'
            if not url:
                if "revit" in switches:
                    url = switches["revit"].endpoint
                    token = switches["revit"].session_token
                    logger.info("Resolved Revit switch from registry: %s", url)
                else:
'@
    $newProviderBlock = @'
            if not url:
                target_version = getattr(config, "target_version", None)
                switch_key = f"revit-{target_version}" if target_version else "revit"

                if switch_key in switches:
                    url = switches[switch_key].endpoint
                    token = switches[switch_key].session_token
                    logger.info(
                        "Resolved Revit switch from registry: version=%s endpoint=%s",
                        target_version or "latest",
                        url,
                    )
                else:
'@

    if ($providerSource.Contains($oldProviderBlock)) {
        $providerSource = $providerSource.Replace($oldProviderBlock, $newProviderBlock)
        [System.IO.File]::WriteAllText($providerFile, $providerSource, [System.Text.UTF8Encoding]::new($false))
    }
    elseif ($providerSource -notmatch 'switch_key\s*=\s*f"revit-\{target_version\}"') {
        throw 'The Revit provider implementation changed and the multi-version patch could not be applied safely.'
    }

    Write-Ok 'Simultaneous Revit version routing was enabled.'

    Start-Step `
        -Title 'Verify dynamic Revit bridge discovery' `
        -Explanation 'The maintained fork refreshes Contract v2 before Revit requests, so an AI client can start before Revit and connect when it opens later.'

    $providerSource = Get-Content -LiteralPath $providerFile -Raw -ErrorAction Stop
    if ($providerSource -notmatch 'def _refresh_bridge_from_registry\(self\)') {
        $dynamicDiscoveryMethod = @'
    def _refresh_bridge_from_registry(self) -> None:
        """Adopt the live, version-specific Contract v2 endpoint when Revit starts after this MCP process."""
        if self.mode != BridgeMode.bridge or self.bridge_url:
            return

        from ..bridge.discovery import discover_switches
        switches = discover_switches()
        target_version = getattr(config, "target_version", None)
        switch_key = f"revit-{target_version}" if target_version else "revit"
        switch = switches.get(switch_key)
        if not switch:
            return

        current_url = getattr(self._bridge, "base_url", "").rstrip("/")
        current_token = getattr(self._bridge, "token", None)
        endpoint = switch.endpoint.rstrip("/")
        if current_url == endpoint and current_token == switch.session_token:
            return

        logger.info("Refreshing Revit bridge from registry: version=%s endpoint=%s", target_version or "latest", endpoint)
        bridge = BridgeClient(endpoint, token=switch.session_token)
        if hasattr(bridge, "initialize"):
            try:
                bridge.initialize()
            except Exception as e:
                logger.warning("Newly discovered Revit bridge is not ready yet: %s", e)
                return
        self._bridge = bridge

'@
        $providerMarker = '    def get_capabilities(self) -> List[ProviderTool]:'
        if (-not $providerSource.Contains($providerMarker)) {
            throw 'The Revit provider implementation changed and the dynamic discovery patch could not be applied safely.'
        }
        $providerSource = $providerSource.Replace($providerMarker, $dynamicDiscoveryMethod + $providerMarker)
    }

    $healthMarker = "        if self.mode == BridgeMode.bridge:`r`n            try:"
    $healthReplacement = "        if self.mode == BridgeMode.bridge:`r`n            self._refresh_bridge_from_registry()`r`n            try:"
    if ($providerSource.Contains($healthMarker)) {
        $providerSource = $providerSource.Replace($healthMarker, $healthReplacement)
    }
    elseif ($providerSource -notmatch 'async def check_health[\s\S]{0,250}_refresh_bridge_from_registry\(\)') {
        throw 'The Revit health implementation changed and the dynamic discovery call could not be applied safely.'
    }

    $executeMarker = "    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:`r`n        # Check path parameters for workspace compliance"
    $executeReplacement = "    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:`r`n        if self.mode == BridgeMode.bridge:`r`n            self._refresh_bridge_from_registry()`r`n`r`n        # Check path parameters for workspace compliance"
    if ($providerSource.Contains($executeMarker)) {
        $providerSource = $providerSource.Replace($executeMarker, $executeReplacement)
    }
    elseif ($providerSource -notmatch 'async def execute_tool[\s\S]{0,250}_refresh_bridge_from_registry\(\)') {
        throw 'The Revit execution implementation changed and the dynamic discovery call could not be applied safely.'
    }
    [System.IO.File]::WriteAllText($providerFile, $providerSource, [System.Text.UTF8Encoding]::new($false))
    Write-Ok 'Dynamic Revit bridge discovery was enabled.'

    Start-Step `
        -Title 'Verify the maintained AEC fork' `
        -Explanation 'The script confirms that the downloaded source includes the agreed Revit fixes and the bundled Codex BIM skill.'

    Assert-MaintainedAecFork -SourceRoot $sourceRoot

    Start-Step `
        -Title 'Enable advanced Revit API access' `
        -Explanation 'Raw Python host execution and user modules are enabled so Codex or Claude can call Revit API functionality that is not included in the built-in tool catalog.'

    Write-Ok 'Advanced Revit API access was enabled.'

    Start-Step `
        -Title 'Prepare the Python MCP server' `
        -Explanation 'A dedicated virtual environment is created so the bridge dependencies do not modify the global Python installation.'

    $venvRoot = Join-Path $sourceRoot '.venv'
    $venvPython = Join-Path $venvRoot 'Scripts\python.exe'

    if (-not (Test-Path -LiteralPath $venvPython)) {
        try {
            Invoke-CheckedProcess `
                -FilePath $pythonExe `
                -Arguments @('-m', 'venv', $venvRoot) `
                -Description 'Creating the Python virtual environment' `
                -WorkingDirectory $sourceRoot
        }
        catch {
            Write-WarningMessage 'The first virtual-environment attempt failed. Removing the incomplete environment and retrying once.'
            Remove-Item -LiteralPath $venvRoot -Recurse -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2

            Invoke-CheckedProcess `
                -FilePath $pythonExe `
                -Arguments @('-m', 'venv', $venvRoot) `
                -Description 'Creating the Python virtual environment on the second attempt' `
                -WorkingDirectory $sourceRoot
        }
    }
    else {
        Write-Ok "Python virtual environment already exists."
    }

    Invoke-CheckedProcess `
        -FilePath $venvPython `
        -Arguments @('-m', 'pip', 'install', '--upgrade', 'pip') `
        -Description 'Updating pip inside the bridge virtual environment' `
        -WorkingDirectory $sourceRoot

    Invoke-CheckedProcess `
        -FilePath $venvPython `
        -Arguments @('-m', 'pip', 'install', '-e', 'packages/mcp-server-revit', 'mcp>=1.25,<2') `
        -Description 'Installing the AEC Model Bridge Python MCP server with MCP SDK v1 compatibility' `
        -WorkingDirectory $sourceRoot

    Start-Step `
        -Title 'Build and install Revit add-ins' `
        -Explanation 'The script builds and installs a separate add-in package for every detected supported Revit version.'

    foreach ($version in $revitVersions) {
        Write-Info "Preparing Revit $version."

        $packageScript = Join-Path $sourceRoot 'scripts\package.ps1'
        $installScript = Join-Path $sourceRoot 'scripts\install.ps1'

        Invoke-CheckedProcess `
            -FilePath 'powershell.exe' `
            -Arguments @(
                '-NoLogo',
                '-NoProfile',
                '-ExecutionPolicy', 'Bypass',
                '-File', $packageScript,
                '-RevitVersion', $version
            ) `
            -Description "Building the AEC Model Bridge package for Revit $version" `
            -WorkingDirectory $sourceRoot

        Invoke-CheckedProcess `
            -FilePath 'powershell.exe' `
            -Arguments @(
                '-NoLogo',
                '-NoProfile',
                '-ExecutionPolicy', 'Bypass',
                '-File', $installScript,
                '-RevitVersion', $version,
                '-AllUsers'
            ) `
            -Description "Installing the AEC Model Bridge add-in for Revit $version" `
            -WorkingDirectory $sourceRoot
    }

    Start-Step `
        -Title 'Configure permanent bridge paths' `
        -Explanation 'All currently available local drives, removable drives, mapped network drives, and their current UNC targets are allowed. The values are saved permanently.'

    $allowedDirectories = Get-AllowedDirectories
    $allowedValue = $allowedDirectories -join ';'
    $workspace = if ($allowedDirectories -contains "$env:SystemDrive\") {
        "$env:SystemDrive\"
    }
    else {
        $allowedDirectories[0]
    }

    Write-Ok "Allowed workspace paths were detected."
    Set-PersistentBridgeEnvironment -Workspace $workspace -Allowed $allowedValue

    Start-Step `
        -Title 'Test the Python MCP server' `
        -Explanation 'Immediate startup errors are printed. A server that remains alive for 5 seconds is stopped automatically and passes the test.'

    Test-McpServerStartup -PythonExe $venvPython -WorkingDirectory $sourceRoot

    Start-Step `
        -Title "Configure $client" `
        -Explanation "Only the AEC Model Bridge entry is added or repaired. Existing unrelated MCP servers and client settings are preserved."

    if ($client -eq 'Codex') {
        Configure-Codex -PythonExe $venvPython -Workspace $workspace -Allowed $allowedValue -RevitVersions $revitVersions
        Install-AecRevitBimSkill -SourceRoot $sourceRoot
    }
    elseif ($client -eq 'Claude') {
        Configure-Claude -PythonExe $venvPython -Workspace $workspace -Allowed $allowedValue -RevitVersions $revitVersions
        Write-Info 'To add the optional Revit BIM skills in Claude Desktop Chat, open Customize > Plugins, add marketplace Moorlack/aec-model-bridge, then install aec-revit-bim.'
    }
    else {
        Configure-Antigravity -PythonExe $venvPython -Workspace $workspace -Allowed $allowedValue -RevitVersions $revitVersions
        Install-AecRevitBimAntigravityPlugin -SourceRoot $sourceRoot
    }

    }

    if ($script:BridgeProduct -eq 'AutoCAD') {
    if ($script:SelectedAction -eq 'UpdateServer') {
        Start-Step `
            -Title 'Check running AutoCAD MCP clients' `
            -Explanation 'The code is shared by every AI client. Clients started before the update keep using the previous version.'
        if (-not (Confirm-NoRunningAutoCadMcp (Join-Path $env:ProgramData 'AECModelBridge\autocad'))) {
            Write-WarningMessage 'Update was cancelled. No changes were made.'
            try { Stop-Transcript | Out-Null } catch {}
            exit 0
        }
    }

    Start-Step `
        -Title 'Download or update best-cad-mcp' `
        -Explanation 'The AutoCAD MCP source is stored separately in ProgramData. An existing repository is updated instead of being deleted.'

    $autoCadRoot = Join-Path $env:ProgramData 'AECModelBridge\autocad'
    $autoCadRepoUrl = 'https://github.com/Moorlack/best-cad-mcp.git'
    $autoCadRepoBranch = 'master'
    $autoCadGitPath = Join-Path $autoCadRoot '.git'
    if (Test-Path -LiteralPath $autoCadGitPath) {
        Invoke-CheckedProcess -FilePath $gitExe -Arguments @('-C', $autoCadRoot, 'remote', 'set-url', 'origin', $autoCadRepoUrl) -Description 'Selecting the maintained AutoCAD MCP fork' -WorkingDirectory $autoCadRoot
        $autoCadStatus = & $gitExe -C $autoCadRoot status --porcelain 2>$null
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to inspect local changes in the best-cad-mcp repository (git exit code $LASTEXITCODE)."
        }
        if ($autoCadStatus) {
            $stashMessage = "best-cad-mcp setup backup $(Get-Date -Format 'yyyyMMdd_HHmmss')"
            Write-WarningMessage 'Local best-cad-mcp source changes were found. Saving them to Git stash before update.'
            Invoke-CheckedProcess -FilePath $gitExe -Arguments @('-C', $autoCadRoot, 'stash', 'push', '--include-untracked', '-m', $stashMessage) -Description 'Saving local best-cad-mcp changes before update' -WorkingDirectory $autoCadRoot
            Write-Info "Saved local source changes to Git stash: $stashMessage"
        }
        Invoke-CheckedProcess -FilePath $gitExe -Arguments @('-C', $autoCadRoot, 'pull', '--ff-only', 'origin', $autoCadRepoBranch) -Description 'Updating best-cad-mcp from the maintained fork' -WorkingDirectory $autoCadRoot
    }
    else {
        if (Test-Path -LiteralPath $autoCadRoot) {
            Move-Item -LiteralPath $autoCadRoot -Destination "$autoCadRoot.backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')" -ErrorAction Stop
        }
        New-Item -ItemType Directory -Path (Split-Path $autoCadRoot -Parent) -Force | Out-Null
        Invoke-CheckedProcess -FilePath $gitExe -Arguments @('clone', '--branch', $autoCadRepoBranch, '--depth', '1', $autoCadRepoUrl, $autoCadRoot) -Description 'Downloading best-cad-mcp from the maintained fork' -WorkingDirectory (Split-Path $autoCadRoot -Parent)
    }

    Start-Step `
        -Title 'Prepare the AutoCAD MCP server' `
        -Explanation 'A dedicated virtual environment is created so AutoCAD bridge dependencies do not modify the global Python installation.'

    # best-cad-mcp 1.7+ requires MCP SDK 2.x. Keep a separate environment so
    # old MCP 1.x files with restrictive ACLs cannot block the upgrade.
    $autoCadVenv = Join-Path $autoCadRoot '.venv-mcp2'
    $autoCadPython = Join-Path $autoCadVenv 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $autoCadPython)) {
        Invoke-CheckedProcess -FilePath $pythonExe -Arguments @('-m', 'venv', $autoCadVenv) -Description 'Creating the AutoCAD MCP virtual environment' -WorkingDirectory $autoCadRoot
    }
    Invoke-CheckedProcess -FilePath $autoCadPython -Arguments @('-m', 'pip', 'install', '--no-cache-dir', '--upgrade', 'pip') -Description 'Updating pip inside the AutoCAD MCP virtual environment' -WorkingDirectory $autoCadRoot
    Invoke-CheckedProcess -FilePath $autoCadPython -Arguments @('-m', 'pip', 'install', '--no-cache-dir', '--upgrade', '-e', '.[visual]') -Description 'Installing the maintained AutoCAD MCP with visual dependencies' -WorkingDirectory $autoCadRoot
    Invoke-CheckedProcess -FilePath $autoCadPython -Arguments @('-m', 'src.visual_selftest') -Description 'Checking image conversion without opening or changing AutoCAD drawings' -WorkingDirectory $autoCadRoot
    Test-AutoCadMcpServerStartup -PythonExe $autoCadPython -WorkingDirectory $autoCadRoot

    $installedCommit = (& $gitExe -C $autoCadRoot log -1 --format='%h %s' 2>$null | Out-String).Trim()
    if ($installedCommit) { Write-Ok "Installed AutoCAD MCP version: $installedCommit" }

    if ($script:SelectedAction -eq 'UpdateServer') {
        $clientsToRestart = @()
        if (Test-CodexBridgeConfigured) { $clientsToRestart += 'ChatGPT/Codex' }
        if (Test-ClaudeBridgeConfigured) { $clientsToRestart += 'Claude' }
        if (Test-AntigravityBridgeConfigured) { $clientsToRestart += 'Google Antigravity' }
        Write-Host ''
        Write-Ok 'Done. The shared AutoCAD MCP server was updated; client registrations were not changed.'
        if ($clientsToRestart) { Write-Info "Fully restart (including the tray): $($clientsToRestart -join ', '), then AutoCAD." }
        else { Write-WarningMessage 'No configured AI client was detected. Use Install/Repair for a client to register the server.' }
        Write-Info "Full log file: $logPath"
        try { Stop-Transcript | Out-Null } catch {}
        exit 0
    }

    $allowedDirectories = Get-AllowedDirectories
    $allowedValue = $allowedDirectories -join ';'
    $workspace = if ($allowedDirectories -contains "$env:SystemDrive\") { "$env:SystemDrive\" } else { $allowedDirectories[0] }

    Start-Step `
        -Title "Configure AutoCAD MCP for $client" `
        -Explanation 'One COM-based AutoCAD MCP server is registered. It can control every detected supported AutoCAD version available to the current Windows user.'

    if ($client -eq 'Codex') {
        Configure-AutoCadCodex -PythonExe $autoCadPython -SourceRoot $autoCadRoot -Workspace $workspace
    }
    elseif ($client -eq 'Claude') {
        Configure-AutoCadClaude -PythonExe $autoCadPython -SourceRoot $autoCadRoot -Workspace $workspace
    }
    else {
        Configure-AutoCadAntigravity -PythonExe $autoCadPython -SourceRoot $autoCadRoot -Workspace $workspace
    }
    }

    Write-Host ''
    Write-Ok "Done. $($script:BridgeProductLabel) MCP bridge was configured."
    if ($client -eq 'Codex') {
        Write-Info 'Open or restart the ChatGPT desktop app, sign in if needed, then choose Codex.'
    }
    elseif ($client -eq 'Antigravity') {
        Write-Info 'Open Google Antigravity from Start menu, sign in with Google, then create or open a project. The MCP bridges are already configured globally.'
    }
    else {
        Write-Info "Restart $client before using the new MCP server."
    }
    Write-Info "Open the required $($script:BridgeProductLabel) version before giving it a task."
    Write-Info 'Press any key when the setup window asks to exit.'
    Write-Info "Full log file: $logPath"
    try { Stop-Transcript | Out-Null } catch {}
    exit 0
}
catch {
    Write-Host ''
    Write-Host 'DETAILED ERROR REPORT' -ForegroundColor Red
    Write-ErrorMessage "Current step number: $StepNumber"
    Write-ErrorMessage "Last native exit code: $LASTEXITCODE"
    Write-Host '=====================' -ForegroundColor Red
    Write-Host ($_ | Format-List * -Force | Out-String) -ForegroundColor Red

    Write-Host '[EXCEPTION]' -ForegroundColor DarkRed
    Write-Host ($_.Exception | Format-List * -Force | Out-String) -ForegroundColor Red

    Write-Host '[SCRIPT STACK TRACE]' -ForegroundColor DarkRed
    Write-Host $_.ScriptStackTrace -ForegroundColor Red

    if ($logPath) {
        Write-ErrorMessage "Full log file: $logPath"
    }

    try { Stop-Transcript | Out-Null } catch {}

    Write-ErrorMessage "The script stopped at the failing step."
    exit 1
}
