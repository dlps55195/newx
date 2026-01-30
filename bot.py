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

async def force_click(page, selector):
    """Bypasses 'intercepted pointer events' by forcing the click action."""
    try:
        element = page.locator(selector).first
        await element.scroll_into_view_if_needed()
        # force=True ignores invisible layers sitting on top of the button
        await element.click(force=True, timeout=5000)
    except:
        # Final fallback: Click via JavaScript injection
        await page.evaluate(f'document.querySelector("{selector}").click()')

async def human_type(page, selector, text):
    # We use force=True here too because the textarea was 'intercepted' in your logs
    await page.locator(selector).click(force=True)
    for char in text:
        await page.keyboard.type(char)
        await asyncio.sleep(random.uniform(0.04, 0.08))

def get_ai_reply(tweet_text):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
    prompt = f"Reply to: {tweet_text}. Max 15 words, lowercase. Wit ends in ' lol'. Reply text only."
    try:
        with httpx.Client() as client:
            resp = client.post(url, headers=headers, json={"model": "google/gemini-2.0-flash-001", "messages": [{"role": "user", "content": prompt}]}, timeout=30.0)
            return re.sub(r'^(fact|question|wit|reply):\s*', '', resp.json()['choices'][0]['message']['content'].strip(), flags=re.IGNORECASE).replace('"', '')
    except: return None

async def run_bot():
    print("💓 Bot Start: Monitoring feed...")
    seen_posts = {}
    if os.path.exists(SEEN_POSTS_FILE):
        try:
            with open(SEEN_POSTS_FILE, 'r') as f: seen_posts = json.load(f)
        except: pass

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled', '--no-sandbox'])
        context = await browser.new_context(user_agent=UserAgent().random, viewport={'width': 1280, 'height': 800})
        
        try:
            cookie_raw = os.getenv("X_COOKIES")
            await context.add_cookies(sanitize_cookies(json.loads(cookie_raw)))
        except: return

        page = await context.new_page()
        print(f"📡 Loading List...")
        await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)

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
            print(f"📝 Attempting: {target['id'][:30]}...")
            reply_text = get_ai_reply(target['text'])
            if not reply_text: continue

            try:
                # 1. Open Reply Modal
                reply_btn = target['element'].locator('[data-testid="reply"]').first
                await reply_btn.click(force=True)
                
                # 2. Type Reply
                textarea = page.locator('[data-testid="tweetTextarea_0"]')
                await textarea.wait_for(state="visible", timeout=10000)
                await human_type(page, '[data-testid="tweetTextarea_0"]', reply_text)
                await asyncio.sleep(1)

                # 3. Send (Trying Force Click then Control+Enter)
                sent = False
                for sel in ['[data-testid="tweetButtonInline"]', '[data-testid="tweetButton"]']:
                    btn = page.locator(sel).first
                    if await btn.is_visible():
                        await btn.click(force=True)
                        sent = True
                        break
                
                if not sent:
                    # Backup: Press Ctrl + Enter to post
                    await page.keyboard.press("Control+Enter")
                
                # 4. Verify
                try:
                    await page.wait_for_selector('[data-testid="tweetTextarea_0"]', state="hidden", timeout=10000)
                    print(f"✅ Verified: {reply_text}")
                    seen_posts[target['id']] = True
                    with open(SEEN_POSTS_FILE, 'w') as f: json.dump(seen_posts, f)
                except:
                    print("❌ Could not verify post sent.")
                
                await asyncio.sleep(random.uniform(10, 15))

            except Exception as e:
                print(f"⚠️ Loop Error: {e}")
                await page.keyboard.press("Escape")

        await browser.close()
        print("🏁 Run complete.")

if __name__ == "__main__":
    asyncio.run(run_bot())
