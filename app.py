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
from datetime import datetime, timedelta, date
from collections import defaultdict
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from dotenv import load_dotenv
from supabase import create_client, Client
from translations import get_translation
import qrcode

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
    """Helper to try selecting with profile_pic/hourly_rate, fallback if column missing."""
    try:
        query = supabase.table(table).select(columns)
        if filters:
            for k, v in filters.items(): query = query.eq(k, v)
        if in_filters:
            for k, v in in_filters.items(): query = query.in_(k, v)
        return query.execute()
    except Exception as e:
        err_str = str(e).lower()
        if 'profile_pic' in err_str or 'hourly_rate' in err_str:
            cols = columns.replace(', profile_pic', '').replace('profile_pic, ', '').replace('profile_pic', '')
            cols = cols.replace(', hourly_rate', '').replace('hourly_rate, ', '').replace('hourly_rate', '')
            query = supabase.table(table).select(cols)
            if filters:
                for k, v in filters.items(): query = query.eq(k, v)
            if in_filters:
                for k, v in in_filters.items(): query = query.in_(k, v)
            resp = query.execute()
            for row in resp.data:
                if 'profile_pic' in columns: row['profile_pic'] = None
                if 'hourly_rate' in columns: row['hourly_rate'] = 500
            return resp
        raise e


def upload_to_supabase_storage(file_obj, folder: str) -> str:
    """Upload a file object to Supabase Storage and return its public URL.
    Files are stored in the 'voicehire-uploads' bucket so they persist
    across server restarts and deployments."""
    ext = file_obj.filename.rsplit('.', 1)[-1].lower()
    filename = f"{folder}/{uuid.uuid4().hex}.{ext}"
    file_bytes = file_obj.read()
    content_type = file_obj.content_type or 'application/octet-stream'
    supabase.storage.from_('voicehire-uploads').upload(
        filename,
        file_bytes,
        {'content-type': content_type, 'upsert': 'true'}
    )
    public_url = f"{supabase_url}/storage/v1/object/public/voicehire-uploads/{filename}"
    return public_url

# ---- TRANSLATION CONFIG ----
@app.context_processor
def inject_translation():
    def t(text):
        lang = session.get('lang', 'en')
        return get_translation(lang, text)
    return dict(t=t)

@app.template_global()
def media_url(path):
    """Return the correct URL for a media file.
    If path is already an absolute URL (Supabase Storage), return it directly.
    Otherwise prefix with /static/ for local legacy files."""
    if not path:
        return None
    if path.startswith('http://') or path.startswith('https://'):
        return path
    # Legacy local path
    return f'/static/{path}'

@app.route('/set_lang/<lang_code>')
def set_lang(lang_code):
    session['lang'] = lang_code
    return redirect(url_for('gateway'))

# ---- TEMPLATE ROUTES ----

@app.route('/')
def index():
    if 'user_id' in session:
        role = session.get('role')
        return redirect(url_for('user_dashboard' if role == 'user' else 'worker_dashboard'))
    return render_template('select_language.html')

@app.route('/home')
def home():
    if 'user_id' in session:
        if session.get('role') == 'user':
            return redirect(url_for('user_dashboard'))
        else:
            return redirect(url_for('worker_dashboard'))
    return render_template('language.html')

@app.route('/gateway')
def gateway():
    # Voice AI assistant page
    if 'user_id' in session:
        role = session.get('role')
        return redirect(url_for('user_dashboard' if role == 'user' else 'worker_dashboard'))
    return render_template('gateway.html')

@app.route('/welcome')
def welcome():
    # Voice-assisted welcome page (optional entry point)
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
        worker_id = session['user_id']
        resp = try_select("workers", "*", filters={"id": worker_id})
        if not resp.data:
            session.clear()
            return redirect(url_for('login_page', role='worker'))
        worker_data = resp.data[0]

        # Fetch real stats from jobs
        jobs_resp = supabase.table("jobs").select("*").eq("worker_id", worker_id).execute()
        jobs = jobs_resp.data or []
        
        # Fetch real stats from bookings
        bookings_resp = supabase.table("bookings").select("*").eq("worker_id", worker_id).execute()
        bookings = bookings_resp.data or []
        
        # Combine completed items
        completed_jobs = [j for j in jobs if j['status'] in ['completed', 'done', 'pending_confirmation']]
        completed_bookings = [b for b in bookings if b['status'] in ['Completed', 'Work Started']]
        
        all_completed = completed_jobs + completed_bookings
        
        # Sort by date desc
        all_completed.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        # Get real rating from reviews table
        reviews_resp = supabase.table("reviews").select("*").eq("worker_id", worker_id).order("created_at", desc=True).execute()
        reviews = reviews_resp.data or []
        
        # Gather all user IDs from reviews and last_two jobs
        user_ids_to_fetch = set()
        for r in reviews:
            if r.get('user_id'): user_ids_to_fetch.add(r['user_id'])
            
        last_two = all_completed[:2]
        for j in last_two:
            cid = j.get('user_id') or j.get('customer_id')
            if cid: user_ids_to_fetch.add(cid)
            
        # Fetch all customers in one go
        customer_map = {}
        if user_ids_to_fetch:
            c_resp = try_select("users", "id, name, profile_pic", in_filters={"id": list(user_ids_to_fetch)})
            if c_resp and getattr(c_resp, 'data', None):
                customer_map = {c['id']: c for c in c_resp.data}
                
        # Enrich reviews with customer details
        for r in reviews:
            c_info = customer_map.get(r['user_id'], {})
            r['customer_name'] = c_info.get('name', "Customer")
            r['customer_pic'] = c_info.get('profile_pic')
        
        ratings = [r['rating'] for r in reviews]
        avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0.0
        review_count = len(ratings)
        
        # Update worker data with real rating
        worker_data['avg_rating'] = avg_rating
        worker_data['review_count'] = review_count
        worker_data['detailed_reviews'] = reviews

        # Calculate daily and monthly stats
        today = datetime.now().strftime("%Y-%m-%d")
        this_month = datetime.now().strftime("%Y-%m")
        
        for j in last_two:
            # Check if it's a job or booking and fetch customer name
            cid = j.get('user_id') or j.get('customer_id')
            c_info = customer_map.get(cid, {})
            j['customer_name'] = c_info.get('name') if c_info.get('name') else j.get('user_name', 'Customer')
        
        # Use hourly_rate if available, else default to 500
        hourly_rate = int(worker_data.get('hourly_rate', 500))
        
        # Get real reviews count for today
        reviews_all = reviews_resp.data or []
        reviews_today = [r for r in reviews_all if r.get('created_at', '').startswith(today)]
        
        stats = {
            "total_services": len(all_completed),
            "pending_requests": len([j for j in jobs if j['status'] == 'open']) + len([b for b in bookings if b['status'] == 'Pending']),
            "completed_jobs": len(all_completed),
            "completed_month": len([j for j in all_completed if j.get('created_at', '').startswith(this_month)]),
            "earnings": sum([int(j.get('amount', hourly_rate)) for j in all_completed]),
            "earnings_today": sum([int(j.get('amount', hourly_rate)) for j in all_completed if j.get('created_at', '').startswith(today)]),
            "earnings_month": sum([int(j.get('amount', hourly_rate)) for j in all_completed if j.get('created_at', '').startswith(this_month)]),
            "reviews_today": len(reviews_today),
            "recent_works": [f"{j.get('customer_name')} on {j.get('created_at')[:10]}" for j in all_completed]
        }

        return render_template('worker_dashboard.html', worker=worker_data, stats=stats)

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return f"Database error: {e}"

@app.route('/api/worker/stats')
def worker_stats_api():
    """Real-time stats endpoint polled by the worker dashboard every 30 seconds."""
    if 'user_id' not in session or session.get('role') != 'worker':
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        worker_id = session['user_id']

        worker_resp = try_select("workers", "hourly_rate", filters={"id": worker_id})
        worker_data = worker_resp.data[0] if worker_resp and worker_resp.data else {}
        hourly_rate = int(worker_data.get('hourly_rate') or 500)

        jobs_resp = supabase.table("jobs").select("status, amount, created_at").eq("worker_id", worker_id).execute()
        jobs = jobs_resp.data or []

        bookings_resp = supabase.table("bookings").select("status, amount, created_at, customer_id").eq("worker_id", worker_id).execute()
        bookings = bookings_resp.data or []

        completed_jobs = [j for j in jobs if j['status'] in ['completed', 'done', 'pending_confirmation']]
        completed_bookings = [b for b in bookings if b['status'] in ['Completed', 'Work Started']]
        all_completed = completed_jobs + completed_bookings

        reviews_resp = supabase.table("reviews").select("rating, created_at").eq("worker_id", worker_id).execute()
        reviews_all = reviews_resp.data or []

        today = datetime.now().strftime("%Y-%m-%d")
        this_month = datetime.now().strftime("%Y-%m")

        reviews_today = [r for r in reviews_all if r.get('created_at', '').startswith(today)]

        stats = {
            "total_services": len(all_completed),
            "pending_requests": len([j for j in jobs if j['status'] == 'open']) + len([b for b in bookings if b['status'] == 'Pending']),
            "completed_month": len([j for j in all_completed if j.get('created_at', '').startswith(this_month)]),
            "earnings_today": sum([int(j.get('amount') or hourly_rate) for j in all_completed if j.get('created_at', '').startswith(today)]),
            "earnings_month": sum([int(j.get('amount') or hourly_rate) for j in all_completed if j.get('created_at', '').startswith(this_month)]),
            "reviews_today": len(reviews_today),
            "hourly_rate": hourly_rate,
        }
        return jsonify(stats), 200
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500


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
        hourly_rate = request.form.get('hourly_rate', 500)
        
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
            "hourly_rate": int(hourly_rate) if str(hourly_rate).isdigit() else 500,
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
        return jsonify({'error': 'Valid phone, password, and role ("user" or "worker") are required'}), 400

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
            voice_path = upload_to_supabase_storage(voice_file, 'audio')

        if video_file and video_file.filename != '':
            if not allowed_file(video_file.filename, ALLOWED_VIDEO_EXTENSIONS):
                return jsonify({'error': 'Invalid video file type'}), 400
            video_path = upload_to_supabase_storage(video_file, 'video')

        id_file = request.files.get('id_proof')
        if id_file and id_file.filename != '':
            if not allowed_file(id_file.filename, ALLOWED_IMAGE_EXTENSIONS):
                return jsonify({'error': 'Invalid image file type for ID proof'}), 400
            id_path = upload_to_supabase_storage(id_file, 'ids')

        profile_pic = request.files.get('profile_pic')
        if profile_pic and profile_pic.filename != '':
            if not allowed_file(profile_pic.filename, ALLOWED_IMAGE_EXTENSIONS):
                return jsonify({'error': 'Invalid image file type for profile picture'}), 400
            profile_pic_path = upload_to_supabase_storage(profile_pic, 'profile_pics')

        lat = request.form.get('latitude')
        lng = request.form.get('longitude')
        hourly_rate = request.form.get('hourly_rate')

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
        
        if hourly_rate:
            update_data["hourly_rate"] = int(hourly_rate) if str(hourly_rate).isdigit() else 500

        if password:
            if len(password) < 6:
                return jsonify({'error': 'Password must be at least 6 characters'}), 400
            update_data["password"] = generate_password_hash(password)

        try:
            supabase.table("workers").update(update_data).eq("id", worker_id).execute()
        except Exception as e:
            err_str = str(e).lower()
            if 'hourly_rate' in err_str or 'profile_pic' in err_str:
                return jsonify({'error': 'Schema Error: Please add "hourly_rate" (integer) and "profile_pic" (text) columns to the "workers" table in Supabase.'}), 400
            if 'duplicate key' in err_str:
                return jsonify({'error': 'Phone number already exists for another account.'}), 400
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
def get_workers():
    work_filter = safe_str(request.args.get('work'))
    location_filter = safe_str(request.args.get('location'))

    try:
        query = supabase.table("workers").select("*")

        if work_filter and work_filter.lower() != 'all':
            query = query.ilike("work", f"%{work_filter}%")
        if location_filter:
            query = query.ilike("location", f"%{location_filter}%")

        workers_resp = query.execute()
        workers = workers_resp.data

        # Fetch all reviews to compute aggregates
        try:
            reviews_resp = supabase.table("reviews").select("worker_id, rating").execute()
            review_map = defaultdict(list)
            for r in reviews_resp.data:
                review_map[r['worker_id']].append(r['rating'])
        except Exception:
            review_map = {}

        for w in workers:
            ratings = review_map.get(w['id'], [])
            w['avg_rating'] = round(sum(ratings) / len(ratings), 2) if ratings else 0
            w['review_count'] = len(ratings)

        # Sort: available first, then by rating desc, then review count desc
        workers.sort(key=lambda w: (not w.get('is_available', True), -w['avg_rating'], -w['review_count']))

        return jsonify(workers), 200
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500

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

    try:
        # Check if jobs table has the new column by trying a safe insert or just ignoring it if it fails
        # For now, let's keep it simple and handle errors
        supabase.table("jobs").insert({
            "user_id": session['user_id'],
            "user_name": session['name'],
            "user_phone": session.get('phone', 'Unknown'),
            "user_profile_pic": session.get('profile_pic'),
            "service_type": service_type,
            "description": description,
            "location": location,
            "is_urgent": bool(data.get('is_urgent')),
            "status": "open"
        }).execute()
        return jsonify({'message': 'Job posted successfully!'}), 201
    except Exception as e:
        print("Error posting job:\n", traceback.format_exc())
        # Try inserting without the new column if it failed (likely due to missing column)
        try:
            supabase.table("jobs").insert({
                "user_id": session['user_id'],
                "user_name": session['name'],
                "user_phone": session.get('phone', 'Unknown'),
                "service_type": service_type,
                "description": description,
                "location": location,
                "status": "open"
            }).execute()
            return jsonify({'message': 'Job posted successfully (without profile pic)!', 'warning': 'Legacy table schema'}), 201
        except Exception:
            return jsonify({'error': 'Server error while posting job'}), 500

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
        worker_map = {}
        if worker_ids:
            workers_resp = supabase.table("workers").select("id, name, phone").in_("id", worker_ids).execute()
            for w in workers_resp.data:
                worker_map[w['id']] = w

        for j in jobs:
            wid = j.get('worker_id')
            if wid and wid in worker_map:
                j['worker_name'] = worker_map[wid]['name']
                j['worker_phone'] = worker_map[wid]['phone']
            else:
                j['worker_name'] = None
                j['worker_phone'] = None

        return jsonify(jobs), 200
    except Exception as e:
        print("Error fetching customer jobs:\n", traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500

@app.route('/api/jobs/<int:job_id>/accept', methods=['POST'])
def accept_job(job_id):
    if 'user_id' not in session or session['role'] != 'worker':
        return jsonify({'error': 'Unauthorized'}), 401

    worker_id = session['user_id']
    try:
        job_resp = supabase.table("jobs").select("status").eq("id", job_id).execute()
        if not job_resp.data:
            return jsonify({'error': 'Job not found'}), 404
        if job_resp.data[0]['status'] != 'open':
            return jsonify({'error': 'Job is no longer open'}), 400

        token = secrets.token_urlsafe(32)
        expires = (datetime.utcnow() + timedelta(hours=48)).isoformat()

        supabase.table("jobs").update({
            "status": "accepted", "worker_id": worker_id,
            "completion_token": token, "token_expires_at": expires
        }).eq("id", job_id).execute()
        return jsonify({'message': 'Job accepted successfully'}), 200
    except Exception as e:
        print("Error accepting job:\n", traceback.format_exc())
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
    if 'user_id' not in session or session['role'] != 'user':
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session['user_id']
    try:
        data = request.get_json() or {}
        new_status = safe_str(data.get('status'))
        if new_status not in ['open', 'completed', 'cancelled']:
            return jsonify({'error': 'Invalid status'}), 400

        job_resp = supabase.table("jobs").select("id").eq("id", job_id).eq("user_id", user_id).execute()
        if not job_resp.data:
            return jsonify({'error': 'Job not found or unauthorized'}), 404

        supabase.table("jobs").update({"status": new_status}).eq("id", job_id).execute()
        return jsonify({'message': f'Job marked as {new_status}'}), 200
    except Exception as e:
        print("Error updating job status:\n", traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500

@app.route('/api/workers/<int:worker_id>/rate', methods=['POST'])
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
#  BOOKING & QR VERIFICATION SYSTEM (from partner's codebase)
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
    """Render a QR code as a base64-encoded PNG string."""
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
    img.save(buf, format="PNG")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')


# ── Booking Page Routes ──────────────────────────────────────────────

@app.route('/bookings')
def my_bookings_page():
    if 'user_id' not in session:
        return redirect(url_for('login_page', role='user'))
    return render_template('my_bookings.html', name=session.get('name'))


@app.route('/bookings/<int:booking_id>')
def booking_detail_page(booking_id):
    if 'user_id' not in session:
        return redirect(url_for('login_page', role='user'))
    try:
        resp = supabase.table("bookings").select("*").eq("id", booking_id).execute()
        if not resp.data:
            return "Booking not found", 404
        booking = resp.data[0]

        uid = session['user_id']
        role = session.get('role')
        if booking['customer_id'] != uid and booking['worker_id'] != uid:
            return "Unauthorized", 403

        w_resp = try_select("workers", "name, phone, work, profile_pic, hourly_rate", filters={"id": booking['worker_id']})
        worker = w_resp.data[0] if w_resp.data else {}

        c_resp = try_select("users", "name, phone, profile_pic", filters={"id": booking['customer_id']})
        customer = c_resp.data[0] if c_resp.data else {}

        token = make_qr_token(booking_id)
        qr_data = {"bid": booking_id, "tok": token}
        qr_b64 = generate_qr_base64(qr_data)
        
        is_customer = (role == 'user' and uid == booking['customer_id'])
        has_reviewed = False
        if booking['status'] == 'Completed' and is_customer:
            try:
                r_resp = supabase.table("reviews").select("id").eq("job_id", booking_id).eq("user_id", uid).execute()
                has_reviewed = bool(r_resp.data)
            except:
                pass

        return render_template(
            'booking_detail.html',
            booking=booking,
            worker=worker,
            customer=customer,
            qr_b64=qr_b64,
            role=role,
            is_customer=is_customer,
            has_reviewed=has_reviewed
        )
    except Exception as e:
        print(traceback.format_exc())
        return f"Error: {e}", 500


@app.route('/book/<int:worker_id>')
def book_worker_page(worker_id):
    if 'user_id' not in session or session.get('role') != 'user':
        return redirect(url_for('login_page', role='user'))
    try:
        resp = supabase.table("workers").select("*").eq("id", worker_id).execute()
        if not resp.data:
            return "Worker not found", 404
        worker = resp.data[0]
        
        # Fetch ratings/reviews for portfolio
        reviews_resp = supabase.table("reviews").select("*").eq("worker_id", worker_id).order("created_at", desc=True).execute()
        reviews = reviews_resp.data or []
        
        user_ids_to_fetch = list(set([r['user_id'] for r in reviews if r.get('user_id')]))
        customer_map = {}
        if user_ids_to_fetch:
            c_resp = try_select("users", "id, name, profile_pic", in_filters={"id": user_ids_to_fetch})
            if c_resp and getattr(c_resp, 'data', None):
                customer_map = {c['id']: c for c in c_resp.data}
                
        for r in reviews:
            c_info = customer_map.get(r['user_id'], {})
            r['customer_name'] = c_info.get('name') if c_info.get('name') else "Customer"
            r['customer_pic'] = c_info.get('profile_pic')
            
        worker['detailed_reviews'] = reviews
        ratings = [r['rating'] for r in reviews if r.get('rating')]
        worker['avg_rating'] = round(sum(ratings) / len(ratings), 1) if ratings else 0.0
        worker['review_count'] = len(ratings)
        
        # Fetch completed work for portfolio from both jobs and bookings tables
        jobs_history = supabase.table("jobs").select("*").eq("worker_id", worker_id).in_("status", ["completed", "Completed"]).execute().data or []
        bookings_history = supabase.table("bookings").select("*").eq("worker_id", worker_id).in_("status", ["completed", "Completed", "Success", "Success!"]).execute().data or []
        
        history = jobs_history + bookings_history
        history.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        # Extract meaningful descriptions for the history items
        worker['work_history'] = []
        for h in history:
            date = h.get('created_at', 'Recently')[:10]
            service = h.get('service_type') or h.get('work') or "Service"
            worker['work_history'].append(f"{service} completed on {date}")

        return render_template('booking_slots.html', worker=worker, slots=TIME_SLOTS)
    except Exception as e:
        print(traceback.format_exc())
        return f"Error: {e}", 500


# ── Booking API Routes ───────────────────────────────────────────────

@app.route('/api/bookings/slots', methods=['GET'])
def get_available_slots():
    worker_id = request.args.get('worker_id', '').strip()
    date_str  = request.args.get('date', '').strip()
    if not worker_id or not date_str:
        return jsonify({'error': 'worker_id and date are required'}), 400
    try:
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
        w_resp = supabase.table("workers").select("id, name").eq("id", worker_id).execute()
        if not w_resp.data:
            return jsonify({'error': 'Worker not found'}), 404

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
            "qr_token":    str(uuid.uuid4().hex) # Use UUID string for token
        }
        
        # Use list for insert to be extra safe with some client versions
        insert_resp = supabase.table("bookings").insert([insert_data]).execute()
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
def get_my_bookings():
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

        # Check for existing reviews if the user is a customer
        reviewed_booking_ids = set()
        completed_ids = [b['id'] for b in bookings if b['status'] == 'Completed']
        if completed_ids and session.get('role') == 'user':
            try:
                r_resp = supabase.table("reviews").select("job_id").in_("job_id", completed_ids).eq("user_id", uid).execute()
                reviewed_booking_ids = {r['job_id'] for r in r_resp.data}
            except Exception as e:
                print(f"Error fetching reviews in bulk: {e}")

        # Enrich bookings
        for b in bookings:
            c_info = customer_map.get(b['customer_id'], {})
            w_info = worker_map.get(b['worker_id'], {})

            b['customer_name'] = c_info.get('name', 'Unknown')
            b['customer_profile_pic'] = c_info.get('profile_pic')

            b['worker_name'] = w_info.get('name', 'Unknown')
            b['worker_work'] = w_info.get('work', 'N/A')
            b['worker_profile_pic'] = w_info.get('profile_pic')
            
            # Attach review status
            b['has_reviewed'] = b['id'] in reviewed_booking_ids

        return jsonify(bookings), 200
    except Exception as e:
        print(f"Error fetching bookings: {e}")
        return jsonify([]), 200


@app.route('/api/bookings/<int:booking_id>', methods=['GET'])
def get_booking(booking_id):
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


@app.route('/api/bookings/<int:booking_id>/checkin', methods=['POST'])
def checkin_booking(booking_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        data  = request.get_json() or {}
        token = safe_str(data.get('token', ''))
        if not token:
            return jsonify({'error': 'QR token is required'}), 400

        resp = supabase.table("bookings").select("*").eq("id", booking_id).execute()
        if not resp.data:
            return jsonify({'error': 'Booking not found'}), 404
        booking = resp.data[0]
        uid = session['user_id']
        if booking['customer_id'] != uid and booking['worker_id'] != uid:
            return jsonify({'error': 'Unauthorized'}), 403
        if booking['status'] != 'Booked':
            return jsonify({'error': f"Cannot check in. Current status: {booking['status']}"}), 400
        if not verify_qr_token(booking_id, token):
            return jsonify({'error': 'Invalid or expired QR code'}), 403

        supabase.table("bookings").update({"status": "Work Started"}).eq("id", booking_id).execute()
        return jsonify({'message': 'Check-in successful! Work has started.', 'status': 'Work Started'}), 200
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/bookings/<int:booking_id>/complete', methods=['POST'])
def complete_booking(booking_id):
    if 'user_id' not in session or session.get('role') != 'user':
        return jsonify({'error': 'Unauthorized'}), 401
    uid = session['user_id']
    try:
        resp = supabase.table("bookings").select("*").eq("id", booking_id).execute()
        if not resp.data:
            return jsonify({'error': 'Booking not found'}), 404
        booking = resp.data[0]
        if booking['customer_id'] != uid:
            return jsonify({'error': 'Only the customer can mark work as complete'}), 403
        if booking['status'] != 'Work Started':
            return jsonify({'error': f"Work must be started before completing. Current: {booking['status']}"}), 400
        supabase.table("bookings").update({"status": "Completed"}).eq("id", booking_id).execute()
        return jsonify({'message': 'Work marked as completed!', 'status': 'Completed'}), 200
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/bookings/<int:booking_id>/review', methods=['POST'])
def review_booking(booking_id):
    if 'user_id' not in session or session.get('role') != 'user':
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        data = request.get_json() or {}
        rating = int(data.get('rating', 0))
        review_text = safe_str(data.get('review', ''))
        
        if not (1 <= rating <= 5):
            return jsonify({'error': 'Valid rating (1-5) is required'}), 400
            
        uid = session['user_id']
        
        resp = supabase.table("bookings").select("*").eq("id", booking_id).execute()
        if not resp.data:
            return jsonify({'error': 'Booking not found'}), 404
            
        booking = resp.data[0]
        if booking['customer_id'] != uid:
            return jsonify({'error': 'Unauthorized'}), 403
        if booking['status'] != 'Completed':
            return jsonify({'error': 'Booking must be completed to leave a review'}), 400
            
        # Check for duplicate review per booking (1 review per booking, not per worker)
        dup_resp = supabase.table("reviews").select("id").eq("booking_id", booking_id).eq("user_id", uid).execute()
        if dup_resp.data:
            return jsonify({'error': 'You have already submitted a review for this booking'}), 400
            
        supabase.table("reviews").insert({
            "booking_id": booking_id,
            "worker_id": booking['worker_id'],
            "user_id": uid,
            "rating": rating,
            "review": review_text
        }).execute()
        
        return jsonify({'message': 'Review submitted successfully!'}), 201
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/bookings/<int:booking_id>/cancel', methods=['POST'])
def cancel_booking(booking_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    uid = session['user_id']
    try:
        resp = supabase.table("bookings").select("*").eq("id", booking_id).execute()
        if not resp.data:
            return jsonify({'error': 'Booking not found'}), 404
        booking = resp.data[0]
        if booking['customer_id'] != uid and booking['worker_id'] != uid:
            return jsonify({'error': 'Unauthorized'}), 403
        if booking['status'] in ('Completed', 'Cancelled'):
            return jsonify({'error': 'Cannot cancel'}), 400
        supabase.table("bookings").update({"status": "Cancelled"}).eq("id", booking_id).execute()
        return jsonify({'message': 'Booking cancelled.', 'status': 'Cancelled'}), 200
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/bookings/<int:booking_id>/accept', methods=['POST'])
def accept_booking(booking_id):
    if 'user_id' not in session or session.get('role') != 'worker':
        return jsonify({'error': 'Unauthorized'}), 401
    uid = session['user_id']
    try:
        resp = supabase.table("bookings").select("*").eq("id", booking_id).execute()
        if not resp.data:
            return jsonify({'error': 'Booking not found'}), 404
        booking = resp.data[0]
        if booking['worker_id'] != uid:
            return jsonify({'error': 'Unauthorized'}), 403
        if booking['status'] != 'Pending':
            return jsonify({'error': f"Cannot accept. Current status: {booking['status']}"}), 400
        supabase.table("bookings").update({"status": "Booked"}).eq("id", booking_id).execute()
        return jsonify({'message': 'Booking accepted!', 'status': 'Booked'}), 200
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/bookings/<int:booking_id>/decline', methods=['POST'])
def decline_booking(booking_id):
    if 'user_id' not in session or session.get('role') != 'worker':
        return jsonify({'error': 'Unauthorized'}), 401
    uid = session['user_id']
    try:
        resp = supabase.table("bookings").select("*").eq("id", booking_id).execute()
        if not resp.data:
            return jsonify({'error': 'Booking not found'}), 404
        booking = resp.data[0]
        if booking['worker_id'] != uid:
            return jsonify({'error': 'Unauthorized'}), 403
        if booking['status'] != 'Pending':
            return jsonify({'error': 'Cannot decline a booking that is not pending'}), 400
        supabase.table("bookings").update({"status": "Cancelled"}).eq("id", booking_id).execute()
        return jsonify({'message': 'Booking declined.', 'status': 'Cancelled'}), 200
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'error': 'Server error'}), 500

if __name__ == '__main__':
    print("Starting VoiceHire Server...")
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() in ['true', '1', 't']
    port = int(os.environ.get('PORT', 5000))
    print(f"Debug Mode: {debug_mode}, Port: {port}")
    # Using '::' to listen on both IPv4 and IPv6 (handles cases where IPv4 loopback is broken)
    app.run(host='::', port=port, debug=debug_mode)
