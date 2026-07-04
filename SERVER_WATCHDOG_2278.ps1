$App      = "D:\SagarSystemHealthMonitor"
$Python   = "C:\Users\Pc\AppData\Local\Python\pythoncore-3.14-64\python.exe"
$ServerPy = "$App\server.py"
$Port     = 2278
$DataDir  = "$App\data"

$WatchdogLog = "$DataDir\server_watchdog.log"
$ConsoleLog  = "$DataDir\server_console.log"
$ErrorLog    = "$DataDir\server_error.log"

New-Item -ItemType Directory -Path $DataDir -Force | Out-Null

function Write-WatchdogLog {
    param([string]$Message)

    $Line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"

    Add-Content `
        -Path $WatchdogLog `
        -Value $Line `
        -Encoding UTF8
}

function Test-ServerPort {
    param([int]$TestPort)

    $Client = New-Object System.Net.Sockets.TcpClient

    try {
        $Result = $Client.BeginConnect(
            "127.0.0.1",
            $TestPort,
            $null,
            $null
        )

        $Connected = $Result.AsyncWaitHandle.WaitOne(3000, $false)

        if (-not $Connected) {
            return $false
        }

        $Client.EndConnect($Result)
        return $Client.Connected
    }
    catch {
        return $false
    }
    finally {
        $Client.Close()
    }
}

Write-WatchdogLog "Watchdog started."

while ($true) {
    try {
        if (-not (Test-Path $Python)) {
            Write-WatchdogLog "Python executable missing: $Python"
            Start-Sleep -Seconds 30
            continue
        }

        if (-not (Test-Path $ServerPy)) {
            Write-WatchdogLog "server.py missing: $ServerPy"
            Start-Sleep -Seconds 30
            continue
        }

        # Remove stale monitor processes before creating one server.
        Get-CimInstance Win32_Process |
        Where-Object {
            $_.CommandLine -match "SagarSystemHealthMonitor.*server\.py"
        } |
        ForEach-Object {
            Stop-Process `
                -Id $_.ProcessId `
                -Force `
                -ErrorAction SilentlyContinue
        }

        Start-Sleep -Seconds 2

        Remove-Item $ConsoleLog -Force -ErrorAction SilentlyContinue
        Remove-Item $ErrorLog -Force -ErrorAction SilentlyContinue

        Write-WatchdogLog "Starting server on port $Port."

        $ServerProcess = Start-Process `
            -FilePath $Python `
            -ArgumentList @(
                "-u",
                $ServerPy,
                "--host",
                "0.0.0.0",
                "--port",
                "$Port"
            ) `
            -WorkingDirectory $App `
            -WindowStyle Hidden `
            -RedirectStandardOutput $ConsoleLog `
            -RedirectStandardError $ErrorLog `
            -PassThru

        Write-WatchdogLog "Server PID: $($ServerProcess.Id)"

        $FailureCount = 0

        while (-not $ServerProcess.HasExited) {
            Start-Sleep -Seconds 10
            $ServerProcess.Refresh()

            if ($ServerProcess.HasExited) {
                break
            }

            if (Test-ServerPort -TestPort $Port) {
                $FailureCount = 0
            }
            else {
                $FailureCount++
                Write-WatchdogLog "Health failure $FailureCount for PID $($ServerProcess.Id)."

                if ($FailureCount -ge 3) {
                    Write-WatchdogLog "Server unhealthy. Restarting PID $($ServerProcess.Id)."

                    Stop-Process `
                        -Id $ServerProcess.Id `
                        -Force `
                        -ErrorAction SilentlyContinue

                    break
                }
            }
        }

        try {
            $ServerProcess.Refresh()
            Write-WatchdogLog "Server exited. Exit code: $($ServerProcess.ExitCode)"
        }
        catch {
            Write-WatchdogLog "Server process ended."
        }
    }
    catch {
        Write-WatchdogLog "Watchdog error: $($_.Exception.Message)"
    }

    Write-WatchdogLog "Restarting server after 5 seconds."
    Start-Sleep -Seconds 5
}
