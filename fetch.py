"""
Enhanced fetch.py with Supabase integration and intelligent content processing
This version stores everything in your database and enables smart filtering
"""

import asyncio
import feedparser
import asyncpg
from pgvector.asyncpg import register_vector
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from playwright.async_api import async_playwright
import hashlib
import logging
import os
import json
from dotenv import load_dotenv
from openai import AsyncOpenAI
from enum import Enum

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ContentCategory(Enum):
    """Content categories for intelligent filtering"""
    TECH_AI = "tech_ai"
    CRYPTO = "crypto"
    POLITICS = "politics"
    REGULATION = "regulation"
    JOURNALISM = "journalism"
    BUSINESS = "business"
    PERSONAL = "personal"

@dataclass
class FetcherConfig:
    """Configuration for fetchers"""
    headless: bool = True
    max_concurrent: int = 3
    request_delay: float = 1.0
    browser_timeout: int = 15000
    max_scroll_attempts: int = 8
    max_retries: int = 2

@dataclass
class EnhancedContentItem:
    """Enhanced content item with database integration"""
    id: str
    source: str  
    source_url: str
    title: str
    content: str
    author: str
    published: datetime
    
    # Enhanced categorization
    primary_category: Optional[ContentCategory] = None
    secondary_categories: List[ContentCategory] = field(default_factory=list)
    auto_tags: List[str] = field(default_factory=list)
    
    # Content characteristics
    content_type: str = "short"  # "short", "medium", "long"
    word_count: int = 0
    reading_time_minutes: int = 1
    
    # AI-generated data (will be populated)
    embedding: Optional[List[float]] = None
    relevance_score: float = 0.5
    complexity_score: float = 0.5
    sentiment: Optional[str] = None
    
    # Source-specific metadata
    source_metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Timestamps
    scraped_at: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        """Generate ID and calculate basic metrics"""
        if not self.id:
            content_hash = hashlib.md5(
                f"{self.source}{self.author}{self.content}".encode()
            ).hexdigest()
            self.id = f"{self.source}_{self.author}_{content_hash[:8]}"
        
        # Calculate word count and reading time
        if not self.word_count:
            self.word_count = len(self.content.split())
        
        if not self.reading_time_minutes or self.reading_time_minutes == 1:
            self.reading_time_minutes = max(1, self.word_count // 200)
        
        # Determine content type
        if self.word_count < 100:
            self.content_type = "short"
        elif self.word_count < 1500:
            self.content_type = "medium"
        else:
            self.content_type = "long"

class DatabaseManager:
    """Manages all database operations with Supabase"""
    
    def __init__(self):
        self.db_pool = None
        self.openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self._embedding_cache = {}
    
    async def initialize(self):
        """Initialize database connection"""
        try:
            self.db_pool = await asyncpg.create_pool(
                os.getenv("SUPABASE_DB_URL"),
                min_size=2,
                max_size=10
            )
            
            # Register vector type
            async with self.db_pool.acquire() as conn:
                await register_vector(conn)
            
            logger.info("✅ Database connection established")
            
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            raise
    
    async def get_embedding(self, text: str) -> List[float]:
        """Get OpenAI embedding with caching"""
        # Create cache key
        text_hash = hashlib.md5(text.encode()).hexdigest()
        
        # Check in-memory cache first
        if text_hash in self._embedding_cache:
            return self._embedding_cache[text_hash]
        
        # Check database cache
        async with self.db_pool.acquire() as conn:
            cached = await conn.fetchval("""
                SELECT embedding FROM embedding_cache WHERE text_hash = $1
            """, text_hash)
            
            if cached:
                self._embedding_cache[text_hash] = cached
                return cached
        
        # Generate new embedding
        try:
            response = await self.openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=text[:8000]  # Truncate if too long
            )
            
            embedding = response.data[0].embedding
            
            # Cache in database and memory
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO embedding_cache (text_hash, embedding)
                    VALUES ($1, $2)
                    ON CONFLICT (text_hash) DO NOTHING
                """, text_hash, embedding)
            
            self._embedding_cache[text_hash] = embedding
            return embedding
            
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            # Return a default embedding if API fails
            return [0.0] * 1536
    
    async def store_content_item(self, item: EnhancedContentItem) -> bool:
        """Store a single content item with embedding"""
        try:
            # Generate embedding for the content
            embedding_text = f"{item.title} {item.content}"
            item.embedding = await self.get_embedding(embedding_text)
            
            # Calculate initial relevance score (basic for now)
            item.relevance_score = await self._calculate_initial_relevance(item)
            
            # Store in database
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO content_items 
                    (id, source, source_url, title, content, author, published,
                     primary_category, content_type, word_count, reading_time_minutes,
                     embedding, relevance_score, complexity_score, source_metadata,
                     scraped_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                    ON CONFLICT (id) DO UPDATE SET
                        embedding = EXCLUDED.embedding,
                        relevance_score = EXCLUDED.relevance_score,
                        source_metadata = EXCLUDED.source_metadata,
                        updated_at = NOW()
                """, 
                item.id, item.source, item.source_url, item.title, item.content,
                item.author, item.published,
                item.primary_category.value if item.primary_category else None,
                item.content_type, item.word_count, item.reading_time_minutes,
                item.embedding, item.relevance_score, item.complexity_score,
                json.dumps(item.source_metadata), item.scraped_at)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to store item {item.id}: {e}")
            return False
    
    async def _calculate_initial_relevance(self, item: EnhancedContentItem) -> float:
        """Calculate initial relevance score based on content and historical data"""
        try:
            async with self.db_pool.acquire() as conn:
                # Check for similar content that was rated highly
                if item.embedding:
                    similar_ratings = await conn.fetch("""
                        SELECT user_feedback, (embedding <-> $1) as distance
                        FROM content_items 
                        WHERE user_feedback IS NOT NULL
                        AND (embedding <-> $1) < 0.3
                        ORDER BY distance
                        LIMIT 5
                    """, item.embedding)
                    
                    if similar_ratings:
                        # Weight by similarity
                        total_weight = 0
                        total_score = 0
                        
                        for row in similar_ratings:
                            weight = 1.0 - row['distance']  # Closer = higher weight
                            score = 1.0 if row['user_feedback'] > 0 else 0.0
                            total_weight += weight
                            total_score += score * weight
                        
                        if total_weight > 0:
                            return total_score / total_weight
                
                # Fallback: basic content analysis
                return self._basic_content_scoring(item)
                
        except Exception as e:
            logger.error(f"Error calculating relevance: {e}")
            return 0.5
    
    def _basic_content_scoring(self, item: EnhancedContentItem) -> float:
        """Basic content scoring based on keywords and patterns"""
        content_lower = item.content.lower()
        title_lower = item.title.lower()
        
        # Quality indicators
        quality_boost = 0.0
        noise_penalty = 0.0
        
        # Positive signals
        quality_words = ['breakthrough', 'research', 'analysis', 'report', 'study', 'development']
        for word in quality_words:
            if word in content_lower:
                quality_boost += 0.1
        
        # Author credibility (basic check)
        credible_domains = ['techcrunch', 'wired', 'reuters', 'bloomberg']
        if any(domain in item.source_url.lower() for domain in credible_domains):
            quality_boost += 0.2
        
        # Noise signals
        noise_words = ['promo', 'discount', 'webinar', 'limited time', 'buy now', 'click here']
        for word in noise_words:
            if word in content_lower:
                noise_penalty += 0.2
        
        # Calculate final score
        base_score = 0.5
        final_score = base_score + quality_boost - noise_penalty
        
        return max(0.1, min(1.0, final_score))
    
    async def get_high_quality_content(self, hours: int = 24, min_score: float = 0.7, limit: int = 50) -> List[Dict]:
        """Get high-quality content from the last N hours"""
        try:
            async with self.db_pool.acquire() as conn:
                results = await conn.fetch("""
                    SELECT id, source, title, content, author, published, 
                           primary_category, relevance_score, source_url,
                           reading_time_minutes, word_count, source_metadata
                    FROM content_items 
                    WHERE scraped_at > NOW() - INTERVAL '%d hours'
                    AND relevance_score >= $1
                    ORDER BY relevance_score DESC, published DESC
                    LIMIT $2
                """ % hours, min_score, limit)
                
                return [dict(row) for row in results]
                
        except Exception as e:
            logger.error(f"Error fetching high-quality content: {e}")
            return []
    
    async def close(self):
        """Close database connection"""
        if self.db_pool:
            await self.db_pool.close()

class TwitterFetcher:
    """Enhanced Twitter scraper with database integration"""
    
    def __init__(self, config: FetcherConfig = None, db_manager: DatabaseManager = None):
        self.config = config or FetcherConfig()
        self.db_manager = db_manager
        self.browser = None
        self.context = None
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent)
    
    async def _init_browser(self):
        """Initialize browser with anti-detection measures"""
        if self.browser is None:
            playwright = await async_playwright().start()
            self.browser = await playwright.chromium.launch(
                headless=self.config.headless,
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
    
    def _auto_categorize(self, content: str, author: str) -> ContentCategory:
        """Auto-categorize content based on keywords and author"""
        content_lower = content.lower()
        author_lower = author.lower()
        
        # AI/Tech keywords
        if any(word in content_lower for word in ['gpt', 'ai', 'ml', 'artificial intelligence', 'neural', 'llm']):
            return ContentCategory.TECH_AI
        
        # Crypto keywords  
        elif any(word in content_lower for word in ['bitcoin', 'crypto', 'defi', 'ethereum', 'blockchain']):
            return ContentCategory.CRYPTO
        
        # Politics keywords
        elif any(word in content_lower for word in ['congress', 'senate', 'policy', 'legislation', 'government']):
            return ContentCategory.POLITICS
        
        # Regulation keywords
        elif any(word in content_lower for word in ['sec', 'regulation', 'compliance', 'federal']):
            return ContentCategory.REGULATION
        
        # Default to business
        else:
            return ContentCategory.BUSINESS
    
    async def fetch_user_tweets(self, username: str, max_tweets: int = 20) -> List[EnhancedContentItem]:
        """Fetch tweets and store in database"""
        async with self._semaphore:
            return await self._fetch_user_tweets_impl(username, max_tweets)
    
    async def _fetch_user_tweets_impl(self, username: str, max_tweets: int) -> List[EnhancedContentItem]:
        """Implementation of tweet fetching"""
        await self._init_browser()
        page = await self.context.new_page()
        items = []
        
        try:
            logger.info(f"🐦 Fetching tweets from @{username}...")
            
            # Try both x.com and twitter.com
            urls_to_try = [f'https://x.com/{username}', f'https://twitter.com/{username}']
            
            page_loaded = False
            for url in urls_to_try:
                try:
                    await page.goto(url, wait_until='domcontentloaded', timeout=self.config.browser_timeout)
                    page_loaded = True
                    break
                except Exception as e:
                    logger.debug(f"Failed to load {url}: {e}")
                    continue
            
            if not page_loaded:
                logger.warning(f"Could not load any URL for {username}")
                return items
            
            # Wait for content to load
            await asyncio.sleep(3)
            
            # Look for tweet elements
            tweet_selectors = [
                '[data-testid="tweet"]',
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
                logger.warning(f"No tweets found for {username}")
                return items
            
            # Scrape tweets
            tweet_count = 0
            seen_content = set()
            scroll_attempts = 0
            
            while tweet_count < max_tweets and scroll_attempts < self.config.max_scroll_attempts:
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
                        if not text or len(text.strip()) < 5:
                            continue
                        
                        # Avoid duplicates
                        content_hash = hashlib.md5(text.encode()).hexdigest()[:8]
                        if content_hash in seen_content:
                            continue
                        seen_content.add(content_hash)
                        
                        # Extract engagement metrics
                        metadata = {}
                        try:
                            # Look for like/retweet buttons
                            metrics = await tweet.query_selector_all('[data-testid*="like"], [data-testid*="retweet"], [data-testid*="reply"]')
                            for metric in metrics:
                                aria_label = await metric.get_attribute('aria-label')
                                if aria_label:
                                    # Extract numbers from aria-label
                                    import re
                                    numbers = re.findall(r'\d+', aria_label)
                                    if numbers:
                                        if 'like' in aria_label.lower():
                                            metadata['likes'] = int(numbers[0])
                                        elif 'retweet' in aria_label.lower():
                                            metadata['retweets'] = int(numbers[0])
                                        elif 'repl' in aria_label.lower():
                                            metadata['replies'] = int(numbers[0])
                        except:
                            pass
                        
                        # Create content item
                        item = EnhancedContentItem(
                            id="",  # Will be auto-generated
                            source="twitter",
                            source_url=f"https://twitter.com/{username}",
                            title=f"Tweet by @{username}",
                            content=text,
                            author=username,
                            published=datetime.now(),  # Could extract actual date
                            primary_category=self._auto_categorize(text, username),
                            source_metadata=metadata
                        )
                        
                        # Store in database immediately
                        if self.db_manager:
                            success = await self.db_manager.store_content_item(item)
                            if success:
                                items.append(item)
                                tweet_count += 1
                                logger.debug(f"Stored tweet {tweet_count}: {text[:50]}...")
                        else:
                            items.append(item)
                            tweet_count += 1
                        
                    except Exception as e:
                        logger.debug(f"Error processing tweet: {e}")
                        continue
                
                if tweet_count >= max_tweets:
                    break
                
                # Scroll for more tweets
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await asyncio.sleep(2)
                scroll_attempts += 1
            
            logger.info(f"✅ Fetched {len(items)} tweets from @{username}")
            
        except Exception as e:
            logger.error(f"Error fetching tweets from {username}: {e}")
        finally:
            await page.close()
        
        return items
    
    async def cleanup(self):
        """Clean up browser resources"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()

class RSSFetcher:
    """Enhanced RSS fetcher with database integration"""
    
    def __init__(self, db_manager: DatabaseManager = None):
        self.db_manager = db_manager
    
    def _auto_categorize_feed(self, feed_url: str, entry_title: str, entry_content: str) -> ContentCategory:
        """Auto-categorize RSS content"""
        text = f"{entry_title} {entry_content}".lower()
        url_lower = feed_url.lower()
        
        # Check URL first
        if any(tech in url_lower for tech in ['techcrunch', 'wired', 'arstechnica']):
            return ContentCategory.TECH_AI
        elif any(crypto in url_lower for crypto in ['coindesk', 'cointelegraph']):
            return ContentCategory.CRYPTO
        
        # Check content
        if any(word in text for word in ['ai', 'artificial intelligence', 'machine learning']):
            return ContentCategory.TECH_AI
        elif any(word in text for word in ['bitcoin', 'cryptocurrency', 'blockchain']):
            return ContentCategory.CRYPTO
        
        return ContentCategory.BUSINESS
    
    async def fetch_feed_items(self, feed_url: str, max_items: int = 20) -> List[EnhancedContentItem]:
        """Fetch RSS feed items and store in database"""
        items = []
        
        try:
            logger.info(f"📰 Fetching RSS feed: {feed_url}")
            
            feed = feedparser.parse(feed_url)
            
            if feed.bozo:
                logger.warning(f"RSS feed has parsing issues: {feed.bozo_exception}")
            
            for i, entry in enumerate(feed.entries[:max_items]):
                try:
                    # Parse date
                    pub_date = datetime.now()
                    for date_field in ['published_parsed', 'updated_parsed']:
                        if hasattr(entry, date_field) and getattr(entry, date_field):
                            try:
                                pub_date = datetime(*getattr(entry, date_field)[:6])
                                break
                            except (TypeError, ValueError):
                                continue
                    
                    # Extract content
                    content = ""
                    if hasattr(entry, 'content') and entry.content:
                        content = entry.content[0].value
                    elif hasattr(entry, 'summary'):
                        content = entry.summary
                    elif hasattr(entry, 'description'):
                        content = entry.description
                    
                    # Clean HTML
                    import re
                    content = re.sub(r'<[^>]+>', '', content)
                    content = re.sub(r'\s+', ' ', content).strip()
                    
                    # Get author
                    author = ""
                    if hasattr(entry, 'author'):
                        author = entry.author
                    elif hasattr(feed.feed, 'title'):
                        author = feed.feed.title
                    
                    # Create content item
                    item = EnhancedContentItem(
                        id="",
                        source="rss",
                        source_url=entry.link if hasattr(entry, 'link') else feed_url,
                        title=entry.title if hasattr(entry, 'title') else content[:100],
                        content=content,
                        author=author,
                        published=pub_date,
                        primary_category=self._auto_categorize_feed(feed_url, 
                                                                   getattr(entry, 'title', ''), 
                                                                   content),
                        source_metadata={
                            'feed_url': feed_url,
                            'feed_title': getattr(feed.feed, 'title', ''),
                        }
                    )
                    
                    # Store in database
                    if self.db_manager:
                        success = await self.db_manager.store_content_item(item)
                        if success:
                            items.append(item)
                    else:
                        items.append(item)
                        
                except Exception as e:
                    logger.warning(f"Error parsing RSS entry: {e}")
                    continue
            
            logger.info(f"✅ Fetched {len(items)} items from RSS feed")
            
        except Exception as e:
            logger.error(f"Error fetching RSS feed {feed_url}: {e}")
        
        return items

# Enhanced main functions with database integration
async def enhanced_fetch_all_sources(
    twitter_usernames: List[str] = None,
    rss_feeds: List[str] = None,
    max_per_source: int = 20
) -> Dict[str, Any]:
    """Enhanced multi-source fetching with database storage"""
    
    # Initialize database
    db_manager = DatabaseManager()
    await db_manager.initialize()
    
    # Default sources
    twitter_usernames = twitter_usernames or ["S4mmyEth", "PinkBrains_io", "naval", "sama", "kupor"]
    rss_feeds = rss_feeds or [
        "https://techcrunch.com/feed/",
        "https://www.coindesk.com/arc/outboundfeeds/rss/"
    ]
    
    all_items = []
    stats = {
        'twitter_items': 0,
        'rss_items': 0,
        'total_stored': 0,
        'processing_time': 0
    }
    
    start_time = datetime.now()
    
    try:
        # Fetch Twitter content
        if twitter_usernames:
            logger.info(f"🐦 Fetching from {len(twitter_usernames)} Twitter accounts...")
            twitter_fetcher = TwitterFetcher(db_manager=db_manager)
            
            for username in twitter_usernames:
                try:
                    items = await twitter_fetcher.fetch_user_tweets(username, max_per_source)
                    all_items.extend(items)
                    stats['twitter_items'] += len(items)
                    await asyncio.sleep(1)  # Be nice to Twitter
                except Exception as e:
                    logger.error(f"Failed to fetch tweets from {username}: {e}")
                    continue
            
            await twitter_fetcher.cleanup()
        
        # Fetch RSS content
        if rss_feeds:
            logger.info(f"📰 Fetching from {len(rss_feeds)} RSS feeds...")
            rss_fetcher = RSSFetcher(db_manager=db_manager)
            
            for feed_url in rss_feeds:
                try:
                    items = await rss_fetcher.fetch_feed_items(feed_url, max_per_source)
                    all_items.extend(items)
                    stats['rss_items'] += len(items)
                except Exception as e:
                    logger.error(f"Failed to fetch RSS feed {feed_url}: {e}")
                    continue
        
        stats['total_stored'] = len(all_items)
        stats['processing_time'] = (datetime.now() - start_time).total_seconds()
        
        logger.info(f"✅ Enhanced fetch completed:")
        logger.info(f"   • Twitter: {stats['twitter_items']} items")
        logger.info(f"   • RSS: {stats['rss_items']} items") 
        logger.info(f"   • Total stored: {stats['total_stored']} items")
        logger.info(f"   • Processing time: {stats['processing_time']:.1f}s")
        
        # Get high-quality content for Notion
        high_quality_items = await db_manager.get_high_quality_content(
            hours=24, min_score=0.7, limit=25
        )
        
        return {
            'all_items': all_items,
            'high_quality_items': high_quality_items,
            'stats': stats
        }
        
    finally:
        await db_manager.close()

# Backward compatibility functions
async def fetch_tweets(usernames=None, max_tweets=20):
    """Backward compatible fetch_tweets function"""
    usernames = usernames or ["paulg", "sama", "naval"]
    
    result = await enhanced_fetch_all_sources(
        twitter_usernames=usernames,
        rss_feeds=[],  # Only Twitter
        max_per_source=max_tweets
    )
    
    # Return content strings for compatibility
    return [item.content for item in result['all_items']]

def fetch_tweets_sync(usernames=None, max_tweets=20):
    """Synchronous wrapper for existing code compatibility"""
    return asyncio.run(fetch_tweets(usernames, max_tweets))

async def fetch_all_sources(twitter_usernames=None, rss_feeds=None, max_per_source=20):
    """Enhanced fetch_all_sources that returns EnhancedContentItem objects"""
    result = await enhanced_fetch_all_sources(twitter_usernames, rss_feeds, max_per_source)
    return result['all_items']

def fetch_all_sources_sync(twitter_usernames=None, rss_feeds=None, max_per_source=20):
    """Synchronous wrapper for multi-source fetching"""
    return asyncio.run(fetch_all_sources(twitter_usernames, rss_feeds, max_per_source))

# New function specifically for getting high-quality content
async def get_filtered_content(hours: int = 24, min_score: float = 0.7, limit: int = 25) -> List[Dict]:
    """Get high-quality content from database for Notion"""
    db_manager = DatabaseManager()
    await db_manager.initialize()
    
    try:
        return await db_manager.get_high_quality_content(hours, min_score, limit)
    finally:
        await db_manager.close()

def get_filtered_content_sync(hours: int = 24, min_score: float = 0.7, limit: int = 25) -> List[Dict]:
    """Synchronous wrapper for getting filtered content"""
    return asyncio.run(get_filtered_content(hours, min_score, limit))