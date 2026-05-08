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

app = Flask(__name__, template_folder='voicehire frontend/template')
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

@app.route('/gateway')
def gateway():
    if 'user_id' in session:
        role = session.get('role')
        return redirect(url_for('user_dashboard' if role == 'user' else 'worker_dashboard'))
    return render_template('gateway.html') 


@app.route('/home')
def home():
    if 'user_id' in session:
        if session.get('role') == 'user':
            return redirect(url_for('user_dashboard'))
        return redirect(url_for('worker_dashboard'))
    return render_template('gateway.html')

@app.route('/home')
def home():
    if 'user_id' in session:
        if session.get('role') == 'user':
            return redirect(url_for('user_dashboard'))
        return redirect(url_for('worker_dashboard'))
    return render_template('gateway.html')

@app.route('/welcome')
def welcome():
    if 'user_id' in session:
        role = session.get('role')
        return redirect(url_for('user_dashboard' if role == 'user' else 'worker_dashboard'))
    return render_template('gateway.html')

@app.route('/role')
def role_selection():
    return render_template('role.html')

@app.route('/login')
def login_page():
    role = request.args.get('role', 'user')
    return render_template('login.html', role=role)

@app.route('/signup/user')
def user_signup_page():
    return render_template('user_signup.html')

@app.route('/signup/worker')
def worker_signup_page():
    return render_template('worker_signup.html')

@app.route('/stitch_worker_dashboard')
def stitch_worker_dashboard():
    return render_template('stitch_worker_dashboard.html')
@app.route('/api/auth/signup/user', methods=['POST'])
def signup_user():
    name = safe_str(request.form.get('name'))
    phone = safe_str(request.form.get('phone'))
    password = safe_str(request.form.get('password'))

    if not all([name, phone, password]):
        return jsonify({'error': 'All fields are required'}), 400
    if not is_valid_phone(phone):
        return jsonify({'error': 'Invalid Indian phone number (10 digits starting with 6-9)'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400

    hashed_pw = generate_password_hash(password)
    try:
        existing = supabase.table("users").select("id").eq("phone", phone).execute()
        if existing.data:
            return jsonify({'error': 'Phone number already registered'}), 400

        profile_pic = request.files.get('profile_pic')
        profile_pic_path = None
        if profile_pic and profile_pic.filename != '':
            if not allowed_file(profile_pic.filename, ALLOWED_IMAGE_EXTENSIONS):
                return jsonify({'error': 'Invalid image file type for profile picture'}), 400
            filename = f"{uuid.uuid4().hex}_{secure_filename(profile_pic.filename)}"
            profile_pic.save(os.path.join(PROFILE_PIC_FOLDER, filename))
            profile_pic_path = f'uploads/profile_pics/{filename}'

        insert_data = {"name": name, "phone": phone, "password": hashed_pw, "profile_pic": profile_pic_path}
        try:
            response = supabase.table("users").insert(insert_data).execute()
        except Exception as e:
            if 'profile_pic' in str(e).lower():
                insert_data.pop('profile_pic', None)
                response = supabase.table("users").insert(insert_data).execute()
            else: raise e

        user_id = response.data[0]['id']
        session['user_id'] = user_id
        session['role'] = 'user'
        session['name'] = name
        session['phone'] = phone
        return jsonify({'message': 'User registered successfully', 'redirect': url_for('user_dashboard')}), 201
    except Exception as e:
        print("Error during user signup:\n", traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/auth/signup/worker', methods=['POST'])
def signup_worker():
    """
    HERO FEATURE: This is called after the worker speaks into the mic.
    The frontend (worker_signup.html) uses Web Speech API to fill the form,
    then submits here. Voice audio is also uploaded.
    """
    name = safe_str(request.form.get('name'))
    work = safe_str(request.form.get('work'))
    location = safe_str(request.form.get('location'))
    phone = safe_str(request.form.get('phone'))
    password = safe_str(request.form.get('password'))

    if not all([name, work, location, phone, password]):
        return jsonify({'error': 'All textual fields are required'}), 400
    if not is_valid_phone(phone):
        return jsonify({'error': 'Invalid Indian phone number (10 digits starting with 6-9)'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400

    hashed_pw = generate_password_hash(password)
    voice_file = request.files.get('voice_note')
    video_file = request.files.get('video')
    voice_path = None
    video_path = None
    profile_pic_path = None

    try:
        existing = supabase.table("workers").select("id").eq("phone", phone).execute()
        if existing.data:
            return jsonify({'error': 'Phone number already registered. Please login.'}), 400

        if voice_file and voice_file.filename != '':
            if not allowed_file(voice_file.filename, ALLOWED_AUDIO_EXTENSIONS):
                return jsonify({'error': 'Invalid audio file type'}), 400
            filename = f"{uuid.uuid4().hex}_{secure_filename(voice_file.filename)}"
            voice_file.save(os.path.join(AUDIO_FOLDER, filename))
            voice_path = f'uploads/audio/{filename}'

        if video_file and video_file.filename != '':
            if not allowed_file(video_file.filename, ALLOWED_VIDEO_EXTENSIONS):
                return jsonify({'error': 'Invalid video file type'}), 400
            filename = f"{uuid.uuid4().hex}_{secure_filename(video_file.filename)}"
            video_file.save(os.path.join(VIDEO_FOLDER, filename))
            video_path = f'uploads/video/{filename}'

        id_file = request.files.get('id_proof')
        id_path = None
        if id_file and id_file.filename != '':
            if not allowed_file(id_file.filename, ALLOWED_IMAGE_EXTENSIONS):
                return jsonify({'error': 'Invalid image file type for ID proof'}), 400
            filename = f"{uuid.uuid4().hex}_{secure_filename(id_file.filename)}"
            id_file.save(os.path.join(ID_FOLDER, filename))
            id_path = f'uploads/ids/{filename}'

        profile_pic = request.files.get('profile_pic')
        if profile_pic and profile_pic.filename != '':
            if not allowed_file(profile_pic.filename, ALLOWED_IMAGE_EXTENSIONS):
                return jsonify({'error': 'Invalid image file type for profile picture'}), 400
            filename = f"{uuid.uuid4().hex}_{secure_filename(profile_pic.filename)}"
            profile_pic.save(os.path.join(PROFILE_PIC_FOLDER, filename))
            profile_pic_path = f'uploads/profile_pics/{filename}'

        lat = request.form.get('latitude')
        lng = request.form.get('longitude')
        insert_data = {
            "name": name, "work": work, "location": location,
            "phone": phone, "password": hashed_pw,
            "voice_note": voice_path, "video": video_path,
            "id_proof_path": id_path, "profile_pic": profile_pic_path,
            "latitude": float(lat) if lat else None,
            "longitude": float(lng) if lng else None,
            "is_available": True, "is_verified": False
        }

        try:
            response = supabase.table("workers").insert(insert_data).execute()
        except Exception as e:
            if 'profile_pic' in str(e).lower():
                insert_data.pop('profile_pic', None)
                response = supabase.table("workers").insert(insert_data).execute()
            else: raise e

        worker_id = response.data[0]['id']
        session['user_id'] = worker_id
        session['role'] = 'worker'
        session['name'] = name
        session['phone'] = phone
        return jsonify({'message': 'Worker registered successfully', 'redirect': url_for('worker_dashboard')}), 201
    except Exception as e:
        print("Error during worker signup:\n", traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data = request.get_json() or {}
    except Exception:
        return jsonify({'error': 'Invalid JSON data'}), 400

    phone = safe_str(data.get('phone'))
    password = safe_str(data.get('password'))
    role = safe_str(data.get('role'))

    if not all([phone, password, role]) or role not in ['user', 'worker']:
        return jsonify({'error': 'Valid phone, password, and role required'}), 400

    table = 'users' if role == 'user' else 'workers'
    try:
        response = supabase.table(table).select("*").eq("phone", phone).execute()
        rows = response.data
        if rows and check_password_hash(rows[0]['password'], password):
            user = rows[0]
            session['user_id'] = user['id']
            session['role'] = role
            session['name'] = user['name']
            if role == 'user':
                session['phone'] = user['phone']
            redirect_url = url_for('user_dashboard') if role == 'user' else url_for('worker_dashboard')
            return jsonify({'message': 'Login successful', 'redirect': redirect_url}), 200
        else:
            return jsonify({'error': 'Invalid phone or password'}), 401
    except Exception as e:
        print("Error during login:\n", traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/auth/logout', methods=['POST'])
def logout_api():
    session.clear()
    return jsonify({'redirect': url_for('role_selection')}), 200

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('role_selection'))


# ════════════════════════════════════════════════════════════════
#  DASHBOARD ROUTES (redirect targets after login)
#  These render the templates — actual data is loaded by Part 2 & 3
# ════════════════════════════════════════════════════════════════

@app.route('/dashboard/user')
def user_dashboard():
    if 'user_id' not in session or session.get('role') != 'user':
        return redirect(url_for('login_page', role='user'))
    try:
        resp = try_select("users", "*", filters={"id": session['user_id']})
        if not resp.data:
            session.clear()
            return redirect(url_for('login_page', role='user'))
        user_data = resp.data[0]
        return render_template('user_dashboard.html', user=user_data)
    except Exception as e:
        return f"Database error: {e}"

@app.route('/dashboard/worker')
def worker_dashboard():
    if 'user_id' not in session or session.get('role') != 'worker':
        return redirect(url_for('login_page', role='worker'))
    try:
        resp = try_select("workers", "*", filters={"id": session['user_id']})
        if not resp.data:
            session.clear()
            return redirect(url_for('login_page', role='worker'))
        worker_data = resp.data[0]
        return render_template('worker_dashboard.html', worker=worker_data)
    except Exception as e:
        return f"Database error: {e}"


if __name__ == '__main__':
    app.run(host='::', port=5000, debug=True)

