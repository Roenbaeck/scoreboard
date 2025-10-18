from flask import (
    Flask,
    request,
    send_from_directory,
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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)

# Secret key needed for session-based auth
app.secret_key = os.environ.get('SCOREBOARD_FLASK_SECRET', 'replace_me_with_random_secret')

# Configuration
TOKEN = 'your_secure_token_here'  # Change this to your secure token
PORT = 8081 # Change this to your desired port
PAGE_PASSWORD = os.environ.get('SCOREBOARD_PAGE_PASSWORD', 'volley')

SCRAPER_LOCK = threading.Lock()
SCRAPER_STATE = {
    'process': None,
    'url': None,
    'log_handle': None,
    'log_path': os.path.join(BASE_DIR, 'scraper.log'),
    'started_at': None
}

LOGIN_TEMPLATE = """<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\">
    <title>Scoreboard Login</title>
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
    <style>
        body { font-family: Arial, sans-serif; background: #f5f6fa; display:flex; justify-content:center; align-items:center; height:100vh; margin:0; }
        .card { background:#fff; padding:30px; border-radius:8px; box-shadow:0 2px 10px rgba(0,0,0,0.1); max-width:360px; width:100%; }
        h1 { margin-top:0; font-size:1.4rem; text-align:center; }
        label { display:block; margin-bottom:8px; font-weight:bold; }
        input[type=password] { width:100%; padding:10px; margin-bottom:16px; border:1px solid #dcdde1; border-radius:4px; font-size:1rem; }
        button { width:100%; padding:10px; background:#3498db; color:#fff; border:none; border-radius:4px; font-size:1rem; cursor:pointer; }
        .error { color:#e74c3c; margin-bottom:12px; text-align:center; }
    </style>
</head>
<body>
    <div class=\"card\">
        <h1>Enter Control Password</h1>
        {% if error %}<div class=\"error\">{{ error }}</div>{% endif %}
        <form method=\"post\">
            <input type=\"hidden\" name=\"next\" value=\"{{ next_url }}\" />
            <label for=\"password\">Password</label>
            <input type=\"password\" id=\"password\" name=\"password\" required autofocus />
            <button type=\"submit\">Continue</button>
        </form>
    </div>
</body>
</html>"""


def _is_authenticated():
    return session.get('scoreboard_auth') is True


def _redirect_to_login():
    return redirect(url_for('login', next=request.path))


def _is_scraper_running_unlocked():
    process = SCRAPER_STATE.get('process')
    return process is not None and process.poll() is None


def _cleanup_scraper_state_unlocked():
    process = SCRAPER_STATE.get('process')
    log_handle = SCRAPER_STATE.get('log_handle')
    if log_handle:
        try:
            log_handle.flush()
            log_handle.close()
        except Exception:
            pass
    SCRAPER_STATE['process'] = None
    SCRAPER_STATE['url'] = None
    SCRAPER_STATE['log_handle'] = None
    SCRAPER_STATE['started_at'] = None


def _ensure_scraper_not_running():
    with SCRAPER_LOCK:
        if not _is_scraper_running_unlocked():
            if SCRAPER_STATE.get('process') is not None:
                _cleanup_scraper_state_unlocked()


def _read_log_tail(max_chars=2000):
    path = SCRAPER_STATE.get('log_path')
    if not path or not os.path.exists(path):
        return ''
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            seek_pos = max(size - max_chars, 0)
            fh.seek(seek_pos)
            if seek_pos > 0:
                fh.readline()
            return fh.read().strip()
    except OSError:
        return ''


@app.route('/')
def index():
    """Serve the main index.html file"""
    return send_from_directory(os.path.join(BASE_DIR, 'html'), 'index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Simple password gate for control interfaces."""
    next_url = request.args.get('next') or request.form.get('next') or url_for('scoreboard_page')
    error = None
    if request.method == 'POST':
        if (request.form.get('password') or '') == PAGE_PASSWORD:
            session['scoreboard_auth'] = True
            return redirect(next_url)
        error = 'Incorrect password. Please try again.'
    return render_template_string(LOGIN_TEMPLATE, error=error, next_url=next_url)


@app.route('/logout')
def logout():
    session.pop('scoreboard_auth', None)
    return redirect(url_for('login'))


@app.route('/scoreboard.html')
def scoreboard_page():
    if not _is_authenticated():
        return _redirect_to_login()
    return send_from_directory(os.path.join(BASE_DIR, 'html'), 'scoreboard.html')


@app.route('/control')
def control():
    """Serve the scraper control UI"""
    if not _is_authenticated():
        return _redirect_to_login()
    return send_from_directory(os.path.join(BASE_DIR, 'html'), 'control.html')

@app.route('/<path:filename>')
def serve_file(filename):
    """Serve static files from the html directory"""
    try:
        return send_from_directory(os.path.join(BASE_DIR, 'html'), filename)
    except FileNotFoundError:
        abort(404)

@app.route('/upload.php', methods=['POST'])
def upload():
    """Handle scoreboard updates"""
    try:
        # Get data from either form or values (handles both multipart and form-encoded)
        token = request.values.get('token')
        filename = request.values.get('filename')
        filedata = request.values.get('filedata')

        if not all([token, filename, filedata]):
            return 'Missing required fields', 400

        # Simple token check
        if token != TOKEN:
            return 'Forbidden: Invalid token', 403

        # Security: Only allow updating scoreboard.xml
        if filename != 'scoreboard.xml':
            return 'Forbidden: Only scoreboard.xml can be updated', 403

        # Write the file
        filepath = os.path.join('html', filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(filedata)

        return 'OK', 200

    except Exception as e:
        return str(e), 500


def _require_auth():
    if not _is_authenticated():
        abort(403)


@app.route('/api/scraper/status', methods=['GET'])
def scraper_status():
    """Return JSON status for scraper process."""
    _require_auth()
    _ensure_scraper_not_running()
    with SCRAPER_LOCK:
        running = _is_scraper_running_unlocked()
        return jsonify({
            'running': running,
            'url': SCRAPER_STATE.get('url') if running else None,
            'started_at': SCRAPER_STATE.get('started_at'),
            'log': _read_log_tail()
        })


@app.route('/api/scraper/start', methods=['POST'])
def scraper_start():
    """Start the scraper daemon with the provided URL."""
    _require_auth()
    match_url = (request.values.get('url') or '').strip()
    if not match_url:
        return jsonify({'error': 'Missing url parameter'}), 400

    with SCRAPER_LOCK:
        if _is_scraper_running_unlocked():
            return jsonify({'error': 'Scraper already running'}), 400

        log_handle = open(SCRAPER_STATE['log_path'], 'a', encoding='utf-8')
        log_handle.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting scraper for {match_url}\n")
        log_handle.flush()

        cmd = [sys.executable, 'scraper.py', match_url, '--daemon']
        process = subprocess.Popen(
            cmd,
            cwd=BASE_DIR,
            stdout=log_handle,
            stderr=log_handle
        )

        SCRAPER_STATE['process'] = process
        SCRAPER_STATE['url'] = match_url
        SCRAPER_STATE['log_handle'] = log_handle
        SCRAPER_STATE['started_at'] = time.strftime('%Y-%m-%d %H:%M:%S')

    return jsonify({'status': 'started', 'url': match_url})


@app.route('/api/scraper/stop', methods=['POST'])
def scraper_stop():
    """Stop the scraper daemon if it is running."""
    _require_auth()
    with SCRAPER_LOCK:
        process = SCRAPER_STATE.get('process')
        if not _is_scraper_running_unlocked():
            _cleanup_scraper_state_unlocked()
            return jsonify({'status': 'stopped', 'message': 'Scraper not running'}), 200

        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        if SCRAPER_STATE.get('log_handle'):
            SCRAPER_STATE['log_handle'].write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Scraper stopped\n")
            SCRAPER_STATE['log_handle'].flush()
        _cleanup_scraper_state_unlocked()

    return jsonify({'status': 'stopped'})


@app.route('/api/stats/generate', methods=['POST'])
def generate_stats():
    """Generate statistics HTML using stats.py for provided source."""
    _require_auth()
    source = (request.values.get('source') or '').strip()
    if not source:
        return jsonify({'error': 'Missing source parameter'}), 400

    output_rel = (request.values.get('output') or 'html/generated_stats.html').strip()
    dump_json_rel = (request.values.get('dump_json') or '').strip()

    output_path = output_rel if os.path.isabs(output_rel) else os.path.join(BASE_DIR, output_rel)
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    cmd = [sys.executable, 'stats.py', source, '--html', output_path, '--html-only']
    if dump_json_rel:
        dump_json_path = dump_json_rel if os.path.isabs(dump_json_rel) else os.path.join(BASE_DIR, dump_json_rel)
        dump_dir = os.path.dirname(dump_json_path)
        if dump_dir and not os.path.exists(dump_dir):
            os.makedirs(dump_dir, exist_ok=True)
        cmd.extend(['--dump-json', dump_json_path])

    result = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True)

    if result.returncode != 0:
        return jsonify({
            'error': 'Stats generation failed',
            'stdout': result.stdout,
            'stderr': result.stderr,
            'returncode': result.returncode
        }), 500

    relative_output = os.path.relpath(output_path, BASE_DIR)
    return jsonify({
        'status': 'generated',
        'output': relative_output,
        'stdout': result.stdout,
        'stderr': result.stderr
    })

if __name__ == '__main__':
    from waitress import serve
    print(f"Starting production server with Waitress on port {PORT}")
    print(f"Access from other devices on your network via your local IP address.")
    print(f"Scraper Controller: http://localhost:{PORT}/control")
    print(f"Scoreboard Controller: http://localhost:{PORT}/scoreboard.html")
    print(f"Overlay: http://localhost:{PORT}/index.html")
    serve(app, host='0.0.0.0', port=PORT)
