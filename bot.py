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
    """Fixes 'SameSite' issues to prevent browser crashes."""
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
    Inputs: Dictionary with 'text', 'author', and 'media_desc'.
    Action: Uses the 'Super Prompt' to classify and generate a high-dwell-time reply.
    """
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
    
    # THE 2026 SUPER PROMPT
    system_instruction = f"""
    [SYSTEM ROLE]
    You are a 2026 X Growth Strategist specialized in "Semantic Authority" and "Dwell Time". 
    Your goal is to categorize the user as an authority in their niche.

    [CONTEXT INPUT]
    - OP Handle: {tweet_data['author']}
    - Post Content: "{tweet_data['text']}"
    - Media/Image Context: "{tweet_data['media_desc']}"

    [STEP 1: SEMANTIC ANALYSIS]
    Determine the "Semantic Vector" of the post. 
    1. Is it technical/niche? -> Target: EXPERT
    2. Is it a viral/low-value "banger"? -> Target: WIT
    3. Is it a broad statement/claim? -> Target: CHALLENGER

    [STEP 2: STRATEGY SELECTION]
    
    IF "EXPERT" (Semantic Feeding):
    - Instructions: Use 1-2 pieces of high-level industry jargon. Act as a peer.
    - Example: "the opex on this is brutal unless you verticalize early."

    IF "WIT" (Pattern Interrupt):
    - Instructions: Lowercase only. Dry, ironic, or self-deprecating. End in ' lol'.
    - Example: "my cpu fans just started screaming reading this lol"

    IF "CHALLENGER" (R2R Loop):
    - Instructions: Respectfully challenge a specific point. Ask "Why?" or "How?".
    - Example: "decent take, but how does this model account for churn?"

    [STRICT OUTPUT RULES]
    - Max 18 words.
    - NO hashtags. NO emojis.
    - Output ONLY the reply text. Do not write "Expert:" or "Reply:".
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
                # Clean up any quotes or labels the AI might accidentally leave
                clean_text = re.sub(r'^(Expert|Wit|Challenger|Reply):\s*', '', content, flags=re.IGNORECASE)
                clean_text = clean_text.replace('"', '').replace("'", "")
                return clean_text
            else:
                print(f"⚠️ AI API Error: {resp.status_code}")
                return None
    except Exception as e:
        print(f"⚠️ AI Request Failed: {e}")
        return None

# --- MAIN BOT LOOP ---
async def run_bot():
    print("💓 Bot Start: Semantic Engine Active")
    
    # 1. Memory Load
    seen_ids = set()
    if os.path.exists(SEEN_POSTS_FILE):
        try:
            with open(SEEN_POSTS_FILE, 'r') as f:
                data = json.load(f)
                seen_ids = set(data) if isinstance(data, list) else set(data.keys())
        except: pass

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled', '--no-sandbox'])
        context = await browser.new_context(user_agent=UserAgent().random, viewport={'width': 1280, 'height': 800})
        
        # 2. Authentication
        try:
            cookie_raw = os.getenv("X_COOKIES")
            if not cookie_raw: return
            await context.add_cookies(sanitize_cookies(json.loads(cookie_raw)))
        except: return

        page = await context.new_page()
        print(f"📡 Loading Feed...")
        await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(6)

        # 3. Enhanced Scraping (Text + Image Alt)
        tweet_elements = await page.locator('article[data-testid="tweet"]').all()
        candidates = []
        five_mins_ago = datetime.now(timezone.utc) - timedelta(minutes=5)

        for tweet in tweet_elements:
            try:
                # Get Unique ID
                link_element = tweet.locator('a[href*="/status/"]').first
                tweet_url = await link_element.get_attribute("href")
                unique_id = tweet_url.split('/')[-1] if tweet_url else None
                
                # Get Timestamp
                time_tag = tweet.locator("time")
                if not await time_tag.count(): continue
                tweet_time = datetime.fromisoformat((await time_tag.get_attribute("datetime")).replace("Z", "+00:00"))
                
                if unique_id and unique_id not in seen_ids and tweet_time > five_mins_ago:
                    # Get Text
                    text_content = (await tweet.inner_text()).replace('\n', ' ')
                    
                    # Get Author Handle
                    author_elem = tweet.locator('div[dir="ltr"] > span').first
                    author_name = await author_elem.inner_text() if await author_elem.count() else "Unknown"
                    
                    # Get Image Context (Crucial for the AI)
                    media_desc = "No media"
                    img_elem = tweet.locator('div[data-testid="tweetPhoto"] img').first
                    if await img_elem.count() > 0:
                        alt_text = await img_elem.get_attribute("alt")
                        if alt_text: 
                            media_desc = f"Image shows: {alt_text}"
                        else:
                            media_desc = "Image present but no description available."

                    candidates.append({
                        "element": tweet, 
                        "data": {
                            "text": text_content, 
                            "author": author_name,
                            "media_desc": media_desc
                        },
                        "id": unique_id
                    })
            except: continue

        print(f"🎯 Fresh Candidates: {len(candidates)}")
        
        # REPLACE YOUR ENTIRE 'for target in candidates' LOOP WITH THIS:
        for target in candidates[:3]:
            if target['id'] in seen_ids: continue
            
            reply_text = get_ai_reply(target['data'])
            if not reply_text: continue
            
            print(f"📝 Target: {target['data']['author']} | Strategy: {reply_text[:30]}...")

            try:
                # 1. Open Reply
                await target['element'].locator('[data-testid="reply"]').first.click(force=True)
                textarea = page.locator('[data-testid="tweetTextarea_0"]')
                await textarea.wait_for(state="visible", timeout=10000)
                
                # 2. Type with human-like variance
                await textarea.click(force=True)
                await page.keyboard.type(reply_text, delay=random.randint(50, 100))
                await asyncio.sleep(2)
                
                # 3. THE AGGRESSIVE SEND LOOP
                # We try clicking AND hitting Ctrl+Enter until the box disappears
                verified = False
                for attempt in range(3):
                    # Try the button first
                    post_btn = page.locator('[data-testid="tweetButtonInline"]').first
                    if await post_btn.is_visible():
                        await post_btn.click(force=True)
                    
                    # Backup: Immediate Keyboard Send
                    await page.keyboard.press("Control+Enter")
                    
                    # Wait 3 seconds to see if the modal closes
                    try:
                        await page.wait_for_selector('[data-testid="tweetTextarea_0"]', state="hidden", timeout=3000)
                        verified = True
                        break
                    except:
                        print(f"🔄 Retry {attempt + 1}: Modal still open...")
                        await asyncio.sleep(1)

                if verified:
                    print(f"✅ Success: {target['id']}")
                    seen_ids.add(target['id'])
                    with open(SEEN_POSTS_FILE, 'w') as f:
                        json.dump(list(seen_ids), f)
                else:
                    # If it fails after 3 tries, take a screenshot and escape
                    print(f"❌ Verification Failed for {target['id']}")
                    await page.screenshot(path=f"fail_{target['id']}.png")
                    await page.keyboard.press("Escape")

                # Randomized "Cooldown" to prevent rate-limiting
                await asyncio.sleep(random.uniform(25, 45))

            except Exception as e:
                print(f"⚠️ Interaction Error: {e}")
                await page.keyboard.press("Escape")

        await browser.close()
        print("🏁 Run complete.")

if __name__ == "__main__":
    asyncio.run(run_bot())
