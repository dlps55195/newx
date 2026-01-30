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
            await asyncio.sleep(0.15)
            await page.keyboard.press("Backspace")
        await page.keyboard.type(char)
        await asyncio.sleep(random.uniform(0.04, 0.10))

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
    if not AI_API_KEY:
        print("❌ CRITICAL: AI_API_KEY is missing.")
        return

    seen_posts = {}
    if os.path.exists(SEEN_POSTS_FILE):
        try:
            with open(SEEN_POSTS_FILE, 'r') as f: seen_posts = json.load(f)
        except: pass

    async with async_playwright() as p:
        print("🌐 Launching Stealth Browser...")
        browser = await p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled', '--no-sandbox'])
        context = await browser.new_context(user_agent=UserAgent().random, viewport={'width': 1280, 'height': 800})
        
        cookie_raw = os.getenv("X_COOKIES")
        if not cookie_raw:
            print("❌ CRITICAL: X_COOKIES is empty.")
            return
        await context.add_cookies(sanitize_cookies(json.loads(cookie_raw)))

        page = await context.new_page()
        print(f"📡 Navigating to List: {LIST_URL}")
        await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(6) 

        # Scan and filter
        tweet_elements = await page.locator('article[data-testid="tweet"]').all()
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

        print(f"🎯 Candidates found: {len(candidates)}")
        
        for target in candidates[:3]:
            print(f"📝 Target: {target['id'][:30]}...")
            reply_text = get_ai_reply(target['text'])
            if not reply_text: continue

            try:
                # 1. Click Reply Icon
                reply_icon = target['element'].locator('[data-testid="reply"]')
                await reply_icon.first.click(timeout=5000)
                
                # 2. Find and Type in Textarea
                textarea = page.locator('[data-testid="tweetTextarea_0"]')
                await textarea.wait_for(state="visible", timeout=7000)
                await human_type(page, '[data-testid="tweetTextarea_0"]', reply_text)
                await asyncio.sleep(1)

                # 3. Resilient Send Logic
                # Tries both 'Inline' and standard 'Tweet' button labels
                send_selectors = [
                    '[data-testid="tweetButtonInline"]', 
                    '[data-testid="tweetButton"]',
                    '//span[text()="Reply"]/ancestor::div[@role="button"]',
                    '//span[text()="Post"]/ancestor::div[@role="button"]'
                ]
                
                for selector in send_selectors:
                    btn = page.locator(selector)
                    if await btn.is_visible():
                        await btn.click()
                        print(f"✅ Reply Sent: {reply_text}")
                        seen_posts[target['id']] = True
                        with open(SEEN_POSTS_FILE, 'w') as f: json.dump(seen_posts, f)
                        break
                
                await asyncio.sleep(random.uniform(5, 8))
            except Exception as e:
                print(f"⚠️ Interaction failed: {e}")
                await page.keyboard.press("Escape") # Clear modal

        await browser.close()
        print("🏁 Run complete.")

if __name__ == "__main__":
    asyncio.run(run_bot())
