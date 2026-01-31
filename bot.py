import os
import json
import asyncio
import random
import re
import httpx
from datetime import datetime, timezone, timedelta
from fake_useragent import UserAgent
from playwright.async_api import async_playwright

# --- CONFIG ---
LIST_URL = "https://x.com/i/lists/2011289206513930641"
SEEN_POSTS_FILE = "seen_posts.json"
AI_API_KEY = os.getenv("AI_API_KEY")

def sanitize_cookies(cookie_list):
    cleaned = []
    for cookie in cookie_list:
        if "sameSite" in cookie and cookie["sameSite"] not in ["Strict", "Lax", "None"]:
            cookie["sameSite"] = "Lax"
        cookie.pop("hostOnly", None)
        cookie.pop("session", None)
        cleaned.append(cookie)
    return cleaned

def get_ai_reply(tweet_text):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
    prompt = f"Reply to: {tweet_text}. Max 15 words, lowercase. Wit ends in ' lol'. Reply text only."
    try:
        with httpx.Client() as client:
            resp = client.post(url, headers=headers, json={"model": "google/gemini-2.0-flash-001", "messages": [{"role": "user", "content": prompt}]}, timeout=30.0)
            if resp.status_code == 200:
                content = resp.json()['choices'][0]['message']['content'].strip()
                return re.sub(r'^(fact|question|wit|reply):\s*', '', content, flags=re.IGNORECASE).replace('"', '')
            return None
    except: return None

async def run_bot():
    print("💓 Bot Start: Monitoring feed...")
    
    # 1. LOAD MEMORY
    seen_ids = set()
    if os.path.exists(SEEN_POSTS_FILE):
        try:
            with open(SEEN_POSTS_FILE, 'r') as f:
                data = json.load(f)
                # Handle both list (new format) and dict (old format)
                if isinstance(data, list):
                    seen_ids = set(data)
                elif isinstance(data, dict):
                    seen_ids = set(data.keys())
        except: pass

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled', '--no-sandbox'])
        context = await browser.new_context(user_agent=UserAgent().random, viewport={'width': 1280, 'height': 800})
        
        # 2. LOGIN
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
        
        # 3. NAVIGATE
        try:
            print(f"📡 Loading List: {LIST_URL}")
            await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(8) # Allow timeline to settle
        except Exception as e:
            print(f"❌ Navigation failed: {e}")
            return

        # 4. SCAN
        tweet_elements = await page.locator('article[data-testid="tweet"]').all()
        candidates = []
        five_mins_ago = datetime.now(timezone.utc) - timedelta(minutes=5)

        for tweet in tweet_elements:
            try:
                # Extract Unique ID from URL
                link_element = tweet.locator('a[href*="/status/"]').first
                tweet_url = await link_element.get_attribute("href")
                unique_id = tweet_url.split('/')[-1] if tweet_url else None
                
                # Check Timestamp
                time_tag = tweet.locator("time")
                if not await time_tag.count(): continue
                iso_time = await time_tag.get_attribute("datetime")
                tweet_time = datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
                
                if unique_id and unique_id not in seen_ids and tweet_time > five_mins_ago:
                    text_content = (await tweet.inner_text()).replace('\n', ' ')
                    candidates.append({"element": tweet, "text": text_content, "id": unique_id})
            except: continue

        print(f"🎯 Fresh Candidates: {len(candidates)}")
        
        # 5. EXECUTE REPLIES
        for target in candidates[:3]:
            # Double check memory (in case of duplicates in same list)
            if target['id'] in seen_ids: continue
            
            print(f"📝 Replying to ID: {target['id']}")
            reply_text = get_ai_reply(target['text'])
            if not reply_text: continue

            try:
                await target['element'].scroll_into_view_if_needed()
                await asyncio.sleep(1)

                # A. Open Reply Modal (Force Click to bypass overlays)
                await target['element'].locator('[data-testid="reply"]').first.click(force=True)
                
                # B. Wait for Textarea
                textarea = page.locator('[data-testid="tweetTextarea_0"]')
                await textarea.wait_for(state="visible", timeout=15000)
                
                # C. Type Reply
                await textarea.click(force=True)
                await page.keyboard.type(reply_text)
                await asyncio.sleep(2)
                
                # D. Send (Priority: Button -> Keyboard Shortcut)
                sent_via_button = False
                send_buttons = ['[data-testid="tweetButtonInline"]', '[data-testid="tweetButton"]']
                for sel in send_buttons:
                    btn = page.locator(sel).first
                    if await btn.is_visible():
                        await btn.click(force=True)
                        sent_via_button = True
                        break
                
                if not sent_via_button:
                    print("⚠️ Button hidden, using Ctrl+Enter...")
                    await page.keyboard.press("Control+Enter")
                
                # E. VERIFICATION (Crucial)
                try:
                    # Success = The textarea disappears
                    await page.wait_for_selector('[data-testid="tweetTextarea_0"]', state="hidden", timeout=15000)
                    print(f"✅ Verified & Saved: {target['id']}")
                    
                    # Update Memory Immediately
                    seen_ids.add(target['id'])
                    with open(SEEN_POSTS_FILE, 'w') as f:
                        json.dump(list(seen_ids), f)
                        
                except Exception:
                    print(f"❌ Verification failed for {target['id']} - Reply modal stayed open.")
                    await page.screenshot(path=f"debug_fail_{target['id']}.png")
                    await page.keyboard.press("Escape") # Close modal to reset

                await asyncio.sleep(random.uniform(20, 40)) # Safety delay

            except Exception as e:
                print(f"⚠️ Interaction Error: {e}")
                await page.keyboard.press("Escape")

        await browser.close()
        print("🏁 Run complete.")

if __name__ == "__main__":
    asyncio.run(run_bot())
