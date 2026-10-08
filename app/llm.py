# Job Portal · built by JAI SHARMA
"""One interface over ChatGPT (OpenAI), Claude (Anthropic) and OpenAI-compatible extras (Gemini, OpenRouter)."""
import json
import re
from concurrent.futures import ThreadPoolExecutor

from .config import env

PROVIDERS = {
    "chatgpt": {"label": "ChatGPT", "key": "OPENAI_API_KEY", "model_env": "OPENAI_MODEL", "model": "gpt-5",
                "chat_url": "https://chatgpt.com/"},
    "claude": {"label": "Claude", "key": "ANTHROPIC_API_KEY", "model_env": "ANTHROPIC_MODEL", "model": "claude-opus-5-5",
               "chat_url": "https://claude.ai/new"},
    "gemini": {"label": "Gemini", "key": "GEMINI_API_KEY", "model_env": "GEMINI_MODEL", "model": "gemini-2.5-pro",
               "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
               "chat_url": "https://gemini.google.com/app"},
    "openrouter": {"label": "OpenRouter", "key": "OPENROUTER_API_KEY", "model_env": "OPENROUTER_MODEL",
                   "model": "meta-llama/llama-3.3-70b-instruct", "base_url": "https://openrouter.ai/api/v1",
                   "chat_url": "https://openrouter.ai/chat"},
}


class NoKey(Exception):
    """Raised when a provider has no API key, so the caller can fall back to manual copy/paste."""


def model_for(p: str) -> str:
    cfg = PROVIDERS[p]
    return env(cfg["model_env"]) or cfg["model"]


def status() -> list[dict]:
    return [{"id": p, "label": c["label"], "model": model_for(p), "configured": bool(env(c["key"])),
             "chat_url": c["chat_url"]} for p, c in PROVIDERS.items()]


def complete(provider: str, system: str, user: str, json_mode: bool = False) -> str:
    cfg = PROVIDERS[provider]
    key = env(cfg["key"])
    if not key:
        raise NoKey(provider)
    if provider == "claude":
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(model=model_for(provider), max_tokens=8192, system=system,
                                     messages=[{"role": "user", "content": user}])
        return "".join(b.text for b in msg.content if b.type == "text")

    from openai import OpenAI
    client = OpenAI(api_key=key, base_url=cfg.get("base_url"))
    kwargs = {"response_format": {"type": "json_object"}} if json_mode and provider == "chatgpt" else {}
    r = client.chat.completions.create(
        model=model_for(provider),
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}], **kwargs)
    return r.choices[0].message.content or ""


def ask_all(providers: list[str], system: str, user: str) -> list[dict]:
    """Send the same prompt to several models in parallel."""
    def one(p):
        try:
            return {"provider": p, "label": PROVIDERS[p]["label"], "model": model_for(p), "text": complete(p, system, user)}
        except NoKey:
            return {"provider": p, "label": PROVIDERS[p]["label"], "error": "No API key — use copy & open instead."}
        except Exception as e:
            return {"provider": p, "label": PROVIDERS[p]["label"], "error": str(e)[:500]}
    with ThreadPoolExecutor(max_workers=len(providers) or 1) as ex:
        return list(ex.map(one, providers))


def parse_json(text: str) -> dict:
    """Pull a JSON object out of a model reply, tolerating ```json fences and chatter around it."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in the reply.")
    return json.loads(text[start:end + 1])
