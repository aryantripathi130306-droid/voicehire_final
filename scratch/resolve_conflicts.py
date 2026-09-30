import os
import re

def resolve_conflict(file_path):
    print(f"Resolving: {file_path}")
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Simple regex to choose HEAD version
    # Pattern: <<<<<<< HEAD\n(.*?)\n=======\n(.*?)\n>>>>>>> [a-f0-9]+
    # We use re.DOTALL to match across lines
    new_content = re.sub(r'<<<<<<< HEAD\n(.*?)\n=======\n(.*?)\n>>>>>>> [a-f0-9]+', r'\1', content, flags=re.DOTALL)
    
    # Also handle the variant without the hash in the marker
    new_content = re.sub(r'<<<<<<< HEAD\n(.*?)\n=======\n(.*?)\n>>>>>>> [^\n]*', r'\1', new_content, flags=re.DOTALL)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

files = [
    r'e:\voicehire web\templates\my_bookings.html',
    r'e:\voicehire web\templates\user_dashboard.html',
    r'e:\voicehire web\templates\worker_dashboard.html'
]

for f in files:
    if os.path.exists(f):
        resolve_conflict(f)
    else:
        print(f"File not found: {f}")
