"""Whisper API wrapper — transcription and translation."""

import io
from core.config import AppConfig, PROVIDERS
from core.errors import (ApiError, call_with_retries, classify,
                         provider_name, status_error)

import httpx
import openai

# NOTE: there used to be an h11 monkey-patch here that turned a stray int
# back into bytes.  It was masking a real bug: lameenc returns a bytearray,
# httpx classifies a bytearray as an *iterable* (not bytes) and switches to
# chunked transfer, where iterating yields ints — one HTTP chunk per byte.
# The patch made that work instead of crashing, at ~9x the upload time.
# The encoders now return real bytes, so the patch is gone; if a bytearray
# ever reaches httpx again it will fail loudly instead of silently crawling.

# ── Hallucination filter ─────────────────────────────────────────────────────
# Whisper often hallucinates these phrases on silence or background noise.
# Using substring matching — any text containing these is filtered out.
_HALLUCINATION_PATTERNS = [
    "продолжение следует",
    "продолжение в следующ",
    "субтитры сделал",
    "субтитры делал",
    "субтитры создал",
    "подписывайтесь на канал",
    "подписывайтесь",
    "подпишитесь",
    "спасибо за просмотр",
    "thanks for watching",
    "thank you for watching",
    "subscribe",
    "subtitles by",
    "subtitles made",
    "редактор субтитров",
    "www.teletext",
    "amara.org",
    "translated by",
]

# Cached client to avoid recreating connection pool every call
_cached_client: openai.OpenAI | None = None
_cached_key: str = ""

# Same for Deepgram, which talks plain REST instead of the OpenAI SDK.
_dg_client: httpx.Client | None = None
_dg_key: str = ""

# GigaChat client and token cache
_gc_client: httpx.Client | None = None
_gc_key: str = ""
_gc_token: str = ""
_gc_token_expires_at: float = 0.0
_gc_token_auth_key: str = ""


def _get_gigachat_client(config: AppConfig) -> httpx.Client:
    """Return a pooled httpx client with verify=False for Sber certificates."""
    global _gc_client, _gc_key

    key = f"{config.proxy}|{config.proxy_enabled}"
    if _gc_client is not None and _gc_key == key:
        return _gc_client

    if _gc_client is not None:
        _gc_client.close()

    kwargs: dict = {
        "timeout": httpx.Timeout(30.0, connect=5.0),
        "limits": httpx.Limits(max_keepalive_connections=4, keepalive_expiry=60.0),
        "verify": False,  # Sber uses Russian Root CA (Минцифры)
    }
    if config.proxy and config.proxy_enabled:
        kwargs["proxy"] = config.proxy

    _gc_client = httpx.Client(**kwargs)
    _gc_key = key
    return _gc_client


def _get_gigachat_token(client: httpx.Client, config: AppConfig) -> str:
    """Acquire or return cached OAuth 2.0 access token for GigaChat API."""
    import time as _t
    import uuid as _uuid
    global _gc_token, _gc_token_expires_at, _gc_token_auth_key

    auth_key = config.active_api_key.strip()
    if not auth_key:
        raise ApiError(
            "auth", "GigaChat: нет ключа",
            "Укажите API-ключ (Authorization Data) для GigaChat в настройках.",
        )

    # Check cache (renew 60 seconds before expiration)
    now = _t.time()
    if _gc_token and _gc_token_auth_key == auth_key and now < _gc_token_expires_at - 60:
        return _gc_token

    oauth_url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    headers = {
        "Authorization": f"Basic {auth_key}",
        "RqUID": str(_uuid.uuid4()),
        "Content-Type": "application/x-www-form-urlencoded",
    }

    last_resp = None
    # Try personal scope first, then corp / b2b
    for scope in ["GIGACHAT_API_PERS", "GIGACHAT_API_CORP", "GIGACHAT_API_B2B"]:
        try:
            resp = client.post(oauth_url, headers=headers, data={"scope": scope})
            last_resp = resp
            if resp.status_code == 200:
                data = resp.json()
                _gc_token = data["access_token"]
                _gc_token_expires_at = data.get("expires_at", 0) / 1000.0
                _gc_token_auth_key = auth_key
                return _gc_token
            elif resp.status_code == 400 and "scope" in resp.text:
                continue
            else:
                break
        except Exception as exc:
            raise classify(exc, "GigaChat", config) from exc

    if last_resp is not None:
        raise status_error(last_resp.status_code, last_resp.content, "GigaChat", config)
    raise ApiError("auth", "GigaChat: ошибка авторизации", "Не удалось получить токен доступа GigaChat.")


def _get_deepgram_client(config: AppConfig) -> httpx.Client:
    """Return a pooled httpx client so we don't pay TCP+TLS on every call.

    httpx closes idle connections after 5s by default; Deepgram tolerates
    a longer idle, so raise it and keep the socket around between phrases.
    """
    global _dg_client, _dg_key

    key = f"{config.proxy}|{config.proxy_enabled}"
    if _dg_client is not None and _dg_key == key:
        return _dg_client

    if _dg_client is not None:
        _dg_client.close()

    kwargs: dict = {
        "timeout": httpx.Timeout(30.0, connect=5.0),
        "limits": httpx.Limits(max_keepalive_connections=4,
                               keepalive_expiry=60.0),
    }
    if config.proxy and config.proxy_enabled:
        kwargs["proxy"] = config.proxy

    _dg_client = httpx.Client(**kwargs)
    _dg_key = key
    return _dg_client


def _get_client(config: AppConfig) -> openai.OpenAI:
    """Return a cached OpenAI client, rebuilding only if config changed."""
    global _cached_client, _cached_key

    key = f"{config.provider}|{config.active_api_key}|{config.proxy}|{config.proxy_enabled}"
    if _cached_client is not None and _cached_key == key:
        return _cached_client

    prov = PROVIDERS.get(config.provider, PROVIDERS["groq"])
    # Explicit timeout — the SDK default is 600s, a hung request would
    # silently stall for 10 minutes.
    timeout = httpx.Timeout(30.0, connect=5.0)
    # max_retries=0 — повторы делает core.errors.call_with_retries,
    # чтобы у всех провайдеров была одна логика и одни уведомления.
    kwargs: dict = {
        "api_key": config.active_api_key,
        "timeout": timeout,
        "max_retries": 0,
    }

    if prov["base_url"]:
        kwargs["base_url"] = prov["base_url"]

    if config.proxy and config.proxy_enabled:
        kwargs["http_client"] = httpx.Client(proxy=config.proxy, timeout=timeout)

    _cached_client = openai.OpenAI(**kwargs)
    _cached_key = key
    return _cached_client


def _is_hallucination(text: str) -> bool:
    """Check if the text is a known Whisper hallucination."""
    lower = text.lower().strip()
    return any(p in lower for p in _HALLUCINATION_PATTERNS)


def _transcribe_deepgram(audio_bytes: bytes, config: AppConfig,
                         content_type: str = "audio/mpeg",
                         timeout: float | None = None,
                         paragraphs: bool = False) -> str:
    """Call Deepgram REST API for transcription."""
    import json as _json
    from urllib.parse import urlencode

    params = {
        "model": config.model or "nova-3",
        "smart_format": "true",
        "punctuate": "true",
        "numerals": "true",
    }
    if config.language:
        params["language"] = config.language
    if config.mode == "translate":
        params["language"] = "en"
    if paragraphs:
        # Длинная запись: Deepgram сам разобьёт текст на абзацы.
        params["paragraphs"] = "true"

    url = f"https://api.deepgram.com/v1/listen?{urlencode(params)}"
    headers = {
        "Authorization": f"Token {config.active_api_key}",
        "Content-Type": content_type,
    }

    print(f"[Deepgram] Отправка {len(audio_bytes)} байт, model={params['model']}")

    import time as _t
    t0 = _t.perf_counter()

    client = _get_deepgram_client(config)
    # bytes() is a no-op for bytes and prevents the chunked-per-byte
    # fallback if a bytearray ever slips through from an encoder.
    payload = bytes(audio_bytes)

    # Сетевые сбои (в том числе устаревшее соединение из пула) и 5xx/429
    # повторяет call_with_retries снаружи.
    extra = {"timeout": httpx.Timeout(timeout, connect=5.0)} if timeout else {}
    resp = client.post(url, headers=headers, content=payload, **extra)
    status, body = resp.status_code, resp.content

    dt = _t.perf_counter() - t0
    print(f"[Deepgram] Ответ за {dt:.1f}с, status={status}")

    if status != 200:
        retry_after = resp.headers.get("retry-after")
        try:
            retry_after = float(retry_after) if retry_after else None
        except ValueError:
            retry_after = None
        raise status_error(status, body, "Deepgram", config, retry_after)

    data = _json.loads(body)
    try:
        alt = data["results"]["channels"][0]["alternatives"][0]
    except (KeyError, IndexError):
        return ""
    text = (alt.get("paragraphs") or {}).get("transcript") or alt.get("transcript", "")
    return text.strip()


def _transcribe_gigachat(audio_bytes: bytes, config: AppConfig,
                         filename: str = "audio.mp3",
                         content_type: str = "audio/mpeg",
                         timeout: float | None = None) -> str:
    """Upload audio to GigaChat files API and transcribe via chat completions."""
    extra = {"timeout": httpx.Timeout(timeout, connect=5.0)} if timeout else {}
    client = _get_gigachat_client(config)
    token = _get_gigachat_token(client, config)

    # 1. Upload audio file to GigaChat
    files_url = "https://gigachat.devices.sberbank.ru/api/v1/files"
    auth_header = {"Authorization": f"Bearer {token}"}
    files = {"file": (filename, bytes(audio_bytes), content_type)}
    data = {"purpose": "general"}

    print(f"[GigaChat] Отправка {len(audio_bytes)} байт...")
    resp = client.post(files_url, headers=auth_header, files=files, data=data,
                       **extra)
    if resp.status_code != 200:
        raise status_error(resp.status_code, resp.content, "GigaChat", config)

    file_info = resp.json()
    file_id = file_info.get("id")
    if not file_id:
        raise ApiError("server", "GigaChat: ошибка загрузки", "Сервер не вернул идентификатор файла.")

    try:
        # 2. Chat completions with audio attachment
        chat_url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        if config.mode == "translate":
            sys_prompt = (
                "Ты голосовой переводчик. Твоя задача — точно перевести речь из прикреплённого "
                "аудиосообщения на английский язык (English). Не добавляй никаких пояснений, "
                "комментариев или кавычек. Выводи ТОЛЬКО перевод."
            )
            user_content = config.prompt or "Переведи это аудио на английский язык."
        else:
            sys_prompt = (
                "Ты голосовой ассистент транскрибации речи в текст. Твоя задача — точно перевести "
                "прикреплённое аудиосообщение в текст. Не добавляй от себя никаких комментариев, "
                "пояснений, вступлений или кавычек. Выводи ТОЛЬКО распознанный текст из аудио. "
                "Если звука нет или только тишина/шум — верни пустую строку."
            )
            user_content = config.prompt or "Транскрибируй прикреплённый аудиофайл."

        body = {
            "model": config.model or "GigaChat-2-Pro",
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_content, "attachments": [file_id]},
            ],
            "temperature": 0.1,
        }

        chat_resp = client.post(
            chat_url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body,
            **extra,
        )
        if chat_resp.status_code != 200:
            raise status_error(chat_resp.status_code, chat_resp.content, "GigaChat", config)

        chat_data = chat_resp.json()
        try:
            text = chat_data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError):
            return ""

        # Filter out trivial punctuation or silence artifacts
        if text.lower() in ("", ".", "...", "-", "–", "—", "пи.", "пи"):
            return ""

        # Remove surrounding quotes if wrapped
        if (text.startswith('"') and text.endswith('"')) or (text.startswith('«') and text.endswith('»')):
            text = text[1:-1].strip()

        return text
    finally:
        # 3. Clean up temporary uploaded file
        try:
            client.post(f"https://gigachat.devices.sberbank.ru/api/v1/files/{file_id}/delete", headers=auth_header)
        except Exception:
            pass


def _transcribe_openai_like(audio_bytes: bytes, config: AppConfig,
                            name: str) -> str:
    """OpenAI / Groq (OpenAI-compatible) — одна попытка запроса."""
    client = _get_client(config)
    # Новый BytesIO на каждую попытку: переиспользовать вычитанный
    # файловый объект между повторами нельзя.
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = "recording.mp3"

    common = {"model": config.model, "file": audio_file}
    # "multi" — режим Deepgram; Whisper такого кода не знает,
    # поэтому язык не передаём и он определяется автоматически.
    if config.language and config.language != "multi":
        common["language"] = config.language
    if config.prompt:
        common["prompt"] = config.prompt

    if config.mode == "translate":
        try:
            response = client.audio.translations.create(**common)
        except Exception as exc:
            # Провайдер может не поддерживать /translations — тогда падаем
            # на транскрипцию с англоязычным промптом.  Но если проблема
            # сетевая, откат бессмысленен: отдаём ошибку наверх, там повтор.
            err = classify(exc, name, config)
            if err.retryable:
                raise err from exc
            print(f"[{name}] /translations недоступен ({err.kind}), "
                  f"пробую транскрипцию")
            audio_file.seek(0)
            if "prompt" not in common:
                common["prompt"] = "Translate the following speech to English."
            response = client.audio.transcriptions.create(**common)
    else:
        response = client.audio.transcriptions.create(**common)

    return response.text.strip()


def _log_retry(attempt: int, total: int, err: ApiError, delay: float) -> None:
    print(f"[Pishper] {err.title}: попытка {attempt}/{total} не удалась "
          f"({err.detail[:120]}), повтор через {delay:.1f}с")


def transcribe(audio_bytes: bytes, config: AppConfig) -> str:
    """Send audio to speech API and return the resulting text.

    Сетевые сбои, таймауты, 429 и 5xx повторяются автоматически;
    всё, что не удалось, летит наружу как core.errors.ApiError
    с готовым текстом для уведомления.
    """
    if not audio_bytes:
        return ""

    name = provider_name(config)

    if config.provider == "deepgram":
        text = call_with_retries(
            lambda: _transcribe_deepgram(audio_bytes, config),
            name=name, config=config, on_retry=_log_retry,
        )
    elif config.provider == "gigachat":
        text = call_with_retries(
            lambda: _transcribe_gigachat(audio_bytes, config),
            name=name, config=config, on_retry=_log_retry,
        )
    else:
        text = call_with_retries(
            lambda: _transcribe_openai_like(audio_bytes, config, name),
            name=name, config=config, on_retry=_log_retry,
        )

    # Filter hallucinations
    if _is_hallucination(text):
        return ""

    # Apply user-defined replacements
    if config.replacements:
        for old, new in config.replacements.items():
            text = text.replace(old, new)

    return text


# ── Распознавание готового аудиофайла ────────────────────────────────────────

# Длинная запись обрабатывается заметно дольше короткой фразы.
_FILE_TIMEOUT = 600.0
_GIGACHAT_MAX_BYTES = 35 * 1024 * 1024   # лимит GigaChat на один аудиофайл


def file_config(config: AppConfig) -> AppConfig:
    """Конфиг для файла: сервис из config.file_provider, ключ — его же.

    Модель берём текущую, если провайдер совпадает с основным,
    иначе — модель по умолчанию у сервиса для файлов.
    """
    from dataclasses import replace
    from core.config import FILE_PROVIDERS

    provider = config.file_provider if config.file_provider in FILE_PROVIDERS else FILE_PROVIDERS[0]
    if provider == config.provider:
        model = config.model
    else:
        model = PROVIDERS[provider]["models"][0][0]
    # Перевод для файлов не делаем: Deepgram его не умеет, а нужна расшифровка.
    return replace(config, provider=provider, model=model, mode="transcribe",
                   api_keys=dict(config.api_keys), replacements=dict(config.replacements))


def transcribe_file(path: str, config: AppConfig) -> str:
    """Распознать аудиофайл сервисом, выбранным в настройках (Deepgram/GigaChat).

    Файл уходит как есть, без перекодирования.  Ошибки — ApiError.
    """
    from pathlib import Path
    from core.config import AUDIO_TYPES, GIGACHAT_AUDIO_TYPES

    cfg = file_config(config)
    name = provider_name(cfg)
    if not cfg.active_api_key:
        raise ApiError(
            "auth", f"{name}: нет ключа",
            f"Укажите API-ключ для {name} в настройках (раздел «Подключение»).",
        )

    p = Path(path)
    content_type = AUDIO_TYPES.get(p.suffix.lower())
    if cfg.provider == "gigachat" and content_type is not None:
        content_type = GIGACHAT_AUDIO_TYPES.get(p.suffix.lower())
        if content_type is None:
            raise ApiError("request", "GigaChat: формат не поддерживается",
                           f"GigaChat не принимает {p.suffix}. "
                           "Выберите Deepgram для файлов в настройках.")
    if content_type is None:
        raise ApiError("request", "Неподдерживаемый файл",
                       f"Формат {p.suffix or '(без расширения)'} не поддерживается.")
    audio = p.read_bytes()
    if not audio:
        return ""
    if cfg.provider == "gigachat" and len(audio) > _GIGACHAT_MAX_BYTES:
        raise ApiError("request", "GigaChat: файл слишком большой",
                       f"GigaChat принимает аудио до 35 МБ, а файл — "
                       f"{len(audio) / 1024 / 1024:.0f} МБ. Выберите Deepgram в настройках.")

    if cfg.provider == "gigachat":
        text = call_with_retries(
            lambda: _transcribe_gigachat(audio, cfg, p.name, content_type,
                                         timeout=_FILE_TIMEOUT),
            name=name, config=cfg, on_retry=_log_retry,
        )
    else:
        text = call_with_retries(
            lambda: _transcribe_deepgram(audio, cfg, content_type,
                                         timeout=_FILE_TIMEOUT, paragraphs=True),
            name=name, config=cfg, on_retry=_log_retry,
        )

    # Фильтр галлюцинаций здесь не нужен: он рассчитан на тишину в коротких
    # фразах и на длинной записи выбросил бы весь текст из-за одного слова.
    for old, new in cfg.replacements.items():
        text = text.replace(old, new)
    return text


# ── Проверка подключения ─────────────────────────────────────────────────────

# Полсекунды тишины: Whisper отклоняет клипы короче ~0.1с, а платить
# за проверку почти нечем — это самый дешёвый настоящий запрос.
_CHECK_MS = 500
_CHECK_SAMPLE_RATE = 16_000   # как у recorder и continuous


def _silence_mp3(bitrate: int = 32) -> bytes:
    """Полсекунды тишины в MP3 — тестовая нагрузка для проверки."""
    import lameenc

    pcm = b"\x00" * (_CHECK_SAMPLE_RATE * 2 * _CHECK_MS // 1000)
    enc = lameenc.Encoder()
    enc.set_bit_rate(bitrate)
    enc.set_in_sample_rate(_CHECK_SAMPLE_RATE)
    enc.set_channels(1)
    enc.set_quality(7)
    return bytes(enc.encode(pcm) + enc.flush())


def check_connection(config: AppConfig) -> float:
    """Проверить провайдера настоящим запросом: ключ, сеть, прокси, модель.

    Возвращает время ответа в секундах.  При неудаче кидает ApiError
    с готовым текстом — тем же, что показывается в уведомлениях.
    """
    import time as _t

    name = provider_name(config)

    if not config.active_api_key:
        raise ApiError(
            "auth", f"{name}: нет ключа",
            f"Укажите API-ключ для {name} — без него проверять нечего.",
        )

    audio = _silence_mp3(config.mp3_bitrate if config.mp3_bitrate in (16, 32, 64) else 32)

    t0 = _t.perf_counter()
    if config.provider == "deepgram":
        call_with_retries(lambda: _transcribe_deepgram(audio, config),
                          name=name, config=config, on_retry=_log_retry)
    elif config.provider == "gigachat":
        call_with_retries(lambda: _transcribe_gigachat(audio, config),
                          name=name, config=config, on_retry=_log_retry)
    else:
        call_with_retries(lambda: _transcribe_openai_like(audio, config, name),
                          name=name, config=config, on_retry=_log_retry)
    return _t.perf_counter() - t0
