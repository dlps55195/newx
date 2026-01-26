import os
import json
import asyncio
import random
import httpx
from fake_useragent import UserAgent
from playwright.async_api import async_playwright

# --- CONFIG ---
LIST_URL = "https://x.com/i/lists/2011289206513930641"
SEEN_POSTS_FILE = "seen_posts.json"
AI_API_KEY = os.getenv("AI_API_KEY") # OpenRouter Key

def get_ai_reply(tweet_text):
    """Generates a reply via OpenRouter (Gemini 2.0 Flash Free)."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "HTTP-Referer": "https://github.com/newx",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "google/gemini-2.0-flash-001",
        "messages": [
            {"role": "system", "content": "You are a casual peer on X. Give a short, 1-sentence reply. No hashtags, no corporate talk. Be chill."},
            {"role": "user", "content": tweet_text}
        ]
    }
    try:
        with httpx.Client() as client:
            response = client.post(url, headers=headers, json=payload, timeout=30.0)
            return response.json()['choices'][0]['message']['content'].strip().replace('"', '')
    except:
        return None

def sanitize_cookies(cookie_list):
    allowed = ["Strict", "Lax", "None"]
    for cookie in cookie_list:
        if "sameSite" in cookie:
            val = str(cookie["sameSite"]).capitalize()
            cookie["sameSite"] = val if val in allowed else "Lax"
    return cookie_list

async def run_bot():
    if not os.path.exists(SEEN_POSTS_FILE):
        seen_posts = {}
    else:
        with open(SEEN_POSTS_FILE, 'r') as f:
            try: seen_posts = json.load(f)
            except: seen_posts = {}

    async with async_playwright() as p:
        ua = UserAgent()
        browser = await p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
        context = await browser.new_context(user_agent=ua.random)
        
        # Stealth: Hide bot status
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        try:
            cookies = json.loads(os.getenv("X_COOKIES"))
            await context.add_cookies(sanitize_cookies(cookies))
        except: return

        page = await context.new_page()
        # Block images for speed
        await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,mp4,woff2}", lambda route: route.abort())

        print(f"📡 Scanning List for newest post...")
        await page.goto(LIST_URL, wait_until="domcontentloaded")
        await asyncio.sleep(4) # Wait for JS to render tweets

        # Get all tweets on the screen
        tweets = await page.locator('article[data-testid="tweet"]').all()
        
        target_tweet = None
        target_id = None

        # Find the FIRST tweet in the list that we haven't seen
        for tweet in tweets:
            tweet_text = await tweet.inner_text()
            # Unique ID based on the first 60 chars of the post
            post_id = tweet_text.split('\n')[0][:60] 

            if post_id not in seen_posts:
                print(f"🎯 Sniper Target Found: {post_id[:30]}...")
                target_tweet = tweet
                target_id = post_id
                break # Stop looking, we found the newest one

        if target_tweet:
            reply_content = get_ai_reply(await target_tweet.inner_text())
            if reply_content:
                print(f"✍️ Replying: {reply_content}")
                await target_tweet.locator('[data-testid="reply"]').click()
                await page.wait_for_selector('[data-testid="tweetTextarea_0"]')
                
                # Human typing
                for char in reply_content:
                    await page.type('[data-testid="tweetTextarea_0"]', char, delay=random.randint(40, 100))
                
                await asyncio.sleep(2)
                try:
                    await page.click('[data-testid="tweetButtonInline"]', timeout=3000)
                except:
                    await page.click('[data-testid="tweetButton"]')
                
                # Wait for success
                await page.wait_for_selector('[data-testid="tweetTextarea_0"]', state="hidden")
                print("✅ Sniper Mission Complete.")
                
                # Update memory
                seen_posts[target_id] = "replied"
                with open(SEEN_POSTS_FILE, 'w') as f:
                    json.dump(seen_posts, f)
        else:
            print("📭 No new tweets found since last scan.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_bot())
