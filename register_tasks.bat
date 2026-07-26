@echo off
REM Run this once (as Administrator) to register the weekly start/stop tasks.

schtasks /Create /TN "XinmingBot_Start" /TR "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File \"C:\Users\Admin\Desktop\xinming-bot\start_bot.ps1\"" /SC WEEKLY /D SUN /ST 10:02 /RL LIMITED /F

schtasks /Create /TN "XinmingBot_Stop" /TR "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File \"C:\Users\Admin\Desktop\xinming-bot\stop_bot.ps1\"" /SC WEEKLY /D SUN /ST 22:05 /RL LIMITED /F

echo Done. Check "Task Scheduler Library" for XinmingBot_Start and XinmingBot_Stop.
pause
