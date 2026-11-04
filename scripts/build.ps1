param(
    [string]$BlenderPath = 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$addonRoot = Join-Path $projectRoot 'addon'
$outputRoot = Join-Path $projectRoot 'dist'
if (-not (Test-Path -LiteralPath $BlenderPath)) { throw "Blender not found: $BlenderPath" }
New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null
& $BlenderPath --factory-startup --command extension validate $addonRoot
if ($LASTEXITCODE -ne 0) { throw 'Extension validation failed' }
& $BlenderPath --factory-startup --command extension build --source-dir $addonRoot --output-dir $outputRoot
if ($LASTEXITCODE -ne 0) { throw 'Extension build failed' }
Get-ChildItem -LiteralPath $outputRoot -Filter 'unity_view_controls-*.zip'
