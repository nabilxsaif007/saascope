"""Provider-agnostic LLM layer. Any LLM, chosen in config — not Claude-locked.

Supported providers: anthropic | openai | gemini | ollama (local).
Each exposes the same complete(system, user_text, images, max_tokens) -> str.
SDKs are imported lazily, so you only install the one you actually use.
"""
from __future__ import annotations
import base64
import json
import os
import urllib.request
from pathlib import Path
from typing import Iterable


def _b64(p: Path) -> tuple[str, str]:
    media = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    return media, base64.b64encode(p.read_bytes()).decode()


class LLMClient:
    def __init__(self, provider: str, model: str):
        self.provider = (provider or "anthropic").lower()
        self.model = model

    def complete(self, system: str, user_text: str,
                 images: Iterable[Path] = (), max_tokens: int = 8000) -> str:
        imgs = [Path(i) for i in images if Path(i).exists()]
        fn = getattr(self, f"_{self.provider}", None)
        if fn is None:
            raise RuntimeError(f"Unknown LLM provider: {self.provider}")
        return fn(system, user_text, imgs, max_tokens)

    def complete_json(self, system: str, user_text: str,
                      images: Iterable[Path] = (), max_tokens: int = 1500) -> dict:
        """Like complete(), but parse the first JSON object out of the reply."""
        raw = self.complete(system, user_text, images, max_tokens)
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1:
            raise ValueError(f"No JSON object in LLM reply: {raw[:200]}")
        return json.loads(raw[start:end + 1])

    # -- Anthropic ----------------------------------------------------------
    def _anthropic(self, system, user_text, imgs, max_tokens) -> str:
        from anthropic import Anthropic
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY not set.")
        content = []
        for p in imgs:
            media, data = _b64(p)
            content.append({"type": "image", "source": {
                "type": "base64", "media_type": media, "data": data}})
        content.append({"type": "text", "text": user_text})
        resp = Anthropic(api_key=key).messages.create(
            model=self.model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": content}])
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")

    # -- OpenAI -------------------------------------------------------------
    def _openai(self, system, user_text, imgs, max_tokens) -> str:
        from openai import OpenAI
        client = OpenAI()  # reads OPENAI_API_KEY
        content = []
        for p in imgs:
            media, data = _b64(p)
            content.append({"type": "image_url",
                            "image_url": {"url": f"data:{media};base64,{data}"}})
        content.append({"type": "text", "text": user_text})
        resp = client.chat.completions.create(
            model=self.model, max_tokens=max_tokens,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": content}])
        return resp.choices[0].message.content or ""

    # -- Gemini -------------------------------------------------------------
    def _gemini(self, system, user_text, imgs, max_tokens) -> str:
        import google.generativeai as genai
        genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
        model = genai.GenerativeModel(self.model, system_instruction=system)
        parts = [user_text]
        for p in imgs:
            media, _ = _b64(p)
            parts.append({"mime_type": media, "data": p.read_bytes()})
        resp = model.generate_content(
            parts, generation_config={"max_output_tokens": max_tokens})
        return resp.text

    def _google(self, *a):  # alias
        return self._gemini(*a)

    # -- Ollama (local, no key) --------------------------------------------
    def _ollama(self, system, user_text, imgs, max_tokens) -> str:
        base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        user_msg = {"role": "user", "content": user_text}
        if imgs:
            user_msg["images"] = [base64.b64encode(p.read_bytes()).decode() for p in imgs]
        payload = {"model": self.model, "stream": False,
                   "messages": [{"role": "system", "content": system}, user_msg]}
        req = urllib.request.Request(
            f"{base}/api/chat", data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read())["message"]["content"]
