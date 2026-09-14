"""
한국투자증권(KIS) Open API 클라이언트

KRX 스크래핑(pykrx) 대체용. KRX 가 2026-07 부터 자동화 조회를 차단해서
(이용약관 제10조 제2호) 공식 API 경로로 옮긴다.

필요 환경변수:
    KIS_APP_KEY       KIS Developers 에서 발급한 앱키
    KIS_APP_SECRET    앱시크릿
    KIS_ENV           "real"(기본) 또는 "paper"(모의투자)

선택 환경변수:
    KIS_TOKEN_CACHE   토큰 캐시 경로 (기본: 리포 루트 /.kis_token.json)
    KIS_RATE_LIMIT    초당 요청 수 (기본 6. 명목 한도는 개인 실전 초당 10~20건
                      이지만 8 에서도 EGW00201(유량 초과)이 관측돼 여유를 둔다.
                      재시도로 복구는 되나 그만큼 느려지므로 안 걸리는 게 낫다)

토큰은 발급 후 24 시간 유효하고 재발급은 1 분에 1 회로 제한되므로 반드시 파일에
캐시해서 재사용한다. GitHub Actions 는 한 job 안에서 워크스페이스가 유지되므로
스텝들이 토큰 하나를 공유한다.

사용:
    from kis_api import KisClient
    kis = KisClient()
    body = kis.get("/uapi/domestic-stock/v1/quotations/inquire-price",
                   tr_id="FHKST01010100",
                   params={"FID_COND_MRKT_DIV_CODE": "J",
                           "FID_INPUT_ISCD": "005930"})
    print(body["output"]["per"])
"""

import json
import os
import random
import threading
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

REAL_HOST = "https://openapi.koreainvestment.com:9443"
PAPER_HOST = "https://openapivts.koreainvestment.com:29443"

TOKEN_PATH = "/oauth2/tokenP"

# 토큰을 만료 몇 초 전까지 유효한 것으로 볼지
TOKEN_BUFFER = 1800

# 초당 거래건수 초과. 잠깐 쉬면 풀린다.
RATE_LIMIT_CODES = {"EGW00201"}

# 토큰이 무효하거나 만료됐을 때 내려오는 코드
TOKEN_INVALID_CODES = {"EGW00121", "EGW00123"}

DEFAULT_CACHE = Path(__file__).resolve().parent.parent / ".kis_token.json"


class KisError(RuntimeError):
    """KIS API 가 rt_cd != 0 으로 거부."""

    def __init__(self, msg, msg_cd="", tr_id="", path=""):
        super().__init__(msg)
        self.msg_cd = msg_cd
        self.tr_id = tr_id
        self.path = path


class _RateLimiter:
    """초당 N 건으로 요청 간격을 벌린다."""

    def __init__(self, per_second):
        self._interval = 1.0 / per_second if per_second > 0 else 0.0
        self._lock = threading.Lock()
        self._next_at = 0.0

    def wait(self):
        if self._interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            if now < self._next_at:
                time.sleep(self._next_at - now)
                now = time.monotonic()
            self._next_at = now + self._interval


class KisClient:
    def __init__(self, app_key=None, app_secret=None, env=None, cache_path=None):
        self.app_key = app_key or os.getenv("KIS_APP_KEY")
        self.app_secret = app_secret or os.getenv("KIS_APP_SECRET")
        if not (self.app_key and self.app_secret):
            raise SystemExit(
                "KIS_APP_KEY / KIS_APP_SECRET 환경변수가 설정되지 않았습니다.\n"
                "   https://apiportal.koreainvestment.com 에서 앱키를 발급받아 "
                ".env 또는 GitHub Secrets 에 넣어주세요."
            )

        self.env = (env or os.getenv("KIS_ENV") or "real").lower()
        self.host = PAPER_HOST if self.env == "paper" else REAL_HOST
        self.cache_path = Path(
            cache_path or os.getenv("KIS_TOKEN_CACHE") or DEFAULT_CACHE
        )

        rate = float(os.getenv("KIS_RATE_LIMIT", "6"))
        self._limiter = _RateLimiter(rate)
        self._session = requests.Session()
        self._token = None
        self._token_expires_at = 0.0

    # --- 토큰 ---------------------------------------------------------
    def _load_token_cache(self):
        try:
            raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if raw.get("app_key") != self.app_key or raw.get("env") != self.env:
            return False
        if time.time() >= raw.get("expires_at", 0) - TOKEN_BUFFER:
            return False
        self._token = raw["access_token"]
        self._token_expires_at = raw["expires_at"]
        return True

    def _save_token_cache(self):
        try:
            self.cache_path.write_text(
                json.dumps(
                    {
                        "app_key": self.app_key,
                        "env": self.env,
                        "access_token": self._token,
                        "expires_at": self._token_expires_at,
                    }
                ),
                encoding="utf-8",
            )
        except OSError as e:
            print(f"  KIS 토큰 캐시 저장 실패(무시): {e}")

    def _issue_token(self):
        resp = self._session.post(
            self.host + TOKEN_PATH,
            json={
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "appsecret": self.app_secret,
            },
            headers={"content-type": "application/json; charset=utf-8"},
            timeout=20,
        )
        try:
            data = resp.json()
        except ValueError:
            raise KisError(
                f"토큰 발급 응답이 JSON 이 아님 (status={resp.status_code}): "
                f"{resp.text[:200]!r}"
            )

        token = data.get("access_token")
        if not token:
            raise KisError(
                f"토큰 발급 실패: {data.get('error_description') or data}",
                msg_cd=data.get("error_code", ""),
            )

        self._token = token
        # expires_in 은 초 단위(보통 86400)
        self._token_expires_at = time.time() + int(data.get("expires_in", 86400))
        self._save_token_cache()
        print(f"KIS 토큰 발급 완료 (환경: {self.env})")

    @property
    def token(self):
        if self._token and time.time() < self._token_expires_at - TOKEN_BUFFER:
            return self._token
        if self._load_token_cache():
            return self._token
        self._issue_token()
        return self._token

    # --- 요청 ---------------------------------------------------------
    def get(self, path, tr_id, params, tr_cont="", max_attempts=5):
        """시세 조회 GET. 성공하면 응답 body(dict) 를 그대로 돌려준다.

        연속조회용 tr_cont 응답 헤더는 body["_tr_cont"] 에 실어 준다.
        """
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
            "tr_cont": tr_cont,
        }

        for attempt in range(1, max_attempts + 1):
            self._limiter.wait()
            try:
                resp = self._session.get(
                    self.host + path, headers=headers, params=params, timeout=20
                )
            except requests.RequestException as e:
                if attempt == max_attempts:
                    raise
                self._backoff(attempt, f"네트워크 오류: {e!r}")
                continue

            try:
                body = resp.json()
            except ValueError:
                if attempt == max_attempts:
                    raise KisError(
                        f"응답이 JSON 이 아님 (status={resp.status_code}): "
                        f"{resp.text[:200]!r}",
                        tr_id=tr_id,
                        path=path,
                    )
                self._backoff(attempt, f"비정상 응답 (status={resp.status_code})")
                continue

            if body.get("rt_cd") == "0":
                body["_tr_cont"] = resp.headers.get("tr_cont", "")
                return body

            msg_cd = body.get("msg_cd", "")
            msg = (body.get("msg1") or "").strip()

            # 초당 유량 초과 -> 잠깐 쉬고 재시도
            if msg_cd in RATE_LIMIT_CODES and attempt < max_attempts:
                self._backoff(attempt, f"유량 초과({msg_cd})", base=0.6)
                continue

            # 토큰 무효/만료 -> 재발급 후 재시도
            if msg_cd in TOKEN_INVALID_CODES and attempt < max_attempts:
                print(f"  KIS 토큰 무효({msg_cd}) — 재발급 후 재시도")
                self._token = None
                self._token_expires_at = 0.0
                try:
                    self.cache_path.unlink()
                except OSError:
                    pass
                headers["authorization"] = f"Bearer {self.token}"
                continue

            raise KisError(
                f"{msg} (msg_cd={msg_cd}, tr_id={tr_id})",
                msg_cd=msg_cd,
                tr_id=tr_id,
                path=path,
            )

        raise KisError(f"{max_attempts}회 재시도 후에도 실패", tr_id=tr_id, path=path)

    @staticmethod
    def _backoff(attempt, reason, base=1.0):
        delay = base * (2 ** (attempt - 1)) + random.uniform(0, 0.3)
        print(f"  {reason} — {delay:.1f}초 후 재시도")
        time.sleep(delay)
