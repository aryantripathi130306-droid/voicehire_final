import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

supabase_url = os.environ.get('SUPABASE_URL')
supabase_key = os.environ.get('SUPABASE_KEY')
supabase: Client = create_client(supabase_url, supabase_key)

def check_table(name):
    try:
        resp = supabase.table(name).select("*").limit(1).execute()
        if resp.data:
            print(f"Table {name} columns: {list(resp.data[0].keys())}")
        else:
            print(f"Table {name} is empty or columns cannot be determined.")
    except Exception as e:
        print(f"Error checking {name}: {e}")

check_table("jobs")
check_table("bookings")
check_table("workers")
check_table("reviews")
