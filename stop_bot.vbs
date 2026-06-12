Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "taskkill /f /im pythonw.exe", 0, False
WshShell.Run "taskkill /f /im python.exe", 0, False
MsgBox "Бот остановлен", 64, "Готово"