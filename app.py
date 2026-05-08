import traceback
import os
import uuid
import re
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from dotenv import load_dotenv
from supabase import create_client, Client
# pyrefly: ignore [missing-import]
from translations import get_translation

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'super_secret_voicehire_key')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ── Upload folders ──────────────────────────────────────────
UPLOAD_FOLDER = os.path.join('static', 'uploads')
AUDIO_FOLDER = os.path.join(UPLOAD_FOLDER, 'audio')
VIDEO_FOLDER = os.path.join(UPLOAD_FOLDER, 'video')
ID_FOLDER = os.path.join(UPLOAD_FOLDER, 'ids')
PROFILE_PIC_FOLDER = os.path.join(UPLOAD_FOLDER, 'profile_pics')
os.makedirs(AUDIO_FOLDER, exist_ok=True)
os.makedirs(VIDEO_FOLDER, exist_ok=True)
os.makedirs(ID_FOLDER, exist_ok=True)
os.makedirs(PROFILE_PIC_FOLDER, exist_ok=True)

ALLOWED_AUDIO_EXTENSIONS = {'mp3', 'wav', 'ogg', 'm4a', 'aac'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'webm', 'ogg', 'mov'}
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png'}

# ── Supabase ─────────────────────────────────────────────────
supabase_url = os.environ.get('SUPABASE_URL')
supabase_key = os.environ.get('SUPABASE_KEY')
if not supabase_url or not supabase_key:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
supabase: Client = create_client(supabase_url, supabase_key)

# ── Helpers ───────────────────────────────────────────────────
def allowed_file(filename, allowed_set):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_set

def is_valid_phone(phone):
    return bool(re.match(r'^[6-9]\d{9}$', str(phone).strip()))

def safe_str(val):
    return str(val).strip() if val else ''

def try_select(table, columns, filters=None, in_filters=None):
    try:
        query = supabase.table(table).select(columns)
        if filters:
            for k, v in filters.items(): query = query.eq(k, v)
        if in_filters:
            for k, v in in_filters.items(): query = query.in_(k, v)
        return query.execute()
    except Exception as e:
        if 'profile_pic' in str(e).lower():
            cols = columns.replace(', profile_pic', '').replace('profile_pic, ', '').replace('profile_pic', '')
            query = supabase.table(table).select(cols)
            if filters:
                for k, v in filters.items(): query = query.eq(k, v)
            if in_filters:
                for k, v in in_filters.items(): query = query.in_(k, v)
            resp = query.execute()
            for row in resp.data: row['profile_pic'] = None
            return resp
        raise e
@app.context_processor
def inject_translation():
    def t(text):
        lang = session.get('lang', 'en')
        return get_translation(lang, text)
    return dict(t=t)

@app.route('/')
def index():
    if 'user_id' in session:
        role = session.get('role')
        return redirect(url_for('user_dashboard' if role == 'user' else 'worker_dashboard'))
    return render_template('select_language.html')   # ← judges see this first

@app.route('/set_lang/<lang_code>')
def set_lang(lang_code):
    session['lang'] = lang_code
    return redirect(url_for('gateway'))


from flask import Flask
app = Flask(__name__)
@app.route('/')
def home():
    return "Hello, VoiceHire!"
if __name__ == '__main__':
    app.run(debug=True)
