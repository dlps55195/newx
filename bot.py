importimport os
import json
import time
import random
from playwright.sync_api import sync_playwright
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

# Initialize the Free Gemini 1.5 Flash Client
client = genai.Client(api_key=GEMINI_API_KEY)

def get_ai_reply(tweet_text):
    """Generates a reply using the free, high-rate-limit Gemini model."""
    prompt = (
        f"You are a helpful, witty social media user. Read this tweet: '{tweet_text}'. "
        "Draft a genuine, non-robotic reply that adds value. "
        "Keep it under 240 characters. No hashtags."
    )
    
    # gemini-1.5-flash is free and fast
    response = client.models.generate_content(
        model='gemini-1.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.7 # varied and creative
        )
    )
    return response.text.strip()

def sanitize_cookies(cookie_list):
    """Fixes the 'Strict/Lax/None' error for Playwright."""
    allowed = ["Strict", "Lax", "None"]
    for cookie in cookie_list:
        if "sameSite" in cookie:
            # Capitalize properly (e.g., 'lax' -> 'Lax')
            val = str(cookie["sameSite"]).capitalize()
            cookie["sameSite"] = val if val in allowed else "Lax"
    return cookie_list

def run_bot():
    if not COOKIES_JSON:
        print("❌ Error: X_COOKIES Secret is missing.")
        return

    with sync_playwright() as p:
        # Launch browser invisibly
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # Load and fix cookies
        try:
            raw_cookies = json.loads(COOKIES_JSON)
            context.add_cookies(sanitize_cookies(raw_cookies))
        except Exception as e:
            print(f"❌ Cookie Error: {e}")
            return

        # Load "Memory" of past replies
        if os.path.exists(SEEN_POSTS_FILE):
            try:
                with open(SEEN_POSTS_FILE, 'r') as f:
                    seen_posts = json.load(f)
            except:
                seen_posts = {}
        else:
            seen_posts = {}

        # Scan all creators
        for handle in HANDLES:
            print(f"🔍 Checking @{handle}...")
            page = context.new_page()
            try:
                # Fast-load strategy
                page.goto(f"https://x.com/{handle}", wait_until="domcontentloaded")
                
                # Wait up to 10s for tweets to appear
                try:
                    page.wait_for_selector('[data-testid="tweet"]', timeout=10000)
                except:
                    print(f"   -> No tweets found/Timeline didn't load for {handle}")
                    page.close()
                    continue

                # Get the newest tweet
                first_tweet = page.locator('[data-testid="tweet"]').first
                tweet_text = first_tweet.inner_text().replace('\n', ' ')
                
                # Create a simple unique ID from the text (first 50 chars)
                tweet_id = tweet_text[:50]

                # If this is a NEW post we haven't replied to yet:
                if handle not in seen_posts or seen_posts[handle] != tweet_id:
                    print(f"   ✨ New Post Detected!")
                    
                    # 1. Generate AI Reply
                    reply_text = get_ai_reply(tweet_text)
                    
                    # 2. Click Reply
                    first_tweet.locator('[data-testid="reply"]').click()
                    page.wait_for_selector('[data-testid="tweetTextarea_0"]')
                    
                    # 3. Type & Send
                    page.fill('[data-testid="tweetTextarea_0"]', reply_text)
                    time.sleep(random.uniform(2, 5)) # Human pause
                    page.click('[data-testid="tweetButton"]')
                    
                    print(f"   ✅ Sent: {reply_text}")
                    
                    # 4. Save to memory
                    seen_posts[handle] = tweet_id
                else:
                    print(f"   (Already replied to latest)")

            except Exception as e:
                print(f"   ⚠️ Error processing {handle}: {e}")
            finally:
                page.close()
                time.sleep(2) # Brief pause between profiles

        # Save Updated Memory
        with open(SEEN_POSTS_FILE, 'w') as f:
            json.dump(seen_posts, f)
        
        browser.close()

if __name__ == "__main__":
    run_bot()
