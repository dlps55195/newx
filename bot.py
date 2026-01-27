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
            {"role": "system", "content": "You are a casual peer on X. Give a short, 1-sentence reply. No hashtags, no corporate talk. Be chill. Lowercase is fine."},
            {"role": "user", "content": tweet_text}
        ]
    }
    try:
        with httpx.Client() as client:
            response = client.post(url, headers=headers, json=payload, timeout=30.0)
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content'].strip().replace('"', '')
            else:
                print(f"⚠️ AI Error: {response.status_code}")
                return None
    except Exception as e:
        print(f"⚠️ AI Exception: {e}")
        return None

def sanitize_cookies(cookie_list):
    allowed = ["Strict", "Lax", "None"]
    for cookie in cookie_list:
        if "sameSite" in cookie:
            val = str(cookie["sameSite"]).capitalize()
            cookie["sameSite"] = val if val in allowed else "Lax"
    return cookie_list

async def run_bot():
    # --- HEARTBEAT & STEALTH LOGIC ---
    print("💓 Heartbeat: Sniper Bot is awake and checking the schedule.")
    
    # 15% chance to just "lurk" and exit. 
    # This breaks the robotic pattern to avoid X's detection.
    if random.random() < 0.15:
        print("🤫 Stealth Mode: Lurking this round to stay under the radar. Exiting.")
        return

    # --- LOAD MEMORY ---
    if not os.path.exists(SEEN_POSTS_FILE):
        seen_posts = {}
        # Create the file if it doesn't exist so git can track it
        with open(SEEN_POSTS_FILE, 'w') as f:
            json.dump({}, f)
    else:
        with open(SEEN_POSTS_FILE, 'r') as f:
            try: 
                seen_posts = json.load(f)
            except: 
                seen_posts = {}

    async with async_playwright() as p:
        ua = UserAgent()
        # Headless mode ON for GitHub Actions
        browser = await p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
        context = await browser.new_context(user_agent=ua.random)
        
        # Stealth: Hide bot status
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        try:
            cookies = json.loads(os.getenv("X_COOKIES"))
            await context.add_cookies(sanitize_cookies(cookies))
        except: 
            print("❌ Error: X_COOKIES not found or invalid.")
            return

        page = await context.new_page()
        # Block images/fonts for speed
        await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,mp4,woff2}", lambda route: route.abort())

        print(f"📡 Scanning List for newest post...")
        
        try:
            # use 'networkidle' to wait until data actually loads
            await page.goto(LIST_URL, wait_until="networkidle", timeout=60000)
        except:
            print("⚠️ Page load timeout (network might be slow). Continuing anyway...")

        # --- JIGGLE SCROLL ---
        # Scroll down and up slightly to force X to render the "lazy" tweets
        await page.mouse.wheel(0, 600)
        await asyncio.sleep(2)
        await page.mouse.wheel(0, -600)
        await asyncio.sleep(2)

        # Get all tweets on the screen
        try:
            await page.wait_for_selector('article[data-testid="tweet"]', timeout=20000)
        except:
            print("📭 No tweets loaded. The list might be empty or restricted.")
            await browser.close()
            return

        tweets = await page.locator('article[data-testid="tweet"]').all()
        print(f"👀 Found {len(tweets)} tweets on screen.")
        
        target_tweet = None
        target_id = None

        # Find the FIRST tweet in the list that we haven't seen
        for tweet in tweets:
            try:
                full_text = await tweet.inner_text()
                # Create a UNIQUE ID based on Name + Handle + Content
                # This fixes the bug where "Elon Musk" was the only ID
                clean_text = full_text.replace('\n', ' ').strip()
                post_id = clean_text[:80] # First 80 chars includes Name + Handle + Start of tweet

                if post_id not in seen_posts:
                    print(f"🎯 Sniper Target Found: {post_id[:30]}...")
                    target_tweet = tweet
                    target_id = post_id
                    break # Stop looking, we found the newest one
            except:
                continue

        if target_tweet:
            # Generate AI Reply
            tweet_content_for_ai = (await target_tweet.inner_text()).replace('\n', ' ')
            reply_content = get_ai_reply(tweet_content_for_ai)
            
            if reply_content:
                print(f"✍️ Replying: {reply_content}")
                
                try:
                    # Click Reply
                    reply_button = target_tweet.locator('[data-testid="reply"]')
                    await reply_button.click()
                    
                    # Wait for text box
                    await page.wait_for_selector('[data-testid="tweetTextarea_0"]', timeout=10000)
                    
                    # Human typing simulation
                    for char in reply_content:
                        await page.type('[data-testid="tweetTextarea_0"]', char, delay=random.randint(40, 100))
                    
                    await asyncio.sleep(2)
                    
                    # Click Tweet
                    try:
                        await page.click('[data-testid="tweetButtonInline"]', timeout=3000)
                    except:
                        await page.click('[data-testid="tweetButton"]')
                    
                    # Wait for success (box disappears)
                    await page.wait_for_selector('[data-testid="tweetTextarea_0"]', state="hidden", timeout=10000)
                    print("✅ Sniper Mission Complete.")
                    
                    # Update memory
                    seen_posts[target_id] = "replied"
                    with open(SEEN_POSTS_FILE, 'w') as f:
                        json.dump(seen_posts, f)
                except Exception as e:
                    print(f"❌ Error during reply action: {e}")

        else:
            print("📭 Verified: No new tweets found in this scan.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_bot())
