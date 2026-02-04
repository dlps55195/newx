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

# --- DEBUGGING FUNCTION ---
async def log_debug_state(page, unique_id, stage):
    """Captures a screenshot and checks for buttons using multiple strategies."""
    timestamp = datetime.now().strftime("%H%M%S")
    filename = f"debug_{unique_id}_{timestamp}_{stage}.png"
    await page.screenshot(path=filename)
    print(f"🔍 [DEBUG: {stage}] Saved screenshot: {filename}")
    
    # Strategy 1: Test ID
    btn_id = page.locator('[data-testid="tweetButtonInline"]').first
    
    # Strategy 2: Role + Text (More robust)
    btn_role = page.get_by_role("button", name=re.compile(r"Post|Reply", re.I)).first

    found = False
    if await btn_id.count() > 0 and await btn_id.is_visible():
        print(f"📊 [ELEMENT STATE] Found via ID. Enabled: {await btn_id.is_enabled()}")
        found = True
    elif await btn_role.count() > 0 and await btn_role.is_visible():
        print(f"📊 [ELEMENT STATE] Found via ROLE. Enabled: {await btn_role.is_enabled()}")
        found = True
    
    if not found:
        print("📊 [ELEMENT STATE]: Post/Reply button NOT FOUND in DOM.")

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
    
    system_instruction = f"""
    [PERSONA]
    You are a cynical, high-context Senior Developer. You've been building for 10 years. 
    You despise "engagement bait" and AI-generated sounding replies. 
    You speak in tech-shorthand and value brevity over politeness.

    [INPUT]
    - Author: {tweet_data['author']}
    - Tweet: "{tweet_data['text']}"
    - Media Context: "{tweet_data['media_desc']}"

    [STRATEGIC ARCHETYPES] (Pick one):
    1. THE "WHY": Ask a high-level architectural question about a trade-off they made.
    2. THE "EDGE CASE": Mention a specific scenario where their tech stack might fail (e.g., race conditions, cold starts, rate limits).
    3. THE "SHARED DEBT": Bond over a specific annoying part of the tech they mentioned (e.g., "prisma migrations are a nightmare").
    4. THE "IRONIC OBSERVER": Give a deadpan, 1-sentence observation on their "build in public" progress.

    [STRICT HUMAN RULES]
    - NO generic praise (Never start with: "Nice," "Great," "Interesting," "I love this").
    - NO emojis. NO hashtags.
    - Use technical nouns from the tweet (e.g., instead of "the tool," say "the redis cache").
    - Syntax: Use lowercase for tech terms. Use occasional sentence fragments.
    - Length: Under 12 words.
    - Goal: Sound like a person replying from their phone while waiting for a build to finish.

    [OUTPUT]
    Raw reply text only.
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
                # Remove quotes and force a more "human" lowercase style
                return content.replace('"', '').replace("'", "").lower()
            return None
    except: return None

# --- MAIN BOT LOOP ---
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
        now = datetime.now(timezone.utc)

        for tweet in tweet_elements:
            try:
                link = tweet.locator('a[href*="/status/"]').first
                tweet_url = await link.get_attribute("href")
                unique_id = tweet_url.split('/')[-1] if tweet_url else None
                # Expanded time window for testing
                if unique_id and unique_id not in seen_ids:
                    text = (await tweet.inner_text()).replace('\n', ' ')
                    author = await tweet.locator('div[dir="ltr"] > span').first.inner_text()
                    candidates.append({"element": tweet, "data": {"text": text, "author": author, "media_desc": "No media"}, "id": unique_id})
            except: continue
        
        print(f"🎯 Candidates Found: {len(candidates)}")

        for target in candidates[:3]:
            reply_text = get_ai_reply(target['data'])
            if not reply_text: continue
            print(f"📝 Target: {target['data']['author']} | Strategy: {reply_text}")

            try:
                # 1. SCROLL & PREP
                await target['element'].evaluate("el => el.scrollIntoView({block: 'center', behavior: 'auto'})")
                await asyncio.sleep(2)

                # 2. OPEN REPLY (Using JS to bypass masks)
                reply_btn = target['element'].locator('[data-testid="reply"]').first
                await reply_btn.evaluate("el => el.click()")
                
                # 3. HANDLE MASK & TEXTAREA
                try:
                    await page.locator('[data-testid="mask"]').wait_for(state="hidden", timeout=4000)
                except: pass

                textarea = page.locator('[data-testid="tweetTextarea_0"]')
                await textarea.wait_for(state="visible", timeout=10000)
                await textarea.click()
                await page.keyboard.type(reply_text, delay=random.randint(60, 100))
                
                # 4. ACTIVATE STATE
                await textarea.dispatch_event("input")
                await page.keyboard.press("Space")
                await page.keyboard.press("Backspace")
                await asyncio.sleep(4) 

                verified = False
                for attempt in range(3):
                    await log_debug_state(page, target['id'], f"attempt_{attempt}")

                    # A. Primary: Hotkey
                    await page.keyboard.press("Control+Enter")
                    await asyncio.sleep(3)

                    # B. Secondary: Click by Role (Pierces Shadow DOM)
                    if await textarea.is_visible():
                        print(f"🔄 Attempt {attempt+1}: Hotkey failed. Trying Smart Click...")
                        # This finds ANY button with 'Post' or 'Reply' in it, ignoring specific IDs
                        smart_btn = page.get_by_role("button", name=re.compile(r"Post|Reply", re.I)).first
                        if await smart_btn.count() > 0:
                             await smart_btn.click(force=True)
                        else:
                             # C. Fallback: ID Click
                             fallback_btn = page.locator('[data-testid="tweetButtonInline"]').first
                             if await fallback_btn.is_visible():
                                 await fallback_btn.click(force=True)
                        await asyncio.sleep(2)

                    # Check for success
                    if not await textarea.is_visible():
                        verified = True
                        break

                if verified:
                    print(f"✅ Success: {target['id']}")
                    seen_ids.add(target['id'])
                    with open(SEEN_POSTS_FILE, 'w') as f: json.dump(list(seen_ids), f)
                else:
                    print(f"❌ Verification Failed: {target['id']}")
                    # Dump HTML context on final failure
                    await page.screenshot(path=f"fail_{target['id']}.png")
                    await page.keyboard.press("Escape")

                await asyncio.sleep(random.uniform(25, 40))
            except Exception as e:
                print(f"⚠️ Interaction Error: {e}")
                await page.keyboard.press("Escape")

        await browser.close()
        print("🏁 Done.")

if __name__ == "__main__":
    asyncio.run(run_bot())
