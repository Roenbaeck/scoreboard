from flask import Flask, request, send_from_directory, abort
import os

app = Flask(__name__)

# Configuration
TOKEN = 'your_secure_token_here'  # Change this to your secure token
PORT = 8081 # Change this to your desired port

@app.route('/')
def index():
    """Serve the main index.html file"""
    return send_from_directory('html', 'index.html')

@app.route('/<path:filename>')
def serve_file(filename):
    """Serve static files from the html directory"""
    try:
        return send_from_directory('html', filename)
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

if __name__ == '__main__':
    from waitress import serve
    print(f"Starting production server with Waitress on port {PORT}")
    print(f"Access from other devices on your network via your local IP address.")
    print(f"Controller: http://localhost:{PORT}/scoreboard.html")
    print(f"Overlay: http://localhost:{PORT}/index.html")
    serve(app, host='0.0.0.0', port=PORT)
