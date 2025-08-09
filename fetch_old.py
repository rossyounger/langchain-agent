import asyncio
import feedparser
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Optional
from playwright.async_api import async_playwright
import hashlib
import logging

logger = logging.getLogger(__name__)

@dataclass
class ContentItem:
    """Standardized content item from any source"""
    id: str
    source: str  # 'twitter', 'rss', 'email', 'web'
    source_url: str
    title: str
    content: str
    author: str
    published: datetime
    
    def __post_init__(self):
        # Generate unique ID if not provided
        if not self.id:
            content_hash = hashlib.md5(
                f"{self.source}{self.author}{self.title}{self.content}".encode()
            ).hexdigest()
            self.id = f"{self.source}_{content_hash[:10]}"

class TwitterFetcher:
    """Playwright-based Twitter scraper"""
    
    def __init__(self):
        self.browser = None
        self.context = None
    
    async def _init_browser(self):
        """Initialize browser with better anti-detection"""
        if self.browser is None:
            playwright = await async_playwright().start()
            self.browser = await playwright.chromium.launch(
                headless=False,  # Make visible for debugging
                args=[
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--disable-web-security',
                    '--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                ]
            )
            
            self.context = await self.browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1280, 'height': 720},
                extra_http_headers={
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
                }
            )
            
            await self.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            """)
    
    async def fetch_user_tweets(self, username: str, max_tweets: int = 20) -> List[ContentItem]:
        """Fetch tweets from a single user with better error handling"""
        await self._init_browser()
        page = await self.context.new_page()
        items = []
        
        try:
            print(f"Attempting to scrape @{username}...")
            
            # Try x.com first, then twitter.com
            urls_to_try = [f'https://x.com/{username}', f'https://twitter.com/{username}']
            
            page_loaded = False
            for url in urls_to_try:
                try:
                    print(f"Trying {url}...")
                    await page.goto(url, wait_until='domcontentloaded', timeout=15000)
                    page_loaded = True
                    break
                except Exception as e:
                    print(f"Failed to load {url}: {e}")
                    continue
            
            if not page_loaded:
                print(f"Could not load any URL for {username}")
                return items
            
            # Wait a bit for content to load
            await asyncio.sleep(3)
            
            # Try different selectors for tweets
            tweet_selectors = [
                '[data-testid="tweet"]',
                '[data-testid="tweetText"]',
                'article[data-testid="tweet"]',
                '[role="article"]'
            ]
            
            tweet_found = False
            for selector in tweet_selectors:
                try:
                    await page.wait_for_selector(selector, timeout=5000)
                    tweet_found = True
                    break
                except:
                    continue
            
            if not tweet_found:
                print(f"No tweets found for {username} - might need login or different approach")
                return items
            
            # Rest of the scraping logic stays the same...
            tweet_count = 0
            last_height = 0
            scroll_attempts = 0
            
            while tweet_count < max_tweets and scroll_attempts < 5:  # Reduced scrolls
                tweets = await page.query_selector_all('[data-testid="tweet"]')
                
                if not tweets:  # Try alternative selector
                    tweets = await page.query_selector_all('[role="article"]')
                
                for tweet in tweets:
                    if tweet_count >= max_tweets:
                        break
                    
                    try:
                        # Extract tweet text - try multiple approaches
                        text = ""
                        
                        # Try main tweet text selector
                        text_element = await tweet.query_selector('[data-testid="tweetText"]')
                        if text_element:
                            text = await text_element.inner_text()
                        else:
                            # Try alternative text extraction
                            text_elements = await tweet.query_selector_all('[lang]')
                            if text_elements:
                                for el in text_elements:
                                    el_text = await el.inner_text()
                                    if el_text and len(el_text) > 10:  # Reasonable length
                                        text = el_text
                                        break
                        
                        if not text or len(text.strip()) < 5:
                            continue
                        
                        # Create simplified content item
                        item = ContentItem(
                            id="",
                            source="twitter",
                            source_url=f"https://twitter.com/{username}",
                            title=f"Tweet by @{username}",
                            content=text,
                            author=username,
                            published=datetime.now()  # Use current time for now
                        )
                        
                        # Avoid duplicates
                        if not any(existing.content == text for existing in items):
                            items.append(item)
                            tweet_count += 1
                            print(f"Found tweet {tweet_count}: {text[:50]}...")
                            
                    except Exception as e:
                        continue
                
                if tweet_count >= max_tweets:
                    break
                
                # Scroll down
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await asyncio.sleep(2)
                
                new_height = await page.evaluate('document.body.scrollHeight')
                if new_height == last_height:
                    break
                last_height = new_height
                scroll_attempts += 1
                
        except Exception as e:
            print(f"Error scraping {username}: {e}")
        finally:
            await page.close()
        
        print(f"Successfully scraped {len(items)} tweets from @{username}")
        return items

    
    async def cleanup(self):
        """Clean up browser resources"""
        if self.browser:
            await self.browser.close()

class RSSFetcher:
    """RSS feed fetcher"""
    
    def fetch_feed_items(self, feed_url: str, max_items: int = 20) -> List[ContentItem]:
        """Fetch items from RSS feed"""
        items = []
        
        try:
            feed = feedparser.parse(feed_url)
            
            for i, entry in enumerate(feed.entries[:max_items]):
                # Parse date
                pub_date = datetime.now()
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    pub_date = datetime(*entry.published_parsed[:6])
                elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                    pub_date = datetime(*entry.updated_parsed[:6])
                
                # Extract content
                content = ""
                if hasattr(entry, 'content') and entry.content:
                    content = entry.content[0].value
                elif hasattr(entry, 'summary'):
                    content = entry.summary
                elif hasattr(entry, 'description'):
                    content = entry.description
                
                # Get author
                author = entry.author if hasattr(entry, 'author') else feed.feed.title
                
                item = ContentItem(
                    id="",
                    source="rss",
                    source_url=feed_url,
                    title=entry.title if hasattr(entry, 'title') else "",
                    content=content,
                    author=author,
                    published=pub_date
                )
                items.append(item)
                
        except Exception as e:
            logger.error(f"Error parsing RSS feed {feed_url}: {e}")
        
        return items

# Updated functions to maintain compatibility with your existing code
async def fetch_tweets(usernames=None, max_tweets=20):
    """Updated fetch_tweets function using Playwright"""
    usernames = usernames or ["paulg", "sama", "naval"]
    twitter_fetcher = TwitterFetcher()
    all_items = []
    
    try:
        for username in usernames:
            items = await twitter_fetcher.fetch_user_tweets(username, max_tweets)
            all_items.extend(items)
            await asyncio.sleep(1)  # Be nice to Twitter
    finally:
        await twitter_fetcher.cleanup()
    
    # Return just the content strings to maintain compatibility
    return [item.content for item in all_items]

async def fetch_all_sources(twitter_usernames=None, rss_feeds=None, max_per_source=20):
    """New function to fetch from multiple sources"""
    twitter_usernames = twitter_usernames or ["paulg", "sama", "naval"]
    rss_feeds = rss_feeds or []
    
    all_items = []
    
    # Fetch Twitter
    if twitter_usernames:
        twitter_fetcher = TwitterFetcher()
        try:
            for username in twitter_usernames:
                items = await twitter_fetcher.fetch_user_tweets(username, max_per_source)
                all_items.extend(items)
                await asyncio.sleep(1)
        finally:
            await twitter_fetcher.cleanup()
    
    # Fetch RSS
    if rss_feeds:
        rss_fetcher = RSSFetcher()
        for feed_url in rss_feeds:
            items = rss_fetcher.fetch_feed_items(feed_url, max_per_source)
            all_items.extend(items)
    
    return all_items

# Convenience function for async execution
def fetch_tweets_sync(usernames=None, max_tweets=20):
    """Synchronous wrapper for existing code compatibility"""
    return asyncio.run(fetch_tweets(usernames, max_tweets))

def fetch_all_sources_sync(twitter_usernames=None, rss_feeds=None, max_per_source=20):
    """Synchronous wrapper for multi-source fetching"""
    return asyncio.run(fetch_all_sources(twitter_usernames, rss_feeds, max_per_source))