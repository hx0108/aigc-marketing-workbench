"""OS resource limits for Windows parser children (no global machine changes)."""
import sys

class ProcessLimits:
    def __init__(self,process,memory_bytes=512*1024*1024,cpu_seconds=20,active_processes=1):
        self.handle=None
        if sys.platform!='win32':return
        import ctypes
        from ctypes import wintypes
        class Basic(ctypes.Structure):
            _fields_=[('PerProcessUserTimeLimit',ctypes.c_longlong),('PerJobUserTimeLimit',ctypes.c_longlong),('LimitFlags',wintypes.DWORD),('MinimumWorkingSetSize',ctypes.c_size_t),('MaximumWorkingSetSize',ctypes.c_size_t),('ActiveProcessLimit',wintypes.DWORD),('Affinity',ctypes.c_size_t),('PriorityClass',wintypes.DWORD),('SchedulingClass',wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_=[(name,ctypes.c_ulonglong) for name in ('ReadOperationCount','WriteOperationCount','OtherOperationCount','ReadTransferCount','WriteTransferCount','OtherTransferCount')]
        class Extended(ctypes.Structure):
            _fields_=[('BasicLimitInformation',Basic),('IoInfo',IO),('ProcessMemoryLimit',ctypes.c_size_t),('JobMemoryLimit',ctypes.c_size_t),('PeakProcessMemoryUsed',ctypes.c_size_t),('PeakJobMemoryUsed',ctypes.c_size_t)]
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR];kernel.CreateJobObjectW.restype=wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD];kernel.SetInformationJobObject.restype=wintypes.BOOL
        kernel.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE];kernel.AssignProcessToJobObject.restype=wintypes.BOOL
        kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle.restype=wintypes.BOOL
        handle=kernel.CreateJobObjectW(None,None)
        if not handle:raise OSError('PARSER_LIMIT_CREATION_FAILED')
        limits=Extended();limits.BasicLimitInformation.LimitFlags=0x100|0x200|0x2|0x4|0x8|0x2000
        limits.BasicLimitInformation.PerProcessUserTimeLimit=cpu_seconds*10_000_000
        limits.BasicLimitInformation.PerJobUserTimeLimit=cpu_seconds*10_000_000
        limits.BasicLimitInformation.ActiveProcessLimit=active_processes
        limits.ProcessMemoryLimit=memory_bytes
        limits.JobMemoryLimit=memory_bytes
        if not kernel.SetInformationJobObject(handle,9,ctypes.byref(limits),ctypes.sizeof(limits)) or not kernel.AssignProcessToJobObject(handle,int(process._handle)):
            kernel.CloseHandle(handle)
            raise OSError('PARSER_LIMIT_ASSIGNMENT_FAILED')
        self.handle=handle;self.kernel=kernel
    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle);self.handle=None
