import os
import json
import asyncio
import random
import re
import httpx
from datetime import datetime, timezone, timedelta
from fake_useragent import UserAgent
from playwright.async_api import async_playwright

# --- CONFIGURATION ---
LIST_URL = "https://x.com/i/lists/2011289206513930641"
SEEN_POSTS_FILE = "seen_posts.json"
AI_API_KEY = os.getenv("AI_API_KEY")

# --- UTILS ---
def sanitize_cookies(cookie_list):
    """Ensures cookie compatibility to prevent browser crashes."""
    cleaned = []
    for cookie in cookie_list:
        if "sameSite" in cookie and cookie["sameSite"] not in ["Strict", "Lax", "None"]:
            cookie["sameSite"] = "Lax"
        cookie.pop("hostOnly", None)
        cookie.pop("session", None)
        cleaned.append(cookie)
    return cleaned

# --- THE STRATEGIC AI BRAIN ---
def get_ai_reply(tweet_data):
    """
    Refactored for SaaS/Solo-Dev context. 
    Focus: Tone-matching, intrinsic value, and zero 'ass-kissing'.
    """
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
    
    # --- THE LOCKED PROMPT (DO NOT TOUCH) ---
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
    - DO NOT include your analysis, reasoning, or labels (e.g., "Reply:"; "Strategy:").
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
                # Clean up any labels the AI might accidentally leave
                clean_text = re.sub(r'^(Expert|Wit|Challenger|Reply|Analysis|Vibe|Strategy):\s*', '', content, flags=re.IGNORECASE)
                return clean_text.replace('"', '').replace("'", "")
            return None
    except Exception:
        return None

# --- MAIN BOT LOOP ---
async def run_bot():
    print("💓 Bot Start: Resilient Engine Active")
    
    # 1. Load Memory
    seen_ids = set()
    if os.path.exists(SEEN_POSTS_FILE):
        try:
            with open(SEEN_POSTS_FILE, 'r') as f:
                data = json.load(f)
                seen_ids = set(data) if isinstance(data, list) else set(data.keys())
        except: pass

    async with async_playwright() as p:
        # Launch with stealth arguments
        browser = await p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled', '--no-sandbox'])
        context = await browser.new_context(user_agent=UserAgent().random, viewport={'width': 1920, 'height': 1080})
        
        try:
            cookie_raw = os.getenv("X_COOKIES")
            if not cookie_raw: return
            await context.add_cookies(sanitize_cookies(json.loads(cookie_raw)))
        except: return

        page = await context.new_page()
        print(f"📡 Loading Feed...")
        
        # FIX: domcontentloaded avoids the 'networkidle' hang
        await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=60000)
        # FIX: Increased wait time to ensure the 'Post' button logic is loaded in background
        await asyncio.sleep(12)

        # 2. Scrape & Filter
        tweet_elements = await page.locator('article[data-testid="tweet"]').all()
        candidates = []
        now = datetime.now(timezone.utc)

        for tweet in tweet_elements:
            try:
                link_element = tweet.locator('a[href*="/status/"]').first
                tweet_url = await link_element.get_attribute("href")
                unique_id = tweet_url.split('/')[-1] if tweet_url else None
                
                # Check 20-minute window
                time_tag = tweet.locator("time")
                if not await time_tag.count(): continue
                tweet_time = datetime.fromisoformat((await time_tag.get_attribute("datetime")).replace("Z", "+00:00"))
                
                if unique_id and unique_id not in seen_ids and (now - tweet_time).total_seconds() < 1200:
                    text_content = (await tweet.inner_text()).replace('\n', ' ')
                    author_elem = tweet.locator('div[dir="ltr"] > span').first
                    author_name = await author_elem.inner_text() if await author_elem.count() else "Unknown"
                    
                    media_desc = "No media"
                    img_elem = tweet.locator('div[data-testid="tweetPhoto"] img').first
                    if await img_elem.count() > 0:
                        alt = await img_elem.get_attribute("alt")
                        media_desc = f"Image content: {alt}" if alt else "Image present"

                    candidates.append({
                        "element": tweet, 
                        "data": {"text": text_content, "author": author_name, "media_desc": media_desc},
                        "id": unique_id
                    })
            except: continue

        print(f"🎯 Candidates Found: {len(candidates)}")

        # 3. Interaction Loop (The 'Verification Failed' Fixes)
        for target in candidates[:3]:
            if target['id'] in seen_ids: continue
            
            print(f"📝 Analyzing {target['data']['author']}...")
            reply_text = get_ai_reply(target['data'])
            
            if not reply_text: continue
            print(f"🤖 Strategy: {reply_text}")

            try:
                # FIX: Instant 'auto' scroll prevents clicking on a moving target
                await target['element'].evaluate("el => el.scrollIntoView({block: 'center', behavior: 'auto'})")
                await asyncio.sleep(2)

                # FIX: Coordinate click to bypass viewport errors
                reply_btn = target['element'].locator('[data-testid="reply"]').first
                box = await reply_btn.bounding_box()
                if box:
                    await page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
                else:
                    await reply_btn.click(force=True)
                
                textarea = page.locator('[data-testid="tweetTextarea_0"]')
                await textarea.wait_for(state="visible", timeout=12000)
                
                # FOCUS & TYPE
                await textarea.click()
                await page.keyboard.type(reply_text, delay=random.randint(40, 90))
                
                # FIX: The "Human Jiggle" to unlock the button
                # We do this specifically to flip the button state from 'Disabled' to 'Active'
                await textarea.dispatch_event("input")
                await asyncio.sleep(0.5)
                await page.keyboard.press("Space")
                await asyncio.sleep(0.5)
                await page.keyboard.press("Backspace")
                await asyncio.sleep(2) # Give React time to update state

                # FIX: 3-Layer Submission Strategy
                verified = False
                for attempt in range(3):
                    post_btn = page.locator('[data-testid="tweetButtonInline"]').first
                    
                    # 1. Hotkey (The most reliable method)
                    await page.keyboard.press("Control+Enter")
                    
                    # 2. Hover + Coordinate Click (If hotkey fails)
                    if await post_btn.is_visible():
                        await post_btn.hover() # Wake up hover state
                        btn_box = await post_btn.bounding_box()
                        if btn_box:
                            await page.mouse.click(
                                btn_box['x'] + btn_box['width'] / 2, 
                                btn_box['y'] + btn_box['height'] / 2
                            )
                    
                    # 3. Check for success (Modal disappears)
                    try:
                        await page.wait_for_selector('[data-testid="tweetTextarea_0"]', state="hidden", timeout=5000)
                        verified = True
                        break
                    except:
                        # Fallback: Direct JS Injection
                        print(f"🔄 Retry {attempt+1} (JS Injection)...")
                        if await post_btn.is_visible():
                            await post_btn.evaluate("el => el.click()")
                        await asyncio.sleep(2)

                if verified:
                    print(f"✅ Verified & Saved: {target['id']}")
                    seen_ids.add(target['id'])
                    with open(SEEN_POSTS_FILE, 'w') as f: json.dump(list(seen_ids), f)
                else:
                    print(f"❌ Verification Failed: {target['id']}")
                    await page.keyboard.press("Escape")

                await asyncio.sleep(random.uniform(20, 40))

            except Exception as e:
                print(f"⚠️ Interaction Error: {e}")
                await page.keyboard.press("Escape")

        await browser.close()
        print("🏁 Run complete.")

if __name__ == "__main__":
    asyncio.run(run_bot())
