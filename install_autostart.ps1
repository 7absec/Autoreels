# Registers a Windows scheduled task that runs one Autoreels autopilot round every 30 minutes while you are signed in.
# Run once:  powershell -ExecutionPolicy Bypass -File install_autostart.ps1
# Remove:    Unregister-ScheduledTask -TaskName "AutoreelsAutopilot" -Confirm:$false
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command python.exe).Source }
$action = New-ScheduledTaskAction -Execute $py -Argument "`"$root\main.py`" once" -WorkingDirectory $root
$every = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 30)
$logon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$trigger = @($every, $logon)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName "AutoreelsAutopilot" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
# The Telegram command bot: starts at sign in, waits quietly until TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are in .env
$botAction = New-ScheduledTaskAction -Execute $py -Argument "`"$root\main.py`" bot" -WorkingDirectory $root
$botSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 99 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "AutoreelsBot" -Action $botAction -Trigger $logon -Settings $botSettings -Force | Out-Null
Start-ScheduledTask -TaskName "AutoreelsBot"
Write-Host "AutoreelsAutopilot registered: one round every 30 minutes. Logs: $root\logs\factory.log"
