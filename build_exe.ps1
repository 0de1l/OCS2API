param(
    [string]$Python = "python",
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot

function Invoke-BuildPython {
    param([string[]]$Arguments)
    # Windows PowerShell 5 treats redirected native stderr as error records.
    # PyInstaller writes progress there; the exit code determines failure.
    $ErrorActionPreference = 'Continue'
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python build step failed with exit code $LASTEXITCODE" }
}

Push-Location $projectRoot
try {
    if (-not $SkipInstall) {
        Invoke-BuildPython -Arguments @('-m', 'pip', 'install', '-r', 'requirements-build.txt')
    }

    if (-not (Test-Path -LiteralPath "logo.png")) { throw "Missing logo.png" }
    New-Item -ItemType Directory -Force "build" | Out-Null
    Invoke-BuildPython -Arguments @('-c', "from PIL import Image, ImageOps; image = ImageOps.pad(Image.open('logo.png').convert('RGBA'), (256,256)); image.save('build/OCS2API.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])")

    Invoke-BuildPython -Arguments @('-m', 'PyInstaller', '--noconfirm', 'OCS2API.spec')
    $artifact = Join-Path $projectRoot 'dist\OCS2API.exe'
    if (-not (Test-Path -LiteralPath $artifact)) { throw "Missing build artifact" }

    Write-Host "Build complete: $artifact"
    Write-Host "Distribute only OCS2API.exe. Runtime config and question bank are not bundled."
} finally {
    Pop-Location
}
