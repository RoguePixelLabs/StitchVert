param(
    [Parameter(Mandatory = $true)][string]$InnoCompiler,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $PSScriptRoot
$runtimeRoot = & $Python -c 'import pathlib, platform, sys, tkinter; assert sys.platform == "win32" and platform.machine() == "AMD64"; print(pathlib.Path(sys.base_prefix))'
if ($LASTEXITCODE -ne 0) { throw "A 64-bit Windows CPython installation with Tk is required." }
$version = & $Python -c 'import runpy,sys; print(runpy.run_path(sys.argv[1])["VERSION"])' (Join-Path $project "updates.py")
if ($LASTEXITCODE -ne 0 -or $version -notmatch '^\d+\.\d+\.\d+$') { throw "Invalid app version." }
$stage = [IO.Path]::GetFullPath((Join-Path $project "build\installer-stage"))
if (-not $stage.StartsWith([IO.Path]::GetFullPath((Join-Path $project "build")) + "\", [StringComparison]::OrdinalIgnoreCase)) {
    throw "Unexpected staging path."
}
if (Test-Path -LiteralPath $stage) {
    if ((Get-Item -LiteralPath $stage).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "The staging folder must be a normal directory."
    }
    Remove-Item -LiteralPath $stage -Recurse -Force
}
$runtime = Join-Path $stage "runtime"
New-Item -ItemType Directory -Path $runtime | Out-Null

$appFiles = @("app.pyw", "converter.py", "legacy_formats.py", "worksheet.py", "updates.py",
    "LICENSE", "LIBEMBROIDERY-LICENSE.txt", "README.md")
foreach ($file in $appFiles) {
    Copy-Item -LiteralPath (Join-Path $project $file) -Destination $stage
}
$codec = New-Item -ItemType Directory -Path (Join-Path $stage "pyembroidery")
Copy-Item -Path (Join-Path $project "pyembroidery\*.py") -Destination $codec.FullName
Copy-Item -LiteralPath (Join-Path $project "pyembroidery\LICENSE.txt") -Destination $codec.FullName

foreach ($file in @("python.exe", "pythonw.exe", "LICENSE.txt")) {
    Copy-Item -LiteralPath (Join-Path $runtimeRoot $file) -Destination $runtime
}
Get-ChildItem -LiteralPath $runtimeRoot -File | Where-Object Name -Match '^(python\d+(t)?|vcruntime140(_1)?)\.dll$' |
    Copy-Item -Destination $runtime
foreach ($folder in @("Lib", "DLLs", "tcl")) {
    $target = Join-Path $runtime $folder
    & robocopy (Join-Path $runtimeRoot $folder) $target /E /XJ /XD __pycache__ site-packages test tests idlelib turtledemo ensurepip /XF *.pyc *.pyo *.lib /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "Could not stage CPython's $folder directory." }
}
& (Join-Path $runtime "python.exe") -I -c 'import ssl, tkinter; root=tkinter.Tk(); root.withdraw(); root.destroy()'
if ($LASTEXITCODE -ne 0) { throw "The staged CPython runtime failed its smoke test." }

& $InnoCompiler "/Qp" "/DAppVersion=$version" (Join-Path $PSScriptRoot "StitchVert.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed." }
$installer = Join-Path $project "dist\StitchVert-$version-Windows-x64-Setup.exe"
$hash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  $([IO.Path]::GetFileName($installer))" | Set-Content -LiteralPath "$installer.sha256" -Encoding ascii
Write-Output $installer
