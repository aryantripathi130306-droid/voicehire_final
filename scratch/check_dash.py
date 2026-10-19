import sys
sys.path.insert(0, '.')
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

with open('translations.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, l in enumerate(lines):
    if "'pa': {" in l:
        print(f"hi ends before line {i+1}: {[lines[j].strip() for j in range(i-3, i)]}")
    if "'en': {" in l:
        print(f"pa ends before line {i+1}: {[lines[j].strip() for j in range(i-3, i)]}")
    if "def get_verified_language" in l:
        print(f"en ends before line {i+1}: {[lines[j].strip() for j in range(i-5, i)]}")
