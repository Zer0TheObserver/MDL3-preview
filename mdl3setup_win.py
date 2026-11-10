"""MDL3Setup Windows layer (dev.47): known folders, registry, processes, certificate store, Authenticode check,
elevation. ctypes only: no PowerShell, no certutil, no batch files."""
import ctypes
import ctypes.wintypes as W
import hashlib
import os
import subprocess
import sys
import winreg

k32 = ctypes.WinDLL('kernel32', use_last_error=True)
shell32 = ctypes.WinDLL('shell32', use_last_error=True)
advapi32 = ctypes.WinDLL('advapi32', use_last_error=True)
crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
wintrust = ctypes.WinDLL('wintrust', use_last_error=True)
ole32 = ctypes.WinDLL('ole32')
k32.CloseHandle.argtypes = [W.HANDLE]
k32.GetExitCodeProcess.argtypes = [W.HANDLE, ctypes.POINTER(W.DWORD)]
ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]


class GUID(ctypes.Structure):
    _fields_ = [('d1', W.DWORD), ('d2', W.WORD), ('d3', W.WORD), ('d4', ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, text):
        import uuid
        u = uuid.UUID(text)
        g = cls(); g.d1, g.d2, g.d3 = u.fields[0], u.fields[1], u.fields[2]
        g.d4[:] = list(u.bytes[8:]); return g


# ---------------------------------------------------------------------------------------------- known folders
FOLDERID_LocalAppData = '{F1B32785-6FBA-4FCF-9D55-7B8E7F157091}'
FOLDERID_ProgramData = '{62AB5D82-FDC1-4DC3-A9DD-070D1D495D97}'


def known_folder(fid):
    shell32.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), W.DWORD, W.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
    p = ctypes.c_wchar_p()
    if shell32.SHGetKnownFolderPath(ctypes.byref(GUID.parse(fid)), 0, None, ctypes.byref(p)) != 0: return None
    try: return p.value
    finally: ole32.CoTaskMemFree(ctypes.cast(p, ctypes.c_void_p))


# --------------------------------------------------------------------------------------------------- processes
class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [('dwSize', W.DWORD), ('cntUsage', W.DWORD), ('th32ProcessID', W.DWORD), ('th32DefaultHeapID', ctypes.c_void_p),
                ('th32ModuleID', W.DWORD), ('cntThreads', W.DWORD), ('th32ParentProcessID', W.DWORD), ('pcPriClassBase', W.LONG),
                ('dwFlags', W.DWORD), ('szExeFile', W.WCHAR * 260)]


k32.Process32FirstW.argtypes = k32.Process32NextW.argtypes = [W.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]


def running(names):
    names = {n.lower() for n in names}
    k32.CreateToolhelp32Snapshot.restype = W.HANDLE
    snap = k32.CreateToolhelp32Snapshot(2, 0)
    if not snap or snap == W.HANDLE(-1).value: return False
    try:
        e = PROCESSENTRY32W(); e.dwSize = ctypes.sizeof(e)
        ok = k32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            if e.szExeFile.lower() in names: return True
            ok = k32.Process32NextW(snap, ctypes.byref(e))
    finally:
        k32.CloseHandle(snap)
    return False


# ---------------------------------------------------------------------------------------------------- registry
def reg_value(root, key, name, view=0):
    try:
        with winreg.OpenKey(root, key, 0, winreg.KEY_READ | view) as k: return str(winreg.QueryValueEx(k, name)[0])
    except OSError:
        return None


def steam_roots():
    out = []
    for root, key, name in ((winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamPath'),
                            (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath'),
                            (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Valve\Steam', 'InstallPath')):
        v = reg_value(root, key, name)
        if v: out.append(os.path.normpath(v.replace('/', '\\')))
    for base in (os.environ.get('ProgramFiles(x86)'), os.environ.get('ProgramFiles')):
        if base and os.path.isdir(os.path.join(base, 'Steam')): out.append(os.path.join(base, 'Steam'))
    return out


def uninstall_locations():
    out = []
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        v = reg_value(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 553850', 'InstallLocation', view)
        if v: out.append(v)
    return out


def ansi_code_page():
    return k32.GetACP()


def ui_chinese():
    return (k32.GetUserDefaultUILanguage() & 0x3ff) == 0x04


# -------------------------------------------------------------------------------------------------- elevation
def elevation_type():
    """1 = default (no split token: UAC off or built-in Administrator), 2 = full (elevated), 3 = limited."""
    token = W.HANDLE()
    advapi32.OpenProcessToken.argtypes = [W.HANDLE, W.DWORD, ctypes.POINTER(W.HANDLE)]
    k32.GetCurrentProcess.restype = W.HANDLE
    if not advapi32.OpenProcessToken(k32.GetCurrentProcess(), 0x0008, ctypes.byref(token)): return 0
    try:
        value, size = W.DWORD(), W.DWORD()
        if not advapi32.GetTokenInformation(token, 18, ctypes.byref(value), 4, ctypes.byref(size)): return 0
        return value.value
    finally:
        k32.CloseHandle(token)


class SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [('cbSize', W.DWORD), ('fMask', W.ULONG), ('hwnd', W.HWND), ('lpVerb', W.LPCWSTR), ('lpFile', W.LPCWSTR),
                ('lpParameters', W.LPCWSTR), ('lpDirectory', W.LPCWSTR), ('nShow', ctypes.c_int), ('hInstApp', W.HINSTANCE),
                ('lpIDList', ctypes.c_void_p), ('lpClass', W.LPCWSTR), ('hkeyClass', W.HKEY), ('dwHotKey', W.DWORD),
                ('hIconOrMonitor', W.HANDLE), ('hProcess', W.HANDLE)]


def shell_run(file, params='', verb='open', wait=False, show=1, directory=None):
    """ShellExecuteExW. Returns (started, exit_code or None). verb='runas' shows the UAC prompt; a refusal -> False."""
    info = SHELLEXECUTEINFOW(); info.cbSize = ctypes.sizeof(info)
    info.fMask = 0x00000040 if wait else 0   # SEE_MASK_NOCLOSEPROCESS
    info.lpVerb, info.lpFile, info.lpParameters, info.nShow, info.lpDirectory = verb, file, params, show, directory
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]
    if not shell32.ShellExecuteExW(ctypes.byref(info)): return False, None
    if not wait or not info.hProcess: return True, None
    k32.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
    k32.WaitForSingleObject(info.hProcess, 0xFFFFFFFF)
    code = W.DWORD(); k32.GetExitCodeProcess(info.hProcess, ctypes.byref(code)); k32.CloseHandle(info.hProcess)
    return True, code.value


def self_command():
    """(exe, leading args) to start this program again (PyInstaller exe or python + script)."""
    if getattr(sys, 'frozen', False): return sys.executable, []
    return sys.executable, [os.path.abspath(sys.argv[0])]


def run_elevated(args):
    exe, lead = self_command()
    params = subprocess.list2cmdline(lead + list(args))
    return shell_run(exe, params, verb='runas', wait=True, show=0)


# ------------------------------------------------------------------------------------------ certificate store
CERT_STORE_PROV_SYSTEM_W = 10
CERT_SYSTEM_STORE_LOCAL_MACHINE = 0x00020000
CERT_SYSTEM_STORE_CURRENT_USER = 0x00010000
CERT_STORE_READONLY_FLAG = 0x00008000
CERT_STORE_OPEN_EXISTING_FLAG = 0x00004000
X509_ASN_ENCODING, PKCS_7_ASN_ENCODING = 1, 0x10000
CERT_FIND_SHA1_HASH = 0x10000
CERT_STORE_ADD_REPLACE_EXISTING = 3


class CRYPT_HASH_BLOB(ctypes.Structure):
    _fields_ = [('cbData', W.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]


crypt32.CertOpenStore.restype = W.HANDLE
crypt32.CertOpenStore.argtypes = [ctypes.c_void_p, W.DWORD, W.HANDLE, W.DWORD, ctypes.c_wchar_p]
crypt32.CertFindCertificateInStore.restype = ctypes.c_void_p
crypt32.CertFindCertificateInStore.argtypes = [W.HANDLE, W.DWORD, W.DWORD, W.DWORD, ctypes.c_void_p, ctypes.c_void_p]
crypt32.CertCreateCertificateContext.restype = ctypes.c_void_p
crypt32.CertCreateCertificateContext.argtypes = [W.DWORD, ctypes.c_char_p, W.DWORD]
crypt32.CertAddCertificateContextToStore.argtypes = [W.HANDLE, ctypes.c_void_p, W.DWORD, ctypes.c_void_p]
crypt32.CertDeleteCertificateFromStore.argtypes = [ctypes.c_void_p]
crypt32.CertFreeCertificateContext.argtypes = [ctypes.c_void_p]
crypt32.CertCloseStore.argtypes = [W.HANDLE, W.DWORD]


def _open_store(name, location, readonly):
    flags = location | CERT_STORE_OPEN_EXISTING_FLAG | (CERT_STORE_READONLY_FLAG if readonly else 0)
    h = crypt32.CertOpenStore(ctypes.c_void_p(CERT_STORE_PROV_SYSTEM_W), 0, None, flags, name)
    if not h: raise OSError(ctypes.get_last_error(), 'CertOpenStore %s failed' % name)
    return h


def _find(store, thumb_hex):
    raw = bytes.fromhex(thumb_hex)
    buf = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    blob = CRYPT_HASH_BLOB(len(raw), buf)
    return crypt32.CertFindCertificateInStore(store, X509_ASN_ENCODING | PKCS_7_ASN_ENCODING, 0, CERT_FIND_SHA1_HASH, ctypes.byref(blob), None)


def cert_present(thumb, name='CA', machine=True):
    try: store = _open_store(name, CERT_SYSTEM_STORE_LOCAL_MACHINE if machine else CERT_SYSTEM_STORE_CURRENT_USER, True)
    except OSError: return False
    try:
        ctx = _find(store, thumb)
        if ctx: crypt32.CertFreeCertificateContext(ctx); return True
        return False
    finally:
        crypt32.CertCloseStore(store, 0)


def cert_add(der, thumb):
    """Adds the DER certificate to the machine's intermediate store (needs administrator). Verifies the thumbprint."""
    if hashlib.sha1(der).hexdigest() != thumb.lower(): raise ValueError('certificate thumbprint mismatch')
    store = _open_store('CA', CERT_SYSTEM_STORE_LOCAL_MACHINE, False)
    try:
        ctx = crypt32.CertCreateCertificateContext(X509_ASN_ENCODING, der, len(der))
        if not ctx: raise OSError(ctypes.get_last_error(), 'CertCreateCertificateContext failed')
        try:
            if not crypt32.CertAddCertificateContextToStore(store, ctx, CERT_STORE_ADD_REPLACE_EXISTING, None):
                raise OSError(ctypes.get_last_error(), 'CertAddCertificateContextToStore failed')
        finally:
            crypt32.CertFreeCertificateContext(ctx)
    finally:
        crypt32.CertCloseStore(store, 0)
    return cert_present(thumb)


def cert_remove(thumb):
    store = _open_store('CA', CERT_SYSTEM_STORE_LOCAL_MACHINE, False)
    try:
        ctx = _find(store, thumb)
        if not ctx: return True
        if not crypt32.CertDeleteCertificateFromStore(ctx):   # frees ctx itself
            raise OSError(ctypes.get_last_error(), 'CertDeleteCertificateFromStore failed')
    finally:
        crypt32.CertCloseStore(store, 0)
    return not cert_present(thumb)


# --------------------------------------------------------------------------------------- Authenticode (offline)
class WINTRUST_FILE_INFO(ctypes.Structure):
    _fields_ = [('cbStruct', W.DWORD), ('pcwszFilePath', W.LPCWSTR), ('hFile', W.HANDLE), ('pgKnownSubject', ctypes.c_void_p)]


class WINTRUST_DATA(ctypes.Structure):
    _fields_ = [('cbStruct', W.DWORD), ('pPolicyCallbackData', ctypes.c_void_p), ('pSIPClientData', ctypes.c_void_p),
                ('dwUIChoice', W.DWORD), ('fdwRevocationChecks', W.DWORD), ('dwUnionChoice', W.DWORD),
                ('pFile', ctypes.POINTER(WINTRUST_FILE_INFO)), ('dwStateAction', W.DWORD), ('hWVTStateData', W.HANDLE),
                ('pwszURLReference', W.LPCWSTR), ('dwProvFlags', W.DWORD), ('dwUIContext', W.DWORD),
                ('pSignatureSettings', ctypes.c_void_p)]


TRUST_CODES = {0: 'valid', 0x800B0100: 'not signed', 0x800B010A: 'chain incomplete (intermediate certificate missing)',
               0x800B0109: 'untrusted root', 0x800B0101: 'expired', 0x80096010: 'bad digest (file changed)',
               0x800B010C: 'revoked', 0x800B0111: 'explicitly distrusted', 0x80092026: 'security setting blocks it'}


def verify_signature(path):
    """WinVerifyTrust, generic Authenticode policy, no revocation, cache-only URL retrieval (no network wait).
    Returns (code, text). code 0 = the chain builds on this machine (what EAC also needs)."""
    action = GUID.parse('{00AAC56B-CD44-11d0-8CC2-00C04FC295EE}')
    fi = WINTRUST_FILE_INFO(ctypes.sizeof(WINTRUST_FILE_INFO), path, None, None)
    wd = WINTRUST_DATA(); wd.cbStruct = ctypes.sizeof(wd)
    wd.dwUIChoice = 2; wd.fdwRevocationChecks = 0; wd.dwUnionChoice = 1; wd.pFile = ctypes.pointer(fi)
    wd.dwStateAction = 1; wd.dwProvFlags = 0x00001000 | 0x00000010   # WTD_CACHE_ONLY_URL_RETRIEVAL | WTD_REVOCATION_CHECK_NONE
    wintrust.WinVerifyTrust.argtypes = [W.HWND, ctypes.POINTER(GUID), ctypes.c_void_p]
    wintrust.WinVerifyTrust.restype = ctypes.c_long
    code = wintrust.WinVerifyTrust(None, ctypes.byref(action), ctypes.byref(wd)) & 0xFFFFFFFF
    wd.dwStateAction = 2
    wintrust.WinVerifyTrust(None, ctypes.byref(action), ctypes.byref(wd))
    return code, TRUST_CODES.get(code, '0x%08X' % code)


# --------------------------------------------------------------------------------------------------- host
FILE_ATTRIBUTE_REPARSE_POINT = 0x400


class Host:
    def __init__(self, log):
        self.local_appdata = known_folder(FOLDERID_LocalAppData) or os.environ.get('LOCALAPPDATA')
        self.program_data = known_folder(FOLDERID_ProgramData) or os.environ.get('ProgramData')
        self.log = log

    def game_running(self):
        return running(['helldivers2.exe'])

    def is_reparse(self, path):
        k32.GetFileAttributesW.restype = W.DWORD
        a = k32.GetFileAttributesW(path)
        return a != 0xFFFFFFFF and bool(a & FILE_ATTRIBUTE_REPARSE_POINT)
