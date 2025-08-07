import os
from notion_client import Client
from dotenv import load_dotenv

load_dotenv()
notion = Client(auth=os.getenv("NOTION_API_KEY"))

def send_to_notion(posts):
    """Send posts to Notion - works with both old format (strings) and new format (ContentItem objects)"""
    db_id = os.getenv("NOTION_DATABASE_ID")
    
    for post in posts:
        try:
            # Handle both old format (strings) and new format (ContentItem objects)
            if isinstance(post, str):
                # Old format - just a string
                notion.pages.create(
                    parent={"database_id": db_id},
                    properties={
                        "Title": {
                            "title": [{"text": {"content": post[:100]}}]  # First 100 chars as title
                        },
                        "Content": {
                            "rich_text": [{"text": {"content": post}}]
                        },
                        "Source": {
                            "select": {"name": "Twitter"}  # Default to Twitter for old format
                        },
                        "Author": {
                            "rich_text": [{"text": {"content": "Unknown"}}]
                        }
                    }
                )
            else:
                # New format - ContentItem object
                notion.pages.create(
                    parent={"database_id": db_id},
                    properties={
                        "Title": {
                            "title": [{"text": {"content": post.title[:100] if post.title else post.content[:100]}}]
                        },
                        "Source": {
                            "select": {"name": post.source.title()}  # twitter -> Twitter
                        },
                        "Author": {
                            "rich_text": [{"text": {"content": post.author}}]
                        },
                        "Content": {
                            "rich_text": [{"text": {"content": post.content}}]
                        },
                        "URL": {
                            "url": post.source_url if post.source_url.startswith('http') else None
                        },
                        "Date": {
                            "date": {"start": post.published.isoformat()}
                        }
                    }
                )
            print(f"✅ Added to Notion: {post[:50] if isinstance(post, str) else post.title[:50]}...")
            
        except Exception as e:
            print(f"❌ Error adding to Notion: {e}")
            # Continue with other posts even if one fails
            continue

def send_items_to_notion(items):
    """Send ContentItem objects to Notion with full metadata"""
    send_to_notion(items)  # Uses the same function, just with ContentItem objects