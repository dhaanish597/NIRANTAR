from __future__ import annotations

import httpx

from app.schemas.commander import ChatMessage


async def explain_with_nvidia(*, message: str, history: list[ChatMessage], context: dict, api_key: str | None, model: str, base_url: str, timeout: float) -> str | None:
    if not api_key:
        return None
    system = (
        "You are the NIRANTAR Emergency Commander assistant. Use only the supplied verified context. "
        "Do not invent routes, roads, shelters, numbers, or safety claims. Explain that an authorised "
        "officer decides. Keep the answer concise and operational."
    )
    messages = [{"role": "system", "content": system}]
    messages.extend({"role": item.role, "content": item.content} for item in history[-10:])
    messages.append({"role": "user", "content": f"Verified context:\n{context}\n\nQuestion: {message}"})
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": messages, "temperature": 0.1, "max_tokens": 500},
            )
            response.raise_for_status()
            content = response.json().get("choices", [{}])[0].get("message", {}).get("content")
            return content.strip() if isinstance(content, str) and content.strip() else None
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        return None


def fallback_answer(message: str, context: dict, route_count: int) -> str:
    if route_count:
        return (f"Based on the current verified impact feed, I found {route_count} safe route option(s) "
                f"that avoid roads marked affected. Review the route details below before authorising movement. "
                f"This answer is using the deterministic fallback because the NVIDIA assistant is unavailable.")
    if context.get("priority_count"):
        return (f"The current feed contains {context['priority_count']} priority settlement(s), including "
                f"{context.get('p1_count', 0)} P1. No verified safe route is available in the current snapshot. "
                "Escalate to the authorised response team rather than using an unverified road.")
    return "The commander feed is still waiting for verified impact data. I cannot make a safe-route recommendation yet."
