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
from io import StringIO
from datetime import datetime, timedelta, date
from collections import defaultdict
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response
from flask_cors import CORS
from dotenv import load_dotenv
from supabase import create_client, Client
from translations import get_translation
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
    ServiceCategoryManager,
    WorkerSkillsManager,
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

# ---- TRANSLATION CONFIG ----
@app.context_processor
def inject_translation():
    def t(text):
        lang = session.get('lang', 'en')
        return get_translation(lang, text)
    return dict(t=t)

@app.route('/set_lang/<lang_code>')
def set_lang(lang_code):
    session['lang'] = lang_code
    # Stay on landing page after language change
    return redirect(url_for('index'))

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
        # Session rotation & authoritative role persistence
        session.clear()
        session['user_id'] = user_id
        session['role'] = 'user'
        session['name'] = name
        session['phone'] = phone

        return jsonify({'message': 'User registered successfully', 'role': 'user', 'redirect': url_for('user_dashboard')}), 201
    except Exception as e:
        print("Error during user signup:\n", traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500

@app.route('/api/auth/signup/worker', methods=['POST'])
def signup_worker():
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
        # Session rotation & authoritative role persistence
        session.clear()
        session['user_id'] = worker_id
        session['role'] = 'worker'
        session['name'] = name
        session['phone'] = phone

        return jsonify({'message': 'Worker registered successfully', 'role': 'worker', 'redirect': url_for('worker_dashboard')}), 201
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

            # Prevent session fixation by rotating session
            session.clear()
            session['user_id'] = user['id']
            session['role'] = role
            session['name'] = user['name']
            session['phone'] = user['phone']

            redirect_url = url_for('user_dashboard') if role == 'user' else url_for('worker_dashboard')
            return jsonify({
                'message': 'Login successful',
                'role': role,
                'redirect': redirect_url
            }), 200

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

@app.route('/get_workers', methods=['GET'])
@app.route('/api/workers', methods=['GET'])
def get_workers():
    work_filter = safe_str(request.args.get('work') or request.args.get('category'))
    location_filter = safe_str(request.args.get('location'))

    try:
        query = supabase.table("workers").select("*")

        if work_filter and work_filter.lower() != 'all':
            query = query.ilike("work", f"%{work_filter}%")
        if location_filter:
            query = query.ilike("location", f"%{location_filter}%")

        workers_resp = query.execute()
        workers = workers_resp.data or []

        # Fetch all reviews to compute aggregates
        try:
            reviews_resp = supabase.table("reviews").select("worker_id, rating").execute()
            review_map = defaultdict(list)
            for r in (reviews_resp.data or []):
                review_map[r['worker_id']].append(r['rating'])
        except Exception:
            review_map = {}

        for w in workers:
            ratings = review_map.get(w['id'], [])
            w['avg_rating'] = round(sum(ratings) / len(ratings), 2) if ratings else 0
            w['review_count'] = len(ratings)

        # Sort: available first, then by rating desc, then review count desc
        workers.sort(key=lambda w: (not w.get('is_available', True), -w['avg_rating'], -w['review_count']))

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
            workers = workers[start_idx:start_idx + limit]

        # Obfuscate privacy-sensitive coordinates and fields for public browsing
        sanitized = [
            LocationPrivacyShield.obfuscate_worker_profile(w, viewer_is_counterparty=False)
            for w in workers
        ]

        return jsonify(sanitized), 200
    except Exception as e:
        print("Error fetching workers:\n", traceback.format_exc())
        return jsonify([]), 200


@app.route('/api/workers/nearby', methods=['GET'])
def get_nearby_jobs():
    """
    GET /api/workers/nearby?limit=5
    Returns open jobs for the logged-in worker, prioritized by worker specialty/trade.
    """
    if 'user_id' not in session or session.get('role') != 'worker':
        return jsonify({'error': 'Unauthorized'}), 401

    worker_id = session['user_id']
    limit = request.args.get('limit', 5)
    try:
        limit = int(limit)
    except (ValueError, TypeError):
        limit = 5

    try:
        # Fetch current worker's trade and location for relevance matching
        w_resp = supabase.table("workers").select("work, location").eq("id", worker_id).execute()
        worker_work = ""
        worker_loc = ""
        if w_resp.data:
            worker_work = (w_resp.data[0].get('work') or '').lower()
            worker_loc = (w_resp.data[0].get('location') or '').lower()

        # Query open jobs
        jobs_resp = supabase.table("jobs").select("*").eq("status", "open").execute()
        jobs = jobs_resp.data or []

        # Score relevance
        for j in jobs:
            score = 0
            st = (j.get('service_type') or '').lower()
            loc = (j.get('location') or '').lower()
            if worker_work and (worker_work in st or st in worker_work):
                score += 10
            if worker_loc and (worker_loc in loc or loc in worker_loc):
                score += 5
            if j.get('is_urgent'):
                score += 8
            j['relevance_score'] = score

        # Sort by relevance desc, then created_at desc
        jobs.sort(key=lambda j: (j.get('relevance_score', 0), j.get('created_at', '')), reverse=True)

        return jsonify(jobs[:limit]), 200
    except Exception as e:
        print("Error fetching nearby jobs for worker:\n", traceback.format_exc())
        return jsonify([]), 200

@app.route('/api/jobs', methods=['POST'])
def post_job():
    if 'user_id' not in session or session['role'] != 'user':
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        data = request.get_json() or {}
    except Exception:
        return jsonify({'error': 'Invalid JSON data'}), 400

    service_type = safe_str(data.get('service_type'))
    description = safe_str(data.get('description'))
    location = safe_str(data.get('location'))

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

        jobs = open_resp.data + accepted_resp.data
        # Sort: urgent first, then newest first
        jobs.sort(key=lambda j: (not j.get('is_urgent', False), j.get('created_at', '') ), reverse=False)
        jobs.sort(key=lambda j: j.get('is_urgent', False), reverse=True)

        return jsonify(jobs), 200
    except Exception as e:
        print("Error fetching jobs:\n", traceback.format_exc())
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
                w_resp = supabase.table("workers").select("id, name, work, avg_rating, review_count, is_verified").in_("id", worker_ids).execute()
                w_map = {w['id']: w for w in (w_resp.data or [])}
                for o in offers:
                    o['worker'] = w_map.get(o['worker_id'], {})
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
        worker = w_resp.data[0] if w_resp.data else {}

        # Fetch customer info
        c_resp = try_select("users", "name, phone, profile_pic", filters={"id": booking['customer_id']})
        customer = c_resp.data[0] if c_resp.data else {}
        token = make_qr_token(booking_id)
        qr_data = {"bid": booking_id, "tok": token}
        qr_b64 = generate_qr_base64(qr_data)

        return render_template(
            'booking_detail.html',
            booking=booking,
            worker=worker,
            customer=customer,
            qr_b64=qr_b64,
            role=role,
            is_customer=(uid == booking['customer_id'])
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
    date_str  = safe_str(data.get('date'))
    time_slot = safe_str(data.get('time_slot'))
    notes     = safe_str(data.get('notes', ''))

    if not worker_id or not date_str or not time_slot:
        return jsonify({'error': 'worker_id, date, and time_slot are required'}), 400
    if time_slot not in TIME_SLOTS:
        return jsonify({'error': 'Invalid time slot'}), 400
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'date must be YYYY-MM-DD'}), 400

    customer_id = session['user_id']
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
        return jsonify({
            'message':    'Booking confirmed!',
            'booking_id': new_id,
            'redirect':   url_for('booking_detail_page', booking_id=new_id)
        }), 201
    except Exception as e:
        err_msg = str(e)
        tb = traceback.format_exc()
        print(f"DEBUG: create_booking failed. Error: {err_msg}\n{tb}")
        return jsonify({
            'error': f'Server Error: {err_msg}',
            'traceback': tb
        }), 500


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
def get_booking(booking_id):
    """Fetch a single booking's current status (used for polling)."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    uid = session['user_id']
    try:
        resp = supabase.table("bookings").select("*").eq("id", booking_id).execute()
        if not resp.data:
            return jsonify({'error': 'Not found'}), 404
        b = resp.data[0]
        if b['customer_id'] != uid and b['worker_id'] != uid:
            return jsonify({'error': 'Unauthorized'}), 403
        return jsonify(b), 200
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/bookings/<booking_id>/checkin', methods=['POST'])
@app.route('/api/bookings/<int:booking_id>/checkin', methods=['POST'])
def checkin_booking(booking_id):
    """
    POST /api/bookings/<booking_id>/checkin
    Body: { "token": "<qr_token>", "lat": ..., "lng": ... }
    Verifies QR token, enforces state transitions, and marks booking as 'Work Started'.
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        data = request.get_json() or {}
        token = safe_str(data.get('token', ''))
        client_lat = data.get('lat')
        client_lng = data.get('lng')

        if not token:
            return jsonify({'error': 'QR token is required'}), 400

        resp = supabase.table("bookings").select("*").eq("id", booking_id).execute()
        if not resp.data:
            return jsonify({'error': 'Booking not found'}), 404
        booking = resp.data[0]
        uid = session['user_id']
        role = session.get('role', 'worker')

        if str(booking['customer_id']) != str(uid) and str(booking['worker_id']) != str(uid):
            return jsonify({'error': 'Unauthorized'}), 403

        # State transition validation
        if booking['status'] not in ('Booked', 'Pending'):
            CheckinEventLogger.log_checkin(
                supabase, booking_id, booking['worker_id'], booking['customer_id'],
                event_type='checkin_attempt', status='failed', token=token,
                ip_address=request.remote_addr, user_agent=request.user_agent.string if request.user_agent else None,
                failure_reason=f"Invalid current status: {booking['status']}"
            )
            return jsonify({'error': f"Cannot check in. Current status: {booking['status']}"}), 400

        # Verify token (handle both UUID hex and HMAC tokens)
        token_valid = (token == booking.get('qr_token')) or verify_qr_token(booking_id, token)
        if not token_valid:
            CheckinEventLogger.log_checkin(
                supabase, booking_id, booking['worker_id'], booking['customer_id'],
                event_type='checkin_attempt', status='failed', token=token,
                ip_address=request.remote_addr, user_agent=request.user_agent.string if request.user_agent else None,
                failure_reason="Invalid or expired QR token"
            )
            return jsonify({'error': 'Invalid or expired QR code'}), 403

        # Success - log checkin event
        CheckinEventLogger.log_checkin(
            supabase, booking_id, booking['worker_id'], booking['customer_id'],
            event_type='checkin_verified', status='success', token=token,
            client_lat=client_lat, client_lng=client_lng,
            ip_address=request.remote_addr, user_agent=request.user_agent.string if request.user_agent else None
        )

        supabase.table("bookings").update({
            "status": "Work Started",
            "updated_at": utc_now_iso()
        }).eq("id", booking_id).execute()

        # Log status transition
        StatusHistoryLogger.log_booking_status(
            supabase, booking_id, booking['status'], "Work Started", uid, role, reason="QR check-in successful"
        )

        # Notify counterparties
        notify_target = booking['customer_id'] if str(uid) == str(booking['worker_id']) else booking['worker_id']
        notify_role = "user" if str(uid) == str(booking['worker_id']) else "worker"
        NotificationService.send_notification(
            supabase,
            recipient_id=notify_target,
            recipient_role=notify_role,
            title="Work Started",
            message=f"Check-in verified for booking #{booking_id}. Work has begun!",
            notif_type="checkin",
            reference_id=str(booking_id)
        )

        AuditLogger.log_event(
            supabase, actor_id=uid, actor_role=role,
            event_type="booking_lifecycle", resource_type="booking",
            resource_id=str(booking_id), action="checkin",
            ip_address=request.remote_addr
        )

        return jsonify({'message': 'Check-in successful! Work has started.', 'status': 'Work Started'}), 200
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/bookings/<booking_id>/complete', methods=['POST'])
@app.route('/api/bookings/<int:booking_id>/complete', methods=['POST'])
def complete_booking(booking_id):
    """
    POST /api/bookings/<booking_id>/complete
    Customer marks the job as done → status = 'Completed'.
    """
    if 'user_id' not in session or session.get('role') != 'user':
        return jsonify({'error': 'Unauthorized: Only the customer can mark work as complete'}), 401

    uid = session['user_id']
    try:
        resp = supabase.table("bookings").select("*").eq("id", booking_id).execute()
        if not resp.data:
            return jsonify({'error': 'Booking not found'}), 404
        booking = resp.data[0]
        if str(booking['customer_id']) != str(uid):
            return jsonify({'error': 'Only the customer can mark work as complete'}), 403
        if booking['status'] != 'Work Started':
            return jsonify({'error': f"Work must be started before completing. Current: {booking['status']}"}), 400

        supabase.table("bookings").update({
            "status": "Completed",
            "updated_at": utc_now_iso()
        }).eq("id", booking_id).execute()

        StatusHistoryLogger.log_booking_status(
            supabase, booking_id, "Work Started", "Completed", uid, "user", reason="Customer marked booking complete"
        )
        NotificationService.send_notification(
            supabase,
            recipient_id=booking['worker_id'],
            recipient_role="worker",
            title="Work Completed!",
            message=f"Customer marked booking #{booking_id} as completed. You can collect payment.",
            notif_type="booking_status",
            reference_id=str(booking_id)
        )
        AuditLogger.log_event(
            supabase, actor_id=uid, actor_role="user",
            event_type="booking_lifecycle", resource_type="booking",
            resource_id=str(booking_id), action="complete_booking",
            ip_address=request.remote_addr
        )

        return jsonify({'message': 'Work marked as completed!', 'status': 'Completed'}), 200
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/bookings/<int:booking_id>/cancel', methods=['POST'])
@app.route('/api/bookings/<booking_id>/cancel', methods=['POST'])
def cancel_booking(booking_id):
    """Customer or assigned worker cancels a booking that hasn't finished yet."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = session['user_id']
    role = session.get('role', 'user')
    try:
        resp = supabase.table("bookings").select("*").eq("id", booking_id).execute()
        if not resp.data:
            return jsonify({'error': 'Booking not found'}), 404
        booking = resp.data[0]
        if str(booking['customer_id']) != str(uid) and str(booking['worker_id']) != str(uid):
            return jsonify({'error': 'Unauthorized'}), 403

        if booking['status'] in ('Completed', 'Cancelled'):
            return jsonify({'error': 'Cannot cancel a completed or already cancelled booking'}), 400

        data = request.get_json() or {}
        reason = safe_str(data.get('reason', 'Cancelled by user'))

        supabase.table("bookings").update({
            "status": "Cancelled",
            "cancellation_reason": reason,
            "cancelled_by": uid,
            "updated_at": utc_now_iso()
        }).eq("id", booking_id).execute()

        StatusHistoryLogger.log_booking_status(
            supabase, booking_id, booking['status'], "Cancelled", uid, role, reason=reason
        )

        notify_target = booking['worker_id'] if str(uid) == str(booking['customer_id']) else booking['customer_id']
        notify_role = "worker" if str(uid) == str(booking['customer_id']) else "user"
        NotificationService.send_notification(
            supabase,
            recipient_id=notify_target,
            recipient_role=notify_role,
            title="Booking Cancelled",
            message=f"Booking #{booking_id} was cancelled. Reason: {reason}",
            notif_type="booking_status",
            reference_id=str(booking_id)
        )

        AuditLogger.log_event(
            supabase, actor_id=uid, actor_role=role,
            event_type="booking_lifecycle", resource_type="booking",
            resource_id=str(booking_id), action="cancel_booking",
            ip_address=request.remote_addr, metadata={"reason": reason}
        )

        return jsonify({'message': 'Booking cancelled.', 'status': 'Cancelled'}), 200
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/bookings/<int:booking_id>/accept', methods=['POST'])
@app.route('/api/bookings/<booking_id>/accept', methods=['POST'])
def accept_booking(booking_id):
    """Worker accepts a pending booking."""
    if 'user_id' not in session or session.get('role') != 'worker':
        return jsonify({'error': 'Unauthorized: Only assigned worker can accept'}), 401

    uid = session['user_id']
    try:
        resp = supabase.table("bookings").select("*").eq("id", booking_id).execute()
        if not resp.data:
            return jsonify({'error': 'Booking not found'}), 404
        booking = resp.data[0]
        if str(booking['worker_id']) != str(uid):
            return jsonify({'error': 'Unauthorized: You are not the worker for this booking'}), 403
        if booking['status'] != 'Pending':
            return jsonify({'error': f"Cannot accept. Current status: {booking['status']}"}), 400

        supabase.table("bookings").update({
            "status": "Booked",
            "updated_at": utc_now_iso()
        }).eq("id", booking_id).execute()

        StatusHistoryLogger.log_booking_status(
            supabase, booking_id, "Pending", "Booked", uid, "worker", reason="Worker accepted appointment"
        )
        NotificationService.send_notification(
            supabase,
            recipient_id=booking['customer_id'],
            recipient_role="user",
            title="Booking Confirmed!",
            message=f"The worker accepted your appointment for {booking.get('date')} ({booking.get('time_slot')}).",
            notif_type="booking_status",
            reference_id=str(booking_id)
        )
        AuditLogger.log_event(
            supabase, actor_id=uid, actor_role="worker",
            event_type="booking_lifecycle", resource_type="booking",
            resource_id=str(booking_id), action="accept_booking",
            ip_address=request.remote_addr
        )

        return jsonify({'message': 'Booking accepted!', 'status': 'Booked'}), 200
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/bookings/<int:booking_id>/decline', methods=['POST'])
@app.route('/api/bookings/<booking_id>/decline', methods=['POST'])
def decline_booking(booking_id):
    """Worker declines a pending booking."""
    if 'user_id' not in session or session.get('role') != 'worker':
        return jsonify({'error': 'Unauthorized: Only assigned worker can decline'}), 401

    uid = session['user_id']
    try:
        resp = supabase.table("bookings").select("*").eq("id", booking_id).execute()
        if not resp.data:
            return jsonify({'error': 'Booking not found'}), 404
        booking = resp.data[0]
        if str(booking['worker_id']) != str(uid):
            return jsonify({'error': 'Unauthorized'}), 403
        if booking['status'] != 'Pending':
            return jsonify({'error': 'Cannot decline a booking that is not pending'}), 400

        supabase.table("bookings").update({
            "status": "Cancelled",
            "cancellation_reason": "Declined by worker",
            "cancelled_by": uid,
            "updated_at": utc_now_iso()
        }).eq("id", booking_id).execute()

        StatusHistoryLogger.log_booking_status(
            supabase, booking_id, "Pending", "Cancelled", uid, "worker", reason="Worker declined appointment"
        )
        NotificationService.send_notification(
            supabase,
            recipient_id=booking['customer_id'],
            recipient_role="user",
            title="Booking Declined",
            message="The worker was unable to accept your booking request.",
            notif_type="booking_status",
            reference_id=str(booking_id)
        )
        AuditLogger.log_event(
            supabase, actor_id=uid, actor_role="worker",
            event_type="booking_lifecycle", resource_type="booking",
            resource_id=str(booking_id), action="decline_booking",
            ip_address=request.remote_addr
        )

        return jsonify({'message': 'Booking declined.', 'status': 'Cancelled'}), 200
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500


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
    reported_role = safe_str(data.get('reported_role'))
    reason = safe_str(data.get('reason'))
    description = safe_str(data.get('description'))
    job_id = data.get('job_id')
    booking_id = data.get('booking_id')

    if not reported_id or not reported_role or not reason or not description:
        return jsonify({'error': 'reported_id, reported_role, reason, and description are required'}), 400

    if reported_role not in ('user', 'worker'):
        return jsonify({'error': 'Invalid reported_role'}), 400

    record = {
        "reporter_id": str(reporter_id),
        "reporter_role": reporter_role,
        "reported_id": str(reported_id),
        "reported_role": reported_role,
        "reason": reason,
        "description": description,
        "status": "open",
        "job_id": int(job_id) if (job_id and str(job_id).isdigit()) else job_id,
        "booking_id": int(booking_id) if (booking_id and str(booking_id).isdigit()) else booking_id
    }
    resp = supabase.table("job_reports").insert(record).execute()
    if not resp.data:
        return jsonify({'error': 'Failed to submit report'}), 500

    new_report = resp.data[0]
    AuditLogger.log_event(
        supabase, actor_id=reporter_id, actor_role=reporter_role,
        event_type="dispute", resource_type="job_report",
        resource_id=str(new_report['id']), action="file_report",
        ip_address=request.remote_addr, metadata={"reason": reason, "reported_id": reported_id}
    )

    return jsonify({
        'message': 'Report submitted successfully. Our safety team is investigating.',
        'report_id': new_report['id']
    }), 201


@app.route('/api/reports', methods=['GET'])
def get_my_reports():
    """Retrieve dispute reports filed by the logged-in user."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = session['user_id']
    resp = supabase.table("job_reports").select("*").eq("reporter_id", uid).order("created_at", desc=True).execute()
    return jsonify(resp.data or []), 200


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