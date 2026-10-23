"""Windows Credential Manager. No file fallback; provision only via local terminal."""
import os
import ctypes
from ctypes import wintypes


class Credential(ctypes.Structure):
    _fields_ = [('Flags',wintypes.DWORD),('Type',wintypes.DWORD),('TargetName',wintypes.LPWSTR),
                ('Comment',wintypes.LPWSTR),('LastWritten',wintypes.FILETIME),('CredentialBlobSize',wintypes.DWORD),
                ('CredentialBlob',ctypes.POINTER(ctypes.c_ubyte)),('Persist',wintypes.DWORD),
                ('AttributeCount',wintypes.DWORD),('Attributes',ctypes.c_void_p),
                ('TargetAlias',wintypes.LPWSTR),('UserName',wintypes.LPWSTR)]


class SecretStore:
    def __init__(self):
        if os.name != 'nt': raise RuntimeError('자동 로그인 자격증명은 Windows에서만 지원합니다.')
        self.api = ctypes.WinDLL('Advapi32.dll', use_last_error=True)
        self.api.CredWriteW.argtypes = [ctypes.POINTER(Credential),wintypes.DWORD]
        self.api.CredReadW.argtypes = [wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.POINTER(ctypes.POINTER(Credential))]
        self.api.CredDeleteW.argtypes = [wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD]
        self.api.CredFree.argtypes = [ctypes.c_void_p]

    def target(self, identifier):
        import re
        if not re.fullmatch('[a-f0-9]{32}', identifier): raise ValueError('계정 ID 오류')
        return 'MyLittleOffice/browser/' + identifier

    def put(self, identifier, username, password):
        if not username or not password or len(password.encode('utf-16-le')) > 2500: raise ValueError('자격증명 입력 오류')
        raw = password.encode('utf-16-le')
        buffer = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
        try:
            value = Credential(Type=1,TargetName=self.target(identifier),UserName=username,
                               CredentialBlobSize=len(raw),CredentialBlob=buffer,Persist=2)
            if not self.api.CredWriteW(ctypes.byref(value),0): raise RuntimeError('Windows 자격증명 저장 실패')
        finally: ctypes.memset(buffer,0,len(raw))

    def get(self, identifier):
        pointer = ctypes.POINTER(Credential)()
        if not self.api.CredReadW(self.target(identifier),1,0,ctypes.byref(pointer)):
            if ctypes.get_last_error() == 1168: return None
            raise RuntimeError('Windows 자격증명 읽기 실패')
        try:
            value = pointer.contents
            return value.UserName, ctypes.string_at(value.CredentialBlob,value.CredentialBlobSize).decode('utf-16-le')
        finally: self.api.CredFree(pointer)

    def exists(self, identifier):
        value = self.get(identifier)
        return value is not None

    def delete(self, identifier):
        if not self.api.CredDeleteW(self.target(identifier),1,0) and ctypes.get_last_error()!=1168:
            raise RuntimeError('Windows 자격증명 삭제 실패')


if __name__ == '__main__':
    import argparse
    import getpass
    from office.store import Store
    from office.browser_accounts import BrowserAccounts
    parser=argparse.ArgumentParser(description='PC에서만 자격증명 등록/회전/삭제. 비밀번호는 명령행 인자로 받지 않습니다.')
    parser.add_argument('operation',choices=['set','delete'])
    parser.add_argument('--root',required=True)
    parser.add_argument('--blog',required=True)
    args=parser.parse_args()
    accounts=BrowserAccounts(Store(args.root));account=accounts.register(args.blog);vault=SecretStore()
    if args.operation=='set':
        vault.put(account['id'],input('네이버 로그인 ID: '),getpass.getpass('비밀번호: '))
        accounts.opt_in(account['id'],True)
    else:
        accounts.opt_in(account['id'],False);vault.delete(account['id'])
    print('자격증명 설정 완료. 비밀값은 사무실이나 AI에 전달되지 않습니다.')
