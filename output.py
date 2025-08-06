import os
from notion_client import Client
from dotenv import load_dotenv

load_dotenv()
notion = Client(auth=os.getenv("NOTION_API_KEY"))

def send_to_notion(posts):
    db_id = os.getenv("NOTION_DATABASE_ID")
    for post in posts:
        notion.pages.create(
            parent={"database_id": db_id},
            properties={
                "Content": {
                    "title": [{"text": {"content": post[:200]}}]
                }
            }
        )
