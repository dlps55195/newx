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

# --- HELPER FUNCTIONS ---

def sanitize_cookies(cookie_list):
    """Fixes 'SameSite' issues and removes junk."""
    cleaned = []
    allowed_samesite = ["Strict", "Lax", "None"]
    for cookie in cookie_list:
        if "sameSite" in cookie:
            if cookie["sameSite"] not in allowed_samesite:
                cookie["sameSite"] = "Lax"
        cookie.pop("hostOnly", None)
        cookie.pop("session", None)
        cleaned.append(cookie)
    return cleaned

async def human_delay(min_s=2.0, max_s=5.0):
    await asyncio.sleep(random.uniform(min_s, max_s))

async def human_type(page, selector, text):
    """Types with realistic speed, errors, and corrections."""
    await page.click(selector)
    for char in text:
        # 3% chance of typo
        if random.random() < 0.03:
            wrong_char = random.choice('abcdefghijklmnopqrstuvwxyz')
            await page.keyboard.press(wrong_char)
            await asyncio.sleep(random.uniform(0.1, 0.4))
            await page.keyboard.press("Backspace")
            await asyncio.sleep(random.uniform(0.1, 0.3))
        
        await page.keyboard.type(char)
        await asyncio.sleep(random.uniform(0.04, 0.12)) # Typing speed
        
        if char in ".,?! ":
            if random.random() < 0.2:
                await asyncio.sleep(random.uniform(0.5, 1.0)) # Thinking pause

async def simulate_reading(page, tweet_element):
    """Scrolls past the tweet to simulate reading."""
    box = await tweet_element.bounding_box()
    if box:
        await page.mouse.wheel(0, box['height'] + random.randint(100, 300))
        await human_delay(1, 2)
        await page.mouse.wheel(0, -random.randint(100, 200))

def get_ai_reply(tweet_text):
    """Generates a reply using your exact prompt."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "HTTP-Referer": "https://github.com/newx",
        "Content-Type": "application/json"
    }
    
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
  - do not write "fact:", "question:", or any style tag.  
  - QUESTION replies must end with a question mark.  
  - FACT replies must be concise and directly tied to the tweet's claim/context.    
  - WIT replies must include " lol" at the end.
  - if the tweet contains disallowed content you cannot engage with, reply with: "i can't reply to that." (all lowercase; counts toward 15 words).

INPUT: the variable contains the full text of the tweet to respond to.

OUTPUT: a single line — the reply text only, obeying every rule above.
"""
    try:
        with httpx.Client() as client:
            resp = client.post(url, headers=headers, json={"model": "google/gemini-2.0-flash-001", "messages": [{"role": "user", "content": prompt}]}, timeout=30.0)
            if resp.status_code == 200:
                content = resp.json()['choices'][0]['message']['content'].strip()
                clean_content = re.sub(r'^(fact|question|wit|reply|response|step 2):\s*', '', content, flags=re.IGNORECASE)
                return clean_content.replace('"', '')
            return None
    except Exception as e:
        print(f"⚠️ AI Error: {e}")
        return None

# --- MAIN BOT LOOP ---

async def run_bot():
    print("💓 Heartbeat: Checking schedule...")
    
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
        viewport = random.choice([
            {'width': 1920, 'height': 1080},
            {'width': 1366, 'height': 768},
            {'width': 375, 'height': 812}
        ])
        
        browser = await p.chromium.launch(
            headless=True, 
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-infobars', '--ignore-certificate-errors', '--disable-extensions']
        )
        context = await browser.new_context(user_agent=ua.random, viewport=viewport)
        
        try:
            cookie_raw = os.getenv("X_COOKIES")
            if not cookie_raw:
                print("❌ ERROR: X_COOKIES secret is empty!")
                return
            await context.add_cookies(sanitize_cookies(json.loads(cookie_raw)))
            print("✅ Cookies loaded.")
        except Exception as e:
            print(f"❌ Cookie Error: {e}")
            return

        page = await context.new_page()
        
        try:
            # 1. Human Navigation
            await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
            await human_delay(3, 5)
            
            # Dismiss Popups
            for btn in ["//span[text()='Got it']", "//span[text()='Dismiss']", "//div[@data-testid='app-bar-close']"]:
                if await page.locator(btn).is_visible():
                    await page.locator(btn).click()
            
            if "login" in page.url:
                print("❌ Session Dead: Login required.")
                return

            print("📡 Navigating to List...")
            await page.goto(LIST_URL, wait_until="domcontentloaded")
            await human_delay(3, 6)
            
            # 2. Scroll to load more tweets
            await page.mouse.wheel(0, 1000)
            await asyncio.sleep(2)
            await page.mouse.wheel(0, 500)
            await asyncio.sleep(2)

        except Exception as e:
            print(f"⚠️ Navigation failed: {e}")
            await page.screenshot(path="nav_error.png")
            return

        # 3. SCAN & FILTER TWEETS
        tweet_elements = await page.locator('article[data-testid="tweet"]').all()
        print(f"🔎 Scanned {len(tweet_elements)} tweets.")
