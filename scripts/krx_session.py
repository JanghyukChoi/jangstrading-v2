"""
KRX 로그인 부트스트랩 (pykrx import 전에 먼저 import 할 것)

배경:
  pykrx 1.2.x 는 `pykrx.website.comm.webio` 를 import 하는 시점에 KRX 로그인을
  1 회 시도한다. 이때 KRX 로그인 API 가 JSON 대신 HTML 오류 페이지를 돌려주면
  requests 의 JSONDecodeError 가 그대로 밖으로 튀어 스크립트가 import 단계에서
  죽는다. 재시도도, 예외 처리도 없다.

  2026-07-20 이후 KRX 쪽 응답이 간헐적으로 HTML 로 바뀌면서, 하루 8 번 로그인하는
  daily-fetch 워크플로가 그중 한 번만 걸려도 전체가 실패하게 됐다. (7/17 이 마지막
  성공 실행)

이 모듈이 하는 일:
  1. pykrx import 동안에는 KRX_ID/KRX_PW 를 감춰서 자동 로그인을 건너뛰게 한다.
     (자격 증명이 없으면 pykrx 는 조용히 None 을 반환하고 예외를 던지지 않는다)
  2. 재시도 + 관대한 응답 파싱이 붙은 자체 로그인으로 세션을 만들어 pykrx 전역
     세션에 주입한다.
  3. 세션 만료 후 재로그인 경로(KRXSession.refresh)도 같은 재시도 로직을 타도록
     auth.login_krx 자체를 교체한다.

사용법:
    import krx_session  # noqa: F401  (import 시점에 로그인까지 끝난다)
    from pykrx import stock

환경변수:
    KRX_ID, KRX_PW            필수
    KRX_LOGIN_ATTEMPTS        로그인 재시도 횟수 (기본 5)
    KRX_LOGIN_REQUIRED=0      로그인 실패해도 예외 대신 경고만 (기본: 실패 시 종료)
"""

import contextlib
import io
import json
import os
import random
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

# KRX 는 짧은 시간에 로그인이 반복되면 JSON 대신 "에러페이지" HTML 을 돌려준다.
# 그래서 워크플로 전체에서 로그인은 1 회만 하고, 세션 쿠키를 파일에 캐시해 뒤따르는
# 스크립트들이 재사용한다. (하루 8 회 로그인 -> 1 회)
CACHE_PATH = Path(
    os.getenv("KRX_SESSION_CACHE")
    or Path(__file__).resolve().parent.parent / ".krx_session.json"
)
# 캐시된 세션을 만료 몇 초 전까지 유효한 것으로 볼지
CACHE_BUFFER = 600

MAX_ATTEMPTS = int(os.getenv("KRX_LOGIN_ATTEMPTS", "5"))
BASE_DELAY = 3.0  # 초, 시도마다 2 배씩 증가
REQUIRED = os.getenv("KRX_LOGIN_REQUIRED", "1") != "0"

_LOGIN_ID = os.getenv("KRX_ID")
_LOGIN_PW = os.getenv("KRX_PW")

# ─── pykrx import 중 자동 로그인 비활성화 ──────────────────────────────
# build_krx_session() 은 자격 증명이 없으면 로그인을 시도하지 않고 None 을 반환한다.
_hidden = {k: os.environ.pop(k) for k in ("KRX_ID", "KRX_PW") if k in os.environ}
try:
    # 자격 증명이 없다는 pykrx 의 안내 문구는 여기선 의도된 동작이라 감춘다
    with contextlib.redirect_stdout(io.StringIO()):
        from pykrx.website.comm import auth, webio  # noqa: E402
finally:
    os.environ.update(_hidden)

# 이 모듈은 pykrx 내부 구조에 의존한다. 업스트림이 바뀌면 조용히 오동작하는 대신
# 여기서 바로 알아채도록 필요한 심볼을 확인한다.
_REQUIRED_ATTRS = (
    "USER_AGENT",
    "LOGIN_PAGE",
    "LOGIN_URL",
    "warmup_krx_session",
    "login_krx",
    "build_krx_session",
    "set_auth_session",
)
_missing = [a for a in _REQUIRED_ATTRS if not hasattr(auth, a)]
if _missing:
    raise ImportError(
        "pykrx 내부 구조가 바뀌어 krx_session 의 로그인 우회가 동작하지 않습니다 "
        f"(누락: {', '.join(_missing)}). scripts/krx_session.py 를 pykrx 최신 버전에 "
        "맞춰 갱신하세요."
    )


class KrxLoginError(RuntimeError):
    """KRX 로그인 실패의 공통 상위 타입."""


class KrxLoginTransient(KrxLoginError):
    """응답이 JSON 이 아니거나 네트워크가 튄 경우 — 재시도 대상."""


class KrxLoginRejected(KrxLoginError):
    """KRX 가 오류 코드로 명확히 거부한 경우 — 재시도 금지.

    KRX 는 비밀번호 실패가 loginErrMaxCnt(5) 회 쌓이면 계정을 잠근다.
    자격 증명 문제를 재시도하면 계정이 잠기므로 즉시 중단해야 한다.
    """


def _parse_login_response(resp):
    """로그인 응답을 dict 로 파싱. JSON 이 아니면 KrxLoginError."""
    try:
        return resp.json()
    except ValueError:
        pass

    # KRX 가 JSON 앞뒤에 공백이나 HTML 을 붙여 보내는 경우 구제 시도
    body = resp.text or ""
    start, end = body.find("{"), body.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(body[start : end + 1])
        except ValueError:
            pass

    preview = " ".join(body.split())[:200]
    raise KrxLoginTransient(
        f"KRX 로그인 응답이 JSON 이 아님 (status={resp.status_code}, "
        f"content-type={resp.headers.get('Content-Type')}): {preview!r}"
    )


def _login_once(login_id, login_pw, session):
    """pykrx.website.comm.auth.login_krx 와 동일한 흐름 + 관대한 파싱."""
    auth.warmup_krx_session(session)

    payload = {
        "mbrNm": "",
        "telNo": "",
        "di": "",
        "certType": "",
        "mbrId": login_id,
        "pw": login_pw,
    }
    headers = {"User-Agent": auth.USER_AGENT, "Referer": auth.LOGIN_PAGE}

    resp = session.post(auth.LOGIN_URL, data=payload, headers=headers, timeout=20)
    data = _parse_login_response(resp)
    error_code = data.get("_error_code", "")
    error_message = data.get("_error_message", "")

    # CD010: 패스워드 변경 필요
    if error_code == "CD010":
        raise KrxLoginRejected(
            "KRX 비밀번호 변경이 필요합니다. https://www.krx.co.kr 에서 변경 후 "
            f"KRX_PW 시크릿을 갱신하세요. ({error_message})"
        )

    # CD011: 중복 로그인 → skipDup 붙여 재전송
    if error_code == "CD011":
        payload["skipDup"] = "Y"
        resp = session.post(auth.LOGIN_URL, data=payload, headers=headers, timeout=20)
        data = _parse_login_response(resp)
        error_code = data.get("_error_code", "")
        error_message = data.get("_error_message", "")

    if error_code != "CD001":
        # CD006(비밀번호 불일치) 등. 남은 시도 횟수를 같이 찍어 둔다.
        left = data.get("loginErrMaxCnt")
        used = data.get("loginErrCnt")
        counter = f" [실패 {used}/{left}]" if left is not None else ""
        raise KrxLoginRejected(
            f"KRX 로그인 거부 (code={error_code}): {error_message}{counter}"
        )

    return True


def login_krx(login_id, login_pw, session=None):
    """auth.login_krx 대체품. 실패 시 백오프를 두고 재시도한다."""
    if session is None:
        session = requests.Session()

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            _login_once(login_id, login_pw, session)
            if attempt > 1:
                print(f"  KRX 로그인 성공 ({attempt}번째 시도)")
            return True
        except KrxLoginRejected as e:
            # 재시도하면 계정이 잠긴다. 즉시 포기.
            print(f"  {e}")
            return False
        except KrxLoginTransient as e:
            reason = str(e)
        except requests.RequestException as e:
            reason = f"네트워크 오류: {e!r}"

        print(f"  KRX 로그인 실패 ({attempt}/{MAX_ATTEMPTS}): {reason}")
        if attempt == MAX_ATTEMPTS:
            return False

        delay = BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 1.5)
        print(f"  {delay:.1f}초 후 재시도...")
        time.sleep(delay)
        # 실패한 세션의 쿠키를 버리고 처음부터 다시
        session.cookies.clear()

    return False


# 세션 만료 시 KRXSession.refresh() 가 부르는 경로까지 재시도가 적용되도록 교체
auth.login_krx = login_krx


# 세션이 살아 있는지 확인할 때 쓰는 가장 가벼운 KRX 조회 (지수 목록)
_VALIDATE_URL = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
_VALIDATE_PAYLOAD = {"bld": "dbms/comm/finder/finder_equidx", "mktsel": "3"}


def _save_cache(krxs):
    """로그인 성공 직후 세션 쿠키를 파일에 저장한다."""
    try:
        CACHE_PATH.write_text(
            json.dumps(
                {
                    "login_time": krxs.login_time,
                    "expiry_time": krxs.expiry_time,
                    "cookies": krxs.cookies,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except OSError as e:
        # 캐시는 최적화일 뿐이라 실패해도 진행한다
        print(f"  ⚠️ KRX 세션 캐시 저장 실패(무시): {e}")


def _load_cache():
    """아직 유효한 캐시가 있으면 KRXSession 으로 복원한다. 없으면 None."""
    try:
        raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    if time.time() >= raw.get("expiry_time", 0) - CACHE_BUFFER:
        return None

    krxs = auth.KRXSession()
    krxs.login_time = raw["login_time"]
    krxs.expiry_time = raw["expiry_time"]
    krxs.cookies = raw["cookies"]
    krxs.is_authenticated = True
    for name, info in krxs.cookies.items():
        krxs.session.cookies.set(
            name,
            info.get("value"),
            domain=info.get("domain") or "data.krx.co.kr",
            path=info.get("path") or "/",
        )
    return krxs


def _is_alive(krxs):
    """캐시된 세션으로 실제 조회가 되는지 확인한다."""
    try:
        resp = krxs.post(_VALIDATE_URL, data=_VALIDATE_PAYLOAD, timeout=15)
        return bool(resp.json().get("block1"))
    except Exception:
        return False


def ensure_session(required=REQUIRED):
    """KRX 로그인 세션을 만들어 pykrx 전역에 주입하고 반환한다."""
    if not (_LOGIN_ID and _LOGIN_PW):
        msg = "KRX_ID / KRX_PW 환경변수가 설정되지 않았습니다."
        if required:
            raise SystemExit(f"❌ {msg}")
        print(f"⚠️ {msg} 비로그인 상태로 진행합니다.")
        return None

    cached = _load_cache()
    if cached is not None and _is_alive(cached):
        left = int(cached.expiry_time - time.time())
        print(f"KRX 세션 캐시 재사용 (남은 유효시간 {left // 60}분)")
        auth.set_auth_session(cached)
        webio.set_session(cached)
        return cached

    krxs = auth.build_krx_session(_LOGIN_ID, _LOGIN_PW)
    if krxs is None:
        msg = f"KRX 로그인이 {MAX_ATTEMPTS}회 재시도 후에도 실패했습니다."
        if required:
            raise SystemExit(f"❌ {msg}")
        print(f"⚠️ {msg} 비로그인 상태로 진행합니다.")
        return None

    _save_cache(krxs)
    auth.set_auth_session(krxs)
    webio.set_session(krxs)
    return krxs


session = ensure_session()
