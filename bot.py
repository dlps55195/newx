import os
import json
import time
import random
from playwright.sync_api import sync_playwright
from google.genai import Client  # Fixed Import logic

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

# Initialize Gemini 2.0 Client
client = Client(api_key=GEMINI_API_KEY)

def get_ai_reply(tweet_text):
    prompt = (
        f"Analyze this tweet: '{tweet_text}'. "
        "Write a short, meaningful, and valuable reply. "
        "Sound like a helpful peer, not a bot. Under 200 characters."
    )
    # Using the latest 2026 flash model
    response = client.models.generate_content(
        model='gemini-2.0-flash', 
        contents=prompt
    )
    return response.text.strip()

def sanitize_cookies(cookie_list):
    """Normalizes cookie attributes for Playwright compatibility."""
    allowed_samesite = ["Strict", "Lax", "None"]
    for cookie in cookie_list:
        if "sameSite" in cookie:
            val = str(cookie["sameSite"]).capitalize()
            cookie["sameSite"] = val if val in allowed_samesite else "Lax"
    return cookie_list

def run_bot():
    if not COOKIES_JSON:
        print("Missing X_COOKIES secret!")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # Load and fix cookies
        try:
            raw_cookies = json.loads(COOKIES_JSON)
            context.add_cookies(sanitize_cookies(raw_cookies))
        except Exception as e:
            print(f"Cookie Error: {e}")
            return

        # Load Memory
        if os.path.exists(SEEN_POSTS_FILE):
            with open(SEEN_POSTS_FILE, 'r') as f:
                seen_posts = json.load(f)
        else:
            seen_posts = {}

        for handle in HANDLES:
            print(f"Checking @{handle}...")
            page = context.new_page()
            try:
                page.goto(f"https://x.com/{handle}", wait_until="domcontentloaded")
                # Wait for the timeline to appear
                page.wait_for_selector('[data-testid="tweet"]', timeout=20000)
                
                # Grab the text of the most recent tweet
                first_tweet = page.locator('[data-testid="tweet"]').first
                tweet_text = first_tweet.inner_text()
                
                # Check if we've replied to this specific text before
                if handle not in seen_posts or seen_posts[handle] != tweet_text[:50]:
                    print(f"New content found for {handle}!")
                    reply_text = get_ai_reply(tweet_text)
                    
                    # Open reply box
                    first_tweet.locator('[data-testid="reply"]').click()
                    page.wait_for_selector('[data-testid="tweetTextarea_0"]')
                    
                    # Human-like typing delay
                    page.fill('[data-testid="tweetTextarea_0"]', reply_text)
                    time.sleep(random.uniform(2, 5))
                    
                    # Send
                    page.click('[data-testid="tweetButton"]')
                    print(f"Replied to {handle}: {reply_text}")
                    
                    # Record this post as seen
                    seen_posts[handle] = tweet_text[:50]
            except Exception as e:
                print(f"Error checking {handle}: {e}")
            finally:
                page.close()

        # Save memory back to repo
        with open(SEEN_POSTS_FILE, 'w') as f:
            json.dump(seen_posts, f)
        
        browser.close()

if __name__ == "__main__":
    run_bot()
