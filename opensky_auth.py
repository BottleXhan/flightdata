"""OpenSky 로그인 (브라우저 없이): 사용자명·비밀번호로 OpenSky 인증 서버에서 토큰을 받아 Trino 에 쓴다.

OpenSky 쪽 파이썬 도구 pyopensky(open-aviation/pyopensky, trino.py)와 같은 방식이다:
  POST https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token
  client_id=trino-client, grant_type=password
토큰은 몇 분 만에 만료되므로, 쿼리를 보낼 때마다 남은 시간을 보고 필요하면 새로 받는다.

비밀번호 기억은 Windows 자격 증명 관리자(CredWrite/CredRead, 암호화 저장)를 쓴다. 파일·저장소에는 넣지 않는다.
"""
import json
import sys
import threading
import time

TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
CLIENT_ID = "trino-client"


class LoginError(Exception):
    """사용자명·비밀번호가 틀렸거나(또는 비밀번호 로그인이 안 되는 계정) 인증 서버 오류."""


class PasswordToken:
    """비밀번호로 받은 접근 토큰. token() 은 만료 1분 전이면 새로 받는다 (refresh_token 우선, 안 되면 비밀번호로)."""

    def __init__(self, user, password):
        self.user, self.password = user.lower(), password
        self._access = self._refresh = None
        self._exp = 0
        self._lock = threading.Lock()

    def _post(self, data):
        import requests
        try:
            r = requests.post(TOKEN_URL, data={"client_id": CLIENT_ID, **data}, timeout=30)
        except requests.RequestException as e:
            raise LoginError(f"OpenSky 인증 서버에 연결하지 못했습니다: {e}") from e
        if r.status_code in (400, 401):
            try:
                err = r.json().get("error_description") or r.json().get("error") or ""
            except ValueError:
                err = r.text[:200]
            raise LoginError(f"OpenSky 로그인 실패 ({err or r.status_code}). 사용자명·비밀번호를 확인하세요.")
        r.raise_for_status()
        p = r.json()
        self._access = p["access_token"]
        self._refresh = p.get("refresh_token")
        self._exp = time.time() + int(p.get("expires_in", 300))
        return self._access

    def token(self):
        with self._lock:
            if self._access and time.time() < self._exp - 60:
                return self._access
            if self._refresh:
                try:
                    return self._post({"grant_type": "refresh_token", "refresh_token": self._refresh})
                except Exception:  # noqa: BLE001 — refresh 가 만료됐으면 비밀번호로 다시
                    self._refresh = None
            return self._post({"grant_type": "password", "username": self.user, "password": self.password})


def trino_auth(tok):
    """trino.dbapi.connect(auth=...) 에 넣을 인증 객체. 요청마다 tok.token() 으로 최신 토큰을 붙인다."""
    from requests.auth import AuthBase
    from trino.auth import Authentication

    class _Bearer(AuthBase):
        def __call__(self, r):
            r.headers["Authorization"] = "Bearer " + tok.token()
            return r

    class _PasswordAuthentication(Authentication):
        def set_http_session(self, http_session):
            http_session.auth = _Bearer()
            return http_session

    return _PasswordAuthentication()


# ---------- 비밀번호 기억 (Windows 자격 증명 관리자) ----------
def _target(user):
    return f"FlightData/OpenSky:{user.lower()}"


if sys.platform.startswith("win"):
    import ctypes
    from ctypes import wintypes

    class _CREDENTIAL(ctypes.Structure):
        _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                    ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME),
                    ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_char)),
                    ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                    ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]

    _adv = ctypes.WinDLL("advapi32", use_last_error=True)
    _CRED_TYPE_GENERIC, _CRED_PERSIST_LOCAL_MACHINE = 1, 2

    def save_password(user, password):
        blob = password.encode("utf-16-le")
        c = _CREDENTIAL()
        c.Type, c.Persist = _CRED_TYPE_GENERIC, _CRED_PERSIST_LOCAL_MACHINE
        c.TargetName, c.UserName = _target(user), user.lower()
        c.CredentialBlobSize = len(blob)
        c.CredentialBlob = ctypes.cast(ctypes.create_string_buffer(blob, len(blob)), ctypes.POINTER(ctypes.c_char))
        return bool(_adv.CredWriteW(ctypes.byref(c), 0))

    def load_password(user):
        p = ctypes.POINTER(_CREDENTIAL)()
        if not _adv.CredReadW(_target(user), _CRED_TYPE_GENERIC, 0, ctypes.byref(p)):
            return None
        try:
            c = p.contents
            return ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize).decode("utf-16-le")
        finally:
            _adv.CredFree(p)

    def forget_password(user):
        return bool(_adv.CredDeleteW(_target(user), _CRED_TYPE_GENERIC, 0))

    CAN_REMEMBER = True
else:                                                        # Windows 가 아니면 keyring 이 있을 때만
    try:
        import keyring

        def save_password(user, password):
            keyring.set_password("FlightData/OpenSky", user.lower(), password)
            return True

        def load_password(user):
            return keyring.get_password("FlightData/OpenSky", user.lower())

        def forget_password(user):
            try:
                keyring.delete_password("FlightData/OpenSky", user.lower())
                return True
            except Exception:  # noqa: BLE001
                return False

        CAN_REMEMBER = True
    except ImportError:
        def save_password(user, password):
            return False

        def load_password(user):
            return None

        def forget_password(user):
            return False

        CAN_REMEMBER = False


if __name__ == "__main__":                                   # 직접 확인용: python opensky_auth.py <사용자명>
    import getpass
    u = sys.argv[1] if len(sys.argv) > 1 else input("OpenSky 사용자명: ")
    t = PasswordToken(u, getpass.getpass("비밀번호: "))
    tok = t.token()
    payload = json.loads(__import__("base64").urlsafe_b64decode(tok.split(".")[1] + "==").decode())
    print("로그인 성공:", payload.get("preferred_username"), "· 만료까지", int(t._exp - time.time()), "초")
