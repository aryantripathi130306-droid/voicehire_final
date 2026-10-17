import traceback
import os
import uuid
import re
import secrets
import hmac
import hashlib
import json
import base64
import io
import csv
import math
from io import StringIO
from datetime import datetime, timedelta, date
from collections import defaultdict
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response
from flask_cors import CORS
from dotenv import load_dotenv
from supabase import create_client, Client
from translations import (
    get_translation,
    get_verified_language,
    format_currency,
    format_date,
    format_number,
    format_relative_time,
    get_localized_status,
    get_localized_validation,
    get_all_translations_for_lang,
    VERIFIED_LANGUAGES,
    DEFAULT_LANGUAGE
)
from voice_service import analyze_voice_intent, get_voice_capabilities, get_verified_language
from orchestration_engine import orchestration_engine, ConversationState, AssistantAction
import qrcode
from auth_security import auth_shield, recovery_manager
from backend_service import (
    LocationPrivacyShield,
    AuditLogger,
    NotificationService,
    StatusHistoryLogger,
    CheckinEventLogger,
    JobConcurrencyShield,
    PaymentManager,
    RazorpayGatewayService,
    ServiceCategoryManager,
    WorkerSkillsManager,
    BookingWorkflowManager,
    BookingCheckinSecurity,
    WorkerProfileManager,
    CustomerProfileManager,
    TrustAndSafetyManager,
    VALID_JOB_TRANSITIONS,
    VALID_BOOKING_TRANSITIONS,
    VALID_PAYMENT_TRANSITIONS,
    utc_now_iso,
)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'super_secret_voicehire_key')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max upload
CORS(app, resources={r"/api/*": {"origins": "*"}})

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

# ---- SUPABASE CLIENT ----
supabase_url = os.environ.get('SUPABASE_URL')
supabase_key = os.environ.get('SUPABASE_KEY')

if not supabase_url or not supabase_key:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env")

supabase: Client = create_client(supabase_url, supabase_key)

# ---- HELPERS ----
def allowed_file(filename, allowed_set):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_set

def is_valid_phone(phone):
    return bool(re.match(r'^[6-9]\d{9}$', str(phone).strip()))

def safe_str(val):
    return str(val).strip() if val else ''

def try_select(table, columns, filters=None, in_filters=None):
    """Helper to try selecting with profile_pic, fallback if column missing."""
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

# ---- TRANSLATION & LOCALIZATION CONFIG ----
@app.before_request
def ensure_language_preference():
    if 'lang' not in session:
        cookie_lang = request.cookies.get('voicehire_lang')
        if cookie_lang:
            session['lang'] = get_verified_language(cookie_lang)
        else:
            session['lang'] = DEFAULT_LANGUAGE

@app.context_processor
def inject_translation():
    lang = session.get('lang', DEFAULT_LANGUAGE)
    return dict(
        t=lambda text, **kwargs: get_translation(lang, text, **kwargs),
        format_currency=lambda amt, include_words=False: format_currency(amt, lang, include_words=include_words),
        format_date=lambda d, fmt='medium': format_date(d, lang, fmt),
        format_number=lambda n: format_number(n, lang),
        format_relative_time=lambda dt: format_relative_time(dt, lang),
        localized_status=lambda s: get_localized_status(s, lang),
        localized_validation=lambda k: get_localized_validation(k, lang),
        current_lang=lang,
        verified_languages=VERIFIED_LANGUAGES
    )

@app.route('/set_lang/<lang_code>', methods=['GET', 'POST'])
def set_lang(lang_code):
    clean_code = get_verified_language(lang_code)
    session['lang'] = clean_code

    # If logged in, persist to database
    if 'user_id' in session:
        uid = session['user_id']
        role = session.get('role', 'user')
        try:
            tbl = 'workers' if role == 'worker' else 'users'
            supabase.table(tbl).update({'language_preference': clean_code}).eq('id', uid).execute()
        except Exception:
            pass

    is_ajax = (
        request.headers.get('Accept') == 'application/json' or
        request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
        request.args.get('format') == 'json' or
        request.is_json
    )
    if is_ajax:
        resp = jsonify({'success': True, 'lang': clean_code})
    else:
        target = request.referrer or url_for('index')
        resp = redirect(target)

    resp.set_cookie('voicehire_lang', clean_code, max_age=30*24*3600, path='/', samesite='Lax')
    return resp

@app.route('/api/translations', methods=['GET'])
def get_translations_api():
    """Retrieve full translation bundle and localization metadata for active or requested language."""
    requested_lang = request.args.get('lang') or session.get('lang', DEFAULT_LANGUAGE)
    clean_lang = get_verified_language(requested_lang)
    translations_bundle = get_all_translations_for_lang(clean_lang)
    return jsonify({
        'lang': clean_lang,
        'default_language': DEFAULT_LANGUAGE,
        'verified_languages': VERIFIED_LANGUAGES,
        'translations': translations_bundle
    }), 200

# ---- TEMPLATE ROUTES ----

@app.route('/')
def index():
    """Landing page with integrated language selector and hero."""
    if 'user_id' in session:
        role = session.get('role')
        return redirect(url_for('user_dashboard' if role == 'user' else 'worker_dashboard'))
    return render_template('gateway.html')

@app.route('/home')
def home():
    return redirect(url_for('index'))

@app.route('/gateway')
def gateway():
    return redirect(url_for('index'))

@app.route('/welcome')
def welcome():
    return redirect(url_for('index'))

@app.route('/role')
def role_selection():
    return redirect(url_for('signup'))

@app.route('/signup')
def signup():
    """Role selection page before signup."""
    if 'user_id' in session:
        role = session.get('role')
        return redirect(url_for('user_dashboard' if role == 'user' else 'worker_dashboard'))
    return render_template('signup_role.html')

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
    return redirect(url_for('worker_dashboard'))

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
        hour = datetime.utcnow().hour + 5  # IST offset
        if hour < 12:
            time_of_day = 'Morning'
        elif hour < 17:
            time_of_day = 'Afternoon'
        else:
            time_of_day = 'Evening'
        return render_template('worker_dashboard.html', worker=worker_data, time_of_day=time_of_day)
    except Exception as e:
        return f"Database error: {e}"

@app.route('/scan')
def scan_page():
    if 'user_id' not in session or session.get('role') != 'worker':
        return redirect(url_for('login_page', role='worker'))
    return render_template('scan.html')

@app.route('/complete-job/<token>', methods=['GET'])
def complete_job_via_qr(token):
    if 'user_id' not in session or session.get('role') != 'worker':
        session['qr_token_pending'] = token
        return redirect(url_for('login_page', role='worker'))
    try:
        job_resp = supabase.table("jobs").select("*").eq("completion_token", token).execute()
        if not job_resp.data:
            return render_template('qr_result.html', success=False, message="Invalid or already used QR code.")
        job = job_resp.data[0]
        if job.get('token_expires_at'):
            expires = datetime.fromisoformat(job['token_expires_at'].replace('Z',''))
            if datetime.utcnow() > expires:
                return render_template('qr_result.html', success=False, message="This QR code has expired.")
        if job['worker_id'] != session['user_id']:
            return render_template('qr_result.html', success=False, message="This QR code is not assigned to you.")
        if job['status'] != 'accepted':
            status = job['status']
            return render_template('qr_result.html', success=False, message=f"Job is already {status}.")
        supabase.table("jobs").update({
            "status": "pending_confirmation",
            "completion_token": None   # Invalidate — one-time use only
        }).eq("id", job['id']).execute()
        return render_template('qr_result.html', success=True,
            message="Job marked as done! The customer will confirm to complete.")
    except Exception as e:
        import traceback; print(traceback.format_exc())
        return render_template('qr_result.html', success=False, message="Server error.")

# ---- AUTHENTICATION API ENDPOINTS ----

@app.route('/api/auth/signup/user', methods=['POST'])
def signup_user():
    data = (request.get_json(silent=True) if request.is_json else None) or {}
    name = safe_str(request.form.get('name') or data.get('name'))
    phone = safe_str(request.form.get('phone') or data.get('phone'))
    password = safe_str(request.form.get('password') or data.get('password'))

    if not all([name, phone, password]):
        return jsonify({'error': 'All fields are required'}), 400
    if not is_valid_phone(phone):
        return jsonify({'error': 'Invalid Indian phone number (10 digits starting with 6-9)'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400

    hashed_pw = generate_password_hash(password)
    try:
        # Cross-role duplicate check
        existing_user = supabase.table("users").select("id").eq("phone", phone).execute()
        if existing_user.data:
            return jsonify({'error': 'This mobile number is already registered as an Employer. Please log in.'}), 400

        existing_worker = supabase.table("workers").select("id").eq("phone", phone).execute()
        if existing_worker.data:
            return jsonify({'error': 'This mobile number is already registered as a Worker. Please log in with your Worker account or use a different number.'}), 400

        profile_pic = request.files.get('profile_pic')
        profile_pic_path = None
        if profile_pic and profile_pic.filename != '':
            if not allowed_file(profile_pic.filename, ALLOWED_IMAGE_EXTENSIONS):
                return jsonify({'error': 'Invalid image file type for profile picture'}), 400
            filename = f"{uuid.uuid4().hex}_{secure_filename(profile_pic.filename)}"
            profile_pic.save(os.path.join(PROFILE_PIC_FOLDER, filename))
            profile_pic_path = f'uploads/profile_pics/{filename}'

        insert_data = {
            "name": name,
            "phone": phone,
            "password": hashed_pw,
            "profile_pic": profile_pic_path
        }
        
        try:
            response = supabase.table("users").insert(insert_data).execute()
        except Exception as e:
            if 'profile_pic' in str(e).lower():
                insert_data.pop('profile_pic', None)
                response = supabase.table("users").insert(insert_data).execute()
            else: raise e

        user_id = response.data[0]['id']
        # Session rotation & authoritative role persistence with language preservation
        cur_lang = session.get('lang') or request.cookies.get('voicehire_lang') or DEFAULT_LANGUAGE
        clean_lang = get_verified_language(cur_lang)
        session.clear()
        session['user_id'] = user_id
        session['role'] = 'user'
        session['name'] = name
        session['phone'] = phone
        session['lang'] = clean_lang

        resp = jsonify({
            'message': 'User registered successfully',
            'role': 'user',
            'user_id': user_id,
            'user': {'id': user_id, 'name': name},
            'redirect': url_for('user_dashboard'),
            'lang': clean_lang
        })
        resp.set_cookie('voicehire_lang', clean_lang, max_age=30*24*3600, path='/', samesite='Lax')
        return resp, 201
    except Exception as e:
        print("Error during user signup:\n", traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500

@app.route('/api/auth/signup/worker', methods=['POST'])
def signup_worker():
    data = (request.get_json(silent=True) if request.is_json else None) or {}
    name = safe_str(request.form.get('name') or data.get('name'))
    work = safe_str(request.form.get('work') or data.get('work'))
    location = safe_str(request.form.get('location') or data.get('location') or 'Delhi NCR')
    phone = safe_str(request.form.get('phone') or data.get('phone'))
    password = safe_str(request.form.get('password') or data.get('password'))

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
        # Cross-role duplicate check
        existing_worker = supabase.table("workers").select("id").eq("phone", phone).execute()
        if existing_worker.data:
            return jsonify({'error': 'This mobile number is already registered as a Worker. Please log in.'}), 400

        existing_user = supabase.table("users").select("id").eq("phone", phone).execute()
        if existing_user.data:
            return jsonify({'error': 'This mobile number is already registered as an Employer. Please log in with your Employer account or use a different number.'}), 400

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
        price = safe_str(request.form.get('price', '0'))
        
        insert_data = {
            "name": name,
            "work": work,
            "location": location,
            "phone": phone,
            "password": hashed_pw,
            "voice_note": voice_path,
            "video": video_path,
            "id_proof_path": id_path,
            "profile_pic": profile_pic_path,
            "latitude": float(lat) if lat else None,
            "longitude": float(lng) if lng else None,
            "price": float(price) if price else 0,
            "is_available": True,
            "is_verified": False
        }

        try:
            response = supabase.table("workers").insert(insert_data).execute()
        except Exception as e:
            if 'profile_pic' in str(e).lower():
                insert_data.pop('profile_pic', None)
                response = supabase.table("workers").insert(insert_data).execute()
            else: raise e

        worker_id = response.data[0]['id']
        # Session rotation & authoritative role persistence with language preservation
        cur_lang = session.get('lang') or request.cookies.get('voicehire_lang') or DEFAULT_LANGUAGE
        clean_lang = get_verified_language(cur_lang)
        session.clear()
        session['user_id'] = worker_id
        session['role'] = 'worker'
        session['name'] = name
        session['phone'] = phone
        session['lang'] = clean_lang

        resp = jsonify({
            'message': 'Worker registered successfully',
            'role': 'worker',
            'worker_id': worker_id,
            'worker': {'id': worker_id, 'name': name},
            'redirect': url_for('worker_dashboard'),
            'lang': clean_lang
        })
        resp.set_cookie('voicehire_lang', clean_lang, max_age=30*24*3600, path='/', samesite='Lax')
        return resp, 201
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
        return jsonify({'error': 'Valid phone, password, and role ("user" or "worker") are required'}), 400

    if not is_valid_phone(phone):
        return jsonify({'error': 'Invalid Indian phone number (10 digits starting with 6-9)'}), 400

    # Brute-force & rate-limiting protection
    client_ip = request.remote_addr or 'unknown'
    rate_key = f"{phone}:{client_ip}"
    is_locked, rem_secs = auth_shield.is_locked(rate_key)
    if not is_locked:
        is_locked, rem_secs = auth_shield.is_locked(phone)

    if is_locked:
        return jsonify({
            'error': f'Too many failed login attempts. Please wait {rem_secs} seconds before trying again.',
            'lockout': True,
            'retry_after': rem_secs
        }), 429

    primary_table = 'users' if role == 'user' else 'workers'
    alternate_role = 'worker' if role == 'user' else 'user'
    alternate_table = 'workers' if role == 'user' else 'users'

    try:
        # Check primary role table
        response = supabase.table(primary_table).select("*").eq("phone", phone).execute()
        rows = response.data

        if rows and check_password_hash(rows[0]['password'], password):
            user = rows[0]
            # Reset rate limits on success
            auth_shield.record_success(rate_key)
            auth_shield.record_success(phone)

            # Prevent session fixation by rotating session while preserving language preference
            saved_lang = user.get('language_preference') or session.get('lang') or request.cookies.get('voicehire_lang') or DEFAULT_LANGUAGE
            clean_lang = get_verified_language(saved_lang)
            session.clear()
            session['user_id'] = user['id']
            session['role'] = role
            session['name'] = user['name']
            session['phone'] = user['phone']
            session['lang'] = clean_lang

            redirect_url = url_for('user_dashboard') if role == 'user' else url_for('worker_dashboard')
            resp = jsonify({
                'message': 'Login successful',
                'role': role,
                'redirect': redirect_url,
                'lang': clean_lang
            })
            resp.set_cookie('voicehire_lang', clean_lang, max_age=30*24*3600, path='/', samesite='Lax')
            return resp, 200

        # Primary failed: Check if user exists in the alternate role table
        alt_response = supabase.table(alternate_table).select("*").eq("phone", phone).execute()
        alt_rows = alt_response.data

        if alt_rows:
            # Role mismatch detected!
            auth_shield.record_failure(rate_key)
            auth_shield.record_failure(phone)

            detected_role_label = 'Worker' if alternate_role == 'worker' else 'Employer'
            requested_role_label = 'Employer' if role == 'user' else 'Worker'
            switch_url = url_for('login_page', role=alternate_role)

            return jsonify({
                'error': 'role_mismatch',
                'message': f'This mobile number is registered as a {detected_role_label}, not an {requested_role_label}. Please log in as {detected_role_label}.',
                'requested_role': role,
                'detected_role': alternate_role,
                'switch_url': switch_url
            }), 403

        # Neither table matched or password incorrect
        locked, rem = auth_shield.record_failure(rate_key)
        auth_shield.record_failure(phone)
        if locked:
            return jsonify({
                'error': f'Too many failed login attempts. Please wait {rem} seconds before trying again.',
                'lockout': True,
                'retry_after': rem
            }), 429

        return jsonify({'error': 'Invalid phone or password'}), 401
    except Exception as e:
        print("Error during login:\n", traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500

@app.route('/api/auth/session', methods=['GET'])
def get_auth_session():
    """Returns the authoritative session details from server."""
    user_id = session.get('user_id')
    role = session.get('role')
    if not user_id or not role:
        return jsonify({'authenticated': False, 'role': None, 'user': None}), 200

    table = 'users' if role == 'user' else 'workers'
    try:
        resp = try_select(table, "*", filters={"id": user_id})
        if not resp.data:
            session.clear()
            return jsonify({'authenticated': False, 'role': None, 'user': None}), 200

        user_data = dict(resp.data[0])
        user_data.pop('password', None)  # Never leak password hash
        return jsonify({
            'authenticated': True,
            'role': role,
            'user_id': user_id,
            'user': user_data
        }), 200
    except Exception as e:
        return jsonify({'error': 'Server error fetching session'}), 500

# ---- ACCOUNT RECOVERY ENDPOINTS ----

@app.route('/forgot-password')
def forgot_password_page():
    role = request.args.get('role', 'worker')
    if role not in ['user', 'worker']:
        role = 'worker'
    return render_template('forgot_password.html', role=role)

@app.route('/api/auth/forgot-password/request', methods=['POST'])
def forgot_password_request():
    try:
        data = request.get_json() or {}
    except Exception:
        return jsonify({'error': 'Invalid JSON data'}), 400

    phone = safe_str(data.get('phone'))
    role = safe_str(data.get('role', 'worker'))

    if not phone or not is_valid_phone(phone):
        return jsonify({'error': 'Please provide a valid 10-digit Indian mobile number'}), 400
    if role not in ['user', 'worker']:
        return jsonify({'error': 'Invalid role specified'}), 400

    # Rate limiting on recovery requests
    rate_key = f"recovery:{phone}"
    is_locked, rem_secs = auth_shield.is_locked(rate_key)
    if is_locked:
        return jsonify({'error': f'Too many reset requests. Please wait {rem_secs} seconds.'}), 429

    table = 'users' if role == 'user' else 'workers'
    resp = supabase.table(table).select("id, name").eq("phone", phone).execute()

    if not resp.data:
        # Check if registered under the alternate role
        alt_table = 'workers' if role == 'user' else 'users'
        alt_role = 'worker' if role == 'user' else 'user'
        alt_resp = supabase.table(alt_table).select("id, name").eq("phone", phone).execute()
        if alt_resp.data:
            alt_name = 'Worker' if alt_role == 'worker' else 'Employer'
            return jsonify({
                'error': 'role_mismatch',
                'message': f'This mobile number is registered as a {alt_name}. Please request account recovery for {alt_name}.',
                'detected_role': alt_role,
                'switch_url': url_for('forgot_password_page', role=alt_role)
            }), 403

        auth_shield.record_failure(rate_key)
        return jsonify({'error': 'No account found with this phone number. Please check the number or sign up.'}), 404

    # Generate OTP via recovery_manager
    otp = recovery_manager.create_recovery_request(phone, role)

    res_data = {
        'message': f'Verification code sent to {phone[:2]}******{phone[-2:]}. Code is valid for 5 minutes.',
        'phone': phone,
        'role': role
    }
    # In testing or debug mode provide code for programmatic verification
    if app.config.get('TESTING') or app.debug:
        res_data['demo_otp'] = otp

    return jsonify(res_data), 200

@app.route('/api/auth/forgot-password/verify', methods=['POST'])
def forgot_password_verify():
    try:
        data = request.get_json() or {}
    except Exception:
        return jsonify({'error': 'Invalid JSON data'}), 400

    phone = safe_str(data.get('phone'))
    role = safe_str(data.get('role', 'worker'))
    otp = safe_str(data.get('otp'))

    if not all([phone, role, otp]):
        return jsonify({'error': 'Phone, role, and OTP are required'}), 400

    success, status, reset_token = recovery_manager.verify_otp(phone, role, otp)
    if not success:
        if status == 'expired':
            return jsonify({'error': 'Verification code has expired. Please request a new code.', 'expired': True}), 400
        elif status == 'too_many_attempts':
            return jsonify({'error': 'Too many incorrect attempts. This code has been invalidated. Please request a new code.', 'invalidated': True}), 400
        elif status == 'no_request_found':
            return jsonify({'error': 'No active recovery request found. Please request a new code.'}), 400
        else:
            return jsonify({'error': 'Invalid verification code. Please check and try again.'}), 400

    return jsonify({
        'message': 'Code verified successfully. You may now enter a new password.',
        'reset_token': reset_token
    }), 200

@app.route('/api/auth/forgot-password/reset', methods=['POST'])
def forgot_password_reset():
    try:
        data = request.get_json() or {}
    except Exception:
        return jsonify({'error': 'Invalid JSON data'}), 400

    phone = safe_str(data.get('phone'))
    role = safe_str(data.get('role', 'worker'))
    reset_token = safe_str(data.get('reset_token'))
    new_password = safe_str(data.get('new_password'))

    if not all([phone, role, reset_token, new_password]):
        return jsonify({'error': 'All fields are required'}), 400
    if len(new_password) < 6:
        return jsonify({'error': 'New password must be at least 6 characters'}), 400

    valid = recovery_manager.verify_and_consume_reset_token(phone, role, reset_token)
    if not valid:
        return jsonify({'error': 'Invalid or expired reset token. Please restart password recovery.'}), 400

    table = 'users' if role == 'user' else 'workers'
    hashed_pw = generate_password_hash(new_password)
    try:
        supabase.table(table).update({'password': hashed_pw}).eq('phone', phone).execute()
        # Invalidate any active session for safety
        session.clear()
        return jsonify({
            'message': 'Password has been reset successfully! You can now log in.',
            'redirect': url_for('login_page', role=role)
        }), 200
    except Exception as e:
        print("Error resetting password:\n", traceback.format_exc())
        return jsonify({'error': 'Failed to update password. Please try again.'}), 500

@app.route('/api/auth/logout', methods=['POST'])
def logout_api():
    session.clear()
    return jsonify({'message': 'Logged out successfully', 'redirect': url_for('role_selection')}), 200

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# ---- DATA API ENDPOINTS ----

@app.route('/api/worker/edit', methods=['POST'])
def edit_worker_profile():
    if 'user_id' not in session or session['role'] != 'worker':
        return jsonify({'error': 'Unauthorized'}), 401

    name = safe_str(request.form.get('name'))
    work = safe_str(request.form.get('work'))
    location = safe_str(request.form.get('location'))
    phone = safe_str(request.form.get('phone'))
    password = safe_str(request.form.get('password'))

    if not all([name, work, location, phone]):
        return jsonify({'error': 'Name, work, location, and phone are required'}), 400
    if not is_valid_phone(phone):
        return jsonify({'error': 'Invalid Indian phone number'}), 400

    worker_id = session['user_id']
    voice_file = request.files.get('voice_note')
    video_file = request.files.get('video')

    try:
        existing_resp = supabase.table("workers").select("voice_note, video, id_proof_path").eq("id", worker_id).execute()
        if not existing_resp.data:
            return jsonify({'error': 'Worker not found'}), 404
        existing = existing_resp.data[0]

        voice_path = existing.get('voice_note')
        video_path = existing.get('video')
        id_path = existing.get('id_proof_path')
        profile_pic_path = existing.get('profile_pic')

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
        price = safe_str(request.form.get('price'))

        update_data = {
            "name": name,
            "work": work,
            "location": location,
            "phone": phone,
            "voice_note": voice_path,
            "video": video_path,
            "id_proof_path": id_path,
            "profile_pic": profile_pic_path,
            "latitude": float(lat) if lat else None,
            "longitude": float(lng) if lng else None,
        }

        if price:
            update_data["price"] = float(price)

        if password:
            if len(password) < 6:
                return jsonify({'error': 'Password must be at least 6 characters'}), 400
            update_data["password"] = generate_password_hash(password)

        try:
            supabase.table("workers").update(update_data).eq("id", worker_id).execute()
        except Exception as e:
            if 'profile_pic' in str(e).lower():
                update_data.pop('profile_pic', None)
                supabase.table("workers").update(update_data).eq("id", worker_id).execute()
            else:
                raise e
        session['name'] = name
        return jsonify({'message': 'Profile updated successfully', 'redirect': url_for('worker_dashboard')}), 200
    except Exception as e:
        print("Error updating profile:\n", traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500

@app.route('/api/worker/voice-resume', methods=['POST'])
def save_voice_resume():
    if 'user_id' not in session or session.get('role') != 'worker':
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json() or {}
    text = safe_str(data.get('resume_text', ''))
    if not text: return jsonify({'error': 'Text required'}), 400
    if len(text) > 1000: return jsonify({'error': 'Max 1000 characters'}), 400
    supabase.table("workers").update({"voice_resume": text}).eq("id", session['user_id']).execute()
    return jsonify({'message': 'Saved'}), 200

@app.route('/api/worker/location', methods=['POST'])
def update_worker_location():
    if 'user_id' not in session or session.get('role') != 'worker':
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json() or {}
    lat, lng = data.get('lat'), data.get('lng')
    if lat is None or lng is None: return jsonify({'error': 'lat and lng required'}), 400
    supabase.table("workers").update({
        "live_lat": float(lat), "live_lng": float(lng),
        "is_sharing_location": True, "location_updated_at": "now()"
    }).eq("id", session['user_id']).execute()
    return jsonify({'message': 'Updated'}), 200

@app.route('/api/worker/location/stop', methods=['POST'])
def stop_sharing_location():
    if 'user_id' not in session or session.get('role') != 'worker':
        return jsonify({'error': 'Unauthorized'}), 401
    supabase.table("workers").update({
        "is_sharing_location": False, "live_lat": None, "live_lng": None
    }).eq("id", session['user_id']).execute()
    return jsonify({'message': 'Stopped'}), 200

@app.route('/api/worker/availability', methods=['POST'])
def update_availability():
    if 'user_id' not in session or session['role'] != 'worker':
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        data = request.get_json() or {}
        is_available = bool(data.get('is_available'))
        worker_id = session['user_id']
        supabase.table("workers").update({"is_available": is_available}).eq("id", worker_id).execute()
        return jsonify({'message': 'Availability updated', 'is_available': is_available}), 200
    except Exception as e:
        print("Error updating availability:\n", traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500

@app.route('/api/worker/profile', methods=['GET'])
def get_worker_profile():
    """Return profile summary, skills, completeness, availability and verification status for the authenticated worker."""
    if 'user_id' not in session or session.get('role') != 'worker':
        return jsonify({'error': 'Unauthorized: Worker access only'}), 401
    try:
        worker_id = session['user_id']
        resp = supabase.table("workers").select("*").eq("id", worker_id).execute()
        if not resp.data:
            return jsonify({'error': 'Worker not found'}), 404
        worker = resp.data[0]
        # Never leak password hash
        worker.pop('password', None)
        worker.pop('password_hash', None)

        # Attach worker skills
        skills = WorkerSkillsManager.get_worker_skills(supabase, worker_id)
        worker['skills'] = skills

        # Mask payout VPA for safety
        vpa = worker.get('payout_vpa')
        if vpa:
            if '@' in str(vpa):
                u, d = str(vpa).split('@', 1)
                worker['payout_vpa_masked'] = f"{u[:2]}***{u[-1]}@{d}" if len(u) > 3 else f"***@{d}"
            else:
                worker['payout_vpa_masked'] = "Configured"

        # Calculate profile completeness
        completeness = WorkerProfileManager.calculate_completeness(worker, skills)
        worker['completeness'] = completeness
        worker['profile_completeness'] = completeness['score']

        # Payout readiness
        gw_ok, _ = RazorpayGatewayService.is_gateway_configured()
        worker['is_payout_ready'] = bool(worker.get('payout_vpa') and worker.get('payout_status') == 'active' and gw_ok)

        return jsonify(worker), 200
    except Exception as e:
        print("Error fetching worker profile:\n", traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/worker/profile', methods=['POST'])
def update_worker_profile_api():
    """
    POST /api/worker/profile
    Worker edits public display info, trade categories, pricing, quote preferences, and service area.
    """
    if 'user_id' not in session or session.get('role') != 'worker':
        return jsonify({'error': 'Unauthorized: Worker access only'}), 401

    worker_id = session['user_id']
    try:
        data = request.get_json(silent=True) or request.form.to_dict() or {}
    except Exception:
        data = {}

    updates = {"updated_at": utc_now_iso()}
    allowed_fields = [
        'name', 'work', 'location', 'phone', 'price',
        'service_radius_km', 'quote_preference', 'bio', 'experience_years', 'language_preference'
    ]

    for field in allowed_fields:
        if field in data and data[field] not in (None, ''):
            val = data[field]
            if field in ('price', 'experience_years', 'service_radius_km'):
                try:
                    updates[field] = float(val) if field == 'price' else int(val)
                except (ValueError, TypeError):
                    pass
            elif field == 'phone':
                clean_phone = safe_str(val)
                if not is_valid_phone(clean_phone):
                    return jsonify({'error': 'Invalid Indian phone number (10 digits starting with 6-9)'}), 400
                updates[field] = clean_phone
            elif field == 'quote_preference':
                q_pref = str(val).strip().lower()
                if q_pref in ('fixed_only', 'estimate_then_confirm', 'inspection_required'):
                    updates['quote_preference'] = q_pref
            elif field == 'language_preference':
                clean_lang = get_verified_language(val)
                updates['language_preference'] = clean_lang
                session['lang'] = clean_lang
            else:
                updates[field] = safe_str(val)

    if not updates or len(updates) <= 1:
        return jsonify({'error': 'No valid fields provided for update'}), 400

    try:
        resp = supabase.table("workers").update(updates).eq("id", worker_id).execute()
        if not resp.data:
            return jsonify({'error': 'Worker record not found'}), 404

        updated_worker = resp.data[0]
        updated_worker.pop('password', None)
        updated_worker.pop('password_hash', None)

        if 'name' in updates:
            session['name'] = updates['name']

        skills = WorkerSkillsManager.get_worker_skills(supabase, worker_id)
        completeness = WorkerProfileManager.calculate_completeness(updated_worker, skills)
        updated_worker['completeness'] = completeness

        AuditLogger.log_event(
            supabase, actor_id=worker_id, actor_role="worker",
            event_type="profile_update", resource_type="worker",
            resource_id=worker_id, action="update_profile",
            ip_address=request.remote_addr, metadata={"updated_fields": list(updates.keys())}
        )

        return jsonify({
            'message': 'Profile updated successfully',
            'worker': updated_worker,
            'completeness': completeness
        }), 200
    except Exception as e:
        print(f"Error updating worker profile: {e}\n{traceback.format_exc()}")
        return jsonify({'error': f'Server error: {e}'}), 500


@app.route('/api/worker/verification', methods=['POST'])
def submit_worker_verification():
    """
    POST /api/worker/verification
    Worker submits government ID proof or trade certification.
    Sets status to 'pending' / 'under_review'.
    CRITICAL: Never automatically marks as verified! Requires human review.
    """
    if 'user_id' not in session or session.get('role') != 'worker':
        return jsonify({'error': 'Unauthorized: Worker access only'}), 401

    worker_id = session['user_id']
    doc_type = safe_str(request.form.get('verification_type') or request.form.get('doc_type', 'trade_license')).lower()
    id_file = request.files.get('id_proof') or request.files.get('document')

    if not id_file or id_file.filename == '':
        return jsonify({'error': 'Verification document file is required'}), 400

    if not allowed_file(id_file.filename, ALLOWED_IMAGE_EXTENSIONS | {'pdf'}):
        return jsonify({'error': 'Invalid file type. Allowed: PNG, JPG, JPEG, WEBP, PDF'}), 400

    filename = f"{uuid.uuid4().hex}_{secure_filename(id_file.filename)}"
    save_path = os.path.join(ID_FOLDER, filename)
    id_file.save(save_path)
    doc_url = f"uploads/ids/{filename}"

    success, msg, result = WorkerProfileManager.submit_verification(
        supabase, worker_id=worker_id, doc_type=doc_type, doc_path=doc_url
    )
    if not success:
        return jsonify({'error': msg}), 400

    return jsonify({
        'message': msg,
        'verification_status': 'pending',
        'is_verified': False,
        'verification_type': doc_type,
        'success': True
    }), 200

@app.route('/api/worker/service-area', methods=['POST'])
def update_worker_service_area():
    """Update worker's registered locality, service radius, or coordinates."""
    if 'user_id' not in session or session.get('role') != 'worker':
        return jsonify({'error': 'Unauthorized: Worker access only'}), 401
    try:
        data = request.get_json() or {}
        location = safe_str(data.get('location'))
        radius_km = data.get('radius_km')
        lat = data.get('lat')
        lng = data.get('lng')
        worker_id = session['user_id']

        updates = {"updated_at": datetime.utcnow().isoformat()}
        if location:
            updates['location'] = location
        if radius_km not in (None, ''):
            try:
                updates['service_radius_km'] = int(radius_km)
            except (ValueError, TypeError):
                pass
        if lat not in (None, '') and lng not in (None, ''):
            try:
                updates['latitude'] = float(lat)
                updates['longitude'] = float(lng)
            except (ValueError, TypeError):
                pass

        supabase.table("workers").update(updates).eq("id", worker_id).execute()
        return jsonify({
            'message': 'Service area updated successfully',
            'location': updates.get('location'),
            'radius_km': updates.get('service_radius_km')
        }), 200
    except Exception as e:
        print("Error updating service area:\n", traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500

@app.route('/get_workers', methods=['GET'])
@app.route('/api/workers', methods=['GET'])
def get_workers():
    work_filter = safe_str(request.args.get('work') or request.args.get('category'))
    skill_filter = safe_str(request.args.get('skill')).lower()
    location_filter = safe_str(request.args.get('location') or request.args.get('locality'))
    available_only = request.args.get('available_only', '').lower() in ('true', '1', 'yes')

    try:
        min_rating = float(request.args.get('min_rating', 0))
    except (ValueError, TypeError):
        min_rating = 0.0

    cust_lat = request.args.get('lat')
    cust_lng = request.args.get('lng')
    radius_arg = request.args.get('radius_km')
    radius_km = float(radius_arg) if radius_arg and radius_arg != 'all' else None
    sort_by = safe_str(request.args.get('sort_by', 'relevance')).lower()

    try:
        query = supabase.table("workers").select("*")

        if work_filter and work_filter.lower() != 'all':
            query = query.ilike("work", f"%{work_filter}%")
        if location_filter:
            query = query.ilike("location", f"%{location_filter}%")

        workers_resp = query.execute()
        workers = workers_resp.data or []

        # If skill filter provided, match against worker_skills table
        if skill_filter:
            try:
                skills_resp = supabase.table("worker_skills").select("worker_id, skill_name").execute()
                skill_matching_ids = {
                    s['worker_id'] for s in (skills_resp.data or [])
                    if skill_filter in safe_str(s.get('skill_name')).lower()
                }
                workers = [
                    w for w in workers
                    if w['id'] in skill_matching_ids or skill_filter in safe_str(w.get('work')).lower()
                ]
            except Exception:
                pass

        # Fetch reviews to compute aggregate ratings
        try:
            reviews_resp = supabase.table("reviews").select("worker_id, rating").execute()
            review_map = defaultdict(list)
            for r in (reviews_resp.data or []):
                review_map[r['worker_id']].append(r['rating'])
        except Exception:
            review_map = {}

        # Enrich workers with rating, review count, and distance
        processed = []
        for w in workers:
            ratings = review_map.get(w['id'], [])
            w['avg_rating'] = round(sum(ratings) / len(ratings), 1) if ratings else (float(w.get('avg_rating', 5.0) or 5.0))
            w['review_count'] = len(ratings)

            # Availability filter
            if available_only and not w.get('is_available', True):
                continue

            # Rating filter
            if min_rating > 0 and w['avg_rating'] < min_rating:
                continue

            # Distance calculation
            w_lat = w.get('latitude') or w.get('live_lat')
            w_lng = w.get('longitude') or w.get('live_lng')
            dist = None
            if cust_lat not in (None, '', 'undefined') and cust_lng not in (None, '', 'undefined') and w_lat and w_lng:
                try:
                    dist = LocationPrivacyShield.calculate_distance_km(float(cust_lat), float(cust_lng), float(w_lat), float(w_lng))
                except Exception:
                    dist = None

            w['distance_km'] = dist

            # Radius filter
            if radius_km is not None and dist is not None:
                if dist > radius_km:
                    continue

            processed.append(w)

        # Sorting
        if sort_by == 'distance':
            processed.sort(key=lambda w: (
                w.get('distance_km') if w.get('distance_km') is not None else 99999,
                -w['avg_rating']
            ))
        elif sort_by == 'rating':
            processed.sort(key=lambda w: (-w['avg_rating'], -w['review_count']))
        elif sort_by == 'price_asc':
            processed.sort(key=lambda w: (float(w.get('price') or 0), -w['avg_rating']))
        elif sort_by == 'price_desc':
            processed.sort(key=lambda w: (-float(w.get('price') or 0), -w['avg_rating']))
        else:
            # Relevance: available first, then closest distance if available, then rating
            processed.sort(key=lambda w: (
                not w.get('is_available', True),
                w.get('distance_km') if w.get('distance_km') is not None else 99999,
                -w['avg_rating'],
                -w['review_count']
            ))

        # Pagination support
        try:
            page = max(1, int(request.args.get('page', 1)))
        except (ValueError, TypeError):
            page = 1

        raw_limit = request.args.get('limit')
        if raw_limit:
            try:
                limit = max(1, min(100, int(raw_limit)))
            except (ValueError, TypeError):
                limit = 20
            start_idx = (page - 1) * limit
            processed = processed[start_idx:start_idx + limit]

        # Obfuscate privacy-sensitive coordinates and fields for public browsing
        sanitized = []
        for w in processed:
            dist_val = w.get('distance_km')
            s = LocationPrivacyShield.obfuscate_worker_profile(w, viewer_is_counterparty=False)
            s['avg_rating'] = w['avg_rating']
            s['review_count'] = w['review_count']
            if dist_val is not None:
                s['distance_km'] = dist_val
            sanitized.append(s)

        return jsonify(sanitized), 200
    except Exception as e:
        print("Error fetching workers:\n", traceback.format_exc())
        return jsonify([]), 200

@app.route('/api/workers/<worker_id>', methods=['GET'])
def get_worker_profile_detail(worker_id):
    """
    Returns authentic profile for a worker:
    trade, bio, service radius, pricing, skills, completed job counts, real verified reviews,
    real verification status, and payment readiness.
    """
    try:
        resp = supabase.table("workers").select("*").eq("id", worker_id).execute()
        if not resp.data:
            return jsonify({'error': 'Worker not found'}), 404
        worker = resp.data[0]

        uid = session.get('user_id')
        # Check if caller has blocked or is blocked by this worker
        if uid and TrustAndSafetyManager.is_blocked(supabase, uid, worker_id):
            return jsonify({'error': 'User profile unavailable due to an active account block'}), 403

        # Check if viewer is an active confirmed booking counterparty
        viewer_is_counterparty = False
        if uid:
            try:
                confirmed_bkg = supabase.table("bookings").select("id").eq("worker_id", worker_id).eq("customer_id", uid).in_("status", ["Booked", "On The Way", "Arrived", "Work Started", "Completed", "Payment Pending", "Paid"]).execute()
                if confirmed_bkg.data:
                    viewer_is_counterparty = True
            except Exception:
                viewer_is_counterparty = False

        # Fetch skills
        skills = WorkerSkillsManager.get_worker_skills(supabase, worker_id)

        # Fetch completed bookings count
        try:
            bookings_resp = supabase.table("bookings").select("id").eq("worker_id", worker_id).eq("status", "Completed").execute()
            completed_count = len(bookings_resp.data or [])
        except Exception:
            completed_count = 0

        # Fetch real reviews (no fake seeded reviews!)
        reviews = TrustAndSafetyManager.get_worker_reviews(supabase, worker_id, limit=20)
        if reviews:
            ratings = [r['rating'] for r in reviews if 'rating' in r and r['rating'] is not None]
            avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0.0
            review_count = len(ratings)
        else:
            # Genuine real count: 0 reviews means 0.0 rating and 0 count
            avg_rating = 0.0
            review_count = 0

        # Obfuscate privacy-sensitive info (never expose password, mask phone unless counterparty, never expose raw ID docs)
        sanitized = LocationPrivacyShield.obfuscate_worker_profile(worker, viewer_is_counterparty=viewer_is_counterparty)
        sanitized['skills'] = skills
        sanitized['completed_jobs_count'] = completed_count
        sanitized['reviews'] = reviews
        sanitized['avg_rating'] = avg_rating
        sanitized['review_count'] = review_count

        # Real verification status (never fake auto-verify)
        sanitized['is_verified'] = bool(worker.get('is_verified', False))
        sanitized['verification_status'] = worker.get('verification_status', 'unsubmitted')
        sanitized['quote_preference'] = worker.get('quote_preference', 'estimate_then_confirm')

        # Payment readiness indicator
        gw_ok, _ = RazorpayGatewayService.is_gateway_configured()
        sanitized['payout_ready'] = bool(worker.get('payout_vpa') and worker.get('payout_status') == 'active' and gw_ok)
        sanitized['cash_available'] = True

        # Stage privacy policy explainer
        sanitized['privacy_stage_info'] = LocationPrivacyShield.get_stage_privacy_policy()

        return jsonify(sanitized), 200
    except Exception as e:
        print("Error fetching worker detail:\n", traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500

@app.route('/api/jobs', methods=['POST'])
def post_job():
    if 'user_id' not in session or session['role'] != 'user':
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        data = request.get_json() or {}
    except Exception:
        return jsonify({'error': 'Invalid JSON data'}), 400

    service_type = safe_str(data.get('service_type') or data.get('title'))
    description = safe_str(data.get('description'))
    location = safe_str(data.get('location') or data.get('address'))

    if not service_type or not description or not location:
        return jsonify({'error': 'Service type, description, and location are required'}), 400

    category_id = data.get('category_id')
    try:
        budget_min = float(data.get('budget_min', 0)) if data.get('budget_min') is not None else 0
        budget_max = float(data.get('budget_max', 0)) if data.get('budget_max') is not None else 0
    except (ValueError, TypeError):
        return jsonify({'error': 'Budget values must be numeric'}), 400

    if budget_max > 0 and budget_min > budget_max:
        return jsonify({'error': 'Minimum budget cannot be greater than maximum budget'}), 400

    insert_payload = {
        "user_id": session['user_id'],
        "user_name": session['name'],
        "user_phone": session.get('phone', 'Unknown'),
        "user_profile_pic": session.get('profile_pic'),
        "service_type": service_type,
        "description": description,
        "location": location,
        "is_urgent": bool(data.get('is_urgent')),
        "status": "open"
    }
    if category_id:
        try:
            insert_payload["category_id"] = int(category_id)
        except (ValueError, TypeError):
            pass
    if budget_min > 0:
        insert_payload["budget_min"] = budget_min
    if budget_max > 0:
        insert_payload["budget_max"] = budget_max

    try:
        resp = supabase.table("jobs").insert(insert_payload).execute()
        if not resp.data:
            return jsonify({'error': 'Failed to post job'}), 500

        job = resp.data[0]
        job_id = job.get('id')

        # Log initial status history
        StatusHistoryLogger.log_job_status(
            supabase, job_id, "created", "open", session['user_id'], "user", reason="Job posted by customer"
        )
        # Log audit trail
        AuditLogger.log_event(
            supabase, actor_id=session['user_id'], actor_role="user",
            event_type="job_lifecycle", resource_type="job",
            resource_id=str(job_id), action="create_job",
            ip_address=request.remote_addr, metadata={"service_type": service_type, "location": location}
        )

        return jsonify({'message': 'Job posted successfully!', 'job': job}), 201
    except Exception as e:
        print("Error posting job:\n", traceback.format_exc())
        return jsonify({'error': f'Server error while posting job: {e}'}), 500

@app.route('/api/auth/profile/user', methods=['POST'])
def edit_user_profile():
    if 'user_id' not in session or session['role'] != 'user':
        return jsonify({'error': 'Unauthorized'}), 401

    name = safe_str(request.form.get('name'))
    phone = safe_str(request.form.get('phone'))
    password = safe_str(request.form.get('password'))

    if not all([name, phone]):
        return jsonify({'error': 'Name and phone are required'}), 400

    user_id = session['user_id']
    profile_pic = request.files.get('profile_pic')
    
    try:
        try:
            existing_resp = try_select("users", "profile_pic", filters={"id": user_id})
            existing = existing_resp.data[0]
            profile_pic_path = existing.get('profile_pic')
        except Exception:
            profile_pic_path = None

        if profile_pic and profile_pic.filename != '':
            if not allowed_file(profile_pic.filename, ALLOWED_IMAGE_EXTENSIONS):
                return jsonify({'error': 'Invalid image file type'}), 400
            filename = f"{uuid.uuid4().hex}_{secure_filename(profile_pic.filename)}"
            profile_pic.save(os.path.join(PROFILE_PIC_FOLDER, filename))
            profile_pic_path = f'uploads/profile_pics/{filename}'

        update_data = {
            "name": name,
            "phone": phone,
            "profile_pic": profile_pic_path
        }
        if password:
            update_data["password"] = generate_password_hash(password)

        try:
            supabase.table("users").update(update_data).eq("id", user_id).execute()
        except Exception as e:
            if 'profile_pic' in str(e).lower():
                update_data.pop('profile_pic', None)
                supabase.table("users").update(update_data).eq("id", user_id).execute()
            else: raise e
        session['name'] = name
        return jsonify({'message': 'Profile updated successfully', 'redirect': url_for('user_dashboard')}), 200
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500


# ── Customer Profile & Saved Addresses API ──────────────────────────

@app.route('/api/customer/profile', methods=['GET'])
def get_customer_profile_api():
    """Returns customer contact details, locality, saved addresses, voice settings, and request stats."""
    if 'user_id' not in session or session.get('role') != 'user':
        return jsonify({'error': 'Unauthorized: Customer access only'}), 401
    uid = session['user_id']
    success, msg, profile = CustomerProfileManager.get_profile(supabase, uid)
    if not success:
        return jsonify({'error': msg}), 404
    return jsonify({
        **profile,
        'profile': profile,
        'voice_settings': profile.get('voice_settings'),
        'language_preference': profile.get('language_preference'),
        'locality': profile.get('locality'),
        'saved_addresses': profile.get('saved_addresses', []),
        'total_bookings': profile.get('total_bookings', 0),
        'active_bookings': profile.get('active_bookings', 0),
        'total_payments': profile.get('total_payments', 0),
        'success': True
    }), 200


@app.route('/api/customer/profile', methods=['POST'])
def update_customer_profile_api():
    """Customer updates basic contact information and preferred service locality."""
    if 'user_id' not in session or session.get('role') != 'user':
        return jsonify({'error': 'Unauthorized: Customer access only'}), 401
    uid = session['user_id']
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    name = safe_str(data.get('name'))
    phone = safe_str(data.get('phone'))
    locality = safe_str(data.get('locality'))

    lang_pref = data.get('language_preference') or data.get('lang')

    updates = {"updated_at": utc_now_iso()}
    if name:
        updates['name'] = name
    if phone:
        if not is_valid_phone(phone):
            return jsonify({'error': 'Invalid Indian phone number (10 digits starting with 6-9)'}), 400
        updates['phone'] = phone
    if locality:
        updates['locality'] = locality
    if lang_pref:
        clean_lang = get_verified_language(lang_pref)
        updates['language_preference'] = clean_lang
        session['lang'] = clean_lang

    if len(updates) <= 1:
        return jsonify({'error': 'No fields provided to update'}), 400

    try:
        resp = supabase.table("users").update(updates).eq("id", uid).execute()
        if not resp.data:
            return jsonify({'error': 'Failed to update customer profile'}), 500
        if name:
            session['name'] = name
        user = dict(resp.data[0])
        user.pop('password', None)
        user.pop('password_hash', None)

        AuditLogger.log_event(
            supabase, actor_id=uid, actor_role="user",
            event_type="profile_update", resource_type="user",
            resource_id=uid, action="update_customer_profile",
            ip_address=request.remote_addr, metadata={"updated_fields": list(updates.keys())}
        )

        return jsonify({'message': 'Customer profile updated successfully', 'user': user}), 200
    except Exception as e:
        return jsonify({'error': f'Server error: {e}'}), 500


@app.route('/api/customer/voice-settings', methods=['POST'])
def update_customer_voice_settings():
    """Customer updates preferred language and voice assistant settings (voice, speed, auto_speak)."""
    if 'user_id' not in session or session.get('role') != 'user':
        return jsonify({'error': 'Unauthorized: Customer access only'}), 401
    uid = session['user_id']
    data = request.get_json(silent=True) or {}
    lang = data.get('language_preference') or data.get('lang')
    locality = data.get('locality')
    voice_settings = data.get('voice_settings')

    success, msg, user = CustomerProfileManager.update_settings(
        supabase, uid, locality=locality, language_preference=lang, voice_settings=voice_settings
    )
    if not success:
        return jsonify({'error': msg}), 400

    AuditLogger.log_event(
        supabase, actor_id=uid, actor_role="user",
        event_type="profile_update", resource_type="user",
        resource_id=uid, action="update_voice_settings",
        ip_address=request.remote_addr, metadata={"language": lang}
    )

    return jsonify({'message': msg, 'settings': user, 'success': True}), 200


@app.route('/api/customer/addresses', methods=['GET'])
def get_customer_saved_addresses():
    """List saved addresses for the authenticated customer."""
    if 'user_id' not in session or session.get('role') != 'user':
        return jsonify({'error': 'Unauthorized: Customer access only'}), 401
    uid = session['user_id']
    addresses = CustomerProfileManager.get_saved_addresses(supabase, uid)
    return jsonify(addresses), 200


@app.route('/api/customer/addresses', methods=['POST'])
def add_customer_saved_address():
    """Add a new saved address with label (Home, Work, Other), locality, and street address."""
    if 'user_id' not in session or session.get('role') != 'user':
        return jsonify({'error': 'Unauthorized: Customer access only'}), 401
    uid = session['user_id']
    data = request.get_json(silent=True) or {}
    label = safe_str(data.get('label', 'Home'))
    street = safe_str(data.get('street_address') or data.get('address_line') or data.get('address'))
    locality = safe_str(data.get('locality') or data.get('area') or 'Central')
    city = safe_str(data.get('city', 'Delhi NCR'))
    pincode = safe_str(data.get('pincode', ''))
    landmark = safe_str(data.get('landmark', ''))
    lat = data.get('latitude')
    lng = data.get('longitude')
    is_default = bool(data.get('is_default', False))

    success, msg, address = CustomerProfileManager.add_saved_address(
        supabase, uid, label=label, street_address=street, locality=locality,
        city=city, pincode=pincode, landmark=landmark, latitude=lat, longitude=lng,
        is_default=is_default
    )
    if not success:
        return jsonify({'error': msg}), 400

    AuditLogger.log_event(
        supabase, actor_id=uid, actor_role="user",
        event_type="address", resource_type="customer_saved_address",
        resource_id=str(address.get('id', '')), action="add_saved_address",
        ip_address=request.remote_addr, metadata={"label": label}
    )

    return jsonify({'message': msg, 'address': address, 'success': True}), 201


@app.route('/api/customer/addresses/<int:address_id>', methods=['DELETE'])
@app.route('/api/customer/addresses/<address_id>', methods=['DELETE'])
def delete_customer_saved_address(address_id):
    """Delete a customer's saved address (enforces strict user ownership access control)."""
    if 'user_id' not in session or session.get('role') != 'user':
        return jsonify({'error': 'Unauthorized: Customer access only'}), 401
    uid = session['user_id']
    res = CustomerProfileManager.delete_saved_address(supabase, address_id, uid)
    success, msg = res[0], res[1]
    if not success:
        status_code = 403 if "unauthorized" in msg.lower() else (404 if "not found" in msg.lower() else 400)
        return jsonify({'error': msg}), status_code

    AuditLogger.log_event(
        supabase, actor_id=uid, actor_role="user",
        event_type="address", resource_type="customer_saved_address",
        resource_id=str(address_id), action="delete_saved_address",
        ip_address=request.remote_addr
    )

    return jsonify({'message': msg, 'success': True}), 200

@app.route('/api/jobs', methods=['GET'])
def get_jobs():
    if 'user_id' not in session or session['role'] != 'worker':
        return jsonify({'error': 'Unauthorized'}), 401

    work_type = safe_str(request.args.get('work'))
    location = safe_str(request.args.get('location'))
    worker_id = session['user_id']

    try:
        # Get open jobs
        open_query = supabase.table("jobs").select("*").eq("status", "open")
        if work_type:
            open_query = open_query.ilike("service_type", f"%{work_type}%")
        if location:
            open_query = open_query.ilike("location", f"%{location}%")
        open_resp = open_query.execute()

        # Get accepted jobs for this worker
        accepted_resp = supabase.table("jobs").select("*").eq("status", "accepted").eq("worker_id", worker_id).execute()

        # Apply privacy shield: Customer phone & exact coordinates masked for open jobs
        open_jobs = [
            LocationPrivacyShield.obfuscate_job_request(j, viewer_is_assigned_worker=False)
            for j in (open_resp.data or [])
        ]
        accepted_jobs = [
            LocationPrivacyShield.obfuscate_job_request(j, viewer_is_assigned_worker=True)
            for j in (accepted_resp.data or [])
        ]

        jobs = open_jobs + accepted_jobs
        # Sort: urgent first, then newest first
        jobs.sort(key=lambda j: (not j.get('is_urgent', False), j.get('created_at', '') ), reverse=False)
        jobs.sort(key=lambda j: j.get('is_urgent', False), reverse=True)

        return jsonify(jobs), 200
    except Exception as e:
        print("Error fetching jobs:\n", traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500

@app.route('/api/workers/nearby', methods=['GET'])
def get_nearby_jobs():
    """
    Returns suitable open jobs near the authenticated worker.
    Filters: radius_km, category, category_id, urgent_only, status, time_filter, search.
    Privacy: Customer phone & exact coordinates are shielded before acceptance.
    """
    if 'user_id' not in session or session.get('role') != 'worker':
        return jsonify({'error': 'Unauthorized: Worker access only'}), 401

    worker_id = session['user_id']
    try:
        # 1. Fetch current worker profile
        worker_resp = supabase.table("workers").select("*").eq("id", worker_id).execute()
        if not worker_resp.data:
            return jsonify({'error': 'Worker profile not found'}), 404
        worker = worker_resp.data[0]

        # 2. Extract query parameters
        req_lat = request.args.get('lat')
        req_lng = request.args.get('lng')
        worker_lat = float(req_lat) if req_lat not in (None, '', 'undefined') else (worker.get('live_lat') or worker.get('latitude'))
        worker_lng = float(req_lng) if req_lng not in (None, '', 'undefined') else (worker.get('live_lng') or worker.get('longitude'))

        radius_arg = request.args.get('radius_km')
        radius_km = float(radius_arg) if radius_arg and radius_arg != 'all' else None

        category_filter = safe_str(request.args.get('category') or request.args.get('work'))
        category_id_arg = request.args.get('category_id')
        category_id = int(category_id_arg) if category_id_arg and category_id_arg.isdigit() else None

        urgent_only = request.args.get('urgent_only', '').lower() in ('true', '1', 'yes')
        time_filter = safe_str(request.args.get('time_filter', 'all')).lower()
        search_query = safe_str(request.args.get('search') or request.args.get('locality')).lower()
        status_filter = safe_str(request.args.get('status', 'open')).lower()

        # 3. Query jobs table
        if status_filter == 'accepted':
            query = supabase.table("jobs").select("*").eq("status", "accepted").eq("worker_id", worker_id)
        elif status_filter == 'all':
            query = supabase.table("jobs").select("*").in_("status", ["open", "accepted"])
        else:
            query = supabase.table("jobs").select("*").eq("status", "open")

        if urgent_only:
            query = query.eq("is_urgent", True)
        if category_id:
            query = query.eq("category_id", category_id)

        jobs_resp = query.execute()
        raw_jobs = jobs_resp.data or []

        # 4. Filter, distance calculate and enrich jobs
        processed_jobs = []
        now = datetime.utcnow()

        for j in raw_jobs:
            # Skip if status is accepted but belongs to someone else
            if j.get('status') == 'accepted' and j.get('worker_id') != worker_id:
                continue

            # Category filter (text-based if category_id not provided)
            st = safe_str(j.get('service_type', '')).lower()
            desc = safe_str(j.get('description', '')).lower()
            loc = safe_str(j.get('location', '')).lower()

            if category_filter and category_filter != 'all':
                c_low = category_filter.lower()
                if c_low not in st and c_low not in desc:
                    continue

            # Search query filter (matches description or location)
            if search_query:
                if search_query not in desc and search_query not in loc and search_query not in st:
                    continue

            # Time filter
            if time_filter == 'urgent' and not j.get('is_urgent'):
                continue
            elif time_filter == 'today':
                created_str = j.get('created_at', '')
                if created_str:
                    try:
                        c_date = datetime.fromisoformat(created_str.replace('Z', '+00:00')).date()
                        if c_date != now.date():
                            continue
                    except Exception:
                        pass

            # Calculate distance if coordinates available
            job_lat = j.get('latitude') if j.get('latitude') is not None else j.get('lat')
            job_lng = j.get('longitude') if j.get('longitude') is not None else j.get('lng')

            # Deterministic map positioning offset around worker when job coordinates are missing
            if (job_lat is None or job_lng is None) and worker_lat and worker_lng:
                jid_hash = abs(hash(str(j.get('id', 0)))) % 1000
                angle = (jid_hash / 1000.0) * 2 * math.pi
                dist_offset_km = 1.0 + (jid_hash % 8) * 0.7  # 1 to ~6.6 km
                deg_lat = dist_offset_km / 111.0
                deg_lng = dist_offset_km / (111.0 * math.cos(math.radians(worker_lat)))
                job_lat = worker_lat + deg_lat * math.sin(angle)
                job_lng = worker_lng + deg_lng * math.cos(angle)
                j['approx_lat'] = round(job_lat, 2)
                j['approx_lng'] = round(job_lng, 2)

            distance = None
            if worker_lat and worker_lng and job_lat and job_lng:
                distance = LocationPrivacyShield.calculate_distance_km(worker_lat, worker_lng, job_lat, job_lng)
                j['distance_km'] = distance

            # Radius filtering
            if radius_km is not None and distance is not None:
                if distance > radius_km:
                    continue

            # Privacy Obfuscation
            is_assigned = (j.get('worker_id') == worker_id and j.get('status') == 'accepted')
            safe_job = LocationPrivacyShield.obfuscate_job_request(j, viewer_is_assigned_worker=is_assigned)
            if distance is not None:
                safe_job['distance_km'] = distance

            # Proposed budget / offer details fallback
            if not safe_job.get('price'):
                if safe_job.get('budget_min') and safe_job.get('budget_max'):
                    safe_job['price'] = f"{int(safe_job['budget_min'])}-{int(safe_job['budget_max'])}"
                elif safe_job.get('budget_min'):
                    safe_job['price'] = int(safe_job['budget_min'])
                elif safe_job.get('budget_max'):
                    safe_job['price'] = int(safe_job['budget_max'])
                else:
                    safe_job['price'] = 450

            processed_jobs.append(safe_job)

        # 5. Sort: Urgent first, then by distance (if available), then newest
        processed_jobs.sort(key=lambda x: (
            not x.get('is_urgent', False),
            x.get('distance_km') if x.get('distance_km') is not None else 99999,
            x.get('created_at', '')
        ))

        limit_arg = request.args.get('limit')
        if limit_arg and limit_arg.isdigit():
            processed_jobs = processed_jobs[:int(limit_arg)]

        return jsonify(processed_jobs), 200

    except Exception as e:
        print("Error fetching nearby jobs:\n", traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500

@app.route('/api/jobs/customer', methods=['GET'])
def get_customer_jobs():
    if 'user_id' not in session or session['role'] != 'user':
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session['user_id']
    try:
        jobs_resp = supabase.table("jobs").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()

        jobs = jobs_resp.data
        # For jobs with a worker_id, fetch worker details
        worker_ids = list({j['worker_id'] for j in jobs if j.get('worker_id')})
        if worker_ids:
            try:
                w_resp = supabase.table("workers").select("id, name, phone, price").in_("id", worker_ids).execute()
            except:
                w_resp = supabase.table("workers").select("id, name, phone").in_("id", worker_ids).execute()
                for w in w_resp.data: w['price'] = 0
            
            worker_map = {w['id']: w for w in w_resp.data}
            for j in jobs:
                wid = j.get('worker_id')
                if wid and wid in worker_map:
                    j['worker_name'] = worker_map[wid]['name']
                    j['worker_phone'] = worker_map[wid]['phone']
                    j['price'] = j.get('price') or worker_map[wid].get('price', 0)
                else:
                    j['worker_name'] = None
                    j['worker_phone'] = None

        # Count pending offers for each job
        job_ids = [j['id'] for j in jobs]
        if job_ids:
            try:
                offers_resp = supabase.table("job_offers").select("job_id, id, status").in_("job_id", job_ids).execute()
                offers_count_map = defaultdict(int)
                for o in (offers_resp.data or []):
                    if o.get('status') == 'pending':
                        offers_count_map[o['job_id']] += 1
                for j in jobs:
                    j['offers_count'] = offers_count_map.get(j['id'], 0)
            except Exception:
                for j in jobs:
                    j['offers_count'] = 0

        return jsonify(jobs), 200
    except Exception as e:
        print("Error fetching customer jobs:\n", traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500

@app.route('/api/jobs/<int:job_id>/accept', methods=['POST'])
@app.route('/api/jobs/<job_id>/accept', methods=['POST'])
def accept_job(job_id):
    if 'user_id' not in session or session.get('role') != 'worker':
        return jsonify({'error': 'Unauthorized: Only workers can accept jobs'}), 401

    worker_id = session['user_id']
    try:
        data = request.get_json() or {}
        price = data.get('price', 0)
        try:
            price = float(price) if price else 0
        except (ValueError, TypeError):
            price = 0

        # Atomic Compare-And-Swap (CAS) to prevent double-acceptance race conditions
        success, reason, accepted_job = JobConcurrencyShield.atomic_accept_job(
            supabase, job_id, worker_id, price
        )
        if not success:
            if reason == "not_found":
                return jsonify({'error': 'Job not found'}), 404
            elif reason == "already_taken":
                return jsonify({'error': 'This job is no longer open or was already accepted by another worker'}), 409
            return jsonify({'error': f'Failed to accept job: {reason}'}), 500

        # Record immutable status history
        StatusHistoryLogger.log_job_status(
            supabase, job_id, "open", "accepted", worker_id, "worker", reason="Job accepted directly by worker"
        )

        # Notify the customer that a worker accepted their job
        customer_id = accepted_job.get("user_id") if accepted_job else None
        if customer_id:
            NotificationService.send_notification(
                supabase,
                recipient_id=customer_id,
                recipient_role="user",
                title="Worker Accepted Your Job",
                message=f"A worker has accepted job #{job_id}.",
                notif_type="job_alert",
                reference_id=str(job_id)
            )

        # Log security audit trail
        AuditLogger.log_event(
            supabase,
            actor_id=worker_id,
            actor_role="worker",
            event_type="job_lifecycle",
            resource_type="job",
            resource_id=str(job_id),
            action="accept_job",
            ip_address=request.remote_addr,
            metadata={"price": price}
        )

        return jsonify({'message': 'Job accepted successfully', 'price': price, 'job': accepted_job}), 200
    except Exception as e:
        print("Error accepting job:\n", traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/jobs/<job_id>/offers', methods=['POST'])
@app.route('/api/jobs/<int:job_id>/offers', methods=['POST'])
def create_job_offer(job_id):
    """Worker submits a proposal/bid on an open customer job."""
    if 'user_id' not in session or session.get('role') != 'worker':
        return jsonify({'error': 'Unauthorized: Only workers can submit job offers'}), 401

    worker_id = session['user_id']
    try:
        data = request.get_json() or {}
        price = float(data.get('proposed_price', 0))
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid proposed_price'}), 400

    if price <= 0:
        return jsonify({'error': 'Proposed price must be greater than zero'}), 400

    try:
        # Check job exists and is open
        job_resp = supabase.table("jobs").select("*").eq("id", job_id).execute()
        if not job_resp.data:
            return jsonify({'error': 'Job not found'}), 404
        job = job_resp.data[0]
        if job.get('status') != 'open':
            return jsonify({'error': 'Job is no longer open for offers'}), 400

        # Prevent duplicate pending offers by same worker
        existing = supabase.table("job_offers").select("id, status").eq("job_id", job_id).eq("worker_id", worker_id).execute()
        if existing.data and any(o.get('status') == 'pending' for o in existing.data):
            return jsonify({'error': 'You already have an active offer for this job'}), 409

        offer_record = {
            "job_id": int(job_id) if str(job_id).isdigit() else job_id,
            "worker_id": str(worker_id),
            "proposed_price": price,
            "estimated_arrival_minutes": data.get('estimated_arrival_minutes'),
            "message": safe_str(data.get('message', '')),
            "status": "pending"
        }
        insert_resp = supabase.table("job_offers").insert(offer_record).execute()
        if not insert_resp.data:
            return jsonify({'error': 'Failed to submit offer'}), 500

        offer = insert_resp.data[0]

        # Dispatch notification to customer
        NotificationService.send_notification(
            supabase,
            recipient_id=job['user_id'],
            recipient_role="user",
            title="New Offer Received",
            message=f"A worker submitted an offer of ₹{price} for your job: {job.get('service_type')}",
            notif_type="offer_received",
            reference_id=str(offer['id'])
        )

        AuditLogger.log_event(
            supabase, actor_id=worker_id, actor_role="worker",
            event_type="job_offer", resource_type="job_offer",
            resource_id=str(offer['id']), action="submit_offer",
            ip_address=request.remote_addr, metadata={"job_id": job_id, "price": price}
        )

        return jsonify({'message': 'Offer submitted successfully', 'offer': offer}), 201
    except Exception as e:
        print("Error submitting job offer:\n", traceback.format_exc())
        return jsonify({'error': f'Server error: {e}'}), 500


@app.route('/api/jobs/<job_id>/offers', methods=['GET'])
@app.route('/api/jobs/<int:job_id>/offers', methods=['GET'])
def get_job_offers(job_id):
    """Retrieve offers for a job (job owner sees all; workers see only their own)."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = session['user_id']
    role = session.get('role')

    try:
        job_resp = supabase.table("jobs").select("user_id, status").eq("id", job_id).execute()
        if not job_resp.data:
            return jsonify({'error': 'Job not found'}), 404
        job = job_resp.data[0]

        if role == 'user' and str(job.get('user_id')) == str(uid):
            resp = supabase.table("job_offers").select("*").eq("job_id", job_id).order("created_at", desc=True).execute()
            offers = resp.data or []
            # Enrich with worker names
            worker_ids = list({o['worker_id'] for o in offers if 'worker_id' in o})
            if worker_ids:
                try:
                    w_resp = supabase.table("workers").select("id, name, work, avg_rating, review_count, is_verified, location, approx_lat, approx_lng, price").in_("id", worker_ids).execute()
                except Exception:
                    w_resp = supabase.table("workers").select("id, name, work, avg_rating, review_count, is_verified").in_("id", worker_ids).execute()
                w_map = {w['id']: w for w in (w_resp.data or [])}
                job_lat = job.get('latitude') or job.get('lat')
                job_lng = job.get('longitude') or job.get('lng')
                for o in offers:
                    w_info = dict(w_map.get(o['worker_id'], {}))
                    if job_lat and job_lng and w_info.get('approx_lat') and w_info.get('approx_lng'):
                        w_info['distance_km'] = LocationPrivacyShield.calculate_distance_km(
                            job_lat, job_lng, w_info['approx_lat'], w_info['approx_lng']
                        )
                    o['worker'] = w_info
            return jsonify(offers), 200
        elif role == 'worker':
            resp = supabase.table("job_offers").select("*").eq("job_id", job_id).eq("worker_id", uid).execute()
            return jsonify(resp.data or []), 200

        return jsonify({'error': 'Unauthorized to view offers for this job'}), 403
    except Exception as e:
        print("Error fetching job offers:\n", traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/jobs/<job_id>/offers/<offer_id>/accept', methods=['POST'])
@app.route('/api/jobs/<int:job_id>/offers/<int:offer_id>/accept', methods=['POST'])
def accept_job_offer(job_id, offer_id):
    """Customer accepts a worker's offer on their job."""
    if 'user_id' not in session or session.get('role') != 'user':
        return jsonify({'error': 'Unauthorized: Only the customer who posted the job can accept offers'}), 401

    customer_id = session['user_id']
    try:
        success, reason, accepted_job = JobConcurrencyShield.atomic_accept_offer(
            supabase, job_id, offer_id, customer_id
        )
        if not success:
            if reason in ("job_not_found", "offer_not_found"):
                return jsonify({'error': reason.replace('_', ' ').capitalize()}), 404
            elif reason == "unauthorized":
                return jsonify({'error': 'Unauthorized: You are not the owner of this job'}), 403
            elif reason in ("job_not_open", "offer_not_pending", "already_taken"):
                return jsonify({'error': 'This job or offer is no longer open for acceptance'}), 409
            return jsonify({'error': f"Failed to accept offer: {reason}"}), 500

        # Log status transition
        StatusHistoryLogger.log_job_status(
            supabase, job_id, "open", "accepted", customer_id, "user", reason=f"Customer accepted offer #{offer_id}"
        )

        # Notify chosen worker
        NotificationService.send_notification(
            supabase,
            recipient_id=accepted_job['worker_id'],
            recipient_role="worker",
            title="Offer Accepted!",
            message=f"The customer accepted your offer of ₹{accepted_job.get('price')} on job #{job_id}!",
            notif_type="job_alert",
            reference_id=str(job_id)
        )

        # Audit event
        AuditLogger.log_event(
            supabase, actor_id=customer_id, actor_role="user",
            event_type="job_lifecycle", resource_type="job",
            resource_id=str(job_id), action="accept_offer",
            ip_address=request.remote_addr, metadata={"offer_id": offer_id, "worker_id": accepted_job['worker_id']}
        )

        return jsonify({'message': 'Offer accepted and job assigned successfully', 'job': accepted_job}), 200
    except Exception as e:
        print("Error accepting job offer:\n", traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/jobs/<int:job_id>/track', methods=['GET'])
def track_worker(job_id):
    if 'user_id' not in session or session.get('role') != 'user':
        return jsonify({'error': 'Unauthorized'}), 401
    job = supabase.table("jobs").select("worker_id, status").eq("id", job_id).eq("user_id", session['user_id']).execute().data
    if not job: return jsonify({'error': 'Not found'}), 404
    if job[0]['status'] not in ['accepted', 'pending_confirmation']:
        return jsonify({'error': 'Job not active'}), 400
    worker = supabase.table("workers").select(
        "name, is_sharing_location, live_lat, live_lng, location_updated_at"
    ).eq("id", job[0]['worker_id']).execute().data
    if not worker: return jsonify({'error': 'Worker not found'}), 404
    return jsonify(worker[0]), 200


@app.route('/api/jobs/<int:job_id>/status', methods=['POST'])
def update_job_status(job_id):
    if 'user_id' not in session or session.get('role') != 'user':
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session['user_id']
    try:
        data = request.get_json() or {}
        new_status = safe_str(data.get('status'))

        job_resp = supabase.table("jobs").select("*").eq("id", job_id).eq("user_id", user_id).execute()
        if not job_resp.data:
            return jsonify({'error': 'Job not found or unauthorized'}), 404

        current_job = job_resp.data[0]
        cur_status = current_job.get("status", "open")
        allowed = VALID_JOB_TRANSITIONS.get(cur_status, set())
        if new_status not in allowed:
            return jsonify({'error': f"Invalid state transition from '{cur_status}' to '{new_status}'"}), 400

        supabase.table("jobs").update({
            "status": new_status,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", job_id).execute()

        # Log status history
        StatusHistoryLogger.log_job_status(
            supabase, job_id, cur_status, new_status, user_id, "user", reason=safe_str(data.get('reason'))
        )
        # Log audit trail
        AuditLogger.log_event(
            supabase, actor_id=user_id, actor_role="user",
            event_type="job_status_change", resource_type="job",
            resource_id=str(job_id), action="update_status",
            ip_address=request.remote_addr, metadata={"from": cur_status, "to": new_status}
        )

        return jsonify({'message': f'Job marked as {new_status}', 'status': new_status}), 200
    except Exception as e:
        print("Error updating job status:\n", traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500

@app.route('/api/workers/<worker_id>/rate', methods=['POST'])
def rate_worker(worker_id):
    if 'user_id' not in session or session['role'] != 'user':
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        data = request.get_json() or {}
        job_id = data.get('job_id')
        rating = int(data.get('rating', 0))
        review = safe_str(data.get('review', ''))

        if not job_id or not (1 <= rating <= 5):
            return jsonify({'error': 'Valid job ID and rating (1-5) are required'}), 400

        user_id = session['user_id']

        job_resp = supabase.table("jobs").select("status, worker_id").eq("id", job_id).eq("user_id", user_id).execute()
        if not job_resp.data:
            return jsonify({'error': 'Job not found'}), 404
        job = job_resp.data[0]

        if job['status'] != 'completed' or job['worker_id'] != worker_id:
            return jsonify({'error': 'Job must be completed to leave a review'}), 400

        # Prevent duplicate reviews
        dup_resp = supabase.table("reviews").select("id").eq("job_id", job_id).execute()
        if dup_resp.data:
            return jsonify({'error': 'Review already submitted for this job'}), 400

        supabase.table("reviews").insert({
            "job_id": job_id,
            "worker_id": worker_id,
            "user_id": user_id,
            "rating": rating,
            "review": review
        }).execute()

        return jsonify({'message': 'Review submitted successfully'}), 201
    except ValueError:
        return jsonify({'error': 'Rating must be an integer'}), 400
    except Exception as e:
        print("Error submitting review:\n", traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500

@app.route('/api/translate', methods=['POST'])
def translate_api():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    lang = data.get('lang') or session.get('lang') or 'en'
    text = data.get('text')

    if not text:
        return jsonify({'error': 'No text provided'}), 400

    if isinstance(text, list):
        translated = {t: get_translation(lang, t) for t in text}
    else:
        translated = get_translation(lang, text)

    return jsonify({'translated': translated})


# ════════════════════════════════════════════════════════════
#  VOICE SERVICE & INTENT PROCESSING
# ════════════════════════════════════════════════════════════

@app.route('/api/voice/intent', methods=['POST'])
def voice_intent_api():
    """
    POST /api/voice/intent
    Payload: { text|transcript: str, lang|language?: str, confidence?: float, state|current_state?: str }
    Returns analyzed intent, confidence, code-switching resolution,
    and conversational clarification in the user's active language.
    """
    if not request.is_json:
        return jsonify({'success': False, 'error': 'Invalid JSON or Content-Type'}), 400

    try:
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({'success': False, 'error': 'Invalid JSON body'}), 400
    except Exception:
        return jsonify({'success': False, 'error': 'Malformed JSON'}), 400

    text = data.get('text') or data.get('transcript') or ''
    lang = data.get('lang') or data.get('language') or session.get('lang') or 'hi'

    try:
        confidence = float(data.get('confidence', 1.0))
    except (TypeError, ValueError):
        confidence = 1.0

    state = data.get('state') or data.get('current_state') or 'GREETING'

    try:
        result = analyze_voice_intent(
            raw_text=text,
            lang_code=lang,
            confidence=confidence,
            current_state=state
        )
        return jsonify(result), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'speech_response': 'माफ़ कीजिये, सर्वर से संपर्क करने में समस्या हुई।',
            'requires_clarification': True
        }), 500


@app.route('/api/voice/capabilities', methods=['GET'])
def voice_capabilities_api():
    """
    GET /api/voice/capabilities
    Returns verified language and locale registry, STT/TTS mappings,
    and server-side credential security status.
    """
    return jsonify(get_voice_capabilities()), 200


# ════════════════════════════════════════════════════════════
#  CONVERSATIONAL ORCHESTRATION ENGINE (Phase 3)
# ════════════════════════════════════════════════════════════

@app.route('/api/orchestrator/turn', methods=['POST'])
def orchestrator_turn_api():
    """
    POST /api/orchestrator/turn
    Payload: { user_input: str, state?: str, language?: str, idempotency_key?: str }
    Processes a deterministic conversational state machine step with authorization,
    consequential confirmation, and deduplication.
    """
    if not request.is_json:
        return jsonify({'success': False, 'error': 'Invalid JSON or Content-Type'}), 400

    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        return jsonify({'success': False, 'error': 'Malformed JSON'}), 400

    user_input = data.get('user_input') or data.get('text') or data.get('transcript') or ''
    
    # State resolution: payload -> session -> initial state
    req_state_str = data.get('state') or session.get('conversation_state')
    current_state = ConversationState.GREETING
    if req_state_str:
        try:
            current_state = ConversationState(req_state_str)
        except ValueError:
            current_state = ConversationState.GREETING
    elif session.get('user_id'):
        current_state = ConversationState.AUTHENTICATED

    # Language resolution: payload -> session -> default
    lang = data.get('language') or data.get('lang') or session.get('lang') or 'hi'
    idempotency_key = data.get('idempotency_key')

    # Construct session context
    if 'collected_fields' not in session:
        session['collected_fields'] = {}
    session_data = {
        'user_id': session.get('user_id'),
        'role': session.get('role'),
        'name': session.get('name'),
        'pending_action': session.get('pending_action'),
        'collected_fields': session.get('collected_fields', {})
    }

    try:
        result = orchestration_engine.process_turn(
            user_input=user_input,
            current_state=current_state,
            language=lang,
            session_data=session_data,
            idempotency_key=idempotency_key
        )

        # Update persistent session
        session['conversation_state'] = result['current_state']
        session['lang'] = result['language']

        action_type = result.get('action')
        args = result.get('action_arguments') or {}

        if action_type == AssistantAction.SET_FORM_FIELD.value and 'field_name' in args:
            session['collected_fields'][args['field_name']] = args.get('value')
            session.modified = True
        elif action_type == AssistantAction.REQUEST_CONFIRMATION.value:
            session['pending_action'] = result.get('pending_action')
            session.modified = True
        elif action_type in {AssistantAction.EXECUTE_CONFIRMED_ACTION.value, AssistantAction.CANCEL_PENDING_ACTION.value}:
            session['pending_action'] = None
            session.modified = True

        return jsonify(result), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'current_state': current_state.value,
            'action': AssistantAction.RECOVER_FROM_ERROR.value,
            'error': str(e),
            'speech_response': 'माफ़ कीजिये, सहायक प्रणाली में समस्या हुई। कृपया पुनः प्रयास करें।',
            'display_text': 'त्रुटि: अनुरोध संसाधित नहीं हो सका।',
            'requires_confirmation': False
        }), 500


@app.route('/api/orchestrator/state', methods=['GET'])
def orchestrator_state_api():
    """
    GET /api/orchestrator/state
    Returns current conversation state, language, active role, and pending confirmation.
    """
    current_state = session.get('conversation_state')
    if not current_state:
        current_state = ConversationState.AUTHENTICATED.value if session.get('user_id') else ConversationState.GREETING.value

    return jsonify({
        'current_state': current_state,
        'language': session.get('lang', 'hi'),
        'user_id': session.get('user_id'),
        'role': session.get('role'),
        'name': session.get('name'),
        'pending_action': session.get('pending_action'),
        'collected_fields': session.get('collected_fields', {})
    }), 200


@app.route('/api/orchestrator/reset', methods=['POST'])
def orchestrator_reset_api():
    """
    POST /api/orchestrator/reset
    Resets the conversation state machine cleanly.
    """
    new_state = ConversationState.AUTHENTICATED.value if session.get('user_id') else ConversationState.GREETING.value
    session['conversation_state'] = new_state
    session['pending_action'] = None
    session['collected_fields'] = {}
    session.modified = True

    return jsonify({
        'success': True,
        'current_state': new_state,
        'message': 'Conversation state reset successfully'
    }), 200


# ════════════════════════════════════════════════════════════
#  BOOKING & QR VERIFICATION SYSTEM
# ════════════════════════════════════════════════════════════

TIME_SLOTS = [
    "09:00-11:00",
    "11:00-13:00",
    "13:00-15:00",
    "15:00-17:00",
    "17:00-19:00",
]

def make_qr_token(booking_id) -> str:
    """Generate a tamper-proof HMAC-SHA256 token for a booking."""
    secret = app.secret_key.encode('utf-8')
    msg = str(booking_id).encode('utf-8')
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()

def verify_qr_token(booking_id, token: str) -> bool:
    """Constant-time comparison to prevent timing attacks."""
    expected = make_qr_token(booking_id)
    return hmac.compare_digest(expected, token)

def generate_qr_base64(data: dict) -> str:
    """
    Render a QR code as a base64-encoded PNG string.
    The QR payload is a compact JSON string with booking_id and token.
    """
    payload = json.dumps(data, separators=(',', ':'))
    qr = qrcode.QRCode(
        version=2,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#000000", back_color="#ffffff")
    buf = io.BytesIO()
    img.save(buf)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')


# ── Booking Page Routes ──────────────────────────────────────────────

@app.route('/bookings')
def my_bookings_page():
    """List of all bookings for the logged-in customer."""
    if 'user_id' not in session:
        return redirect(url_for('login_page', role='user'))
    return render_template('my_bookings.html', name=session.get('name'))


@app.route('/bookings/<booking_id>')
@app.route('/booking/<booking_id>')
def booking_detail_page(booking_id):
    """Booking detail page — shows QR code and live status."""
    if 'user_id' not in session:
        return redirect(url_for('login_page', role='user'))
    try:
        resp = supabase.table("bookings").select("*").eq("id", booking_id).execute()
        if not resp.data:
            return "Booking not found", 404
        booking = resp.data[0]

        uid = session['user_id']
        role = session.get('role')
        # Only the customer or the worker of this booking can view it
        if booking['customer_id'] != uid and booking['worker_id'] != uid:
            return "Unauthorized", 403

        # Fetch worker info (using try_select for profile_pic safety)
        w_resp = try_select("workers", "name, phone, work, profile_pic", filters={"id": booking['worker_id']})
        worker = dict(w_resp.data[0]) if w_resp.data else {}

        # Fetch customer info
        c_resp = try_select("users", "name, phone, profile_pic", filters={"id": booking['customer_id']})
        customer = dict(c_resp.data[0]) if c_resp.data else {}

        # Stage-based privacy protection: Mask private phone numbers until confirmed
        is_confirmed_stage = booking.get('status') in (
            'Booked', 'On The Way', 'Arrived', 'Work Started', 'Completed', 'Payment Pending', 'Paid'
        )
        if not is_confirmed_stage:
            if worker.get('phone'):
                worker['phone'] = LocationPrivacyShield.mask_phone(worker.get('phone'))
            if customer.get('phone'):
                customer['phone'] = LocationPrivacyShield.mask_phone(customer.get('phone'))

        # Fetch status history for timeline
        try:
            h_resp = supabase.table("booking_status_history").select("*").eq("booking_id", booking_id).order("created_at", desc=False).execute()
            status_history = h_resp.data or []
        except Exception:
            status_history = []

        creds = BookingCheckinSecurity.generate_checkin_credentials(booking_id, ttl_seconds=300)
        qr_b64 = generate_qr_base64(creds['qr_payload'])

        # Fetch latest payment record for this booking
        latest_payment = None
        try:
            p_resp = supabase.table("payments").select("*").eq("booking_id", booking_id).order("created_at", desc=True).limit(1).execute()
            if p_resp.data:
                latest_payment = p_resp.data[0]
        except Exception:
            latest_payment = None

        payment_options = PaymentManager.get_payment_options(supabase, booking_id, uid)

        # Check if customer has already submitted a review for this booking
        existing_review = None
        try:
            r_resp = supabase.table("reviews").select("*").eq("booking_id", booking_id).execute()
            if r_resp.data:
                existing_review = r_resp.data[0]
        except Exception:
            existing_review = None

        counterparty_id = booking['worker_id'] if uid == booking['customer_id'] else booking['customer_id']
        is_blocked = TrustAndSafetyManager.is_blocked(supabase, uid, counterparty_id)
        stage_policy = LocationPrivacyShield.get_stage_privacy_policy()

        return render_template(
            'booking_detail.html',
            booking=booking,
            worker=worker,
            customer=customer,
            qr_b64=qr_b64,
            checkin_code=creds['code'],
            checkin_token=creds['token'],
            checkin_exp=creds['expires_at'],
            role=role,
            is_customer=(uid == booking['customer_id']),
            is_confirmed_stage=is_confirmed_stage,
            status_history=status_history,
            latest_payment=latest_payment,
            payment_options=payment_options,
            existing_review=existing_review,
            is_counterparty_blocked=is_blocked,
            stage_policy=stage_policy
        )
    except Exception as e:
        print(traceback.format_exc())
        return f"Error: {e}", 500


@app.route('/book/<worker_id>', endpoint='book_worker_page')
@app.route('/book/<worker_id>', endpoint='booking_slots_page')
def book_worker_page(worker_id):
    """Time-slot booking page for a specific worker."""
    if 'user_id' not in session or session.get('role') != 'user':
        return redirect(url_for('login_page', role='user'))
    try:
        resp = supabase.table("workers").select("id, name, work, location, is_available").eq("id", worker_id).execute()
        if not resp.data:
            return "Worker not found", 404
        worker = resp.data[0]
        return render_template('booking_slots.html', worker=worker, slots=TIME_SLOTS)
    except Exception as e:
        return f"Error: {e}", 500


# ── Booking API Routes ───────────────────────────────────────────────

@app.route('/api/bookings/slots', methods=['GET'])
def get_available_slots():
    """
    GET /api/bookings/slots?worker_id=<uuid>&date=<YYYY-MM-DD>
    Returns all slots with availability status.
    """
    worker_id = request.args.get('worker_id', '').strip()
    date_str  = request.args.get('date', '').strip()

    if not worker_id or not date_str:
        return jsonify({'error': 'worker_id and date are required'}), 400

    try:
        # Validate date
        datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'date must be YYYY-MM-DD'}), 400
    try:
        resp = supabase.table("bookings") \
            .select("time_slot") \
            .eq("worker_id", worker_id) \
            .eq("date", date_str) \
            .neq("status", "Cancelled") \
            .execute()
        booked_slots = {row['time_slot'] for row in resp.data}
        result = [{"slot": s, "available": s not in booked_slots} for s in TIME_SLOTS]
        return jsonify(result), 200
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/bookings', methods=['POST'])
@app.route('/create_booking', methods=['POST'])
def create_booking():
    """
    POST /api/bookings
    Body: { worker_id, date, time_slot, notes? }
    Creates a booking and returns the booking data with QR token.
    """
    if 'user_id' not in session or session.get('role') != 'user':
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        data = request.get_json() or {}
    except Exception:
        return jsonify({'error': 'Invalid JSON'}), 400

    worker_id = safe_str(data.get('worker_id'))
    date_str  = safe_str(data.get('date') or data.get('booking_date'))
    time_slot = safe_str(data.get('time_slot'))
    notes     = safe_str(data.get('notes', ''))

    if not worker_id:
        return jsonify({'error': 'worker_id is required'}), 400

    customer_id = session['user_id']
    if TrustAndSafetyManager.is_blocked(supabase, customer_id, worker_id):
        return jsonify({'error': 'Cannot create booking: Interaction between these accounts has been blocked'}), 403

    if not date_str or not time_slot:
        return jsonify({'error': 'worker_id, date, and time_slot are required'}), 400
    if time_slot not in TIME_SLOTS:
        return jsonify({'error': 'Invalid time slot'}), 400
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'date must be YYYY-MM-DD'}), 400

    try:
        # Check worker exists and get price
        w_resp = supabase.table("workers").select("id, name, price").eq("id", worker_id).execute()
        if not w_resp.data:
            return jsonify({'error': 'Worker not found'}), 404

        worker_price = w_resp.data[0].get('price', 0)

        # Double-booking guard
        conflict = supabase.table("bookings") \
            .select("id") \
            .eq("worker_id", worker_id) \
            .eq("date", date_str) \
            .eq("time_slot", time_slot) \
            .neq("status", "Cancelled") \
            .execute()
        if conflict.data:
            return jsonify({'error': 'This slot is already booked. Please choose another.'}), 409

        insert_data = {
            "customer_id": int(customer_id) if str(customer_id).isdigit() else customer_id,
            "worker_id":   int(worker_id) if str(worker_id).isdigit() else worker_id,
            "date":        date_str,
            "time_slot":   time_slot,
            "notes":       notes,
            "status":      "Pending",
            "total_price": worker_price,
            "qr_token":    uuid.uuid4().hex
        }
        
        insert_resp = supabase.table("bookings").insert(insert_data).execute()
        if not insert_resp.data:
            return jsonify({'error': 'Failed to create booking record'}), 500

        booking = insert_resp.data[0]
        new_id  = booking['id']

        # Notify assigned worker
        try:
            NotificationService.send_notification(
                supabase,
                recipient_id=worker_id,
                recipient_role="worker",
                title="New Direct Booking Request",
                message=f"You have a new booking request for {date_str} ({time_slot}).",
                notif_type="booking_created",
                reference_id=str(new_id)
            )
            StatusHistoryLogger.log_booking_status(
                supabase, new_id, "created", "Pending", customer_id, "user", reason="Direct booking requested by customer"
            )
            AuditLogger.log_event(
                supabase, actor_id=customer_id, actor_role="user",
                event_type="booking_lifecycle", resource_type="booking",
                resource_id=str(new_id), action="create_booking",
                ip_address=request.remote_addr, metadata={"worker_id": worker_id, "date": date_str, "time_slot": time_slot}
            )
        except Exception as log_err:
            print("Warning: Failed to log booking notification/audit:", log_err)

        return jsonify({
            'message':    'Booking confirmed!',
            'booking_id': new_id,
            'redirect':   url_for('booking_detail_page', booking_id=new_id)
        }), 201
    except Exception as e:
        err_msg = str(e)
        tb = traceback.format_exc()
        print(f"DEBUG: create_booking failed. Error: {err_msg}\n{tb}")
        payload = {'error': 'Failed to create booking. Please try again.'}
        if app.debug:
            payload['debug_error'] = err_msg
            payload['traceback'] = tb
        return jsonify(payload), 500


@app.route('/api/bookings', methods=['GET'])
@app.route('/api/bookings/user', methods=['GET'])
@app.route('/api/bookings/worker', methods=['GET'])
def get_my_bookings():
    """
    GET /api/bookings
    Returns bookings for the logged-in user (customer or worker).
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    uid = session['user_id']
    try:
        # Get all bookings where user is either customer or worker
        resp = supabase.table("bookings").select("*").or_(f"customer_id.eq.{uid},worker_id.eq.{uid}").order("date", desc=False).execute()
        bookings = resp.data

        if not bookings:
            return jsonify([]), 200

        # Collect all unique IDs to fetch in bulk
        customer_ids = list({b['customer_id'] for b in bookings})
        worker_ids = list({b['worker_id'] for b in bookings})

        # Fetch all customers in one query
        customers_resp = try_select("users", "id, name, profile_pic", in_filters={"id": customer_ids})
        customer_map = {c['id']: c for c in customers_resp.data}

        # Fetch all workers in one query
        workers_resp = try_select("workers", "id, name, profile_pic, work", in_filters={"id": worker_ids})
        worker_map = {w['id']: w for w in workers_resp.data}

        # Enrich bookings
        for b in bookings:
            c_info = customer_map.get(b['customer_id'], {})
            w_info = worker_map.get(b['worker_id'], {})

            b['customer_name'] = c_info.get('name', 'Unknown')
            b['customer_profile_pic'] = c_info.get('profile_pic')

            b['worker_name'] = w_info.get('name', 'Unknown')
            b['worker_work'] = w_info.get('work', 'N/A')
            b['worker_profile_pic'] = w_info.get('profile_pic')

        return jsonify(bookings), 200
    except Exception as e:
        print(f"Error fetching bookings: {e}")
        return jsonify([]), 200


@app.route('/api/bookings/<int:booking_id>', methods=['GET'])
@app.route('/api/bookings/<booking_id>', methods=['GET'])
def get_booking(booking_id):
    """Fetch an authoritative single booking with enriched details, status history, and stage-specific privacy."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    uid = session['user_id']
    role = session.get('role', 'user')
    success, msg, data = BookingWorkflowManager.get_booking_details(supabase, booking_id, uid, role)
    if not success:
        if "not found" in msg.lower():
            return jsonify({'error': 'Not found'}), 404
        if "unauthorized" in msg.lower():
            return jsonify({'error': 'Unauthorized'}), 403
        return jsonify({'error': msg}), 500
    return jsonify(data), 200


@app.route('/api/bookings/<booking_id>/checkin', methods=['POST'])
@app.route('/api/bookings/<int:booking_id>/checkin', methods=['POST'])
def checkin_booking(booking_id):
    """
    POST /api/bookings/<booking_id>/checkin
    Body: { "token": "<qr_token>", "code": "<6_digit_pin>", "lat": ..., "lng": ... }
    Verifies short-lived QR token or 6-digit PIN, enforces state transitions, and marks booking as 'Work Started'.
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    # 1. Rate limiting check (sliding window per booking/IP)
    rate_key = f"{request.remote_addr}:{booking_id}"
    allowed, retry_after = BookingCheckinSecurity.rate_limiter.is_allowed(rate_key)
    if not allowed:
        return jsonify({'error': f"Too many check-in attempts. Please wait {retry_after} seconds before trying again."}), 429

    try:
        data = request.get_json(silent=True) or {}
        token = safe_str(data.get('token', ''))
        code = safe_str(data.get('code', ''))
        client_lat = data.get('lat')
        client_lng = data.get('lng')

        if not token and not code:
            return jsonify({'error': 'QR token or 6-digit verification code is required'}), 400

        resp = supabase.table("bookings").select("*").eq("id", booking_id).execute()
        if not resp.data:
            return jsonify({'error': 'Booking not found'}), 404
        booking = resp.data[0]
        uid = session['user_id']
        role = session.get('role', 'worker')
        cust_id = booking.get('customer_id') or booking.get('user_id')
        worker_id = booking.get('worker_id')

        # 2. Strict participant verification: only assigned worker can perform check-in
        if str(worker_id) != str(uid):
            return jsonify({'error': 'Unauthorized: Only the assigned worker can perform check-in'}), 403

        # 3. Status checks
        if booking['status'] == 'Cancelled':
            return jsonify({'error': 'Cannot check in: Booking has been cancelled'}), 400
        if booking['status'] == 'Work Started':
            return jsonify({'error': 'Cannot check in: Work has already started for this booking'}), 400
        if booking['status'] not in ('Booked', 'Confirmed', 'Pending', 'On The Way', 'Arrived'):
            CheckinEventLogger.log_checkin(
                supabase, booking_id, worker_id, cust_id,
                event_type='checkin_attempt', status='failed', token=token or code,
                ip_address=request.remote_addr, user_agent=request.user_agent.string if request.user_agent else None,
                failure_reason=f"Invalid current status: {booking['status']}"
            )
            return jsonify({'error': f"Cannot check in. Current status: {booking['status']}"}), 400

        # 4. Cryptographic token / PIN verification with replay detection
        if code:
            token_valid, err_msg = BookingCheckinSecurity.verify_checkin_pin(booking_id, code)
        else:
            token_valid, err_msg = BookingCheckinSecurity.verify_checkin_token(booking_id, token)
            # Legacy fallback check
            if not token_valid and ((token == booking.get('qr_token')) or verify_qr_token(booking_id, token)):
                # Check if legacy token was already consumed
                token_hash = hashlib.sha256(f"{booking_id}:{token}".encode('utf-8')).hexdigest()
                if token_hash not in BookingCheckinSecurity._consumed_token_hashes:
                    token_valid = True
                    err_msg = "Valid"
                else:
                    token_valid = False
                    err_msg = "This check-in QR code has already been consumed (replay detected)"

        if not token_valid:
            CheckinEventLogger.log_checkin(
                supabase, booking_id, worker_id, cust_id,
                event_type='checkin_attempt', status='failed', token=token or code,
                ip_address=request.remote_addr, user_agent=request.user_agent.string if request.user_agent else None,
                failure_reason=err_msg
            )
            return jsonify({'error': err_msg or 'Invalid or expired check-in code'}), 403

        # 5. Consume token/PIN (enforce single-use, prevent replay)
        BookingCheckinSecurity.mark_consumed(booking_id, token if token else code)

        # 6. Log success checkin event
        CheckinEventLogger.log_checkin(
            supabase, booking_id, worker_id, cust_id,
            event_type='checkin_verified', status='success', token=token or code,
            client_lat=client_lat, client_lng=client_lng,
            ip_address=request.remote_addr, user_agent=request.user_agent.string if request.user_agent else None
        )

        # 7. Transition status to Work Started
        success, msg, updated = BookingWorkflowManager.transition_status(
            supabase, booking_id, "Work Started", uid, role,
            reason="QR check-in verified successfully" if token else "Manual 6-digit PIN check-in verified",
            metadata={"token": token or code, "client_lat": client_lat, "client_lng": client_lng}
        )
        if not success:
            return jsonify({'error': msg}), 400

        return jsonify({
            'message': 'Check-in verified successfully by server! Work has started.',
            'status': 'Work Started',
            'booking': updated,
            'success': True
        }), 200
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/bookings/<booking_id>/confirm-checkin', methods=['POST'])
@app.route('/api/bookings/<int:booking_id>/confirm-checkin', methods=['POST'])
def confirm_customer_checkin(booking_id):
    """
    POST /api/bookings/<booking_id>/confirm-checkin
    Customer explicit confirmation endpoint for on-site arrival verification without camera.
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = session['user_id']
    resp = supabase.table("bookings").select("*").eq("id", booking_id).execute()
    if not resp.data:
        return jsonify({'error': 'Booking not found'}), 404

    booking = resp.data[0]
    cust_id = booking.get('customer_id') or booking.get('user_id')
    worker_id = booking.get('worker_id')
    if str(cust_id) != str(uid):
        return jsonify({'error': 'Unauthorized: Only the assigned customer can confirm check-in'}), 403

    if booking['status'] == 'Cancelled':
        return jsonify({'error': 'Cannot check in: Booking has been cancelled'}), 400
    if booking['status'] == 'Work Started':
        return jsonify({'error': 'Cannot check in: Work has already started for this booking'}), 400
    if booking['status'] not in ('Booked', 'Confirmed', 'On The Way', 'Arrived', 'Pending'):
        return jsonify({'error': f"Cannot check in: Booking is currently {booking['status']}"}), 400

    CheckinEventLogger.log_checkin(
        supabase, booking_id, worker_id, cust_id,
        event_type='checkin_verified', status='success',
        ip_address=request.remote_addr, user_agent=request.user_agent.string if request.user_agent else None
    )

    success, msg, updated = BookingWorkflowManager.transition_status(
        supabase, booking_id, "Work Started", uid, "user",
        reason="Customer explicitly confirmed worker arrival on-site",
        metadata={"customer_confirmed": True}
    )
    if not success:
        return jsonify({'error': msg}), 400

    return jsonify({
        'message': 'Worker arrival confirmed by customer! Work is now In Progress.',
        'status': 'Work Started',
        'booking': updated
    }), 200


@app.route('/api/bookings/<booking_id>/checkin-token', methods=['GET'])
@app.route('/api/bookings/<int:booking_id>/checkin-token', methods=['GET'])
def get_booking_checkin_token(booking_id):
    """Generates or refreshes short-lived check-in QR credentials and 6-digit PIN for assigned booking participants."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    uid = session['user_id']
    resp = supabase.table("bookings").select("*").eq("id", booking_id).execute()
    if not resp.data:
        return jsonify({'error': 'Booking not found'}), 404
    booking = resp.data[0]
    booking_customer_id = booking.get('customer_id') or booking.get('user_id')
    booking_worker_id = booking.get('worker_id')
    if str(booking_customer_id) != str(uid) and str(booking_worker_id) != str(uid):
        return jsonify({'error': 'Unauthorized: Access restricted to booking participants'}), 403
    if booking.get('status') not in ('Booked', 'Confirmed', 'On The Way', 'Arrived', 'Pending', 'Requested'):
        return jsonify({'error': f"Cannot generate check-in token for booking in '{booking.get('status')}' status"}), 400

    creds = BookingCheckinSecurity.generate_checkin_credentials(booking_id, ttl_seconds=300)
    qr_b64 = generate_qr_base64(creds['qr_payload'])
    creds['qr_b64'] = qr_b64
    return jsonify(creds), 200


@app.route('/api/bookings/<booking_id>/complete', methods=['POST'])
@app.route('/api/bookings/<int:booking_id>/complete', methods=['POST'])
def complete_booking(booking_id):
    """Customer or counterparty marks work as complete."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = session['user_id']
    role = session.get('role', 'user')

    success, msg, updated = BookingWorkflowManager.transition_status(
        supabase, booking_id, "Completed", uid, role,
        reason="Customer marked booking complete" if role == 'user' else "Worker requested completion",
        metadata={"force_worker": (role == 'worker')}
    )
    if not success:
        if "not found" in msg.lower():
            return jsonify({'error': 'Booking not found'}), 404
        if "unauthorized" in msg.lower():
            return jsonify({'error': msg}), 403
        if "already" in msg.lower() or "impossible" in msg.lower() or "cannot" in msg.lower():
            return jsonify({'error': msg}), 400
        if "stale" in msg.lower():
            return jsonify({'error': msg}), 409
        return jsonify({'error': msg}), 500

    return jsonify({'message': 'Work marked as completed!', 'status': 'Completed', 'booking': updated}), 200


@app.route('/api/bookings/<int:booking_id>/cancel', methods=['POST'])
@app.route('/api/bookings/<booking_id>/cancel', methods=['POST'])
def cancel_booking(booking_id):
    """Customer or worker cancels a booking under authoritative policy."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = session['user_id']
    role = session.get('role', 'user')
    data = request.get_json(silent=True) or {}
    reason = safe_str(data.get('reason', 'Cancelled by user'))

    success, msg, updated = BookingWorkflowManager.transition_status(
        supabase, booking_id, "Cancelled", uid, role, reason=reason
    )
    if not success:
        if "not found" in msg.lower():
            return jsonify({'error': 'Booking not found'}), 404
        if "unauthorized" in msg.lower():
            return jsonify({'error': msg}), 403
        if "already" in msg.lower() or "cannot" in msg.lower() or "detailed cancellation reason" in msg.lower() or "impossible" in msg.lower():
            return jsonify({'error': msg}), 400
        if "stale" in msg.lower():
            return jsonify({'error': msg}), 409
        return jsonify({'error': msg}), 500

    return jsonify({'message': 'Booking cancelled.', 'status': 'Cancelled', 'booking': updated}), 200


@app.route('/api/bookings/<int:booking_id>/accept', methods=['POST'])
@app.route('/api/bookings/<booking_id>/accept', methods=['POST'])
def accept_booking(booking_id):
    """Worker accepts a pending booking."""
    if 'user_id' not in session or session.get('role') != 'worker':
        return jsonify({'error': 'Unauthorized: Only assigned worker can accept'}), 401

    uid = session['user_id']
    success, msg, updated = BookingWorkflowManager.transition_status(
        supabase, booking_id, "Booked", uid, "worker", reason="Worker accepted appointment"
    )
    if not success:
        if "not found" in msg.lower():
            return jsonify({'error': 'Booking not found'}), 404
        if "unauthorized" in msg.lower():
            return jsonify({'error': msg}), 403
        if "already" in msg.lower() or "cannot" in msg.lower() or "impossible" in msg.lower():
            return jsonify({'error': msg}), 400
        if "stale" in msg.lower():
            return jsonify({'error': msg}), 409
        return jsonify({'error': msg}), 500

    return jsonify({'message': 'Booking accepted!', 'status': 'Booked', 'booking': updated}), 200


@app.route('/api/bookings/<int:booking_id>/decline', methods=['POST'])
@app.route('/api/bookings/<booking_id>/decline', methods=['POST'])
def decline_booking(booking_id):
    """Worker declines a pending booking."""
    if 'user_id' not in session or session.get('role') != 'worker':
        return jsonify({'error': 'Unauthorized: Only assigned worker can decline'}), 401

    uid = session['user_id']
    success, msg, updated = BookingWorkflowManager.transition_status(
        supabase, booking_id, "Cancelled", uid, "worker", reason="Worker declined appointment"
    )
    if not success:
        if "not found" in msg.lower():
            return jsonify({'error': 'Booking not found'}), 404
        if "unauthorized" in msg.lower():
            return jsonify({'error': msg}), 403
        if "already" in msg.lower() or "cannot" in msg.lower() or "impossible" in msg.lower():
            return jsonify({'error': msg}), 400
        if "stale" in msg.lower():
            return jsonify({'error': msg}), 409
        return jsonify({'error': msg}), 500

    return jsonify({'message': 'Booking declined.', 'status': 'Cancelled', 'booking': updated}), 200


@app.route('/api/bookings/<int:booking_id>/travel', methods=['POST'])
@app.route('/api/bookings/<booking_id>/travel', methods=['POST'])
def travel_booking(booking_id):
    """Worker signals they have started travelling to the customer location."""
    if 'user_id' not in session or session.get('role') != 'worker':
        return jsonify({'error': 'Unauthorized: Only assigned worker can set travel status'}), 401

    uid = session['user_id']
    data = request.get_json(silent=True) or {}
    eta = data.get('eta_minutes')

    success, msg, updated = BookingWorkflowManager.transition_status(
        supabase, booking_id, "On The Way", uid, "worker",
        reason="Worker is travelling to location",
        metadata={"eta_minutes": eta}
    )
    if not success:
        if "not found" in msg.lower():
            return jsonify({'error': 'Booking not found'}), 404
        if "unauthorized" in msg.lower():
            return jsonify({'error': msg}), 403
        if "already" in msg.lower() or "cannot" in msg.lower() or "impossible" in msg.lower():
            return jsonify({'error': msg}), 400
        if "stale" in msg.lower():
            return jsonify({'error': msg}), 409
        return jsonify({'error': msg}), 500

    return jsonify({'message': 'Status updated: On The Way', 'status': 'On The Way', 'booking': updated}), 200


@app.route('/api/bookings/<int:booking_id>/arrive', methods=['POST'])
@app.route('/api/bookings/<booking_id>/arrive', methods=['POST'])
def arrive_booking(booking_id):
    """Worker signals they have arrived at the customer location."""
    if 'user_id' not in session or session.get('role') != 'worker':
        return jsonify({'error': 'Unauthorized: Only assigned worker can set arrival status'}), 401

    uid = session['user_id']
    success, msg, updated = BookingWorkflowManager.transition_status(
        supabase, booking_id, "Arrived", uid, "worker",
        reason="Worker arrived at location"
    )
    if not success:
        if "not found" in msg.lower():
            return jsonify({'error': 'Booking not found'}), 404
        if "unauthorized" in msg.lower():
            return jsonify({'error': msg}), 403
        if "already" in msg.lower() or "cannot" in msg.lower() or "impossible" in msg.lower():
            return jsonify({'error': msg}), 400
        if "stale" in msg.lower():
            return jsonify({'error': msg}), 409
        return jsonify({'error': msg}), 500

    return jsonify({'message': 'Status updated: Arrived', 'status': 'Arrived', 'booking': updated}), 200


@app.route('/api/bookings/<int:booking_id>/dispute', methods=['POST'])
@app.route('/api/bookings/<booking_id>/dispute', methods=['POST'])
def dispute_booking(booking_id):
    """Customer or worker flags a dispute or problem on the booking."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = session['user_id']
    role = session.get('role', 'user')
    data = request.get_json(silent=True) or {}
    reason = safe_str(data.get('reason') or data.get('description'))

    success, msg, updated = BookingWorkflowManager.transition_status(
        supabase, booking_id, "Disputed", uid, role, reason=reason
    )
    if not success:
        if "not found" in msg.lower():
            return jsonify({'error': 'Booking not found'}), 404
        if "unauthorized" in msg.lower():
            return jsonify({'error': msg}), 403
        if "already" in msg.lower() or "cannot" in msg.lower() or "impossible" in msg.lower() or "description" in msg.lower():
            return jsonify({'error': msg}), 400
        if "stale" in msg.lower():
            return jsonify({'error': msg}), 409
        return jsonify({'error': msg}), 500

    # Also record into reports table
    try:
        target_id = updated.get('worker_id') if role == 'user' else updated.get('customer_id')
        target_role = 'worker' if role == 'user' else 'user'
        supabase.table("reports").insert({
            "reporter_id": uid,
            "reporter_role": role,
            "reported_id": target_id,
            "reported_role": target_role,
            "booking_id": booking_id,
            "reason": reason[:100] if reason else "Booking dispute",
            "description": reason,
            "status": "pending",
            "created_at": utc_now_iso()
        }).execute()
    except Exception:
        pass

    return jsonify({'message': 'Dispute registered. Support team has been notified.', 'status': 'Disputed', 'booking': updated}), 200


@app.route('/api/bookings/<int:booking_id>/messages', methods=['POST', 'GET'])
@app.route('/api/bookings/<booking_id>/messages', methods=['POST', 'GET'])
def booking_messages_api(booking_id):
    """In-app communication between connected customer and worker."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = session['user_id']
    role = session.get('role', 'user')

    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        text = safe_str(data.get('message'))
        success, msg, res = BookingWorkflowManager.send_booking_message(supabase, booking_id, uid, role, text)
        if not success:
            status_code = 403 if "unauthorized" in msg.lower() else (404 if "not found" in msg.lower() else 400)
            return jsonify({'error': msg}), status_code
        return jsonify({'message': 'Message sent', 'data': res}), 201

    # GET
    success, msg, messages = BookingWorkflowManager.get_booking_messages(supabase, booking_id, uid)
    if not success:
        status_code = 403 if "unauthorized" in msg.lower() else (404 if "not found" in msg.lower() else 500)
        return jsonify({'error': msg}), status_code
    return jsonify(messages), 200


# ── Service Categories API ──────────────────────────────────────────

@app.route('/api/categories', methods=['GET'])
def get_service_categories():
    """Returns active service categories for service filtering and job postings."""
    categories = ServiceCategoryManager.get_categories(supabase)
    return jsonify(categories), 200


# ── Worker Skills API ───────────────────────────────────────────────

@app.route('/api/worker/skills', methods=['GET'])
def get_current_worker_skills():
    """Fetch skills for the authenticated worker."""
    if 'user_id' not in session or session.get('role') != 'worker':
        return jsonify({'error': 'Unauthorized'}), 401
    skills = WorkerSkillsManager.get_worker_skills(supabase, session['user_id'])
    return jsonify(skills), 200


@app.route('/api/workers/<worker_id>/skills', methods=['GET'])
def get_worker_skills_by_id(worker_id):
    """Fetch skills for any worker by ID."""
    skills = WorkerSkillsManager.get_worker_skills(supabase, worker_id)
    return jsonify(skills), 200


@app.route('/api/worker/skills', methods=['POST'])
def add_worker_skill():
    """Worker adds a specialized skill/trade."""
    if 'user_id' not in session or session.get('role') != 'worker':
        return jsonify({'error': 'Unauthorized: Only workers can add skills'}), 401

    try:
        data = request.get_json() or {}
    except Exception:
        return jsonify({'error': 'Invalid JSON'}), 400

    skill_name = safe_str(data.get('skill_name'))
    category_id = data.get('category_id')
    exp_years = data.get('experience_years', 1)
    is_primary = bool(data.get('is_primary', False))

    success, msg, skill = WorkerSkillsManager.add_worker_skill(
        supabase, session['user_id'], skill_name, category_id, exp_years, is_primary
    )
    if not success:
        status_code = 409 if "already" in msg.lower() else 400
        return jsonify({'error': msg}), status_code

    AuditLogger.log_event(
        supabase, actor_id=session['user_id'], actor_role="worker",
        event_type="profile_update", resource_type="worker_skill",
        resource_id=str(skill.get('id', '')), action="add_skill",
        ip_address=request.remote_addr, metadata={"skill": skill_name}
    )
    return jsonify({'message': msg, 'skill': skill}), 201


@app.route('/api/worker/skills/<int:skill_id>', methods=['DELETE'])
def delete_worker_skill(skill_id):
    """Worker removes a skill (enforces record ownership)."""
    if 'user_id' not in session or session.get('role') != 'worker':
        return jsonify({'error': 'Unauthorized'}), 401

    success, msg = WorkerSkillsManager.delete_worker_skill(supabase, skill_id, session['user_id'])
    if not success:
        status_code = 403 if "unauthorized" in msg.lower() else 404
        return jsonify({'error': msg}), status_code

    AuditLogger.log_event(
        supabase, actor_id=session['user_id'], actor_role="worker",
        event_type="profile_update", resource_type="worker_skill",
        resource_id=str(skill_id), action="delete_skill",
        ip_address=request.remote_addr
    )
    return jsonify({'message': msg}), 200


# ── Payments API ────────────────────────────────────────────────────

@app.route('/api/payments', methods=['POST'])
def create_payment():
    """
    POST /api/payments
    Processes/records a payment for a booking or job.
    Enforces server-side price validation, party authorization, and idempotency deduplication.
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        data = request.get_json() or {}
    except Exception:
        return jsonify({'error': 'Invalid JSON'}), 400

    payer_id = session['user_id']
    booking_id = data.get('booking_id')
    job_id = data.get('job_id')
    payment_method = safe_str(data.get('payment_method', 'cash')).lower()
    idempotency_key = safe_str(data.get('idempotency_key', '')) or None
    notes = safe_str(data.get('notes', ''))

    if payment_method not in ('cash', 'upi', 'qr', 'wallet', 'card'):
        return jsonify({'error': 'Invalid payment method'}), 400

    payee_id = None
    amount = 0.0

    # Server-side amount and relationship validation (Never trust arbitrary browser prices!)
    if booking_id:
        b_resp = supabase.table("bookings").select("*").eq("id", booking_id).execute()
        if not b_resp.data:
            return jsonify({'error': 'Booking not found'}), 404
        booking = b_resp.data[0]
        if str(booking.get('customer_id')) != str(payer_id):
            return jsonify({'error': 'Unauthorized: Only the customer can pay for this booking'}), 403
        payee_id = booking['worker_id']
        amount = float(booking.get('total_price') or booking.get('price') or data.get('amount', 0))
    elif job_id:
        j_resp = supabase.table("jobs").select("*").eq("id", job_id).execute()
        if not j_resp.data:
            return jsonify({'error': 'Job not found'}), 404
        job = j_resp.data[0]
        if str(job.get('user_id')) != str(payer_id):
            return jsonify({'error': 'Unauthorized: Only the customer can pay for this job'}), 403
        payee_id = job.get('worker_id')
        if not payee_id:
            return jsonify({'error': 'Job does not have an assigned worker yet'}), 400
        amount = float(job.get('price') or data.get('amount', 0))
    else:
        return jsonify({'error': 'Either booking_id or job_id is required'}), 400

    if amount <= 0:
        return jsonify({'error': 'Payment amount must be greater than zero'}), 400

    success, msg, payment = PaymentManager.process_payment(
        supabase,
        payer_id=payer_id,
        payee_id=payee_id,
        amount=amount,
        payment_method=payment_method,
        booking_id=booking_id,
        job_id=job_id,
        idempotency_key=idempotency_key,
        notes=notes
    )
    if not success:
        return jsonify({'error': msg}), 400

    # Notify payee worker
    NotificationService.send_notification(
        supabase,
        recipient_id=payee_id,
        recipient_role="worker",
        title="Payment Received",
        message=f"You received a payment of ₹{amount} via {payment_method.upper()}.",
        notif_type="payment",
        reference_id=str(payment['id']),
        idempotency_key=f"pay_notif_{payment['id']}"
    )

    AuditLogger.log_event(
        supabase, actor_id=payer_id, actor_role=session.get('role', 'user'),
        event_type="financial", resource_type="payment",
        resource_id=str(payment['id']), action="record_payment",
        ip_address=request.remote_addr, metadata={"amount": amount, "method": payment_method}
    )

    return jsonify({'message': msg, 'payment': payment}), 201


@app.route('/api/payments', methods=['GET'])
def get_payments():
    """Retrieve payments history for the logged-in user with pagination."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = session['user_id']
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (ValueError, TypeError):
        page = 1
    try:
        limit = max(1, min(100, int(request.args.get('limit', 20))))
    except (ValueError, TypeError):
        limit = 20

    resp = supabase.table("payments").select("*").or_(f"payer_id.eq.{uid},payee_id.eq.{uid}").order("created_at", desc=True).execute()
    all_payments = resp.data or []
    start = (page - 1) * limit
    paged = all_payments[start:start + limit]
    return jsonify(paged), 200


@app.route('/api/payments/<payment_id>', methods=['GET'])
def get_payment_detail(payment_id):
    """Retrieve a single payment record (with participant authorization check)."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = session['user_id']
    resp = supabase.table("payments").select("*").eq("id", payment_id).execute()
    if not resp.data:
        return jsonify({'error': 'Payment not found'}), 404

    pay = resp.data[0]
    if str(pay.get('payer_id')) != str(uid) and str(pay.get('payee_id')) != str(uid):
        return jsonify({'error': 'Unauthorized'}), 403

    return jsonify(pay), 200


# ── Payment Options & Provider Readiness API ────────────────────────
@app.route('/api/bookings/<booking_id>/payment-options', methods=['GET'])
@app.route('/api/bookings/<int:booking_id>/payment-options', methods=['GET'])
def get_booking_payment_options(booking_id):
    """
    GET /api/bookings/<booking_id>/payment-options
    Returns server-validated booking amount, permitted methods, provider readiness,
    and explains when online payment is not yet enabled.
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = session['user_id']
    options = PaymentManager.get_payment_options(supabase, booking_id, uid)
    if "error" in options:
        return jsonify(options), 404
    return jsonify(options), 200


# ── Payment Intent & Checkout Order Creation API ────────────────────
@app.route('/api/payments/create-intent', methods=['POST'])
def create_payment_intent():
    """
    POST /api/payments/create-intent
    Body: { "booking_id": 1, "payment_method": "cash"|"upi"|"card"|"netbanking", "idempotency_key": "..." }
    Creates payment order/transaction on backend linked to booking and amount.
    Returns hosted checkout options, amount-bound QR if UPI, or cash instructions.
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    payer_id = session['user_id']
    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        return jsonify({'error': 'Invalid JSON'}), 400

    booking_id = data.get('booking_id')
    payment_method = safe_str(data.get('payment_method', 'cash')).lower()
    idempotency_key = safe_str(data.get('idempotency_key', '')) or None
    notes = safe_str(data.get('notes', ''))

    if not booking_id:
        return jsonify({'error': 'booking_id is required'}), 400

    success, msg, result = PaymentManager.create_payment_intent(
        supabase,
        payer_id=payer_id,
        booking_id=booking_id,
        payment_method=payment_method,
        idempotency_key=idempotency_key,
        notes=notes
    )
    if not success:
        return jsonify({'error': msg}), 400

    AuditLogger.log_event(
        supabase, actor_id=payer_id, actor_role=session.get('role', 'user'),
        event_type="financial", resource_type="payment_intent",
        resource_id=str(booking_id), action="create_payment_intent",
        ip_address=request.remote_addr, metadata={"method": payment_method}
    )

    return jsonify({'message': msg, 'success': True, **(result or {})}), 200


# ── Payment Cryptographic Verification API ──────────────────────────
@app.route('/api/payments/verify', methods=['POST'])
def verify_payment():
    """
    POST /api/payments/verify
    Body: { "booking_id": 1, "razorpay_order_id": "...", "razorpay_payment_id": "...", "razorpay_signature": "..." }
    Verifies completion using authenticated server-side signature procedure.
    Never marks paid based on client return or screenshot.
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = session['user_id']
    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        return jsonify({'error': 'Invalid JSON'}), 400

    booking_id = data.get('booking_id')
    order_id = safe_str(data.get('razorpay_order_id') or data.get('gateway_order_id') or data.get('order_id', ''))
    payment_id = safe_str(data.get('razorpay_payment_id') or data.get('gateway_payment_id') or data.get('payment_id', ''))
    signature = safe_str(data.get('razorpay_signature') or data.get('gateway_signature') or data.get('signature', ''))

    if not order_id or not payment_id or not signature:
        return jsonify({'error': 'razorpay_order_id, razorpay_payment_id, and razorpay_signature are required'}), 400

    success, msg, payment = PaymentManager.verify_and_complete_payment(
        supabase,
        booking_id=booking_id,
        order_id=order_id,
        payment_id=payment_id,
        signature=signature,
        user_id=uid
    )
    if not success:
        AuditLogger.log_event(
            supabase, actor_id=uid, actor_role=session.get('role', 'user'),
            event_type="financial", resource_type="payment",
            resource_id=order_id, action="payment_verification_failed",
            ip_address=request.remote_addr, metadata={"error": msg, "payment_id": payment_id}
        )
        return jsonify({'error': msg, 'success': False}), 400

    AuditLogger.log_event(
        supabase, actor_id=uid, actor_role=session.get('role', 'user'),
        event_type="financial", resource_type="payment",
        resource_id=str(payment['id']), action="payment_verified_and_settled",
        ip_address=request.remote_addr, metadata={"order_id": order_id, "payment_id": payment_id}
    )

    is_already_settled = "already" in msg.lower()
    return jsonify({
        'message': msg,
        'status': 'completed',
        'booking_status': 'Paid',
        'payment': payment,
        'success': True,
        'already_settled': is_already_settled
    }), 200


# ── Payment Failure Notification API ────────────────────────────────
@app.route('/api/payments/fail', methods=['POST'])
def record_payment_failure():
    """
    POST /api/payments/fail
    Body: { "booking_id": 1, "order_id": "...", "error_code": "...", "error_description": "..." }
    Records failure, prevents false completion, leaves booking in Payment Pending for retry or cash.
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = session['user_id']
    data = request.get_json(silent=True) or {}
    booking_id = data.get('booking_id')
    order_id = safe_str(data.get('order_id') or data.get('gateway_order_id', ''))
    err_code = safe_str(data.get('error_code', 'FAILED'))
    err_desc = safe_str(data.get('error_description', 'Payment checkout was cancelled or failed'))

    success, msg, payment = PaymentManager.handle_payment_failure(
        supabase, booking_id, order_id, err_code, err_desc, user_id=uid
    )
    return jsonify({'message': msg, 'payment': payment, 'success': True}), 200


# ── Cash Payment In-Person Confirmation API ─────────────────────────
@app.route('/api/bookings/<booking_id>/confirm-cash-payment', methods=['POST'])
@app.route('/api/bookings/<int:booking_id>/confirm-cash-payment', methods=['POST'])
def confirm_cash_payment(booking_id):
    """
    POST /api/bookings/<booking_id>/confirm-cash-payment
    Separately defined confirmation process for cash payments.
    Only the assigned worker can confirm physical cash receipt on-site.
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    worker_id = session['user_id']
    data = request.get_json(silent=True) or {}
    notes = safe_str(data.get('notes', ''))

    success, msg, payment = PaymentManager.confirm_cash_payment(
        supabase, booking_id=booking_id, worker_id=worker_id, notes=notes
    )
    if not success:
        status_code = 403 if ("unauthorized" in msg.lower() or "only the assigned worker" in msg.lower()) else 400
        return jsonify({'error': msg}), status_code

    AuditLogger.log_event(
        supabase, actor_id=worker_id, actor_role="worker",
        event_type="financial", resource_type="payment",
        resource_id=str(payment['id']), action="confirm_cash_payment",
        ip_address=request.remote_addr, metadata={"booking_id": booking_id, "amount": payment.get('amount')}
    )

    return jsonify({
        'message': msg,
        'status': 'completed',
        'booking_status': 'Paid',
        'payment': payment,
        'success': True
    }), 200


# ── Webhook API (Server-to-Server Callbacks) ─────────────────────────
@app.route('/api/payments/webhook', methods=['POST'])
def payment_webhook():
    """
    POST /api/payments/webhook
    Receives and verifies authenticated provider webhook notifications.
    Enforces webhook signature check and event deduplication.
    """
    signature = request.headers.get('X-Razorpay-Signature', '')
    raw_body = request.get_data()

    success, msg, result = PaymentManager.handle_webhook(
        supabase, raw_body=raw_body, signature=signature
    )
    if not success:
        return jsonify({'error': msg}), 400

    is_duplicate = "duplicate" in msg.lower() or "already processed" in msg.lower()
    return jsonify({'message': msg, 'result': result, 'duplicate': is_duplicate, 'success': True}), 200


# ── Worker Payout Profile API ────────────────────────────────────────
@app.route('/api/worker/payout-profile', methods=['GET'])
def get_worker_payout_profile():
    """Worker views their payout onboarding status and masked UPI VPA."""
    if 'user_id' not in session or session.get('role') != 'worker':
        return jsonify({'error': 'Unauthorized'}), 401

    uid = session['user_id']
    resp = supabase.table("workers").select("id, name, payout_vpa, payout_account_id, payout_status").eq("id", uid).execute()
    if not resp.data:
        return jsonify({'error': 'Worker profile not found'}), 404

    w = resp.data[0]
    vpa = w.get('payout_vpa') or ""
    masked_vpa = vpa
    if "@" in vpa:
        user_part, domain = vpa.split("@", 1)
        if len(user_part) > 3:
            masked_vpa = f"{user_part[:2]}***{user_part[-1]}@{domain}"

    gateway_configured, gateway_msg = RazorpayGatewayService.is_gateway_configured()

    return jsonify({
        'worker_id': uid,
        'payout_vpa_masked': masked_vpa,
        'payout_status': w.get('payout_status', 'unconfigured'),
        'payout_account_id': w.get('payout_account_id'),
        'is_eligible_for_online': bool(vpa and w.get('payout_status') == 'active' and gateway_configured),
        'gateway_configured': gateway_configured,
        'gateway_message': gateway_msg
    }), 200


@app.route('/api/worker/payout-profile', methods=['POST'])
def update_worker_payout_profile():
    """
    Worker supplies their UPI VPA or Razorpay Route account ID for settlements.
    Does NOT store raw card details or sensitive banking credentials.
    """
    if 'user_id' not in session or session.get('role') != 'worker':
        return jsonify({'error': 'Unauthorized'}), 401

    uid = session['user_id']
    try:
        data = request.get_json() or {}
    except Exception:
        return jsonify({'error': 'Invalid JSON'}), 400

    payout_vpa = safe_str(data.get('payout_vpa', ''))
    payout_account_id = safe_str(data.get('payout_account_id', ''))

    success, msg, result = PaymentManager.validate_and_update_worker_payout(
        supabase, worker_id=uid, payout_vpa=payout_vpa, payout_account_id=payout_account_id
    )
    if not success:
        return jsonify({'error': msg}), 400

    AuditLogger.log_event(
        supabase, actor_id=uid, actor_role="worker",
        event_type="payout", resource_type="worker",
        resource_id=str(uid), action="update_payout_profile",
        ip_address=request.remote_addr, metadata={"status": "active"}
    )

    return jsonify({
        'message': msg,
        'profile': result,
        'success': True,
        'payout_status': result.get('payout_status', 'active') if result else 'active'
    }), 200


# ── Notifications API ───────────────────────────────────────────────

@app.route('/api/notifications', methods=['GET'])
def get_notifications():
    """Retrieve in-app notifications for the current authenticated user."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = session['user_id']
    unread_only = request.args.get('unread_only', 'false').lower() in ('true', '1')
    try:
        limit = max(1, min(100, int(request.args.get('limit', 20))))
    except (ValueError, TypeError):
        limit = 20

    query = supabase.table("notifications").select("*").eq("recipient_id", uid)
    if unread_only:
        query = query.eq("is_read", False)
    query = query.order("created_at", desc=True).limit(limit)
    resp = query.execute()
    return jsonify(resp.data or []), 200


@app.route('/api/notifications/<notification_id>/read', methods=['POST'])
def mark_notification_read(notification_id):
    """Mark a notification as read (with recipient ownership verification)."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = session['user_id']
    resp = supabase.table("notifications").update({"is_read": True}).eq("id", notification_id).eq("recipient_id", uid).execute()
    if not resp.data:
        return jsonify({'error': 'Notification not found or unauthorized'}), 404

    return jsonify({'message': 'Notification marked as read'}), 200


@app.route('/api/notifications/read-all', methods=['POST'])
def mark_all_notifications_read():
    """Mark all unread notifications for the authenticated user as read."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = session['user_id']
    supabase.table("notifications").update({"is_read": True}).eq("recipient_id", uid).eq("is_read", False).execute()
    return jsonify({'message': 'All notifications marked as read'}), 200


# ── Dispute Reports API ─────────────────────────────────────────────

@app.route('/api/reports', methods=['POST'])
def create_report():
    """
    POST /api/reports
    Submits a dispute/issue report against a counterparty for a job or booking.
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        data = request.get_json() or {}
    except Exception:
        return jsonify({'error': 'Invalid JSON'}), 400

    reporter_id = session['user_id']
    reporter_role = session.get('role', 'user')
    reported_id = safe_str(data.get('reported_id'))
    reported_role = safe_str(data.get('reported_role') or ('worker' if reporter_role == 'user' else 'user'))
    category = safe_str(data.get('category', 'other')).lower()
    reason = safe_str(data.get('reason'))
    description = safe_str(data.get('description'))
    job_id = data.get('job_id')
    booking_id = data.get('booking_id')

    if not reported_id or not reason or not description:
        return jsonify({'error': 'reported_id, reason, and description are required'}), 400

    if reported_role not in ('user', 'worker'):
        return jsonify({'error': 'Invalid reported_role'}), 400

    success, msg, new_report = TrustAndSafetyManager.file_report(
        supabase,
        reporter_id=reporter_id,
        reporter_role=reporter_role,
        reported_id=reported_id,
        reported_role=reported_role,
        category=category,
        reason=reason,
        description=description,
        booking_id=booking_id,
        job_id=job_id
    )
    if not success:
        return jsonify({'error': msg}), 400

    return jsonify({
        'message': 'Report submitted successfully. Server status: Open. Our safety team is investigating.',
        'report_id': new_report['id'],
        'status': new_report.get('status', 'open'),
        'report': new_report,
        'success': True
    }), 201


@app.route('/api/reports', methods=['GET'])
def get_my_reports():
    """Retrieve dispute and incident reports filed by the logged-in user with their real server-recorded status."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = session['user_id']
    reports = TrustAndSafetyManager.get_user_reports(supabase, uid)
    return jsonify(reports), 200


# ── Booking Reviews & Real Ratings API ──────────────────────────────

@app.route('/api/bookings/<booking_id>/review', methods=['POST'])
@app.route('/api/bookings/<int:booking_id>/review', methods=['POST'])
@app.route('/api/bookings/<booking_id>/reviews', methods=['POST'])
@app.route('/api/bookings/<int:booking_id>/reviews', methods=['POST'])
def submit_booking_review_api(booking_id):
    """
    POST /api/bookings/<booking_id>/review
    Body: { "rating": 5, "review": "Excellent work!" }
    Reviews can ONLY be submitted for eligible completed bookings.
    Prevents duplicate reviews for the same booking.
    Calculates authentic average rating and real review counts.
    """
    if 'user_id' not in session or session.get('role') != 'user':
        return jsonify({'error': 'Unauthorized: Only customers can submit reviews'}), 401

    uid = session['user_id']
    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        return jsonify({'error': 'Invalid JSON'}), 400

    rating = data.get('rating')
    review_text = safe_str(data.get('review', ''))

    success, msg, result = TrustAndSafetyManager.submit_booking_review(
        supabase,
        booking_id=booking_id,
        customer_id=uid,
        rating=rating,
        review_text=review_text
    )
    if not success:
        if "unauthorized" in msg.lower():
            status_code = 403
        elif "not found" in msg.lower():
            status_code = 404
        elif "already" in msg.lower():
            status_code = 409
        else:
            status_code = 400
        return jsonify({'error': msg, 'success': False}), status_code

    return jsonify({
        'message': msg,
        'review': result,
        'success': True
    }), 201


@app.route('/api/workers/<worker_id>/reviews', methods=['GET'])
def get_worker_reviews_api(worker_id):
    """Returns authentic verified client reviews and stats for a worker (no fake seeded reviews)."""
    try:
        limit = max(1, min(100, int(request.args.get('limit', 20))))
    except (ValueError, TypeError):
        limit = 20
    reviews = TrustAndSafetyManager.get_worker_reviews(supabase, worker_id, limit=limit)
    return jsonify(reviews), 200


# ── User Safety, Blocking & Moderation API ──────────────────────────

@app.route('/api/blocks', methods=['POST'])
def block_user_api():
    """
    POST /api/blocks
    Body: { "blocked_id": "<uuid>", "blocked_role": "worker"|"user", "reason": "..." }
    Blocks an abusive counterparty to prevent bookings, messages, and offers.
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = session['user_id']
    role = session.get('role', 'user')
    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        return jsonify({'error': 'Invalid JSON'}), 400

    blocked_id = safe_str(data.get('blocked_id'))
    blocked_role = safe_str(data.get('blocked_role') or ('worker' if role == 'user' else 'user'))
    reason = safe_str(data.get('reason', 'User blocked for inappropriate behavior'))

    if not blocked_id:
        return jsonify({'error': 'blocked_id is required'}), 400

    success, msg, block = TrustAndSafetyManager.block_user(
        supabase, blocker_id=uid, blocker_role=role,
        blocked_id=blocked_id, blocked_role=blocked_role, reason=reason
    )
    if not success:
        return jsonify({'error': msg}), 400

    return jsonify({'message': msg, 'block': block, 'success': True}), 201


@app.route('/api/blocks/<blocked_id>', methods=['DELETE'])
def unblock_user_api(blocked_id):
    """Unblock a previously blocked counterparty."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = session['user_id']
    success, msg = TrustAndSafetyManager.unblock_user(supabase, blocker_id=uid, blocked_id=blocked_id)
    if not success:
        return jsonify({'error': msg}), 404

    AuditLogger.log_event(
        supabase, actor_id=uid, actor_role=session.get('role', 'user'),
        event_type="trust_and_safety", resource_type="blocked_user",
        resource_id=str(blocked_id), action="unblock_user",
        ip_address=request.remote_addr
    )

    return jsonify({'message': msg, 'success': True}), 200


@app.route('/api/blocks', methods=['GET'])
def get_blocked_users_api():
    """List users blocked by the authenticated user."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = session['user_id']
    blocked = TrustAndSafetyManager.get_blocked_users(supabase, blocker_id=uid)
    return jsonify(blocked), 200


# ── Privacy Transparency & Stage Visibility API ─────────────────────

@app.route('/api/privacy/stage-policy', methods=['GET'])
def get_stage_privacy_policy_api():
    """Returns authoritative explanation of what profile, contact, and location info is visible at each stage."""
    return jsonify(LocationPrivacyShield.get_stage_privacy_policy()), 200


@app.route('/api/export-workers', methods=['GET'])
def export_workers():
    """Fetch only the logged-in worker's data and return as CSV for download."""
    if 'user_id' not in session or session.get('role') != 'worker':
        return jsonify({'error': 'Unauthorized'}), 401
    
    uid = session['user_id']
    try:
        # Fetch only the current worker
        resp = supabase.table("workers").select("*").eq("id", uid).execute()
        workers = resp.data
        
        if not workers:
            return jsonify({'error': 'Worker record not found'}), 404
        
        # Clean data (remove passwords, etc.)
        for w in workers:
            w.pop('password', None)
        
        # Also fetch their bookings to include in "all data"
        b_resp = supabase.table("bookings").select("*").eq("worker_id", uid).execute()
        bookings = b_resp.data
        
        # Create CSV
        output = StringIO()
        writer = csv.writer(output)
        
        # Section 1: Profile Info
        writer.writerow(["--- WORKER PROFILE ---"])
        profile = workers[0]
        headers = list(profile.keys())
        writer.writerow(headers)
        # Convert all values to string to be safe
        writer.writerow([str(v) for v in profile.values()])
        
        # Section 2: Booking History
        if bookings:
            writer.writerow([])
            writer.writerow(["--- BOOKING HISTORY ---"])
            b_headers = list(bookings[0].keys())
            writer.writerow(b_headers)
            for b in bookings:
                writer.writerow([str(v) for v in b.values()])
        
        # Convert uid to string before slicing
        filename_id = str(uid)[:8]
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-disposition": f"attachment; filename=worker_data_{filename_id}.csv"}
        )
    except Exception as e:
        import traceback; print(traceback.format_exc())
        return jsonify({'error': 'Failed to export worker data'}), 500

@app.route('/api/worker/stats', methods=['GET'])
def get_worker_stats():
    """Fetch earnings and job stats for the logged-in worker."""
    if 'user_id' not in session or session.get('role') != 'worker':
        return jsonify({'error': 'Unauthorized'}), 401
    
    uid = session['user_id']
    try:
        # 1. Get worker info
        w_resp = supabase.table("workers").select("name, work").eq("id", uid).execute()
        if not w_resp.data:
            return jsonify({'error': 'Worker not found'}), 404
        worker_info = w_resp.data[0]
        
        # 2. Get all completed bookings
        b_resp = supabase.table("bookings").select("*").eq("worker_id", uid).eq("status", "Completed").execute()
        bookings = b_resp.data
        
        # Get worker's current price as fallback
        base_price = 0
        try:
            w_price_resp = supabase.table("workers").select("price").eq("id", uid).execute()
            if w_price_resp.data:
                base_price = w_price_resp.data[0].get('price', 0) or 0
        except: pass

        now = datetime.utcnow()
        today_str = now.strftime('%Y-%m-%d')
        month_str = now.strftime('%Y-%m')
        
        today_earnings = 0
        month_earnings = 0
        
        for b in bookings:
            # Use total_price if exists, otherwise fallback to base_price
            price = b.get('total_price')
            if price is None:
                price = b.get('price') # check other possible name
            if price is None:
                price = base_price
                
            b_date = b.get('date', '')
            if b_date == today_str:
                today_earnings += price
            if b_date.startswith(month_str):
                month_earnings += price
                
        # 3. Get last two jobs (Completed or otherwise)
        # Fetching last 2 based on created_at or date
        last_jobs_resp = supabase.table("bookings").select("*").eq("worker_id", uid).order("date", desc=True).limit(2).execute()
        last_jobs = []
        for lj in last_jobs_resp.data:
            last_jobs.append({
                "work": worker_info['work'], # Since bookings don't have work type yet, use worker's specialty
                "date": lj['date'],
                "status": lj['status']
            })
            
        return jsonify({
            "name": worker_info['name'],
            "today_earnings": today_earnings,
            "month_earnings": month_earnings,
            "total_jobs": len(bookings) if bookings else 0,
            "last_jobs": last_jobs
        }), 200
        
    except Exception as e:
        import traceback; print(traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500

if __name__ == '__main__':
    print("Starting VoiceHire Server...")
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() in ['true', '1', 't']
    port = int(os.environ.get('PORT', 5000))
    print(f"Debug Mode: {debug_mode}, Port: {port}")
    # Using '::' to listen on both IPv4 and IPv6 (handles cases where IPv4 loopback is broken)
    app.run(host='::', port=port, debug=debug_mode)