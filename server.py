from flask import (
    Flask,
    request,
    send_from_directory,
    send_file,
    abort,
    jsonify,
    session,
    redirect,
    url_for,
    render_template_string
)
import os
import subprocess
import threading
import sys
import time
import json
import re
import secrets
from collections import defaultdict
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
USERS_FILE = os.path.join(BASE_DIR, 'users.json')

app = Flask(__name__)

# Secret key needed for session-based auth
# Generate a random secret if not provided via environment
if 'SCOREBOARD_FLASK_SECRET' not in os.environ:
    app.secret_key = secrets.token_hex(32)
    print("WARNING: Using generated session secret. Set SCOREBOARD_FLASK_SECRET env var for persistence across restarts.")
else:
    app.secret_key = os.environ['SCOREBOARD_FLASK_SECRET']

# Rate limiting for brute force protection
LOGIN_ATTEMPTS = defaultdict(list)  # ip -> [timestamp, ...]
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 300  # 5 minutes

# Configuration
PORT = 8081
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB max upload size

# User management
USERS = {}
USERS_LOCK = threading.Lock()

def load_users():
    """Load users from JSON config file."""
    global USERS
    if not os.path.exists(USERS_FILE):
        print(f"Warning: {USERS_FILE} not found. No users configured.")
        USERS = {}
        return
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            USERS = data.get('users', {})
        print(f"Loaded {len(USERS)} user(s) from {USERS_FILE}")
    except Exception as e:
        print(f"Error loading users file: {e}")
        USERS = {}

def get_user(username):
    """Get user config by username."""
    with USERS_LOCK:
        return USERS.get(username)

def validate_password(username, password):
    """Validate username and password."""
    user = get_user(username)
    if not user:
        return False
    return check_password_hash(user.get('password_hash', ''), password)

def validate_username(username):
    """Check if username is alphanumeric + hyphens only."""
    return username and re.match(r'^[a-z0-9-]+$', username)

def check_rate_limit(ip_address):
    """Check if IP has exceeded login rate limit."""
    now = time.time()
    attempts = LOGIN_ATTEMPTS[ip_address]
    
    # Remove attempts older than the window
    attempts[:] = [timestamp for timestamp in attempts if now - timestamp < LOGIN_WINDOW_SECONDS]
    
    if len(attempts) >= MAX_LOGIN_ATTEMPTS:
        return False  # Rate limited
    return True

def record_login_attempt(ip_address):
    """Record a failed login attempt."""
    LOGIN_ATTEMPTS[ip_address].append(time.time())

# Load users on startup
load_users()

# Scraper state per user
SCRAPER_STATES = {}
SCRAPER_LOCK = threading.Lock()

def _get_user_data_dir(username):
    """Get data directory for a user."""
    return os.path.join(DATA_DIR, username)

def _get_user_state(username):
    """Get or create scraper state for a user."""
    with SCRAPER_LOCK:
        if username not in SCRAPER_STATES:
            user_data_dir = _get_user_data_dir(username)
            os.makedirs(user_data_dir, exist_ok=True)
            SCRAPER_STATES[username] = {
                'process': None,
                'url': None,
                'log_handle': None,
                'log_path': os.path.join(user_data_dir, 'scraper.log'),
                'started_at': None
            }
        return SCRAPER_STATES[username]

def _is_scraper_running_unlocked(state):
    process = state.get('process')
    return process is not None and process.poll() is None

def _cleanup_scraper_state_unlocked(state):
    process = state.get('process')
    log_handle = state.get('log_handle')
    if log_handle:
        try:
            log_handle.flush()
            log_handle.close()
        except Exception:
            pass
    state['process'] = None
    state['url'] = None
    state['log_handle'] = None
    state['started_at'] = None

def _ensure_scraper_not_running(username):
    state = _get_user_state(username)
    with SCRAPER_LOCK:
        if not _is_scraper_running_unlocked(state):
            if state.get('process') is not None:
                _cleanup_scraper_state_unlocked(state)

def _read_log_tail(log_path, max_chars=2000):
    if not log_path or not os.path.exists(log_path):
        return ''
    try:
        with open(log_path, 'r', encoding='utf-8') as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            seek_pos = max(size - max_chars, 0)
            fh.seek(seek_pos)
            if seek_pos > 0:
                fh.readline()
            return fh.read().strip()
    except OSError:
        return ''

LOGIN_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Scoreboard Login</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: Arial, sans-serif; background: #f5f6fa; display:flex; justify-content:center; align-items:center; height:100vh; margin:0; }
        .card { background:#fff; padding:30px; border-radius:8px; box-shadow:0 2px 10px rgba(0,0,0,0.1); max-width:360px; width:100%; }
        h1 { margin-top:0; font-size:1.4rem; text-align:center; }
        label { display:block; margin-bottom:8px; font-weight:bold; }
        input[type=text], input[type=password] { width:100%; box-sizing:border-box; padding:10px; margin-bottom:16px; border:1px solid #dcdde1; border-radius:4px; font-size:1rem; }
        button { width:100%; padding:10px; background:#3498db; color:#fff; border:none; border-radius:4px; font-size:1rem; cursor:pointer; }
        .error { color:#e74c3c; margin-bottom:12px; text-align:center; }
    </style>
</head>
<body>
    <div class="card">
        <h1>Scoreboard Login</h1>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
        <form method="post">
            <input type="hidden" name="next" value="{{ next_url }}">
            <label for="username">Username</label>
            <input type="text" id="username" name="username" required autofocus autocomplete="username">
            <label for="password">Password</label>
            <input type="password" id="password" name="password" required autocomplete="current-password">
            <button type="submit">Login</button>
        </form>
    </div>
</body>
</html>"""

def _is_authenticated():
    return session.get('username') is not None

def _get_current_user():
    return session.get('username')

def _redirect_to_login():
    return redirect(url_for('login', next=request.path))

def _require_user_access(username):
    """Ensure logged-in user matches the requested username."""
    current_user = _get_current_user()
    if not current_user:
        abort(403)
    if current_user != username:
        abort(403)

@app.route('/')
def index():
    """Redirect to login page."""
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Username + password login with rate limiting."""
    next_url = request.args.get('next') or request.form.get('next') or ''
    error = None
    
    if request.method == 'POST':
        # Check rate limit
        ip_address = request.remote_addr
        if not check_rate_limit(ip_address):
            error = 'Too many failed login attempts. Please try again in 5 minutes.'
            return render_template_string(LOGIN_TEMPLATE, error=error, next_url=next_url), 429
        
        username = (request.form.get('username') or '').strip().lower()
        password = request.form.get('password') or ''
        
        if username and validate_username(username) and validate_password(username, password):
            # Successful login - clear any failed attempts
            LOGIN_ATTEMPTS.pop(ip_address, None)
            session['username'] = username
            if next_url:
                return redirect(next_url)
            return redirect(url_for('user_control', username=username))
        
        # Failed login - record attempt
        record_login_attempt(ip_address)
        error = 'Incorrect username or password.'
    
    return render_template_string(LOGIN_TEMPLATE, error=error, next_url=next_url)

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

# User-scoped routes
@app.route('/<username>/')
def user_overlay(username):
    """Public overlay view - no auth required."""
    if not validate_username(username) or not get_user(username):
        abort(404)
    return send_from_directory(os.path.join(BASE_DIR, 'html'), 'index.html')

@app.route('/<username>/control')
def user_control(username):
    """Scraper control UI."""
    if not validate_username(username) or not get_user(username):
        abort(404)
    _require_user_access(username)
    return send_from_directory(os.path.join(BASE_DIR, 'html'), 'control.html')

@app.route('/<username>/scoreboard.html')
def user_scoreboard(username):
    """Manual scoreboard controller."""
    if not validate_username(username) or not get_user(username):
        abort(404)
    _require_user_access(username)
    
    # Read the HTML file and inject the token
    html_path = os.path.join(BASE_DIR, 'html', 'scoreboard.html')
    with open(html_path, 'r') as f:
        html_content = f.read()
    
    user = get_user(username)
    token = user.get('token', '')
    
    return render_template_string(html_content, token=token)

@app.route('/<username>/scoreboard.xml')
def user_scoreboard_xml(username):
    """Serve user's scoreboard XML file."""
    if not validate_username(username) or not get_user(username):
        abort(404)
    user_data_dir = _get_user_data_dir(username)
    xml_path = os.path.join(user_data_dir, 'scoreboard.xml')
    if not os.path.exists(xml_path):
        abort(404)
    return send_file(xml_path, mimetype='application/xml')

@app.route('/<username>/<path:filename>')
def user_serve_file(username, filename):
    """Serve static files from html directory or user data directory."""
    if not validate_username(username) or not get_user(username):
        abort(404)
    
    # Try html directory first (CSS, JS, images)
    html_path = os.path.join(BASE_DIR, 'html', filename)
    if os.path.exists(html_path) and os.path.isfile(html_path):
        return send_from_directory(os.path.join(BASE_DIR, 'html'), filename)
    
    # Try user data directory (generated stats, etc.)
    user_data_dir = _get_user_data_dir(username)
    user_file_path = os.path.join(user_data_dir, filename)
    if os.path.exists(user_file_path) and os.path.isfile(user_file_path):
        return send_file(user_file_path)
    
    abort(404)

@app.route('/<username>/upload.php', methods=['POST'])
def user_upload(username):
    """Handle scoreboard updates for a specific user."""
    if not validate_username(username) or not get_user(username):
        abort(404)
    
    try:
        token = request.values.get('token')
        filename = request.values.get('filename')
        filedata = request.values.get('filedata')

        if not all([token, filename, filedata]):
            return 'Missing required fields', 400

        # Check user's token
        user = get_user(username)
        if token != user.get('token'):
            return 'Forbidden: Invalid token', 403

        # Security: Only allow updating scoreboard.xml
        if filename != 'scoreboard.xml':
            return 'Forbidden: Only scoreboard.xml can be updated', 403

        # Write to user's data directory
        user_data_dir = _get_user_data_dir(username)
        os.makedirs(user_data_dir, exist_ok=True)
        filepath = os.path.join(user_data_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(filedata)

        return 'OK', 200

    except Exception as e:
        return str(e), 500

# API endpoints
@app.route('/<username>/api/scraper/status', methods=['GET'])
def user_scraper_status(username):
    """Return JSON status for user's scraper process."""
    if not validate_username(username) or not get_user(username):
        abort(404)
    _require_user_access(username)
    
    _ensure_scraper_not_running(username)
    state = _get_user_state(username)
    
    with SCRAPER_LOCK:
        running = _is_scraper_running_unlocked(state)
        return jsonify({
            'running': running,
            'url': state.get('url') if running else None,
            'started_at': state.get('started_at'),
            'log': _read_log_tail(state.get('log_path'))
        })

@app.route('/<username>/api/scraper/start', methods=['POST'])
def user_scraper_start(username):
    """Start the scraper daemon for a user."""
    if not validate_username(username) or not get_user(username):
        abort(404)
    _require_user_access(username)
    
    match_url = (request.values.get('url') or '').strip()
    if not match_url:
        return jsonify({'error': 'Missing url parameter'}), 400

    state = _get_user_state(username)
    user_data_dir = _get_user_data_dir(username)
    
    with SCRAPER_LOCK:
        if _is_scraper_running_unlocked(state):
            return jsonify({'error': 'Scraper already running'}), 400

        log_handle = open(state['log_path'], 'a', encoding='utf-8')
        log_handle.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting scraper for {match_url}\n")
        log_handle.flush()

        output_xml = os.path.join(user_data_dir, 'scoreboard.xml')
        cmd = [sys.executable, 'scraper.py', match_url, '--daemon', '--output', output_xml]
        process = subprocess.Popen(
            cmd,
            cwd=BASE_DIR,
            stdout=log_handle,
            stderr=log_handle
        )

        state['process'] = process
        state['url'] = match_url
        state['log_handle'] = log_handle
        state['started_at'] = time.strftime('%Y-%m-%d %H:%M:%S')

    return jsonify({'status': 'started', 'url': match_url})

@app.route('/<username>/api/scraper/stop', methods=['POST'])
def user_scraper_stop(username):
    """Stop the scraper daemon for a user."""
    if not validate_username(username) or not get_user(username):
        abort(404)
    _require_user_access(username)
    
    state = _get_user_state(username)
    
    with SCRAPER_LOCK:
        process = state.get('process')
        if not _is_scraper_running_unlocked(state):
            _cleanup_scraper_state_unlocked(state)
            return jsonify({'status': 'stopped', 'message': 'Scraper not running'}), 200

        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        if state.get('log_handle'):
            state['log_handle'].write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Scraper stopped\n")
            state['log_handle'].flush()
        _cleanup_scraper_state_unlocked(state)

    return jsonify({'status': 'stopped'})

@app.route('/<username>/api/stats/generate', methods=['POST'])
def user_generate_stats(username):
    """Generate statistics HTML for a user."""
    if not validate_username(username) or not get_user(username):
        abort(404)
    _require_user_access(username)
    
    source = (request.values.get('source') or '').strip()
    if not source:
        return jsonify({'error': 'Missing source parameter'}), 400

    user_data_dir = _get_user_data_dir(username)
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    output_filename = f'stats_{timestamp}.html'
    output_path = os.path.join(user_data_dir, output_filename)
    dump_json_path = os.path.join(user_data_dir, f'match_{timestamp}.json')

    cmd = [sys.executable, 'stats.py', source, '--html', output_path, '--dump-json', dump_json_path, '--html-only']
    result = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True)

    if result.returncode != 0:
        return jsonify({
            'error': 'Stats generation failed',
            'stdout': result.stdout,
            'stderr': result.stderr,
            'returncode': result.returncode
        }), 500

    return jsonify({
        'status': 'generated',
        'output': output_filename,
        'stdout': result.stdout,
        'stderr': result.stderr
    })

if __name__ == '__main__':
    from waitress import serve
    # Ensure data directory exists
    os.makedirs(DATA_DIR, exist_ok=True)
    
    print(f"Starting production server with Waitress on port {PORT}")
    print(f"Access from other devices on your network via your local IP address.")
    print(f"Login at: http://localhost:{PORT}/login")
    if USERS:
        print(f"Configured users: {', '.join(USERS.keys())}")
    serve(app, host='0.0.0.0', port=PORT)
