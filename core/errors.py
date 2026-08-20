"""Классификация ошибок речевого API и повторные попытки.

Один слой на все провайдеры: и OpenAI-SDK (OpenAI/Groq), и REST-вызовы
Deepgram кидают разные исключения, а пользователю нужно одно понятное
сообщение — и автоматический повтор там, где он имеет смысл.
"""

import time

import httpx
import openai

# Пауза перед повтором: 3 попытки всего (2 повтора).
# Больше смысла нет — пользователь ждёт вставки текста.
RETRY_DELAYS = (0.7, 2.0)

# Для «нет соединения» хватает двух попыток: первая часто ловит просто
# закрытый сервером keep-alive сокет, а если VPN выключен, то каждая
# попытка ещё и упирается в connect-таймаут — ждать три раза незачем.
MAX_ATTEMPTS_BY_KIND = {"network": 2}

# Сколько ждать максимум, если сервер прислал Retry-After
MAX_RETRY_AFTER = 5.0


class ApiError(RuntimeError):
    """Ошибка обращения к речевому API с готовым текстом для пользователя.

    kind:  network | timeout | auth | quota | rate_limit | server | request | unknown
    """

    def __init__(self, kind: str, title: str, message: str, *,
                 retryable: bool = False, detail: str = "",
                 retry_after: float | None = None) -> None:
        super().__init__(f"{title} — {message}")
        self.kind = kind
        self.title = title
        self.message = message
        self.retryable = retryable
        self.detail = detail
        self.retry_after = retry_after

    @property
    def user_text(self) -> str:
        return self.message

    @property
    def is_network(self) -> bool:
        return self.kind in ("network", "timeout")


def provider_name(config) -> str:
    """Человекочитаемое имя активного провайдера."""
    from core.config import PROVIDERS
    prov = PROVIDERS.get(config.provider)
    return prov["name"] if prov else (config.provider or "API")


def _vpn_hint(config) -> str:
    """Подсказка про VPN/прокси — с учётом того, включён ли прокси."""
    if config is not None and getattr(config, "proxy", "") and getattr(config, "proxy_enabled", False):
        return "Проверьте прокси в настройках, VPN и интернет-соединение."
    return ("Скорее всего выключен VPN или пропал интернет — "
            "включите VPN (или прокси в настройках).")


def status_error(status: int, body: bytes | str, name: str,
                 config=None, retry_after: float | None = None) -> ApiError:
    """Собрать ApiError по HTTP-статусу ответа."""
    if isinstance(body, bytes):
        body = body.decode("utf-8", "replace")
    detail = f"HTTP {status}: {body[:400]}"

    if status in (401, 403):
        return ApiError(
            "auth", f"{name}: ключ не принят",
            f"{name} отклонил API-ключ (HTTP {status}). "
            "Проверьте ключ в настройках.",
            detail=detail,
        )
    if status == 402:
        return ApiError(
            "quota", f"{name}: закончился баланс",
            f"На аккаунте {name} закончились средства или кредиты.",
            detail=detail,
        )
    if status == 429:
        return ApiError(
            "rate_limit", f"{name}: лимит запросов",
            f"{name} превысил лимит запросов и не ответил после повторов. "
            "Подождите немного и повторите запись.",
            retryable=True, detail=detail, retry_after=retry_after,
        )
    if status in (408, 502, 503, 504) or status >= 500:
        return ApiError(
            "server", f"{name}: сервис недоступен",
            f"{name} отвечает ошибкой {status} — похоже, проблема на стороне "
            "сервиса. Попробуйте позже или смените провайдера в настройках.",
            retryable=True, detail=detail, retry_after=retry_after,
        )
    if status == 413:
        return ApiError(
            "request", f"{name}: запись слишком большая",
            "Аудио превышает лимит провайдера — говорите короче "
            "или уменьшите битрейт в настройках.",
            detail=detail,
        )
    return ApiError(
        "request", f"{name}: запрос отклонён",
        f"{name} ответил ошибкой {status}. Подробности в логе.",
        detail=detail,
    )


def _retry_after_of(exc: Exception) -> float | None:
    """Достать Retry-After из ответа, если он есть."""
    resp = getattr(exc, "response", None)
    headers = getattr(resp, "headers", None)
    if not headers:
        return None
    raw = headers.get("retry-after")
    if not raw:
        return None
    try:
        return min(float(raw), MAX_RETRY_AFTER)
    except (TypeError, ValueError):
        return None


def classify(exc: Exception, name: str, config=None) -> ApiError:
    """Превратить любое исключение вызова API в ApiError."""
    if isinstance(exc, ApiError):
        return exc

    detail = f"{type(exc).__name__}: {exc}"

    # ── Таймауты ──
    if isinstance(exc, (httpx.TimeoutException, openai.APITimeoutError)):
        return ApiError(
            "timeout", f"{name}: нет ответа",
            f"{name} не ответил вовремя. {_vpn_hint(config)}",
            retryable=True, detail=detail,
        )

    # ── Сеть: нет маршрута, DNS, прокси, обрыв соединения ──
    if isinstance(exc, (httpx.TransportError, openai.APIConnectionError)):
        return ApiError(
            "network", f"{name}: нет соединения",
            f"Не удалось связаться с {name}. {_vpn_hint(config)}",
            retryable=True, detail=detail,
        )
    if isinstance(exc, (ConnectionError, OSError)):
        return ApiError(
            "network", f"{name}: нет соединения",
            f"Сеть недоступна ({type(exc).__name__}). {_vpn_hint(config)}",
            retryable=True, detail=detail,
        )

    # ── Ответ с HTTP-статусом от SDK ──
    status = getattr(exc, "status_code", None)
    if status is None:
        resp = getattr(exc, "response", None)
        status = getattr(resp, "status_code", None)
    if isinstance(status, int):
        err = status_error(status, str(exc), name, config, _retry_after_of(exc))
        err.detail = detail
        return err

    return ApiError(
        "unknown", f"{name}: ошибка",
        f"Не удалось распознать речь: {exc}",
        detail=detail,
    )


def call_with_retries(fn, *, name: str, config=None, on_retry=None):
    """Вызвать *fn* с повторами на сетевых/временных ошибках.

    on_retry(attempt, total, ApiError, delay) — колбэк для лога/UI.
    Все ошибки наружу летят уже как ApiError.
    """
    total = len(RETRY_DELAYS) + 1
    for attempt in range(1, total + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — классифицируем всё
            err = classify(exc, name, config)
            limit = min(total, MAX_ATTEMPTS_BY_KIND.get(err.kind, total))
            if not err.retryable or attempt >= limit:
                raise err from exc
            delay = err.retry_after or RETRY_DELAYS[attempt - 1]
            if on_retry is not None:
                on_retry(attempt, limit, err, delay)
            time.sleep(delay)
