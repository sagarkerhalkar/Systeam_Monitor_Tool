param(
  [string]$ServerUrl = "https://monitor.sagarkerhalkar.com"
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Dist = Join-Path $Root 'dist'
New-Item -ItemType Directory -Force -Path $Dist | Out-Null
$ServerUrl = $ServerUrl.TrimEnd('/')
$src = Join-Path $Dist 'SagarMonitorClientSetup.cs'
$exe = Join-Path $Dist 'SagarMonitorClientSetup.exe'
$serverLiteral = $ServerUrl.Replace('\\','\\\\').Replace('"','\"')
@"
using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Security.Principal;

class SagarMonitorClientSetup {
  const string ServerUrl = "$serverLiteral";
  static bool IsAdmin(){
    try { return new WindowsPrincipal(WindowsIdentity.GetCurrent()).IsInRole(WindowsBuiltInRole.Administrator); }
    catch { return false; }
  }
  static void RelaunchAsAdmin(){
    var psi = new ProcessStartInfo();
    psi.FileName = Process.GetCurrentProcess().MainModule.FileName;
    psi.UseShellExecute = true;
    psi.Verb = "runas";
    Process.Start(psi);
  }
  [STAThread]
  static int Main(){
    try{
      if(!IsAdmin()){ RelaunchAsAdmin(); return 0; }
      string temp = @"C:\Temp";
      Directory.CreateDirectory(temp);
      string bootstrap = Path.Combine(temp, "BOOTSTRAP_WINDOWS_CLIENT_2278.ps1");
      using(var wc = new WebClient()){
        wc.Headers.Add("User-Agent", "SagarMonitorClientSetup/6.0");
        wc.DownloadFile(ServerUrl + "/scripts/BOOTSTRAP_WINDOWS_CLIENT_2278.ps1", bootstrap);
      }
      var ps = new ProcessStartInfo();
      ps.FileName = "powershell.exe";
      ps.Arguments = "-NoProfile -ExecutionPolicy Bypass -File \"" + bootstrap + "\" -ServerUrl \"" + ServerUrl + "\"";
      ps.UseShellExecute = true;
      ps.Verb = "runas";
      var p = Process.Start(ps);
      if(p != null) p.WaitForExit();
      return 0;
    }catch(Exception ex){
      File.WriteAllText(@"C:\Temp\SagarMonitorClientSetup_error.txt", ex.ToString());
      return 1;
    }
  }
}
"@ | Set-Content -Path $src -Encoding UTF8
$candidates = @(
  "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
  "$env:WINDIR\Microsoft.NET\Framework\v4.0.30319\csc.exe"
) | Where-Object { Test-Path $_ }
if(-not $candidates){ throw "csc.exe not found. Install .NET Framework Developer Pack or use SagarMonitorClientSetup.vbs fallback." }
& $candidates[0] /nologo /target:winexe /out:$exe $src
Write-Host "Created: $exe" -ForegroundColor Green
Write-Host "Copy this EXE to Windows clients and double-click as Administrator." -ForegroundColor Cyan

