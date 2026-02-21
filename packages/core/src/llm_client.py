from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class LLMResponse:
    text: str
    raw: Any


class LLMClient:
    """
    Minimal Gemini client wrapper.

    Usage:
        client = LLMClient(model="gemini-1.5-pro")
        response = client.generate("Hello")
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-1.5-pro",
        temperature: float = 0.2,
        max_output_tokens: int = 2048,
    ) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is required to call Gemini.")
        self.model = model
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens

        try:
            from google import genai
        except ImportError as exc:
            raise ImportError(
                "Missing dependency: google-genai. Install via `pip install google-genai`."
            ) from exc

        self._genai = genai
        self._client = genai.Client(api_key=self.api_key)

    def list_models(self) -> list[str]:
        """
        List available Gemini models and their supported methods.
        """
        models = self._client.models.list()
        return [model.name for model in models]

    def _combine_prompt(self, prompt: str, system_prompt: Optional[str]) -> str:
        if system_prompt:
            return f"{system_prompt.strip()}\n\n{prompt}"
        return prompt

    def _extract_json_text(self, text: str) -> Optional[str]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = "\n".join(
                line
                for line in cleaned.splitlines()
                if not line.strip().startswith("```")
            ).strip()

        start = None
        stack = []
        for idx, ch in enumerate(cleaned):
            if ch in "{[":
                if start is None:
                    start = idx
                stack.append(ch)
            elif ch in "}]":
                if stack:
                    stack.pop()
                    if not stack and start is not None:
                        return cleaned[start : idx + 1]

        return None

    def _trim_to_last_json_ending(self, text: str) -> Optional[str]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = "\n".join(
                line
                for line in cleaned.splitlines()
                if not line.strip().startswith("```")
            ).strip()

        last_obj = cleaned.rfind("}")
        last_arr = cleaned.rfind("]")
        last = max(last_obj, last_arr)
        if last == -1:
            return None
        return cleaned[: last + 1]

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        response_mime_type: Optional[str] = None,
        safety_settings: Optional[Any] = None,
    ) -> LLMResponse:
        """
        Generate a response from Gemini.

        If `response_mime_type` is "application/json", the caller should parse
        the resulting text as JSON.
        """
        generation_config = {
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
        }
        if response_mime_type:
            generation_config["response_mime_type"] = response_mime_type
        if safety_settings:
            generation_config["safety_settings"] = safety_settings

        prompt_text = self._combine_prompt(prompt, system_prompt)

        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt_text,
            config=generation_config,
        )
        text = getattr(response, "text", "") or ""
        return LLMResponse(text=text, raw=response)

    def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        schema_hint: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Convenience method that asks for JSON output and parses it.

        `schema_hint` is optional metadata used to guide the model.
        """
        hint_text = ""
        if schema_hint:
            hint_text = "\nReturn JSON that matches this schema:\n" + json.dumps(
                schema_hint, indent=2
            )

        strict_instruction = (
            "You must return ONLY valid JSON. Do not include prose, "
            "markdown fences, comments, or trailing text. If you are unsure, "
            "return an empty JSON object {}."
        )

        if system_prompt:
            combined_system = f"{system_prompt.strip()}\n\n{strict_instruction}"
        else:
            combined_system = strict_instruction

        last_error: Optional[Exception] = None
        original_temperature = self.temperature
        original_max_output_tokens = self.max_output_tokens
        self.temperature = 0.0
        self.max_output_tokens = max(self.max_output_tokens, 4096)

        try:
            for _ in range(2):
                response = self.generate(
                    prompt + hint_text,
                    system_prompt=combined_system,
                    response_mime_type="application/json",
                )
                try:
                    return json.loads(response.text)
                except json.JSONDecodeError as exc:
                    last_error = exc
                    extracted = self._extract_json_text(response.text)
                    if extracted:
                        try:
                            return json.loads(extracted)
                        except json.JSONDecodeError:
                            pass

                    trimmed = self._trim_to_last_json_ending(response.text)
                    if trimmed:
                        try:
                            return json.loads(trimmed)
                        except json.JSONDecodeError:
                            pass

            raise ValueError(
                "Gemini did not return valid JSON after retries. Raw response:\n"
                + response.text
            ) from last_error
        finally:
            self.temperature = original_temperature
            self.max_output_tokens = original_max_output_tokens
