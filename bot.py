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
    
    # --- STRICTLY UNTOUCHED PROMPT ---
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
