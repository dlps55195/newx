import os
import json
import asyncio
import random
import re
import httpx
from fake_useragent import UserAgent
from playwright.async_api import async_playwright

# --- CONFIG ---
LIST_URL = "https://x.com/i/lists/2011289206513930641" # <--- Your List ID
SEEN_POSTS_FILE = "seen_posts.json"
AI_API_KEY = os.getenv("AI_API_KEY")

# --- HELPER FUNCTIONS ---

def sanitize_cookies(cookie_list):
    """Fixes 'SameSite' issues and removes junk to prevent Playwright crashes."""
    cleaned = []
    allowed_samesite = ["Strict", "Lax", "None"]
    for cookie in cookie_list:
        # Enforce valid SameSite values
        if "sameSite" in cookie:
            if cookie["sameSite"] not in allowed_samesite:
                cookie["sameSite"] = "Lax"
        # Remove keys that often cause errors
        cookie.pop("hostOnly", None)
        cookie.pop("session", None)
        cleaned.append(cookie)
    return cleaned

async def human_delay(min_s=1.5, max_s=5.0):
    """Random pause to simulate thinking."""
    await asyncio.sleep(random.uniform(min_s, max_s))

async def human_type(page, selector, text):
    """Types text with variable speed and occasional typos + corrections."""
    await page.click(selector)
    
    for char in text:
        # 3% chance to make a typo
        if random.random() < 0.03:
            wrong_char = random.choice('abcdefghijklmnopqrstuvwxyz')
            await page.keyboard.press(wrong_char)
            await asyncio.sleep(random.uniform(0.1, 0.4)) # Realize mistake
            await page.keyboard.press("Backspace")
            await asyncio.sleep(random.uniform(0.1, 0.3)) # Recover
        
        await page.keyboard.type(char)
        # Random speed per keystroke (fast bursts vs slow hunting)
        await asyncio.sleep(random.uniform(0.05, 0.15)) 
        
        # Occasional "thinking" pause mid-sentence
        if char in ".,?! ":
            if random.random() < 0.2:
                await asyncio.sleep(random.uniform(0.5, 1.2))

async def simulate_reading(page, tweet_element):
    """Scrolls past the tweet, stops, and scrolls back up slightly."""
    box = await tweet_element.bounding_box()
    if box:
        # Scroll slightly past it (like reading comments)
        await page.mouse.wheel(0, box['height'] + random.randint(100, 300))
        await human_delay(1, 3)
        # Scroll back up to the tweet
        await page.mouse.wheel(0, -random.randint(100, 200))
        await human_delay(0.5, 1.5)

def get_ai_reply(tweet_text):
    """Generates a reply using the exact strategic prompt provided."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "HTTP-Referer": "https://github.com/newx",
        "Content-Type": "application/json"
    }
    
    # User's exact prompt structure
    prompt = f"""
You are a casual X user whose job is to read a single tweet (variable: {tweet_text}) and produce exactly one reply text that maximizes appropriateness & engagement.

STEP 1 — choose the best reply style from these three, using the tweet's content and tone:
  • FACT — a tiny, directly relevant fact (use when the tweet states a claim, stat, or shares new info).  
  • QUESTION — a short, sharp question that encourages a reply (use when the tweet is open, asks something, or invites conversation).  
  • WIT — a brief sarcastic/chill observation (use when the tweet is playful, ranty, or ironic). always append " lol" at the end for WIT.

STEP 2 — generate the reply following these strict rules:
  - output only the reply text (no labels, explanations, or metadata).  
  - prefer lowercase (use proper punctuation only where needed).  
  - no emojis unless used ironically to amplify wit.  
  - maximum 15 words. Count words precisely.  
  - do not write "fact:", "question:", "wit:", or any style tag.  
  - QUESTION replies must end with a question mark.  
  - FACT replies must be concise and directly tied to the tweet's claim/context.  
  - WIT replies must include " lol" at the end (space + lol).  
  - if the tweet contains disallowed content you cannot engage with, reply with: "i can't reply to that." (all lowercase; counts toward 15 words).

INPUT: the variable contains the full text of the tweet to respond to.

OUTPUT: a single line — the reply text only, obeying every rule above.
"""

    payload = {
        "model": "google/gemini-2.0-flash-001",
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(url, headers=headers, json=payload, timeout=30.0)
            if response.status_code == 200:
                content = response.json()['choices'][0]['message']['content'].strip()
                # FINAL CLEAN: Remove any accidental labels (e.g. "WIT: nice lol")
                clean_content = re.sub(r'^(fact|question|wit|reply|response|step 2):\s*', '', content, flags=re.IGNORECASE)
                return clean_content.replace('"', '')
            return None
    except Exception as e:
        print(f"⚠️ AI Error: {e}")
        return None

# --- MAIN BOT LOOP ---

async def run_bot():
    print("💓 Heartbeat: Checking schedule...")
    
    # 20% Chance to Lurk (Log in, scroll, do nothing) - Builds Trust
    is_lurking = random.random() < 0.20
    if is_lurking: print("👀 Mode: Passive Lurking (No replies this run)")

    # Load Memory
    if not os.path.exists(SEEN_POSTS_FILE):
        seen_posts = {}
        with open(SEEN_POSTS_FILE, 'w') as f: json.dump({}, f)
    else:
        with open(SEEN_POSTS_FILE, 'r') as f: 
            try: seen_posts = json.load(f)
            except: seen_posts = {}

    async with async_playwright() as p:
        ua = UserAgent()
        
        # 1. Randomized Viewport (Mobile mix)
        viewport = random.choice([
            {'width': 1920, 'height': 1080},
            {'width': 1366, 'height': 768},
            {'width': 375, 'height': 812} # Mobile
        ])
        
        # 2. Stealth Args (Hide Automation)
        browser = await p.chromium.launch(
            headless=True, 
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-infobars',
                '--ignore-certificate-errors',
                '--disable-extensions'
            ]
        )
        
        context = await browser.new_context(user_agent=ua.random, viewport=viewport)
        
        # 3. Robust Cookie Injection
        try:
            cookie_raw = os.getenv("X_COOKIES")
            if not cookie_raw:
                print("❌ ERROR: X_COOKIES secret is empty!")
                return
            cookies = json.loads(cookie_raw)
            if not isinstance(cookies, list):
                print("❌ ERROR: Cookies must be a LIST (start with [).")
                return
            
            # Clean and Add
            await context.add_cookies(sanitize_cookies(cookies))
            print("✅ Cookies loaded & sanitized.")
        except json.JSONDecodeError:
            print("❌ ERROR: X_COOKIES is not valid JSON.")
            return
        except Exception as e:
            print(f"❌ Cookie Error: {e}")
            return

        page = await context.new_page()
        
        # 4. Human Navigation: Home -> Wait -> List
        try:
            print("📡 Navigating to Home Feed (Human Pattern)...")
            await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
            await human_delay(3, 6)
            
            # Check for Popups (e.g. "Dismiss")
            for btn in ["//span[text()='Got it']", "//span[text()='Dismiss']", "//div[@data-testid='app-bar-close']"]:
                if await page.locator(btn).is_visible():
                    await page.locator(btn).click()
                    await asyncio.sleep(1)

            if "login" in page.url:
                print("❌ Session Dead: Redirected to Login.")
                await page.screenshot(path="login_fail.png")
                return

            print("📡 Navigating to Target List...")
            await page.goto(LIST_URL, wait_until="domcontentloaded")
            await human_delay(2, 5)

        except Exception as e:
            print(f"⚠️ Navigation failed: {e}")
            await page.screenshot(path="nav_error.png")
            return

        # 5. Search for Tweets (Resilient Selectors)
        await page.mouse.wheel(0, random.randint(200, 500)) # Initial scroll
        await human_delay()

        selectors = ['article[data-testid="tweet"]', 'div[data-testid="cellInnerDiv"]']
        tweets = []
        for sel in selectors:
            found = await page.locator(sel).all()
            if len(found) > 0:
                tweets = found
                break
        
        if not tweets:
            print("📭 No tweets found.")
            await page.screenshot(path="debug_empty.png")
            return

        # 6. Target Selection (Skip top tweet sometimes)
        target_index = 0
        if len(tweets) > 1 and random.random() < 0.3:
            target_index = 1
            print("Skipping top tweet to look natural...")
        
        target_tweet = tweets[target_index]
        
        try:
            raw_text = await target_tweet.inner_text()
            if not raw_text.strip(): return
            
            post_id = raw_text.replace('\n', ' ')[:80] # Simple ID generation

            if not is_lurking and post_id not in seen_posts:
                print(f"🎯 Target Found: {post_id[:30]}...")
                
                await target_tweet.scroll_into_view_if_needed()
                await simulate_reading(page, target_tweet)
                
                reply_text = get_ai_reply(raw_text.replace('\n', ' '))
                
                if reply_text:
                    print(f"🧠 AI: {reply_text}")
                    
                    # Click Reply
                    await target_tweet.locator('[data-testid="reply"]').first.click()
                    await page.wait_for_selector('[data-testid="tweetTextarea_0"]', state="visible")
                    await human_delay(1.5, 3.5)
                    
                    # Type with Typos
                    await human_type(page, '[data-testid="tweetTextarea_0"]', reply_text)
                    await human_delay(1, 3)
                    
                    # Click Send
                    send_btn = page.locator('[data-testid="tweetButtonInline"]')
                    if not await send_btn.is_visible():
                         send_btn = page.locator('[data-testid="tweetButton"]')
                    
                    await send_btn.click()
                    print("✅ Sent.")
                    
                    # Update Memory
                    seen_posts[post_id] = "replied"
                    with open(SEEN_POSTS_FILE, 'w') as f: json.dump(seen_posts, f)
            else:
                print("⏭️ Tweet already seen or lurking.")

        except Exception as e:
            print(f"❌ Interaction Failed: {e}")
            await page.screenshot(path="interact_error.png")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_bot())
