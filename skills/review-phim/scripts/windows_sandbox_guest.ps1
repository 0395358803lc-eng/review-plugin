# Runs ONLY inside the Windows Sandbox guest. No host-side PowerShell bypass.
param([Parameter(Mandatory=$true)][string]$JobPath)
$ErrorActionPreference = 'Stop'
$job = Get-Content -LiteralPath $JobPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $job.nonce -or -not $job.job_id -or -not $job.result_path) {
    throw 'Missing immutable guest job metadata'
}
$out = [ordered]@{
    nonce = [string]$job.nonce
    job_id = [string]$job.job_id
    run_id = [string]$job.run_id
    mode = [string]$job.mode
    exit_code = 1
    started_utc = [DateTime]::UtcNow.ToString('o')
}
function Test-ReadOnlyMap([string] $folder) {
    # The test creates no permanent source/logo data. Any unexpected write is removed.
    if (-not (Test-Path -LiteralPath $folder -PathType Container)) { return $false }
    $probe = Join-Path $folder ('.review-sandbox-deny-' + $job.nonce + '.txt')
    $denied = $false
    try { [System.IO.File]::WriteAllText($probe, 'DO-NOT-WRITE-TO-SOURCE'); $denied = $false }
    catch { $denied = $true }
    finally {
        if (Test-Path -LiteralPath $probe) {
            # Delete only the file this probe tried to create.
            try { Remove-Item -LiteralPath $probe -Force -ErrorAction Stop } catch {}
        }
    }
    return $denied
}
try {
    if ($job.mode -eq 'acceptance') {
        $rw = Join-Path $job.guest_work ('runs\' + $job.run_id + '\sandbox_jobs\rw-probe-' + $job.nonce + '.txt')
        [System.IO.File]::WriteAllText($rw, 'guest-workspace-rw-test')
        $workspace_ok = (Test-Path -LiteralPath $rw) -and
            (([System.IO.File]::ReadAllText($rw)) -eq 'guest-workspace-rw-test')
        Remove-Item -LiteralPath $rw -Force
        $video_ok = Test-ReadOnlyMap ([string]$job.guest_source)
        $logo_ok = $true
        if ($job.guest_logo) { $logo_ok = Test-ReadOnlyMap ([string]$job.guest_logo) }
        if (-not (Get-Command Get-NetAdapter -ErrorAction SilentlyContinue)) { throw 'Get-NetAdapter unavailable: cannot verify network isolation' }
        $adapters = @(Get-NetAdapter -ErrorAction Stop |
            Where-Object { $_.Status -eq 'Up' -and $_.Name -notmatch '(?i)loopback' })
        $network_ok = $adapters.Count -eq 0
        $out.acceptance_checks = [ordered]@{
            workspace_rw = [bool]$workspace_ok
            video_root_ro = [bool]$video_ok
            logo_root_ro = [bool]$logo_ok
            network_disabled = [bool]$network_ok
        }
        if ($workspace_ok -and $video_ok -and $logo_ok -and $network_ok) {
            $out.exit_code = 0
        } else {
            $out.error = 'REAL_GUEST_ISOLATION_CHECK_FAILED'
        }
    } elseif ($job.mode -eq 'execute') {
        if (-not $job.executable -or -not $job.cwd) { throw 'Missing executable or cwd' }
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = [string]$job.executable
        $psi.Arguments = [string]$job.args_quoted
        $psi.WorkingDirectory = [string]$job.cwd
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.EnvironmentVariables['TEMP'] = Join-Path $job.guest_work 'tmp'
        $psi.EnvironmentVariables['TMP'] = Join-Path $job.guest_work 'tmp'
        $psi.EnvironmentVariables['HF_HOME'] = Join-Path $job.guest_work 'cache\huggingface'
        $psi.EnvironmentVariables['XDG_CACHE_HOME'] = Join-Path $job.guest_work 'cache'
        $p = New-Object System.Diagnostics.Process
        $p.StartInfo = $psi
        if (-not $p.Start()) { throw 'Guest process could not start' }
        $stdoutTask = $p.StandardOutput.ReadToEndAsync()
        $stderrTask = $p.StandardError.ReadToEndAsync()
        $p.WaitForExit()
        $out.exit_code = [int]$p.ExitCode
        # Bound result size; larger raw logs must be stored in the mapped WORKSPACE.
        $out.stdout = $stdoutTask.Result.Substring(0, [Math]::Min(60000, $stdoutTask.Result.Length))
        $out.stderr = $stderrTask.Result.Substring(0, [Math]::Min(60000, $stderrTask.Result.Length))
    } else {
        throw ('Unsupported guest job mode: ' + $job.mode)
    }
} catch {
    $out.exit_code = 1
    $out.error = $_.Exception.Message
}
$out.finished_utc = [DateTime]::UtcNow.ToString('o')
$tmp = [string]$job.result_path + '.tmp'
[System.IO.File]::WriteAllText($tmp, ($out | ConvertTo-Json -Depth 8 -Compress), ([System.Text.UTF8Encoding]::new($false)))
Move-Item -LiteralPath $tmp -Destination ([string]$job.result_path) -Force
# Exit the disposable VM. The host must not consider launcher exit as success.
Start-Process -FilePath "$env:WINDIR\System32\shutdown.exe" -ArgumentList '/s /t 1' -WindowStyle Hidden
