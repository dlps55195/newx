import os
import json
import asyncio
import random
import re
import math
import httpx
from datetime import datetime, timezone, timedelta
from fake_useragent import UserAgent
from playwright.async_api import async_playwright

# --- CONFIG ---
LIST_URL = "https://x.com/i/lists/2011289206513930641"
SEEN_POSTS_FILE = "seen_posts.json"
AI_API_KEY = os.getenv("AI_API_KEY")

# --- HELPER FUNCTIONS ---

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

async def human_delay(min_s=2.0, max_s=5.0):
    await asyncio.sleep(random.uniform(min_s, max_s))

async def human_click(page, selector):
    """Moves mouse in a randomized curve before clicking to bypass bot detection."""
    try:
        element = page.locator(selector).first
        if await element.is_visible():
            box = await element.bounding_box()
            if box:
                # Start from current mouse position
                start_x, start_y = 0, 0 # Default if unknown, Playwright handles this internally usually
                
                # Target a random point inside the button
                target_x = box['x'] + box['width'] * random.uniform(0.2, 0.8)
                target_y = box['y'] + box['height'] * random.uniform(0.2, 0.8)
                
                # Move in steps to simulate human speed
                steps = random.randint(5, 15)
                await page.mouse.move(target_x, target_y, steps=steps)
                await asyncio.sleep(random.uniform(0.1, 0.3))
                await page.mouse.click(target_x, target_y)
    except Exception as e:
        # Fallback to standard click if curve fails
        print(f"⚠️ Human click failed, using standard click: {e}")
        await page.locator(selector).first.click()

async def human_type(page, selector, text):
    """Types with realistic speed, occasional typos, and corrections."""
    await page.click(selector)
    for char in text:
        # 3% chance to make a typo
        if random.random() < 0.03:
            wrong_char = random.choice('abcdefghijklmnopqrstuvwxyz')
            await page.keyboard.press(wrong_char)
            await asyncio.sleep(random.uniform(0.1, 0.3))
            await page.keyboard.press("Backspace")
        
        await page.keyboard.type(char)
        await asyncio.sleep(random.uniform(0.04, 0.12)) # Normal typing speed
        
        # Occasional pause
        if char in ".,?! " and random.random() < 0.2:
            await asyncio.sleep(random.uniform(0.5, 1.0))

def get_ai_reply(tweet_text):
    """Generates a contextual reply using your prompt strategy."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
    
    prompt = f"""
    You are a casual X user. Read this tweet: "{tweet_text}"
    Produce ONE reply text (max 15 words).
    - Style: FACT (relevant info), QUESTION (engaging), or WIT (ironic, ends with ' lol').
    - Output ONLY the reply. Lowercase preferred. No labels like 'Wit:' or 'Fact:'.
    """
    
    try:
        payload = {
            "model": "google/gemini-2.0-flash-001",
            "messages": [{"role": "user", "content": prompt}]
        }
        with httpx.Client() as client:
            resp = client.post(url, headers=headers, json=payload, timeout=30.0)
            if resp.status_code == 200:
                content = resp.json()['choices'][0]['message']['content'].strip()
                # Clean up any potential labels the AI added
                clean = re.sub(r'^(fact|question|wit|reply):\s*', '', content, flags=re.IGNORECASE).replace('"', '')
                return clean
            return None
    except Exception as e:
        print(f"⚠️ AI generation failed: {e}")
        return None

# --- MAIN BOT LOOP ---

async def run_bot():
    print("💓 Bot Start: Checking for fresh content...")
    
    # 1. Validation
    if not AI_API_KEY:
        print("❌ CRITICAL: AI_API_KEY is missing.")
        return

    # 2. Load Memory
    seen_posts = {}
    if os.path.exists(SEEN_POSTS_FILE):
        try:
            with open(SEEN_POSTS_FILE, 'r') as f: seen_posts = json.load(f)
        except: print("⚠️ Memory file corrupted, starting fresh.")

    async with async_playwright() as p:
        print("🌐 Launching Stealth Browser...")
        # Mobile-ish Viewport to blend in
        browser = await p.chromium.launch(
            headless=True, 
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
        )
        context = await browser.new_context(
            user_agent=UserAgent().random, 
            viewport={'width': 1280, 'height': 800}
        )
        
        # 3. Cookies
        try:
            cookie_raw = os.getenv("X_COOKIES")
            if not cookie_raw:
                print("❌ CRITICAL: X_COOKIES is empty.")
                return
            await context.add_cookies(sanitize_cookies(json.loads(cookie_raw)))
        except Exception as e:
            print(f"❌ Cookie Error: {e}")
            return

        page = await context.new_page()
        
        # 4. Navigation (Home -> List)
        try:
            print(f"📡 Navigating to List: {LIST_URL}")
            await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(6) # Let the timeline settle
        except Exception as e:
            print(f"❌ Navigation failed: {e}")
            return

        # 5. Scan & Filter (Freshness < 5 mins)
        tweet_elements = await page.locator('article[data-testid="tweet"]').all()
        print(f"🔎 Found {len(tweet_elements)} tweets on page.")
        
        candidates = []
        five_mins_ago = datetime.now(timezone.utc) - timedelta(minutes=5)

        for tweet in tweet_elements:
            try:
                time_tag = tweet.locator("time")
                if not await time_tag.count(): continue
                
                iso_time = await time_tag.get_attribute("datetime")
                tweet_time = datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
                
                # Check Freshness
                if tweet_time > five_mins_ago:
                    text_content = (await tweet.inner_text()).replace('\n', ' ')
                    post_id = text_content[:80] # Use text snippet as ID
                    
                    if post_id not in seen_posts:
                        candidates.append({
                            "element": tweet, 
                            "text": text_content, 
                            "id": post_id,
                            "time": tweet_time
                        })
            except: continue

        # Sort by Newest -> Oldest
        candidates.sort(key=lambda x: x["time"], reverse=True)
        print(f"🎯 Candidates within 5-min window: {len(candidates)}")
        
        # 6. Process Replies (Max 3)
        for i, target in enumerate(candidates[:3]):
            print(f"📝 processing {i+1}/{min(3, len(candidates))}: {target['id'][:30]}...")
            
            reply_text = get_ai_reply(target['text'])
            if not reply_text: continue

            try:
                # A. Scroll & Click Reply
                await target['element'].scroll_into_view_if_needed()
                await human_delay(1, 2)
                
                reply_btn = target['element'].locator('[data-testid="reply"]').first
                if await reply_btn.is_visible():
                    await human_click(page, '[data-testid="reply"]')
                else:
                    print("⚠️ Reply button not visible.")
                    continue
                
                # B. Wait for Textarea & Type
                textarea = page.locator('[data-testid="tweetTextarea_0"]')
                await textarea.wait_for(state="visible", timeout=10000)
                await human_type(page, '[data-testid="tweetTextarea_0"]', reply_text)
                await human_delay(1, 3)

                # C. Find & Click Send (Resilient)
                found_send = False
                # Try specific test-ids first, then generic text
                selectors = [
                    '[data-testid="tweetButtonInline"]', 
                    '[data-testid="tweetButton"]',
                    '//span[text()="Reply"]',
                    '//span[text()="Post"]'
                ]
                
                for sel in selectors:
                    btn = page.locator(sel).first
                    if await btn.is_visible():
                        await human_click(page, sel)
                        found_send = True
                        break
                
                if not found_send:
                    print("⚠️ Could not find Send button.")
                    await page.screenshot(path="debug_no_send_btn.png")
                    continue

                # D. VERIFICATION (Crucial Step)
                # Wait for the textarea to disappear (success) or timeout (failure)
                print("⏳ Verifying reply...")
                try:
                    await page.wait_for_selector('[data-testid="tweetTextarea_0"]', state="hidden", timeout=8000)
                    print(f"✅ Reply Sent & Verified: {reply_text}")
                    
                    # Only save to memory if verified
                    seen_posts[target['id']] = True
                    with open(SEEN_POSTS_FILE, 'w') as f: json.dump(seen_posts, f)
                    
                except Exception:
                    print("❌ Verification Failed: Modal did not close. X likely ignored the click.")
                    await page.screenshot(path="debug_verification_fail.png")

                # E. Delay before next reply
                if i < len(candidates[:3]) - 1:
                    wait_time = random.uniform(10, 20)
                    print(f"⏳ Sleeping {wait_time:.1f}s...")
                    await asyncio.sleep(wait_time)

            except Exception as e:
                print(f"⚠️ Interaction Loop Error: {e}")
                await page.keyboard.press("Escape") 

        await browser.close()
        print("🏁 Run complete.")

if __name__ == "__main__":
    asyncio.run(run_bot())
