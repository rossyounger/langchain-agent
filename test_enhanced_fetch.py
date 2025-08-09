"""
Test script for your enhanced fetch system
"""
import asyncio
from fetch import enhanced_fetch_all_sources, get_filtered_content_sync

async def test_enhanced_system():
    """Test the new enhanced fetch system"""
    
    print("🧪 Testing Enhanced Content Intelligence System")
    print("=" * 60)
    
    # Test 1: Fetch a small amount of content
    print("1️⃣ Testing enhanced fetch with small dataset...")
    
    try:
        result = await enhanced_fetch_all_sources(
            twitter_usernames=["sama", "naval"],  # Just 2 accounts for testing
            rss_feeds=["https://techcrunch.com/feed/"],  # Just 1 feed
            max_per_source=5  # Only 5 items each
        )
        
        print(f"   ✅ Fetched {result['stats']['total_stored']} items total")
        print(f"   📊 Twitter: {result['stats']['twitter_items']} items")
        print(f"   📰 RSS: {result['stats']['rss_items']} items")
        print(f"   ⏱️  Processing time: {result['stats']['processing_time']:.1f}s")
        
        # Show some examples
        if result['all_items']:
            print(f"\n📄 Sample items stored:")
            for i, item in enumerate(result['all_items'][:3]):
                print(f"   {i+1}. [{item.source}] {item.title[:50]}...")
                print(f"      Category: {item.primary_category.value if item.primary_category else 'None'}")
                print(f"      Score: {item.relevance_score:.2f}")
                print(f"      Words: {item.word_count}")
        
    except Exception as e:
        print(f"   ❌ Enhanced fetch failed: {e}")
        return False
    
    # Test 2: Get filtered content
    print(f"\n2️⃣ Testing filtered content retrieval...")
    
    try:
        filtered_items = get_filtered_content_sync(
            hours=24,
            min_score=0.5,  # Lower threshold for testing
            limit=10
        )
        
        print(f"   ✅ Retrieved {len(filtered_items)} high-quality items")
        
        if filtered_items:
            print(f"   📊 Quality breakdown:")
            categories = {}
            scores = []
            
            for item in filtered_items:
                cat = item.get('primary_category', 'None')
                categories[cat] = categories.get(cat, 0) + 1
                scores.append(item.get('relevance_score', 0))
            
            for cat, count in categories.items():
                print(f"      • {cat}: {count} items")
            
            avg_score = sum(scores) / len(scores) if scores else 0
            print(f"   📈 Average quality score: {avg_score:.2f}")
        
    except Exception as e:
        print(f"   ❌ Filtered content retrieval failed: {e}")
        return False
    
    # Test 3: Check database storage
    print(f"\n3️⃣ Testing database integration...")
    
    try:
        from fetch import DatabaseManager
        
        db_manager = DatabaseManager()
        await db_manager.initialize()
        
        # Check recent content count
        async with db_manager.db_pool.acquire() as conn:
            recent_count = await conn.fetchval("""
                SELECT COUNT(*) FROM content_items 
                WHERE scraped_at > NOW() - INTERVAL '1 hour'
            """)
            
            total_count = await conn.fetchval("SELECT COUNT(*) FROM content_items")
            
            rated_count = await conn.fetchval("""
                SELECT COUNT(*) FROM content_items WHERE user_feedback IS NOT NULL
            """)
        
        await db_manager.close()
        
        print(f"   ✅ Database connection working")
        print(f"   📊 Content in database:")
        print(f"      • Last hour: {recent_count} items")
        print(f"      • Total: {total_count} items")
        print(f"      • User-rated: {rated_count} items")
        
    except Exception as e:
        print(f"   ❌ Database test failed: {e}")
        return False
    
    print(f"\n🎉 All tests passed! Your enhanced system is working perfectly.")
    print(f"\n🚀 Next steps:")
    print(f"   1. Replace your old fetch.py with the enhanced version")
    print(f"   2. Your existing main.py will work but be much smarter")
    print(f"   3. Try the new get_filtered_content_sync() function")
    print(f"   4. Start rating content in Notion to teach the system")
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_enhanced_system())
    
    if success:
        print(f"\n✨ Your content intelligence system is ready!")
    else:
        print(f"\n⚠️  Some tests failed - check the errors above")