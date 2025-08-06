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
        """Initialize browser with anti-detection"""
        if self.browser is None:
            playwright = await async_playwright().start()
            self.browser = await playwright.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
            )
            
            self.context = await self.browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1280, 'height': 720}
            )
            
            await self.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            """)
    
    async def fetch_user_tweets(self, username: str, max_tweets: int = 20) -> List[ContentItem]:
        """Fetch tweets from a single user"""
        await self._init_browser()
        page = await self.context.new_page()
        items = []
        
        try:
            await page.goto(f'https://twitter.com/{username}', wait_until='networkidle')
            await page.wait_for_selector('[data-testid="tweet"]', timeout=10000)
            
            tweet_count = 0
            last_height = 0
            scroll_attempts = 0
            
            while tweet_count < max_tweets and scroll_attempts < 10:
                tweets = await page.query_selector_all('[data-testid="tweet"]')
                
                for tweet in tweets:
                    if tweet_count >= max_tweets:
                        break
                    
                    try:
                        # Extract tweet text
                        text_element = await tweet.query_selector('[data-testid="tweetText"]')
                        if not text_element:
                            continue
                            
                        text = await text_element.inner_text()
                        if not text or len(text.strip()) == 0:
                            continue
                        
                        # Get timestamp
                        time_element = await tweet.query_selector('time')
                        datetime_str = await time_element.get_attribute('datetime') if time_element else None
                        tweet_date = datetime.now()
                        
                        if datetime_str:
                            try:
                                tweet_date = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
                            except:
                                pass
                        
                        # Create content item
                        item = ContentItem(
                            id="",  # Will be auto-generated
                            source="twitter",
                            source_url=f"https://twitter.com/{username}",
                            title=f"Tweet by @{username}",
                            content=text,
                            author=username,
                            published=tweet_date
                        )
                        
                        # Avoid duplicates
                        if not any(existing.content == text for existing in items):
                            items.append(item)
                            tweet_count += 1
                            
                    except Exception as e:
                        logger.error(f"Error extracting tweet: {e}")
                        continue
                
                # Scroll down
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await asyncio.sleep(2)
                
                new_height = await page.evaluate('document.body.scrollHeight')
                if new_height == last_height:
                    break
                last_height = new_height
                scroll_attempts += 1
                
        except Exception as e:
            logger.error(f"Error scraping {username}: {e}")
        finally:
            await page.close()
        
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