param(
    [Parameter(Mandatory = $true)]
    [string]$DistributionRoot,
    [Parameter(Mandatory = $true)]
    [string]$OutputArchive
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath $DistributionRoot).Path
$output = [IO.Path]::GetFullPath($OutputArchive)
if (Test-Path -LiteralPath $output) {
    throw "Refusing to overwrite existing archive: $output"
}

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$stream = [System.IO.File]::Open($output, [System.IO.FileMode]::CreateNew)
$archive = [System.IO.Compression.ZipArchive]::new(
    $stream,
    [System.IO.Compression.ZipArchiveMode]::Create,
    $false
)
$count = 0
try {
    Get-ChildItem -LiteralPath $root -Recurse -File | ForEach-Object {
        $relative = $_.FullName.Substring($root.Length + 1).Replace("\", "/")
        $parts = $relative -split "/"
        if ($parts[0] -in @("cache", "userconfig", "docs")) { return }
        if ($relative.StartsWith("files/plugins/ginza/bin/")) { return }
        if ($parts -contains "__pycache__") { return }
        if ($_.Extension -eq ".pyc") { return }
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archive,
            $_.FullName,
            $relative,
            [System.IO.Compression.CompressionLevel]::Optimal
        ) | Out-Null
        $count++
    }
}
finally {
    $archive.Dispose()
    $stream.Dispose()
}

Write-Output "created entries=$count path=$output"
