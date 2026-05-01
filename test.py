import requests
import os
from dotenv import load_dotenv


load_dotenv()
print("KEY:", os.getenv("OPENAI_API_KEY"))
url = "https://api.openai.com/v1/chat/completions"

headers = {
    "Authorization": f"Bearer {os.getenv('LLM_API_KEY')}",
    "Content-Type": "application/json"
}

data = {
    "model": "gpt-4o-mini",
    "messages": [
        {"role": "user", "content": "Reply OK"} 
    ]
}

resp = requests.post(url, headers=headers, json=data)

print(resp.status_code)
print(resp.text)