import os
import json
import time
import random
from playwright.sync_api import sync_playwright
import google.generativeai as genai

# --- CONFIGURATION ---
HANDLES = ["elonmusk", "GaryVee"] # Add your handles here
SEEN_POSTS_FILE = "seen_posts.json"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
COOKIES_JSON = os.getenv("X_COOKIES")

# Setup AI
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

def get_ai_reply(tweet_text):
    prompt = f"Write a short, engaging, and valuable reply to this tweet: '{tweet_text}'. Be human, avoid bot-like language, and keep it under 200 characters."
    response = model.generate_content(prompt)
    return response.text.strip()

def run_bot():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Load session
        context = browser.new_context()
        context.add_cookies(json.loads(COOKIES_JSON))
        
        # Load history
        if os.path.exists(SEEN_POSTS_FILE):
            with open(SEEN_POSTS_FILE, 'r') as f:
                seen_posts = json.load(f)
        else:
            seen_posts = {}

        for handle in HANDLES:
            print(f"Checking @{handle}...")
            page = context.new_page()
            page.goto(f"https://x.com/{handle}")
            
            # Wait for tweets to load
            page.wait_for_selector('[data-testid="tweet"]', timeout=10000)
            
            # Get the first tweet
            first_tweet = page.locator('[data-testid="tweet"]').first
            tweet_text = first_tweet.inner_text()
            # This is a simplified way to get a unique ID/link
            tweet_link = page.url 
            
            if handle not in seen_posts or seen_posts[handle] != tweet_text[:50]:
                print(f"New post found from {handle}!")
                
                # Generate Reply
                reply_text = get_ai_reply(tweet_text)
                
                # Click Reply Button
                first_tweet.locator('[data-testid="reply"]').click()
                page.wait_for_selector('[data-testid="tweetTextarea_0"]')
                
                # Type Reply with human delay
                page.fill('[data-testid="tweetTextarea_0"]', reply_text)
                time.sleep(random.uniform(2, 5))
                page.click('[data-testid="tweetButton"]')
                
                # Update History
                seen_posts[handle] = tweet_text[:50]
                print(f"Replied: {reply_text}")
            
            page.close()

        # Save history
        with open(SEEN_POSTS_FILE, 'w') as f:
            json.dump(seen_posts, f)
        
        browser.close()

if __name__ == "__main__":
    run_bot()
