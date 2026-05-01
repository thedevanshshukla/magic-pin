import re
from llm_client import llm_call

def humanize_message(body: str) -> str:
    if "visit" in body and "days" in body:
        return body

    prompt = f"""
Rewrite this WhatsApp message to sound natural and human.

STRICT RULES:
- Do NOT change numbers
- Do NOT change meaning
- Do NOT remove CTA
- Keep under 320 chars
- Keep urgency strong
- Avoid repetition

MESSAGE:
{body}

Return only improved message.
"""
    try:
        return llm_call(prompt)
    except Exception:
        return body

def validate_humanized(original: str, new: str) -> str:
    if len(new) > 320:
        return original
    if new.count("?") != 1:
        return original
    if re.findall(r"\d+", original) != re.findall(r"\d+", new):
        return original
    if len(new) < int(0.7 * len(original)):
        return original
    return new
