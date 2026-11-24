"""Show integrity level and UIAccess for specified processes, without user data."""
import os
import sys
import win32api
import win32con
import win32security

for pid in [os.getpid(), *(int(value) for value in sys.argv[1:])]:
    process = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    token = win32security.OpenProcessToken(process, win32con.TOKEN_QUERY)
    try:
        sid = win32security.GetTokenInformation(token, 25)[0]
        ui_access = win32security.GetTokenInformation(token, 26)
        print("PID", pid, "INTEGRITY", win32security.ConvertSidToStringSid(sid), "UIACCESS", ui_access)
    finally:
        win32api.CloseHandle(token)
        win32api.CloseHandle(process)
