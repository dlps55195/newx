import os
import json
import asyncio
import random
import re
import httpx
from datetime import datetime, timezone
from fake_useragent import UserAgent
from playwright.async_api import async_playwright

# --- CONFIGURATION ---
LIST_URL = "https://x.com/i/lists/2011289206513930641"
SEEN_POSTS_FILE = "seen_posts.json"
AI_API_KEY = os.getenv("AI_API_KEY")

# --- IMPROVED DEBUGGING ---
async def log_debug_state(page, unique_id, stage):
    timestamp = datetime.now().strftime("%H%M%S")
    filename = f"debug_{unique_id}_{timestamp}_{stage}.png"
    await page.screenshot(path=filename)
    print(f"🔍 [DEBUG: {stage}] Saved screenshot: {filename}")
    
    # Check for ANY button that looks like a post/send button
    selectors = [
        '[data-testid="tweetButtonInline"]',
        '[data-testid="tweetButton"]',
        'div[role="button"]:has-text("Post")',
        'div[role="button"]:has-text("Reply")'
    ]
    
    found = False
    for selector in selectors:
        btn = page.locator(selector).first
        if await btn.count() > 0:
            attrs = await btn.evaluate("""el => {
                return {
                    selector: el.getAttribute('data-testid') || 'text-match',
                    aria_disabled: el.getAttribute('aria-disabled'),
                    visible: el.offsetWidth > 0,
                    text: el.innerText
                }
            }""")
            print(f"📊 [ELEMENT FOUND]: {attrs}")
            found = True
            break
    if not found:
        print("📊 [ELEMENT STATE]: No Post/Reply button found in DOM with any known selector.")

# --- UTILS & AI ---
def sanitize_cookies(cookie_list):
    cleaned = []
    for cookie in cookie_list:
        if "sameSite" in cookie and cookie["sameSite"] not in ["Strict", "Lax", "None"]:
            cookie["sameSite"] = "Lax"
        cookie.pop("hostOnly", None)
        cookie.pop("session", None)
        cleaned.append(cookie)
    return cleaned

def get_ai_reply(tweet_data):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
    
    # PROMPT (UNCHANGED AS REQUESTED)
    system_instruction = f"""
    [SYSTEM ROLE]
    You are a 2026 SaaS Growth Strategist and Solo-Dev Peer. You operate in the "Build in Public" niche.
    Your goal is to build "Semantic Authority" by providing high-value, punchy insights that increase Dwell Time.

    [CONTEXT INPUT]
    - OP Handle: {tweet_data['author']}
    - Post Content: "{tweet_data['text']}"
    - Media/Image Context: "{tweet_data['media_desc']}"

    [STEP 1: VIBE CHECK]
    Analyze the OP's tone: Are they exhausted, flexing, seeking feedback, or being snarky? 
    Vaguely match their syntax (if they use lowercase, you use lowercase; if they are brief, you be brief).

    [STEP 2: VALUE INJECTION]
    Do not blindly agree. Avoid generic praise like "Great work" or "Keep going." 
    Instead, provide "Intrinsic Value":
    - Identify a hidden trade-off in their tech stack.
    - Ask a high-level architectural "Why?"
    - Offer a "praise + pivot" (e.g., "Clean UI, but how's the latency on that filter logic?")
    - Use "Peer Jargon" naturally (e.g., boilerplate, state management, churn, opex, verticalizing).

    [STEP 3: NO ASS-KISSING]
    Maintain a peer-to-peer level of respect. If a take is mid, be slightly skeptical or ironic. 

    [STRICT OUTPUT RULES]
    - Max 18 words.
    - NO hashtags. NO emojis.
    - DO NOT include your analysis, reasoning, or labels (e.g., "Reply:").
    - DO NOT use enthusiastic bot-language ("Amazing!", "Incredible!", "Wow!").
    - Output ONLY the raw tweet text.
    """
    
    try:
        payload = {
            "model": "google/gemini-2.0-flash-001",
            "messages": [{"role": "user", "content": system_instruction}]
        }
        with httpx.Client() as client:
            resp = client.post(url, headers=headers, json=payload, timeout=30.0)
            if resp.status_code == 200:
                content = resp.json()['choices'][0]['message']['content'].strip()
                clean_text = re.sub(r'^(Expert|Wit|Challenger|Reply|Analysis|Vibe|Strategy):\s*', '', content, flags=re.IGNORECASE)
                return clean_text.replace('"', '').replace("'", "")
            return None
    except: return None

# --- RUN BOT ---
async def run_bot():
    print("💓 Bot Start: Resilient Engine Active")
    seen_ids = set()
    if os.path.exists(SEEN_POSTS_FILE):
        try:
            with open(SEEN_POSTS_FILE, 'r') as f:
                data = json.load(f)
                seen_ids = set(data) if isinstance(data, list) else set(data.keys())
        except: pass

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled', '--no-sandbox'])
        context = await browser.new_context(user_agent=UserAgent().random, viewport={'width': 1920, 'height': 1080})
        
        cookie_raw = os
