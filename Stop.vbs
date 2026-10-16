Set ws = CreateObject("Wscript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
ws.Run "powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File """ & dir & "\stop.ps1""", 0, True
MsgBox "CRM demo parada. La URL publica ya no funciona." & vbCrLf & vbCrLf & _
       "Puedes volver a arrancarla con Start.vbs cuando quieras.", 64, "CRM demo"
