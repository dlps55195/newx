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

async def log_debug_state(page, unique_id, stage):
    """Captures a screenshot for diagnostics."""
    timestamp = datetime.now().strftime("%H%M%S")
    filename = f"debug_{unique_id}_{timestamp}_{stage}.png"
    await page.screenshot(path=filename)
    print(f"🔍 [DEBUG: {stage}] Saved screenshot: {filename}")

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
    
    # --- THE PERFECT HUMAN PROMPT ---
    system_instruction = f"""
    [POST CONTEXT]
    Author: {tweet_data['author']}
    Content: "{tweet_data['text']}"
    Media: "{tweet_data['media_desc']}"

    [UNIVERSAL HUMAN FRAMEWORK]
    Follow these steps for any post you see:
    1. THE HOOK: Detect the main vibe (Success, Struggle, Question, or Life Update).
    2. THE MIRROR: Mention a specific detail from their post (e.g., the MRR number, the coffee, the late hour, the specific tool).
    3. THE MOMENTUM: Add a relatable "me too" sentiment or a very simple question.

    [X-POST BENCHMARKS / EXAMPLES]
    - Post: "Finally hit $2k MRR after 6 months of shipping every day. 🚀"
      AI Logic: (Success + $2k) -> "huge milestone!! how are you celebrating? 🙌"
    - Post: "Struggling with these Stripe webhooks. Why is local testing so painful?"
      AI Logic: (Struggle + Stripe) -> "the stripe struggle is real, hope you fix it soon 😭"
    - Post: "Productivity hack: 5am gym session then 4 hours of deep work."
      AI Logic: (Action + 5am) -> "now im feeling guilty 🍪😭 when did you start doing thar?"
    - Post: "Is it just me or is the new X UI actually kind of nice?"
      AI Logic: (Opinion + UI) -> "tbh i’m actually liking it too, looks way cleaner 🙌"

    [STRICT STYLE CONSTRAINTS]
    - lowercase only.
    - Max 12 words.
    - 1-2 emojis max.
    - Slang allowed: lol, rn, tbh, vibe, huge, same, honestly.
    - BANNED: delve, leverage, explore, transformative, "nice post!", "great work!".
    - Output ONLY the raw reply text.
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
                return content.replace('"', '').replace("'", "").lower()
            return None
    except: return None

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
        
        cookie_raw = os.getenv("X_COOKIES")
        if not cookie_raw: return
        await context.add_cookies(sanitize_cookies(json.loads(cookie_raw)))

        page = await context.new_page()
        print(f"📡 Loading Feed...")
        await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(12) 

        tweet_elements = await page.locator('article[data-testid="tweet"]').all()
        candidates = []
        for tweet in tweet_elements:
            try:
                link = tweet.locator('a[href*="/status/"]').first
                tweet_url = await link.get_attribute("href")
                unique_id = tweet_url.split('/')[-1] if tweet_url else None
                if unique_id and unique_id not in seen_ids:
                    text = (await tweet.inner_text()).replace('\n', ' ')
                    author = await tweet.locator('div[dir="ltr"] > span').first.inner_text()
                    candidates.append({"element": tweet, "data": {"text": text, "author": author, "media_desc": "No media"}, "id": unique_id})
            except: continue

        for target in candidates[:3]:
            reply_text = get_ai_reply(target['data'])
            if not reply_text: continue
            print(f"📝 Target: {target['data']['author']} | Human Reply: {reply_text}")

            try:
                await target['element'].evaluate("el => el.scrollIntoView({block: 'center', behavior: 'auto'})")
                await asyncio.sleep(2)
                await target['element'].locator('[data-testid="reply"]').first.evaluate("el => el.click()")
                await asyncio.sleep(2)
                
                textarea = page.locator('[data-testid="tweetTextarea_0"]')
                await textarea.wait_for(state="visible", timeout=10000)
                await textarea.click()
                await page.keyboard.type(reply_text, delay=random.randint(60, 110))
                
                await textarea.dispatch_event("input")
                await page.keyboard.press("Space")
                await page.keyboard.press("Backspace")
                await asyncio.sleep(4) 

                verified = False
                for attempt in range(3):
                    await page.keyboard.press("Control+Enter")
                    await asyncio.sleep(3)
                    
                    if not await textarea.is_visible():
                        verified = True
                        break
                    
                    # Smart Click Fallback
                    smart_btn = page.get_by_role("button", name=re.compile(r"Post|Reply", re.I)).first
                    if await smart_btn.count() > 0:
                         await smart_btn.click(force=True)
                         await asyncio.sleep(2)

                if verified:
                    print(f"✅ Success: {target['id']}")
                    seen_ids.add(target['id'])
                    with open(SEEN_POSTS_FILE, 'w') as f: json.dump(list(seen_ids), f)
                else:
                    print(f"❌ Failed: {target['id']}")
                    await page.keyboard.press("Escape")

                await asyncio.sleep(random.uniform(25, 40))
            except Exception as e:
                print(f"⚠️ Interaction Error: {e}")
                await page.keyboard.press("Escape")

        await browser.close()
        print("🏁 Done.")

if __name__ == "__main__":
    asyncio.run(run_bot())
