import os
from openai import OpenAI

_client = None

def get_client():
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("Missing OPENAI_API_KEY")
        _client = OpenAI(api_key=api_key)
    return _client

def llm_call(prompt: str) -> str:
    client = get_client()

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        messages=[
            {"role": "system", "content": "You rewrite text exactly as instructed."},
            {"role": "user", "content": prompt}
        ],
    )

    return resp.choices[0].message.content.strip()
