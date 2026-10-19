import sys, json

more_translations = {
    "VoiceHire AI Assistant": {
        "hi": "VoiceHire AI सहायक",
        "pa": "VoiceHire AI ਸਹਾਇਕ",
        "en": "VoiceHire AI Assistant"
    },
    "Namaste!": {
        "hi": "नमस्ते!",
        "pa": "ਸਤਿ ਸ਼੍ਰੀ ਅਕਾਲ!",
        "en": "Namaste!"
    },
    "and": {
        "hi": "और",
        "pa": "ਅਤੇ",
        "en": "and"
    },
    "I am your VoiceHire voice assistant. I can help you find local work or book skilled workers.": {
        "hi": "मैं आपका VoiceHire आवाज़ सहायक हूँ। मैं आपको स्थानीय काम खोजने या कुशल कामगारों को बुक करने में मदद कर सकता हूँ।",
        "pa": "ਮੈਂ ਤੁਹਾਡਾ VoiceHire ਆਵਾਜ਼ ਸਹਾਇਕ ਹਾਂ। ਮੈਂ ਸਥਾਨਕ ਕੰਮ ਲੱਭਣ ਜਾਂ ਹੁਨਰਮੰਦ ਕਾਮਿਆਂ ਨੂੰ ਬੁੱਕ ਕਰਨ ਵਿੱਚ ਤੁਹਾਡੀ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ।",
        "en": "I am your VoiceHire voice assistant. I can help you find local work or book skilled workers."
    }
}

with open("translations.py", "r", encoding="utf-8") as f:
    content = f.read()

target = '    "Find nearby job requests, accept bookings, and manage your duty status.": {\n        "hi": "आस-पास के कार्य अनुरोध खोजें, बुकिंग स्वीकार करें, और अपनी ड्यूटी स्थिति प्रबंधित करें।",\n        "pa": "ਨੇੜਲੀਆਂ ਨੌਕਰੀਆਂ ਦੀਆਂ ਬੇਨਤੀਆਂ ਲੱਭੋ, ਬੁਕਿੰਗਾਂ ਸਵੀਕਾਰ ਕਰੋ, ਅਤੇ ਆਪਣੀ ਡਿਊਟੀ ਸਥਿਤੀ ਦਾ ਪ੍ਰਬੰਧਨ ਕਰੋ।",\n        "en": "Find nearby job requests, accept bookings, and manage your duty status."\n    },\n}'

if target not in content:
    print("Error: target not found in translations.py")
    sys.exit(1)

lines = []
for k, v in more_translations.items():
    formatted = f'    {json.dumps(k, ensure_ascii=False)}: {{\n        "hi": {json.dumps(v["hi"], ensure_ascii=False)},\n        "pa": {json.dumps(v["pa"], ensure_ascii=False)},\n        "en": {json.dumps(v["en"], ensure_ascii=False)}\n    }},'
    lines.append(formatted)

inserted_text = "\n".join(lines)
replacement = '    "Find nearby job requests, accept bookings, and manage your duty status.": {\n        "hi": "आस-पास के कार्य अनुरोध खोजें, बुकिंग स्वीकार करें, और अपनी ड्यूटी स्थिति प्रबंधित करें।",\n        "pa": "ਨੇੜਲੀਆਂ ਨੌਕਰੀਆਂ ਦੀਆਂ ਬੇਨਤੀਆਂ ਲੱਭੋ, ਬੁਕਿੰਗਾਂ ਸਵੀਕਾਰ ਕਰੋ, ਅਤੇ ਆਪਣੀ ਡਿਊਟੀ ਸਥਿਤੀ ਦਾ ਪ੍ਰਬੰਧਨ ਕਰੋ।",\n        "en": "Find nearby job requests, accept bookings, and manage your duty status."\n    },\n' + inserted_text + '\n}'

new_content = content.replace(target, replacement, 1)

with open("translations.py", "w", encoding="utf-8") as f:
    f.write(new_content)

print(f"Successfully added {len(more_translations)} translations to translations.py!")
