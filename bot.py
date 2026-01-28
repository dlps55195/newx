import os
import json
import asyncio
import random
import re
import httpx
from fake_useragent import UserAgent
from playwright.async_api import async_playwright

# --- CONFIG ---
LIST_URL = "https://x.com/i/lists/2011289206513930641"
SEEN_POSTS_FILE = "seen_posts.json"
AI_API_KEY = os.getenv("AI_API_KEY")

# --- HUMAN BEHAVIOR ENGINES ---

async def human_delay(min_s=1.0, max_s=4.0):
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
        await asyncio.sleep(random.uniform(0.04, 0.15)) 
        
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
    """Generates a reply using the user's specific strategic prompt."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "HTTP-Referer": "https://github.com/newx",
        "Content-Type": "application/json"
    }
    
    # Your exact prompt formatted for the AI
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
            {"role": "user", "content": prompt} # Note: Sent as a single user message for direct instruction
        ]
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(url, headers=headers, json=payload, timeout=30.0)
            if response.status_code == 200:
                content = response.json()['choices'][0]['message']['content'].strip()
                
                # FINAL SAFETY CLEANUP: 
                # Removes labels like "WIT:", "FACT:", or "QUESTION:" if the AI ignores the prompt
                clean_content = re.sub(r'^(fact|question|wit|reply|response):\s*', '', content, flags=re.IGNORECASE)
                
                return clean_content.replace('"', '')
            return None
    except Exception as e:
        print(f"AI Error: {e}")
        return None

# --- MAIN BOT LOOP ---

async def run_bot():
    print("💓 Heartbeat: Checking schedule...")
    
    # 20% Chance to just "Lurk" (Log in, scroll, do nothing)
    # This builds a "Passive" history that X trusts.
    is_lurking = random.random() < 0.20
    if is_lurking: print("👀 Mode: Passive Lurking (No replies this run)")

    # Load Memory
    if not os.path.exists(SEEN_POSTS_FILE):
        seen_posts = {}
        with open(SEEN_POSTS_FILE, 'w') as f: json.dump({}, f)
    else:
        with open(SEEN_POSTS_FILE, 'r') as f: seen_posts = json.load(f)

    async with async_playwright() as p:
        ua = UserAgent()
        
        # 1. Randomized Viewport (Mobile vs Desktop sizes)
        viewport = random.choice([
            {'width': 1920, 'height': 1080},
            {'width': 1366, 'height': 768},
            {'width': 1440, 'height': 900},
            {'width': 375, 'height': 812} # Mobile-ish
        ])
        
        browser = await p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
        context = await browser.new_context(user_agent=ua.random, viewport=viewport)
        
        # Inject Cookies
        try:
            cookies = json.loads(os.getenv("X_COOKIES"))
            await context.add_cookies(cookies)
        except: 
            print("❌ Error: Cookies missing/invalid.")
            return

        page = await context.new_page()
        
        # 2. Navigate with "Load" wait (more human than networkidle)
        try:
            print("📡 Navigating to List...")
            await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(random.randint(5, 10))
        except: return

        # 3. Security Check
        if "login" in page.url:
            print("❌ Session Dead: Redirected to Login.")
            await page.screenshot(path="login_fail.png")
            return

        # 4. The "Search Pattern"
        # Humans don't see the top tweet immediately. We scroll a bit.
        await page.mouse.wheel(0, random.randint(200, 500))
        await human_delay()

        tweets = await page.locator('article[data-testid="tweet"]').all()
        
        if not tweets:
            print("📭 No tweets found.")
            await page.screenshot(path="debug_empty.png")
            return

        # 5. Pick a Target (Not always the first one!)
        # Sometimes skip the top tweet to look "picky"
        target_index = 0
        if len(tweets) > 1 and random.random() < 0.3:
            target_index = 1
            print("Skipping top tweet to look natural...")
        
        target_tweet = tweets[target_index]
        raw_text = await target_tweet.inner_text()
        post_id = raw_text.replace('\n', ' ')[:80]

        if not is_lurking and post_id not in seen_posts:
            print(f"🎯 Target Found: {post_id[:30]}...")
            
            # Scroll to it specifically
            await target_tweet.scroll_into_view_if_needed()
            await simulate_reading(page, target_tweet)
            
            # Generate Reply
            tweet_content = raw_text.replace('\n', ' ')
            reply_text = get_ai_reply(tweet_content)
            
            if reply_text:
                print(f"🧠 AI Thought: {reply_text}")
                
                # Click Reply
                await target_tweet.locator('[data-testid="reply"]').click()
                
                # Wait for box (with variability)
                await page.wait_for_selector('[data-testid="tweetTextarea_0"]', state="visible")
                await human_delay(1.5, 3.5)
                
                # 6. TYPE WITH TYPOS
                await human_type(page, '[data-testid="tweetTextarea_0"]', reply_text)
                
                # Final "Read over" pause
                await human_delay(1, 3)
                
                try:
                    await page.click('[data-testid="tweetButtonInline"]')
                    print("✅ Sent.")
                    seen_posts[post_id] = "replied"
                    with open(SEEN_POSTS_FILE, 'w') as f: json.dump(seen_posts, f)
                except:
                    # Fallback for different button types
                    await page.click('[data-testid="tweetButton"]')

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_bot())
