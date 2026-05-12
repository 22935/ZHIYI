param(
    [string]$Keyword = "",
    [switch]$IncludePdf,
    [int]$OpenIndex = -1,
    [string]$OpenPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Open-Document {
    param([string]$TargetPath)

    $resolved = $TargetPath
    if (-not [System.IO.Path]::IsPathRooted($resolved)) {
        $resolved = Join-Path $repoRoot $resolved
    }

    if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
        throw "Document not found: $resolved"
    }

    Start-Process -FilePath $resolved | Out-Null
    Write-Host "Opened: $resolved"
}

if ($OpenPath) {
    Open-Document -TargetPath $OpenPath
    exit 0
}

$patterns = @("*.md")
if ($IncludePdf) {
    $patterns += "*.pdf"
}

$docRoots = @(
    (Join-Path $repoRoot "寮€鍙戞枃妗?),
    (Join-Path $repoRoot "agent\app\data\rag\knowledge_base")
)

$rootDocs = @(
    (Join-Path $repoRoot "README.md"),
    (Join-Path $repoRoot "PROJECT_TECHNICAL_MANUAL.md"),
    (Join-Path $repoRoot "DEFENSE_SCRIPT.md")
)

$files = @()
foreach ($root in $docRoots) {
    if (-not (Test-Path -LiteralPath $root -PathType Container)) {
        continue
    }
    foreach ($pattern in $patterns) {
        $files += Get-ChildItem -Path $root -Recurse -File -Filter $pattern -ErrorAction SilentlyContinue
    }
}

foreach ($doc in $rootDocs) {
    if (-not (Test-Path -LiteralPath $doc -PathType Leaf)) {
        continue
    }
    if ($IncludePdf -or ([System.IO.Path]::GetExtension($doc).ToLowerInvariant() -eq ".md")) {
        $files += Get-Item -LiteralPath $doc
    }
}

$files = $files | Sort-Object -Property FullName -Unique

if ($Keyword) {
    $files = $files | Where-Object {
        $_.Name -like "*$Keyword*" -or $_.FullName -like "*$Keyword*"
    }
}

if (-not $files -or $files.Count -eq 0) {
    Write-Host "No documents found."
    Write-Host "Try: .\scripts\docs.ps1 -IncludePdf"
    exit 1
}

Write-Host "Document list (Ctrl+Click path to open in terminal):"
for ($i = 0; $i -lt $files.Count; $i++) {
    $clickablePath = "{0}:1" -f $files[$i].FullName
    Write-Output ("[{0}] {1}" -f $i.ToString().PadLeft(3), $clickablePath)
}

if ($OpenIndex -ge 0) {
    if ($OpenIndex -ge $files.Count) {
        throw "OpenIndex out of range. Max index is $($files.Count - 1)."
    }
    Open-Document -TargetPath $files[$OpenIndex].FullName
    exit 0
}

Write-Host ""
Write-Host "Tips:"
Write-Host "  - Open by index: .\scripts\docs.ps1 -OpenIndex 0"
Write-Host "  - Filter by keyword: .\scripts\docs.ps1 -Keyword RAG"
Write-Host "  - Include PDFs: .\scripts\docs.ps1 -IncludePdf"
Write-Host "  - Open direct path: .\scripts\docs.ps1 -OpenPath file"
