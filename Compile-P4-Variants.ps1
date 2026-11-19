[CmdletBinding()]
param(
    [string]$ArduinoCli = 'arduino-cli',
    [string]$OutputRoot = '',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$sketch = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $sketch 'build_variants'
}
$sketchFiles = @(Get-ChildItem -LiteralPath $sketch -Filter '*.ino' -File)
if ($sketchFiles.Count -ne 1) {
    throw 'Expected exactly one .ino file in the project folder.'
}
$cli = (Get-Command $ArduinoCli -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$python = (Get-Command python -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
if (!(Test-Path -LiteralPath (Join-Path $sketch 'zh-CN/dashboard_source.zh-CN.html') -PathType Leaf)) {
    throw 'Missing zh-CN/dashboard_source.zh-CN.html'
}
$output = [System.IO.Path]::GetFullPath($OutputRoot)
$finalBuild = Join-Path $sketch 'Final-Build'
$sketchName = $sketchFiles[0].Name
$firmwareName = $sketchFiles[0].BaseName
$revisions = @{ postv3 = 'REV3.X'; prev3 = 'REV1.X' }
$options = 'FlashSize=32M,PartitionScheme=app3M_fat9M_16MB,PSRAM=enabled,USBMode=hwcdc,CDCOnBoot=cdc,FlashMode=qio'
$failed = @()

# Keep all compiler work directories and exported binaries isolated.
foreach ($configuration in @(
    @{ Variant = 'postv3'; Chinese = $false },
    @{ Variant = 'prev3'; Chinese = $false },
    @{ Variant = 'postv3'; Chinese = $true },
    @{ Variant = 'prev3'; Chinese = $true }
)) {
    $variant = $configuration.Variant
    $languageSuffix = if ($configuration.Chinese) { '.zh-CN' } else { '' }
    $buildId = "$variant$languageSuffix"
    $destination = Join-Path $output $buildId
    $buildPath = Join-Path $destination 'build'
    $artifacts = Join-Path $destination 'firmware'
    $log = Join-Path $destination 'compile.log'
    $fqbn = "esp32:esp32:esp32p4:ChipVariant=$variant,$options"
    $revision = $revisions[$variant]
    $releaseName = "$firmwareName$languageSuffix"
    $compileSketch = $sketch
    if ($configuration.Chinese -and !$DryRun) {
        $prepared = & $python (Join-Path $sketch 'tools/prepare_chinese_build.py') --project $sketch --destination (Join-Path $destination 'work') --output-root $output
        if ($LASTEXITCODE -ne 0) {
            $failed += $buildId
            Write-Host "FAILED: $buildId preparing Chinese dashboard" -ForegroundColor Red
            continue
        }
        $compileSketch = [string]($prepared | Select-Object -Last 1)
    }
    $cliArgs = @('compile', '--fqbn', $fqbn, '--build-path', $buildPath,
        '--output-dir', $artifacts, $compileSketch)

    Write-Host "`n=== $buildId ==="
    Write-Host "Board: $fqbn"
    Write-Host "Firmware: $artifacts"
    Write-Host "Final OTA: $(Join-Path $finalBuild "$releaseName.OTA.$revision.bin")"
    Write-Host "Final fullflash: $(Join-Path $finalBuild "$releaseName.FULLFLASH.$revision.merged.bin")"
    if ($DryRun) {
        if ($configuration.Chinese) { Write-Host 'Plan: copy sketch into isolated work folder, embed zh-CN dashboard, compile that copy.' }
        Write-Host ('Command: "{0}" {1}' -f $cli, (($cliArgs | ForEach-Object { '"' + $_ + '"' }) -join ' '))
        continue
    }

    New-Item -ItemType Directory -Path $destination, $buildPath, $artifacts -Force | Out-Null
    # Record all output while keeping Arduino CLI's own exit code authoritative.
    # Windows PowerShell can wrap native stderr as ErrorRecord objects.
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $cli @cliArgs 2>&1 | Tee-Object -FilePath $log
        $result = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($result -ne 0) {
        $failed += $buildId
        Write-Host "FAILED: $buildId (exit $result). Log: $log" -ForegroundColor Red
    } else {
        try {
            # Only the application OTA binary and merged fullflash are published.
            $publishFiles = @(
                @{ Source = "$sketchName.bin"; Target = "$releaseName.OTA.$revision.bin" },
                @{ Source = "$sketchName.merged.bin"; Target = "$releaseName.FULLFLASH.$revision.merged.bin" }
            )
            foreach ($file in $publishFiles) {
                $original = Join-Path $artifacts $file.Source
                if (!(Test-Path -LiteralPath $original -PathType Leaf) -or
                    (Get-Item -LiteralPath $original).Length -eq 0) {
                    throw "Missing or empty compiler output: $original"
                }
            }
            New-Item -ItemType Directory -Path $finalBuild -Force | Out-Null
            foreach ($file in $publishFiles) {
                $original = Join-Path $artifacts $file.Source
                $renamed = Join-Path $artifacts $file.Target
                Move-Item -LiteralPath $original -Destination $renamed -Force
                Copy-Item -LiteralPath $renamed -Destination (Join-Path $finalBuild $file.Target) -Force
            }
            Write-Host "SUCCESS: $buildId ($revision). OTA and fullflash copied to $finalBuild" -ForegroundColor Green
        } catch {
            $failed += $buildId
            Write-Host "FAILED: $buildId packaging. $_" -ForegroundColor Red
        }
    }
}

if ($failed.Count -gt 0) {
    Write-Host ("Build failed: " + ($failed -join ', ')) -ForegroundColor Red
    exit 1
}
if ($DryRun) { Write-Host "`nDry run complete. No compilation was started." }
else {
    Write-Host "`nAll four variants compiled successfully. Final binaries: $finalBuild"
    # Delete only the explicitly named project build_variants directory.
    # A custom OutputRoot may contain unrelated files and is retained.
    $cleanupTarget = [System.IO.Path]::GetFullPath((Join-Path $sketch 'build_variants')).TrimEnd('\', '/')
    if ($output.TrimEnd('\', '/') -ieq $cleanupTarget) {
        $resolvedTarget = (Resolve-Path -LiteralPath $output).ProviderPath.TrimEnd('\', '/')
        $targetItem = Get-Item -LiteralPath $output
        if ($resolvedTarget -ine $cleanupTarget -or
            ($targetItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
            throw "Refusing cleanup of redirected build directory: $output"
        }
        Remove-Item -LiteralPath $resolvedTarget -Recurse -Force
        Write-Host "Removed temporary build directory: $resolvedTarget"
    } else {
        Write-Host "Custom output directory retained: $output"
    }
}
exit 0
