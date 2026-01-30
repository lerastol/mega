"""
Клиент для работы с LLM (OpenAI / YandexGPT).
Цель: единый интерфейс generate_response с retry при таймаутах.
"""
from __future__ import annotations

import os
import time
import json
from typing import Any

# OpenAI
from openai import OpenAI
from openai import APITimeoutError, APIConnectionError

# Yandex — через requests к API (документация Yandex Cloud)
import requests


class LLMClient:
    """
    Интерфейс к LLM: OpenAI (GPT-4o-mini) или YandexGPT.
    Провайдер задаётся через LLM_PROVIDER=openai|yandex и соответствующие ключи.
    """

    DEFAULT_MAX_RETRIES = 3
    DEFAULT_RETRY_DELAY = 2.0
    DEFAULT_TIMEOUT = 60.0

    def __init__(
        self,
        provider: str | None = None,
        openai_api_key: str | None = None,
        yandex_api_key: str | None = None,
        yandex_folder_id: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY,
    ):
        self.provider = (provider or os.environ.get("LLM_PROVIDER", "yandex")).lower()
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        if self.provider == "openai":
            self._openai_key = (
                openai_api_key
                or os.environ.get("OPENAI_API_KEY")
                or os.environ.get("LLM_API_KEY")
            )
            if not self._openai_key:
                raise ValueError(
                    "OPENAI_API_KEY не задан для провайдера openai. "
                    "Задайте в .env переменную OPENAI_API_KEY или LLM_API_KEY. "
                    "Ключ создаётся на https://platform.openai.com/api-keys"
                )
            # Подсказка, если в .env оставлен плейсхолдер
            if "ijklmnop" in self._openai_key or self._openai_key.endswith("xxxx"):
                raise ValueError(
                    "В .env указан плейсхолдер вместо реального ключа OpenAI. "
                    "Замените OPENAI_API_KEY на ключ с https://platform.openai.com/api-keys"
                )
            self._client = OpenAI(api_key=self._openai_key)
        elif self.provider == "yandex":
            self._yandex_key = yandex_api_key or os.environ.get("YANDEX_API_KEY")
            self._yandex_folder = yandex_folder_id or os.environ.get("YANDEX_FOLDER_ID")
            if not self._yandex_key:
                raise ValueError(
                    "YANDEX_API_KEY не задан для провайдера yandex. "
                    "Задайте в .env переменную YANDEX_API_KEY. "
                    "Ключ создаётся в Yandex Cloud: https://console.yandex.cloud"
                )
            if not self._yandex_folder:
                raise ValueError(
                    "YANDEX_FOLDER_ID не задан для провайдера yandex. "
                    "Укажите в .env идентификатор каталога (folder) из Yandex Cloud."
                )
            self._client = None
        else:
            raise ValueError(f"Неизвестный провайдер LLM: {self.provider}")

    def generate_response(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        as_json: bool = False,
    ) -> str | dict[str, Any]:
        """
        Отправить запрос в LLM и вернуть ответ.
        :param system_prompt: системный промпт (роль).
        :param user_prompt: запрос пользователя.
        :param as_json: если True — парсить ответ как JSON и вернуть dict.
        :return: строка ответа или dict при as_json=True.
        """
        last_error = None
        for attempt in range(self.max_retries):
            try:
                text = self._call_llm(system_prompt, user_prompt)
                if as_json:
                    return json.loads(text)
                return text
            except (APITimeoutError, APIConnectionError, requests.exceptions.Timeout) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
        raise last_error  # type: ignore[misc]

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        if self.provider == "openai":
            return self._call_openai(system_prompt, user_prompt)
        return self._call_yandex(system_prompt, user_prompt)

    def _call_openai(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            timeout=self.timeout,
        )
        return (response.choices[0].message.content or "").strip()

    def _call_yandex(self, system_prompt: str, user_prompt: str) -> str:
        # Yandex GPT API (REST): https://cloud.yandex.ru/docs/yandexgpt/api-ref/
        url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        headers = {
            "Authorization": f"Api-Key {self._yandex_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "modelUri": f"gpt://{self._yandex_folder}/yandexgpt/latest",
            "completionOptions": {
                "stream": False,
                "temperature": 0.3,
                "maxTokens": "2000",
            },
            "messages": [
                {"role": "system", "text": system_prompt},
                {"role": "user", "text": user_prompt},
            ],
        }
        resp = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        alternatives = data.get("result", {}).get("alternatives", [])
        if not alternatives:
            return ""
        return (alternatives[0].get("message", {}).get("text", "") or "").strip()
