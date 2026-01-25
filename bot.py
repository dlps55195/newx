import os
import json
import asyncio
import random
from fake_useragent import UserAgent
from playwright.async_api import async_playwright
from google import genai
from google.genai import types

# --- CONFIGURATION ---
HANDLES = [
    "levelsio", "marclou", "tdinh_me", "yongfook", "dannypostma", 
    "SimonHoiberg", "tibo_maker", "ajlkn", "thepatwalls", "dvassallo", 
    "arvidkahl", "andreyazimov", "pietrobianchini", "dagorenouf", "mubashariqbal", 
    "sergiobeiraomar", "folbert", "lucas_perret", "johnrushx", "alexwestco", 
    "tonydinh", "kharkwal_gagan", "p_v_g_t", "SarthakSadh", "sveta_bay", 
    "KevonAS", "thisiskp_", "shashbag", "IndieJames_", "marckohlbrugge", 
    "bentossell", "nathanbarry", "robwalling", "liam_darby", "lucasbuiltit", 
    "theRealKSet", "IndiePaige", "shubham_upd", "damengchen", "philm_me", 
    "pborenstein", "mikerubini", "romansitko", "h_makadia", "jakobgreenfeld", 
    "justinjackson", "dru_riley", "monicalent", "petecodes", "jasonleow", 
    "nicoverbruggen", "vponamariov", "SaaS_Nico", "saas_guy", "IndieHacker_HQ", 
    "mrdanrowe", "shivam_shubham", "tudorbarbu", "dominik_sumer", "jake_prins", 
    "imkevinpy", "SaaS_Journal", "nico_jeannen", "thesamparr", "sarthakgh", 
    "ankitsaurav", "dabit3", "tallyforms", "the_yash_chavan", "paul_yacoubian", 
    "wwshaef", "tylermking", "rchase", "iammarcthomas", "gvrizzo", 
    "dsabar", "merott", "stephan_nasser", "jess_wallace_", "heyrobin_b", 
    "marcus_at_work", "shripad_dev", "v_p_s_g", "saas_mark", "solo_founder", 
    "bootstrapped_dev", "shippable_it", "shivam_dev", "indie_maker_max", "dev_solo_v", 
    "saas_growth_logs", "micro_saas_ceo", "build_in_pub_alex", "tom_jacquesson", "devan_s", 
    "marie_martens", "noah_bragg", "ch_daniel", "amar_ghose", "pete_codes"
] # Add your handles here
SEEN_POSTS_FILE = "seen_posts.json"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
COOKIES_JSON = os.getenv("X_COOKIES")
BATCH_SIZE = 3  # Check 3 accounts at the same time (Safe limit for free GitHub runners)

# Setup 2026 Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

def get_ai_reply(tweet_text):
    """Generates a reply using the stable Gemini 2.0 Flash."""
    try:
        prompt = f"Reply to this tweet as a helpful peer: '{tweet_text}'. Under 180 chars. No hashtags."
        response = client.models.generate_content(
            model='gemini-2.0-flash', 
            contents=prompt
        )
        return response.text.strip()
    except:
        return None

def sanitize_cookies(cookie_list):
    allowed = ["Strict", "Lax", "None"]
    for cookie in cookie_list:
        if "sameSite" in cookie:
            val = str(cookie["sameSite"]).capitalize()
            cookie["sameSite"] = val if val in allowed else "Lax"
    return cookie_list

async def process_handle(context, handle, seen_posts):
    """The worker function that checks a single handle."""
    page = await context.new_page()
    result = None
    
    try:
        # SPEED HACK: Block images, fonts, and media to load page instantly
        await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,mp4,mp3}", lambda route: route.abort())
        
        print(f"🔍 Checking @{handle}...")
        
        # STEALTH: Move mouse to look human
        await page.goto(f"https://x.com/{handle}", wait_until="domcontentloaded", timeout=30000)
        await page.mouse.move(random.randint(100, 500), random.randint(100, 500))
        
        # Trigger timeline load
        await page.evaluate("window.scrollTo(0, 500)")
        
        # Wait for tweet
        try:
            await page.wait_for_selector('article[data-testid="tweet"]', timeout=8000)
        except:
            print(f"   💨 @{handle} - No tweets found (Page load issues)")
            await page.close()
            return None

        # Extract text
        tweets = page.locator('article[data-testid="tweet"]')
        first_tweet = tweets.first
        tweet_text = await first_tweet.inner_text()
        clean_text = tweet_text.split('\n')[0][:50] # Just the ID/First line
        
        # Check Memory
        if handle not in seen_posts or seen_posts[handle] != clean_text:
            print(f"   ✨ NEW POST for @{handle}!")
            reply_content = get_ai_reply(await first_tweet.inner_text())
            
            if reply_content:
                # Interaction
                await first_tweet.locator('[data-testid="reply"]').click()
                await page.wait_for_selector('[data-testid="tweetTextarea_0"]')
                await page.fill('[data-testid="tweetTextarea_0"]', reply_content)
                
                # Human pause
                await asyncio.sleep(random.uniform(2, 4))
                
                # Robust Click
                await page.click('[data-testid="tweetButton"]')
                await page.wait_for_selector('[data-testid="tweetTextarea_0"]', state="hidden")
                
                print(f"   ✅ Replied to @{handle}")
                result = (handle, clean_text) # Return success data
    except Exception as e:
        print(f"   ⚠️ Error @{handle}: {str(e)[:50]}")
    finally:
        await page.close()
    
    return result

async def run_bot():
    if not COOKIES_JSON: return
    
    # STEALTH ARGS: Hide the "Automation" flags
    async with async_playwright() as p:
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
            device_scale_factor=1
        )
        
        # Stealth Script Injection (Removes "navigator.webdriver")
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        try:
            await context.add_cookies(sanitize_cookies(json.loads(COOKIES_JSON)))
        except: pass

        # Load Memory
        if os.path.exists(SEEN_POSTS_FILE):
            with open(SEEN_POSTS_FILE, 'r') as f:
                seen_posts = json.load(f)
        else:
            seen_posts = {}

        # BATCH PROCESSING
        # We split the list of handles into chunks of 3 and process them in parallel
        for i in range(0, len(HANDLES), BATCH_SIZE):
            batch = HANDLES[i:i + BATCH_SIZE]
            print(f"⚡ Processing Batch: {batch}")
            
            tasks = [process_handle(context, handle, seen_posts) for handle in batch]
            results = await asyncio.gather(*tasks)
            
            # Update memory with results
            for res in results:
                if res:
                    handle, post_id = res
                    seen_posts[handle] = post_id
            
            # Save immediately after every batch
            with open(SEEN_POSTS_FILE, 'w') as f:
                json.dump(seen_posts, f)
            
            # Sleep between batches to avoid Rate Limits
            await asyncio.sleep(random.randint(5, 10))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_bot())
