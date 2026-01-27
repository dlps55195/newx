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
AI_API_KEY = os.getenv("AI_API_KEY") 

def get_ai_reply(tweet_text):
    """Generates a strategic reply: Educational, Engagement, or Humor."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "HTTP-Referer": "https://github.com/newx",
        "Content-Type": "application/json"
    }
    
    system_content = (
        "You are a strategic X growth expert. Analyze the tweet and choose the BEST response style:\n"
        "1. EDUCATIONAL: If the tweet is informative, add a tiny helpful tip or fact.\n"
        "2. ENGAGEMENT: If it's an opinion, ask a short, sharp question to get the author to reply.\n"
        "3. HUMOR: If it's casual or a meme, be witty, sarcastic, or chill.\n\n"
        "RULES:\n"
        "- 1 sentence only.\n"
        "- DO NOT include the category name (like 'Educational:' or 'Humor:') in your reply.\n"
        "- No hashtags, no corporate jargon, no emojis (unless ironic).\n"
        "- Use lowercase if it feels more natural.\n"
        "- Be authentic, like a real person in the conversation."
    )
    
    payload = {
        "model": "google/gemini-2.0-flash-001",
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": f"Tweet Content: {tweet_text}"}
        ]
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(url, headers=headers, json=payload, timeout=30.0)
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content'].strip().replace('"', '')
            return None
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
    print("💓 Heartbeat: Sniper Bot is awake.")
    
    # 15% Stealth Lurk
    if random.random() < 0.15:
        print("🤫 Stealth Mode: Lurking. Exiting.")
        return

    # --- LOAD MEMORY ---
    if not os.path.exists(SEEN_POSTS_FILE):
        seen_posts = {}
        with open(SEEN_POSTS_FILE, 'w') as f:
            json.dump({}, f)
    else:
        with open(SEEN_POSTS_FILE, 'r') as f:
            try: seen_posts = json.load(f)
            except: seen_posts = {}

    async with async_playwright() as p:
        ua = UserAgent()
        browser = await p.chromium.launch(headless=True, args=[
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox'
        ])
        
        context = await browser.new_context(
            user_agent=ua.random,
            viewport={'width': 1280, 'height': 720}
        )
        
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        try:
            cookies = json.loads(os.getenv("X_COOKIES"))
            await context.add_cookies(sanitize_cookies(cookies))
        except Exception as e: 
            print(f"❌ Error: X_COOKIES invalid: {e}")
            return

        page = await context.new_page()
        # Block heavy media to save GitHub bandwidth
        await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,mp4,woff2}", lambda route: route.abort())

        print(f"📡 Navigating to List...")
        try:
            await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(7) # Critical for X's heavy JS
        except Exception as e:
            print(f"⚠️ Navigation failed: {e}")

        # --- DIAGNOSTICS ---
        current_url = page.url
        print(f"📍 Bot is currently at: {current_url}")
        
        if "login" in current_url:
            print("❌ SESSION EXPIRED: X redirected to login. Refresh your cookies!")
            await page.screenshot(path="login_wall.png")
            await browser.close()
            return

        # --- JIGGLE SCROLL ---
        await page.mouse.wheel(0, 500)
        await asyncio.sleep(2)
        await page.mouse.wheel(0, -500)
        await asyncio.sleep(3)

        # --- MULTI-SELECTOR SEARCH ---
        selectors = [
            'article[data-testid="tweet"]',
            'div[data-testid="cellInnerDiv"]',
            '[role="article"]'
        ]
        
        tweets = []
        for selector in selectors:
            found = await page.locator(selector).all()
            if len(found) > 0:
                tweets = found
                print(f"✅ Found {len(tweets)} elements using selector: {selector}")
                break

        if not tweets:
            print("📭 Truly no tweets found. Taking screenshot...")
            await page.screenshot(path="no_tweets_debug.png")
            await browser.close()
            return

        # --- SNIPER LOGIC ---
        target_tweet = None
        target_id = None

        for tweet in tweets:
            try:
                raw_text = await tweet.inner_text()
                if not raw_text.strip(): continue
                
                # UNIQUE ID: Handle + first bit of text
                clean_text = raw_text.replace('\n', ' ').strip()
                post_id = clean_text[:100]

                if post_id not in seen_posts:
                    print(f"🎯 Target Acquired: {post_id[:40]}...")
                    target_tweet = tweet
                    target_id = post_id
                    break
            except: continue

        if target_tweet:
            tweet_content = (await target_tweet.inner_text()).replace('\n', ' ')
            reply_text = get_ai_reply(tweet_content)
            
            if reply_text:
                print(f"✍️ Strategic Reply: {reply_text}")
                try:
                    await target_tweet.locator('[data-testid="reply"]').click()
                    await page.wait_for_selector('[data-testid="tweetTextarea_0"]', timeout=10000)
                    
                    for char in reply_text:
                        await page.type('[data-testid="tweetTextarea_0"]', char, delay=random.randint(40, 100))
                    
                    await asyncio.sleep(2)
                    try:
                        await page.click('[data-testid="tweetButtonInline"]', timeout=3000)
                    except:
                        await page.click('[data-testid="tweetButton"]')
                    
                    await page.wait_for_selector('[data-testid="tweetTextarea_0"]', state="hidden", timeout=10000)
                    print("✅ Sniper Mission Complete.")
                    
                    seen_posts[target_id] = "replied"
                    with open(SEEN_POSTS_FILE, 'w') as f:
                        json.dump(seen_posts, f)
                except Exception as e:
                    print(f"❌ Action failed: {e}")
                    await page.screenshot(path="action_error.png")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_bot())
