import json, re, requests, time
from config import LLM_BASE_URL, LLM_MODEL, LLM_API_KEY

def call_llm(prompt, max_retries=2):
    if not LLM_API_KEY:
        return None
    max_chars = 25000
    if len(prompt) > max_chars:
        prompt = prompt[:max_chars] + "\n\n[文本已截断]"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LLM_API_KEY}"}
    payload = {"model": LLM_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 8192, "temperature": 0.1, "thinking": {"type": "disabled"}}
    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(f"{LLM_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=120)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            if resp.status_code in (400, 401, 403):
                return None
            if attempt < max_retries: time.sleep(3)
        except Exception as e:
            if attempt < max_retries: time.sleep(2)
    return None

def parse_json_from_llm(text):
    """Extract JSON from LLM response, handling markdown code blocks."""
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        return json.loads(m.group())
    return json.loads(text)
