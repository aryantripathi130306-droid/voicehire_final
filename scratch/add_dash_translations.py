import sys, json

dash_translations = {
    "My Job Requests": {
        "hi": "मेरे कार्य अनुरोध",
        "pa": "ਮੇਰੀਆਂ ਨੌਕਰੀਆਂ ਦੀਆਂ ਬੇਨਤੀਆਂ",
        "en": "My Job Requests"
    },
    "Payments": {
        "hi": "भुगतान",
        "pa": "ਭੁਗਤਾਨ",
        "en": "Payments"
    },
    "Searching near:": {
        "hi": "निकट खोज रहे हैं:",
        "pa": "ਨੇੜੇ ਖੋਜ ਰਹੇ ਹਾਂ:",
        "en": "Searching near:"
    },
    "Change Locality": {
        "hi": "इलाका बदलें",
        "pa": "ਇਲਾਕਾ ਬਦਲੋ",
        "en": "Change Locality"
    },
    "Verified Employer": {
        "hi": "सत्यापित नियोक्ता",
        "pa": "ਪ੍ਰਮਾਣਿਤ ਮਾਲਕ",
        "en": "Verified Employer"
    },
    "Find, compare and book verified service professionals in your area.": {
        "hi": "अपने क्षेत्र में सत्यापित सेवा पेशेवरों को खोजें, तुलना करें और बुक करें।",
        "pa": "ਆਪਣੇ ਖੇਤਰ ਵਿੱਚ ਪ੍ਰਮਾਣਿਤ ਸੇਵਾ ਪੇਸ਼ੇਵਰਾਂ ਨੂੰ ਲੱਭੋ, ਤੁਲਨਾ ਕਰੋ ਅਤੇ ਬੁੱਕ ਕਰੋ।",
        "en": "Find, compare and book verified service professionals in your area."
    },
    "Find nearby job requests, accept bookings, and manage your duty status.": {
        "hi": "आस-पास के कार्य अनुरोध खोजें, बुकिंग स्वीकार करें, और अपनी ड्यूटी स्थिति प्रबंधित करें।",
        "pa": "ਨੇੜਲੀਆਂ ਨੌਕਰੀਆਂ ਦੀਆਂ ਬੇਨਤੀਆਂ ਲੱਭੋ, ਬੁਕਿੰਗਾਂ ਸਵੀਕਾਰ ਕਰੋ, ਅਤੇ ਆਪਣੀ ਡਿਊਟੀ ਸਥਿਤੀ ਦਾ ਪ੍ਰਬੰਧਨ ਕਰੋ।",
        "en": "Find nearby job requests, accept bookings, and manage your duty status."
    }
}

with open("translations.py", "r", encoding="utf-8") as f:
    content = f.read()

target = '    "Booking History": {\n        "hi": "बुकिंग इतिहास",\n        "pa": "ਬੁਕਿੰਗ ਇਤਿਹਾਸ",\n        "en": "Booking History"\n    },\n}'

if target not in content:
    print("Error: target not found in translations.py")
    sys.exit(1)

lines = []
for k, v in dash_translations.items():
    formatted = f'    {json.dumps(k, ensure_ascii=False)}: {{\n        "hi": {json.dumps(v["hi"], ensure_ascii=False)},\n        "pa": {json.dumps(v["pa"], ensure_ascii=False)},\n        "en": {json.dumps(v["en"], ensure_ascii=False)}\n    }},'
    lines.append(formatted)

inserted_text = "\n".join(lines)
replacement = '    "Booking History": {\n        "hi": "बुकिंग इतिहास",\n        "pa": "ਬੁਕਿੰਗ ਇਤਿਹਾਸ",\n        "en": "Booking History"\n    },\n' + inserted_text + '\n}'

new_content = content.replace(target, replacement, 1)

with open("translations.py", "w", encoding="utf-8") as f:
    f.write(new_content)

print(f"Successfully added {len(dash_translations)} translations to translations.py!")
