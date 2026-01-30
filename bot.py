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

async def human_type(page, selector, text):
    await page.click(selector)
    for char in text:
        if random.random() < 0.03:
            await page.keyboard.press(random.choice('abcdefg'))
            await asyncio.sleep(0.2)
            await page.keyboard.press("Backspace")
        await page.keyboard.type(char)
        await asyncio.sleep(random.uniform(0.05, 0.12))

def get_ai_reply(tweet_text):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
    prompt = f"Casual X reply (max 15 words, lowercase) for: {tweet_text}. No labels. End WIT with ' lol'."
    try:
        with httpx.Client() as client:
            resp = client.post(url, headers=headers, json={"model": "google/gemini-2.0-flash-001", "messages": [{"role": "user", "content": prompt}]}, timeout=30.0)
            return resp.json()['choices'][0]['message']['content'].strip() if resp.status_code == 200 else None
    except: return None

async def run_bot():
    print("💓 Bot Start: Checking for fresh content...")
    
    # 1. Check AI Key
    if not AI_API_KEY:
        print("❌ CRITICAL: AI_API_KEY is missing from Secrets.")
        return

    # 2. Load Memory
    seen_posts = {}
    if os.path.exists(SEEN_POSTS_FILE):
        try:
            with open(SEEN_POSTS_FILE, 'r') as f: seen_posts = json.load(f)
        except: print("⚠️ Memory file corrupted, starting fresh.")

    async with async_playwright() as p:
        print("🌐 Launching Stealth Browser...")
        browser = await p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
        context = await browser.new_context(user_agent=UserAgent().random)
        
        # 3. Cookie Validation
        cookie_raw = os.getenv("X_COOKIES")
        if not cookie_raw:
            print("❌ CRITICAL: X_COOKIES is empty.")
            return
        await context.add_cookies(sanitize_cookies(json.loads(cookie_raw)))

        page = await context.new_page()
        
        # 4. Navigation Flow
        print(f"📡 Navigating to List: {LIST_URL}")
        await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5) # Allow dynamic content to load

        # 5. Freshness Filtering (5 Minutes)
        tweet_elements = await page.locator('article[data-testid="tweet"]').all()
        print(f"🔎 Found {len(tweet_elements)} total tweets on page.")
        
        candidates = []
        five_mins_ago = datetime.now(timezone.utc) - timedelta(minutes=5)

        for tweet in tweet_elements:
            try:
                time_tag = tweet.locator("time")
                if not await time_tag.count(): continue
                
                iso_time = await time_tag.get_attribute("datetime")
                tweet_time = datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
                
                if tweet_time > five_mins_ago:
                    text_content = (await tweet.inner_text()).replace('\n', ' ')
                    post_id = text_content[:80]
                    if post_id not in seen_posts:
                        candidates.append({"element": tweet, "text": text_content, "id": post_id})
            except: continue

        print(f"🎯 Candidates within 5-min window: {len(candidates)}")
        
        # 6. Execute up to 3 Replies
        for target in candidates[:3]:
            print(f"📝 Replying to: {target['id'][:40]}...")
            reply_text = get_ai_reply(target['text'])
            if not reply_text: continue

            try:
                await target['element'].locator('[data-testid="reply"]').first.click()
                await page.wait_for_selector('[data-testid="tweetTextarea_0"]', timeout=5000)
                await human_type(page, '[data-testid="tweetTextarea_0"]', reply_text)
                await page.click('[data-testid="tweetButtonInline"]')
                
                print(f"✅ Reply Sent: {reply_text}")
                seen_posts[target['id']] = True
                with open(SEEN_POSTS_FILE, 'w') as f: json.dump(seen_posts, f)
                await asyncio.sleep(random.uniform(5, 10))
            except Exception as e:
                print(f"⚠️ Interaction failed for one tweet: {e}")

        await browser.close()
        print("🏁 Run complete.")

if __name__ == "__main__":
    asyncio.run(run_bot())
