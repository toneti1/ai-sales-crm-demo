Set ws = CreateObject("Wscript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
ws.Run "powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File """ & dir & "\stop.ps1""", 0, True
MsgBox "CRM demo stopped. The public URL is no longer active." & vbCrLf & vbCrLf & _
       "You can start it again with Start.vbs anytime.", 64, "CRM demo"
