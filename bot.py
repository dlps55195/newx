import os
import json
import time
import random
from playwright.sync_api import sync_playwright
from google import genai

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

# Setup Modern Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

def get_ai_reply(tweet_text):
    prompt = f"Write a short, engaging, and valuable reply to this tweet: '{tweet_text}'. Be human, avoid bot-like language, and keep it under 200 characters."
    response = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
    return response.text.strip()

def sanitize_cookies(cookie_list):
    """Fixes the 'Strict|Lax|None' error by normalizing sameSite values."""
    allowed = ["Strict", "Lax", "None"]
    for cookie in cookie_list:
        if "sameSite" in cookie:
            # Capitalize first letter (e.g., 'lax' -> 'Lax')
            val = str(cookie["sameSite"]).capitalize()
            cookie["sameSite"] = val if val in allowed else "Lax"
    return cookie_list

def run_bot():
    if not COOKIES_JSON:
        print("Error: X_COOKIES secret is missing!")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # Apply Sanitized Cookies
        raw_cookies = json.loads(COOKIES_JSON)
        context.add_cookies(sanitize_cookies(raw_cookies))
        
        # Load memory
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
                page.wait_for_selector('[data-testid="tweet"]', timeout=15000)
                
                first_tweet = page.locator('[data-testid="tweet"]').first
                tweet_text = first_tweet.inner_text()
                
                # Check if this is a new post
                if handle not in seen_posts or seen_posts[handle] != tweet_text[:50]:
                    print(f"New post found!")
                    reply_text = get_ai_reply(tweet_text)
                    
                    # Interaction
                    first_tweet.locator('[data-testid="reply"]').click()
                    page.wait_for_selector('[data-testid="tweetTextarea_0"]')
                    page.fill('[data-testid="tweetTextarea_0"]', reply_text)
                    
                    time.sleep(random.uniform(2, 4)) # Human-like pause
                    page.click('[data-testid="tweetButton"]')
                    
                    seen_posts[handle] = tweet_text[:50]
                    print(f"Replied to @{handle}")
            except Exception as e:
                print(f"Skipping @{handle} due to error: {e}")
            finally:
                page.close()

        # Save memory back to file
        with open(SEEN_POSTS_FILE, 'w') as f:
            json.dump(seen_posts, f)
        
        browser.close()

if __name__ == "__main__":
    run_bot()
