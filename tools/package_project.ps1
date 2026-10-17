param(
    [string]$OutputDirectory,
    [string]$ScreenshotDirectory
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $projectRoot 'packages' }
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
$release = Get-Content -LiteralPath (Join-Path $projectRoot 'version.json') -Raw | ConvertFrom-Json
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$packageName = "CCTVLogAnalyzer-$($release.version)-source-$stamp"
$staging = Join-Path $OutputDirectory $packageName
New-Item -ItemType Directory -Path $staging | Out-Null

# Select source explicitly: never traverse case results or previous archives.
$selected = @(
    Get-ChildItem -LiteralPath $projectRoot -File -Force | Where-Object {
        $_.Extension -in '.py', '.md', '.bat', '.ps1' -or
        $_.Name -eq 'version.json' -or $_.Name -eq '.gitignore' -or
        $_.Name -like 'requirements*.txt'
    }
    foreach ($directory in 'scripts', 'tests', 'docs', 'assets', 'installer', 'tools') {
        Get-ChildItem -LiteralPath (Join-Path $projectRoot $directory) -File -Recurse |
            Where-Object {
                $_.FullName -notmatch '[\\/]__pycache__[\\/]' -and
                ($_.Extension -in '.py', '.json', '.md', '.png', '.ico', '.iss', '.ps1' -or
                 $_.FullName -eq (Join-Path $projectRoot 'scripts\libewf.dll'))
            }
    }
    Get-ChildItem -LiteralPath (Join-Path $projectRoot 'scratchpad') -File -Recurse |
        Where-Object {
            $_.FullName -notmatch '[\\/](data|__pycache__|tools)[\\/]' -and
            ($_.Extension -in '.py', '.h' -or $_.Name -eq 'tvt_log_enum.txt' -or
             $_.Name -eq 'hik_viewer_copy.txt')
        }
)
foreach ($file in $selected) {
    if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "Refusing linked source file: $($file.FullName)"
    }
    $relative = $file.FullName.Substring($projectRoot.Length + 1)
    $destination = Join-Path $staging $relative
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination)) | Out-Null
    Copy-Item -LiteralPath $file.FullName -Destination $destination
}
if ($ScreenshotDirectory) {
    $screenshots = Get-ChildItem -LiteralPath $ScreenshotDirectory -File |
        Where-Object { $_.Extension -eq '.png' -or $_.Name -eq 'SCREENSHOTS.md' }
    $destination = Join-Path $staging 'screenshots'
    New-Item -ItemType Directory -Path $destination | Out-Null
    foreach ($file in $screenshots) {
        Copy-Item -LiteralPath $file.FullName -Destination $destination
    }
}
$files = @(Get-ChildItem -LiteralPath $staging -File -Recurse | Sort-Object FullName |
    ForEach-Object {
        [ordered]@{
            path = $_.FullName.Substring($staging.Length + 1).Replace('\', '/')
            bytes = $_.Length
            sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    })
$sourceCommit = $null
$sourceClean = $null
if ((Get-Command git -ErrorAction SilentlyContinue) -and (Test-Path -LiteralPath (Join-Path $projectRoot '.git'))) {
    $sourceCommit = & git -C $projectRoot rev-parse HEAD
    $sourceClean = -not [bool](& git -C $projectRoot status --porcelain)
}
$manifest = [ordered]@{
    product = $release.product_name
    version = $release.version
    created_utc = [DateTime]::UtcNow.ToString('o')
    scope = 'Current source snapshot including uncommitted files; no Git history or case data'
    source_commit = $sourceCommit
    source_worktree_clean = $sourceClean
    files = $files
}
$manifest | ConvertTo-Json -Depth 5 |
    Set-Content -LiteralPath (Join-Path $staging 'PACKAGE-MANIFEST.json') -Encoding utf8
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zipPath = "$staging.zip"
[IO.Compression.ZipFile]::CreateFromDirectory(
    $staging, $zipPath, [IO.Compression.CompressionLevel]::Optimal, $true)
$hash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  $([IO.Path]::GetFileName($zipPath))" |
    Set-Content -LiteralPath "$zipPath.sha256" -Encoding ascii
Write-Output "ZIP: $zipPath"
Write-Output "SOURCE FOLDER: $staging"
Write-Output "FILES: $($files.Count) plus manifest"
Write-Output "SHA256: $hash"
