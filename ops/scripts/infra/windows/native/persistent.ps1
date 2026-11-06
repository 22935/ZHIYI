param(
    [Parameter(Mandatory=$true)][ValidateSet('init','up','status','down','recover','backup','restore')][string]$Action,
    [string]$HomeDir = "$env:LOCALAPPDATA\ZhiyiNative\default",
    [string]$Python = "$env:LOCALAPPDATA\ZhiyiNative\python\Scripts\python.exe",
    [string]$PostgresBin = "$env:LOCALAPPDATA\ZhiyiNative\dependencies\postgresql-15.19\pgsql\bin",
    [string]$Memurai = "$env:LOCALAPPDATA\ZhiyiNative\dependencies\memurai-4.1.2\memurai.exe",
    [string]$ProviderKeyFile,
    [string]$Workspace,
    [string]$TestPython,
    [string]$BackendJar,
    [string]$Snapshot,
    [ValidateRange(0,1000)][int]$PortOffset = 0,
    [switch]$Desktop
)
$ErrorActionPreference = 'Stop'
$nativeArgs = @("$PSScriptRoot\persistent_runtime.py",$Action,'--home',$HomeDir)
if ($Action -eq 'init') {
    $nativeArgs += @('--postgres-bin',$PostgresBin,'--memurai',$Memurai)
    $nativeArgs += @('--port-offset',"$PortOffset")
    if ($ProviderKeyFile) { $nativeArgs += @('--provider-key-file',$ProviderKeyFile) }
    if ($Workspace) { $nativeArgs += @('--workspace',$Workspace) }
    if ($TestPython) { $nativeArgs += @('--test-python',$TestPython) }
    if ($BackendJar) { $nativeArgs += @('--backend-jar',$BackendJar) }
}
if ($Desktop) { $nativeArgs += '--desktop' }
if ($Snapshot) { $nativeArgs += @('--snapshot',$Snapshot) }
& $Python @nativeArgs
exit $LASTEXITCODE
