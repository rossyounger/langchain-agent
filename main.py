from fetch import fetch_tweets_sync, fetch_all_sources_sync
from filter import is_signal
from output import send_to_notion

def main():
    """Original main function - still works exactly the same"""
    tweets = fetch_tweets_sync()
    signal = [t for t in tweets if is_signal(t)]
    send_to_notion(signal)

def main_multi_source():
    """New main function with multiple data sources"""
    
    # Configure your sources
    twitter_usernames = ["paulg", "sama", "naval", "elonmusk"]
    rss_feeds = [
        "https://feeds.feedburner.com/oreilly/radar",
        "https://rss.cnn.com/rss/edition.rss",
        "https://feeds.a16z.com/a16z.rss"
    ]
    
    # Fetch from all sources
    print("Fetching from all sources...")
    all_items = fetch_all_sources_sync(
        twitter_usernames=twitter_usernames,
        rss_feeds=rss_feeds,
        max_per_source=10
    )
    
    print(f"Fetched {len(all_items)} total items")
    
    # Extract just the content for filtering (maintains compatibility)
    all_content = [item.content for item in all_items]
    
    # Apply your existing filter
    signal = [content for content in all_content if is_signal(content)]
    
    print(f"Found {len(signal)} signal items after filtering")
    
    # Send to Notion using your existing function
    send_to_notion(signal)
    
    # Optional: Print some info about what was found
    sources_summary = {}
    for item in all_items:
        if item.source in sources_summary:
            sources_summary[item.source] += 1
        else:
            sources_summary[item.source] = 1
    
    print("Sources summary:", sources_summary)

if __name__ == "__main__":
    # Use the original main() or the new main_multi_source()
    # main()  # Original version
    main_multi_source()  # New multi-source version