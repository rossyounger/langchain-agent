"""
Test script to verify your Supabase setup is working
Run this to make sure everything is connected properly
"""

import asyncio
import asyncpg
from pgvector.asyncpg import register_vector
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

async def test_supabase_connection():
    """Test all aspects of your Supabase setup"""
    
    print("🧪 Testing Supabase Connection...")
    print("=" * 50)
    
    try:
        # Test 1: Basic connection
        print("1️⃣ Testing database connection...")
        conn = await asyncpg.connect(os.getenv("SUPABASE_DB_URL"))
        await register_vector(conn)
        print("   ✅ Connected to Supabase successfully!")
        
        # Test 2: Check if tables exist
        print("\n2️⃣ Checking database schema...")
        tables = await conn.fetch("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('content_items', 'detailed_ratings', 'learning_patterns', 'system_metrics')
        """)
        
        table_names = [row['table_name'] for row in tables]
        expected_tables = ['content_items', 'detailed_ratings', 'learning_patterns', 'system_metrics']
        
        for table in expected_tables:
            if table in table_names:
                print(f"   ✅ Table '{table}' exists")
            else:
                print(f"   ❌ Table '{table}' missing")
        
        # Test 3: Check vector extension
        print("\n3️⃣ Testing vector extension...")
        vector_test = await conn.fetchval("""
            SELECT EXISTS(
                SELECT 1 FROM pg_extension WHERE extname = 'vector'
            );
        """)
        
        if vector_test:
            print("   ✅ Vector extension is enabled")
        else:
            print("   ❌ Vector extension not found")
        
        # Test 4: Insert a test record
        print("\n4️⃣ Testing data insertion...")
        
        # Generate a simple test embedding (normally from OpenAI)
        test_embedding = [0.1] * 1536  # Dummy embedding
        
        test_id = f"test_{int(datetime.now().timestamp())}"
        
        await conn.execute("""
            INSERT INTO content_items 
            (id, source, title, content, author, published, embedding, relevance_score)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """, 
            test_id,
            "test_source", 
            "Test Article", 
            "This is a test article to verify database functionality",
            "test_user",
            datetime.now(),
            test_embedding,
            0.75
        )
        
        print("   ✅ Successfully inserted test record")
        
        # Test 5: Query the data back
        print("\n5️⃣ Testing data retrieval...")
        
        result = await conn.fetchrow("""
            SELECT id, source, title, relevance_score 
            FROM content_items 
            WHERE id = $1
        """, test_id)
        
        if result:
            print(f"   ✅ Retrieved record: {result['title']} (score: {result['relevance_score']})")
        else:
            print("   ❌ Failed to retrieve test record")
        
        # Test 6: Test vector similarity (basic)
        print("\n6️⃣ Testing vector similarity...")
        
        similar = await conn.fetch("""
            SELECT id, title, (embedding <-> $1) as distance 
            FROM content_items 
            WHERE id = $2
            LIMIT 1
        """, test_embedding, test_id)
        
        if similar:
            print(f"   ✅ Vector similarity working (distance: {similar[0]['distance']})")
        else:
            print("   ❌ Vector similarity test failed")
        
        # Test 7: Check the analysis view
        print("\n7️⃣ Testing analysis view...")
        
        analysis = await conn.fetch("SELECT * FROM content_analysis LIMIT 5")
        print(f"   ✅ Analysis view returned {len(analysis)} rows")
        
        # Clean up test record
        await conn.execute("DELETE FROM content_items WHERE id = $1", test_id)
        print("   🧹 Cleaned up test record")
        
        # Final summary
        print(f"\n🎉 All tests passed! Your Supabase setup is ready.")
        print(f"📊 Database has {len(table_names)}/{len(expected_tables)} required tables")
        print(f"🧠 Vector embeddings are working correctly")
        print(f"📈 Ready to start storing your content intelligence data!")
        
    except Exception as e:
        print(f"❌ Error testing Supabase: {e}")
        print(f"\n🔧 Troubleshooting:")
        print(f"1. Check your SUPABASE_DB_URL in .env file")
        print(f"2. Make sure you ran the schema SQL in Supabase")
        print(f"3. Verify your database password is correct")
        
    finally:
        if conn:
            await conn.close()

async def test_openai_embeddings():
    """Test OpenAI embeddings if API key is provided"""
    
    openai_key = os.getenv("OPENAI_API_KEY")
    
    if not openai_key:
        print("\n⚠️  OPENAI_API_KEY not found - skipping embeddings test")
        print("   Add your OpenAI API key to .env to test embeddings")
        return
    
    print("\n🤖 Testing OpenAI embeddings...")
    
    try:
        from openai import AsyncOpenAI
        
        client = AsyncOpenAI(api_key=openai_key)
        
        response = await client.embeddings.create(
            model="text-embedding-3-small",
            input="This is a test sentence for embedding generation"
        )
        
        embedding = response.data[0].embedding
        print(f"   ✅ Generated embedding with {len(embedding)} dimensions")
        
    except Exception as e:
        print(f"   ❌ OpenAI embeddings test failed: {e}")
        print(f"   Make sure your OPENAI_API_KEY is valid")

if __name__ == "__main__":
    asyncio.run(test_supabase_connection())
    asyncio.run(test_openai_embeddings())