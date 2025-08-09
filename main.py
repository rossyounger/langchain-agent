from fetch import fetch_tweets_sync, fetch_all_sources_sync, get_filtered_content_sync
from filter import is_signal
from output import send_to_notion

def main():
    """Original main function - still works exactly the same"""
    tweets = fetch_tweets_sync()
    signal = [t for t in tweets if is_signal(t)]
    send_to_notion(signal)

def main_multi_source():
    """Enhanced main function using intelligent filtering"""
    
    print("🧠 Running Enhanced Content Intelligence Pipeline...")
    
    # Get high-quality content directly from database (no manual filtering needed!)
    high_quality_items = get_filtered_content_sync(
        hours=24,      # Last 24 hours
        min_score=0.7, # Only high-quality content  
        limit=25       # Top 25 items
    )
    
    print(f"✅ Found {len(high_quality_items)} high-quality items")
    
    # Send to Notion (these are already smart-filtered)
    if high_quality_items:
        # Convert to strings for your existing send_to_notion function
        content_strings = [item['content'] for item in high_quality_items]
        send_to_notion(content_strings)
        print(f"📋 Sent {len(content_strings)} items to Notion")
    else:
        print("ℹ️  No new high-quality content found")

if __name__ == "__main__":
    # Use the original main() or the new main_multi_source()
    # main()  # Original version
    main_multi_source()  # New multi-source version