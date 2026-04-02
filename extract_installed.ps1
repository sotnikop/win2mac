# extract_installed.ps1
# Collects all installed programs from Windows registry and winget
# Output: installed_programs.csv and installed_programs.txt

$outputDir = "$env:USERPROFILE\Documents\mac-migration"
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$csvPath  = "$outputDir\installed_programs.csv"
$txtPath  = "$outputDir\installed_programs.txt"

Write-Host "Collecting installed programs..."

# --- Registry sources ---
$regPaths = @(
    "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
    "HKLM:\Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
    "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*"
)

$programs = @{}

foreach ($path in $regPaths) {
    Get-ItemProperty $path -ErrorAction SilentlyContinue |
    Where-Object { $_.DisplayName -and $_.DisplayName.Trim() -ne "" } |
    ForEach-Object {
        $name = $_.DisplayName.Trim()
        if (-not $programs.ContainsKey($name)) {
            $programs[$name] = [PSCustomObject]@{
                Name      = $name
                Version   = if ($_.DisplayVersion) { $_.DisplayVersion.Trim() } else { "" }
                Publisher = if ($_.Publisher)       { $_.Publisher.Trim() }       else { "" }
                Source    = "Registry"
            }
        }
    }
}

# --- Winget (if available) ---
$wingetAvailable = $null -ne (Get-Command winget -ErrorAction SilentlyContinue)
if ($wingetAvailable) {
    Write-Host "Querying winget..."
    $wingetOutput = winget list --accept-source-agreements 2>$null
    # Skip header lines (everything before the separator line "---")
    $dataStarted = $false
    foreach ($line in $wingetOutput) {
        if ($line -match "^-{3,}") { $dataStarted = $true; continue }
        if (-not $dataStarted)     { continue }
        if ($line.Trim() -eq "")   { continue }

        # winget columns are fixed-width; Name is first ~40 chars
        # Try to parse: Name  Id  Version  Source
        if ($line.Length -gt 10) {
            $name = $line.Substring(0, [Math]::Min(40, $line.Length)).Trim()
            if ($name -and -not $programs.ContainsKey($name)) {
                $programs[$name] = [PSCustomObject]@{
                    Name      = $name
                    Version   = ""
                    Publisher = ""
                    Source    = "Winget"
                }
            }
        }
    }
}

# --- Microsoft Store apps ---
Write-Host "Querying Microsoft Store apps..."
Get-AppxPackage -ErrorAction SilentlyContinue |
Where-Object { $_.Name -notmatch "^Microsoft\.UI\.|^Microsoft\.VCLibs|^Microsoft\.Net|^Windows\." } |
ForEach-Object {
    $name = $_.Name -replace "^[A-Za-z0-9]+\.", "" # strip vendor prefix
    if ($name -and -not $programs.ContainsKey($name)) {
        $programs[$name] = [PSCustomObject]@{
            Name      = $name
            Version   = $_.Version
            Publisher = $_.Publisher
            Source    = "Microsoft Store"
        }
    }
}

# --- Export ---
$sorted = $programs.Values | Sort-Object Name

$sorted | Export-Csv -Path $csvPath -NoTypeInformation -Encoding UTF8
Write-Host "CSV saved: $csvPath"

# Also write a plain text list (one program per line) for easy reading
$sorted | ForEach-Object { $_.Name } | Out-File -FilePath $txtPath -Encoding UTF8
Write-Host "Text list saved: $txtPath"
Write-Host ""
Write-Host "Total programs found: $($sorted.Count)"
Write-Host ""
Write-Host "Next step: run  python assess_mac_compat.py  to generate the Mac compatibility report."
