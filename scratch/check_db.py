import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase = create_client(url, key)

try:
    print("Checking 'workers' table...")
    res = supabase.table("workers").select("id").limit(1).execute()
    if res.data:
        val = res.data[0]['id']
        print(f"Worker ID: {val}, Type: {type(val)}")
    else:
        print("No workers found.")

    print("\nChecking 'bookings' table...")
    # This might fail if the table doesn't exist or has UUID issue
    try:
        res = supabase.table("bookings").select("*").limit(1).execute()
        print("Bookings table exists.")
    except Exception as e:
        print(f"Bookings table check failed: {e}")

except Exception as e:
    print(f"Error: {e}")
