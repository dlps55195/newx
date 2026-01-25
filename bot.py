import os
import json
import asyncio
import random
from fake_useragent import UserAgent
from playwright.async_api import async_playwright
from google import genai
from google.genai import types

# --- CONFIGURATION ---
LIST_URL = "https://x.com/i/lists/2011289206513930641"
SEEN_POSTS_FILE = "seen_posts.json"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
COOKIES_JSON = os.getenv("X_COOKIES")

# Use Gemini 2.0 Flash (Stable 2026)
client = genai.Client(api_key=GEMINI_API_KEY)

def get_ai_reply(tweet_text):
    """Generates a contextual reply using Gemini."""
    try:
        # Prompt engineered for short, casual, non-bot-like responses
        prompt = (
            f"Read this tweet: '{tweet_text}'. \n"
            "Write a reply that is: \n"
            "1. Casual and short (under 140 chars). \n"
            "2. Relevant to the topic. \n"
            "3. Sounds like a helpful peer, not a generic AI. \n"
            "4. Do NOT use hashtags."
        )
        response = client.models.generate_content(
            model='gemini-2.0-flash', 
            contents=prompt
        )
        return response.text.strip().replace('"', '')
    except Exception as e:
        print(f"      AI Error: {e}")
        return None

def sanitize_cookies(cookie_list):
    """Fixes cookie formatting for Playwright."""
    allowed = ["Strict", "Lax", "None"]
    for cookie in cookie_list:
        if "sameSite" in cookie:
            val = str(cookie["sameSite"]).capitalize()
            cookie["sameSite"] = val if val in allowed else "Lax"
    return cookie_list

async def run_bot():
    if not COOKIES_JSON:
        print("❌ Error: X_COOKIES environment variable is missing.")
        return

    # Load Memory (Seen Posts)
    if os.path.exists(SEEN_POSTS_FILE):
        with open(SEEN_POSTS_FILE, 'r') as f:
            try:
                seen_posts = json.load(f)
            except:
                seen_posts = {}
    else:
        seen_posts = {}

    async with async_playwright() as p:
        # --- STEALTH BROWSER SETUP ---
        ua = UserAgent()
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-infobars',
                '--window-size=1920,1080',
            ]
        )
        
        context = await browser.new_context(
            user_agent=ua.random,
            viewport={'width': 1920, 'height': 1080},
            device_scale_factor=1,
            locale='en-US'
        )
        
        # Inject script to hide "navigator.webdriver" property (Critical for X)
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        try:
            await context.add_cookies(sanitize_cookies(json.loads(COOKIES_JSON)))
        except Exception as e:
            print(f"❌ Cookie Error: {e}")
            return

        page = await context.new_page()

        # SPEED OPTIMIZATION: Block media to load page instantly
        await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,mp4,mp3,woff,woff2}", lambda route: route.abort())

        try:
            print(f"🚀 Loading List Feed...")
            await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=60000)
            
            # Small human-like mouse movement
            await page.mouse.move(random.randint(100, 500), random.randint(100, 500))
            
            # Scroll to trigger timeline loading
            await page.evaluate("window.scrollTo(0, 800)")
            await asyncio.sleep(3)

            # Wait for tweets to appear
            await page.wait_for_selector('article[data-testid="tweet"]', timeout=20000)
            
            # Get all visible tweets (Usually the top 5-10 most recent)
            tweets = await page.locator('article[data-testid="tweet"]').all()
            print(f"   found {len(tweets)} recent tweets in the list.")

            # Iterate through tweets
            for i, tweet in enumerate(tweets):
                try:
                    # Extract Tweet Text
                    tweet_text = await tweet.inner_text()
                    
                    # Generate a unique ID based on the text content (simple but effective)
                    # In a full app, we would scrape the data-tweet-id attribute, but this is safer for stealth
                    text_lines = tweet_text.split('\n')
                    clean_text = " ".join(text_lines)
                    short_id = clean_text[:60] # Use first 60 chars as ID
                    
                    # Try to find the handle (usually the 2nd line in inner_text, e.g., @elonmusk)
                    handle = "Unknown"
                    for line in text_lines:
                        if line.startswith("@"):
                            handle = line
                            break

                    print(f"   🔎 Checking tweet {i+1} from {handle}...")

                    if short_id not in seen_posts:
                        print(f"      ✨ NEW POST detected!")
                        
                        # Generate AI Reply
                        reply_content = get_ai_reply(clean_text)
                        
                        if reply_content:
                            print(f"      📝 AI wrote: {reply_content}")
                            
                            # Click Reply Icon (scoped to this specific tweet)
                            reply_button = tweet.locator('[data-testid="reply"]')
                            await reply_button.click()
                            
                            # Wait for the modal to open
                            await page.wait_for_selector('[data-testid="tweetTextarea_0"]', timeout=8000)
                            
                            # Type the reply (Human typing speed)
                            await page.fill('[data-testid="tweetTextarea_0"]', reply_content)
                            await asyncio.sleep(random.uniform(1.5, 3.5))
                            
                            # Click 'Reply' button in the modal
                            await page.click('[data-testid="tweetButton"]')
