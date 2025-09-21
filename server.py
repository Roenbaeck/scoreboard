import http.server
import socketserver
import os
import cgi

# Configuration
TOKEN = 'your_secure_token_here'  # Change this to your secure token

class MyHandler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/upload.php':
            try:
                form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={'REQUEST_METHOD':'POST', 'CONTENT_TYPE': self.headers.get('Content-Type', '')})
                if 'filename' in form and 'filedata' in form and 'token' in form:
                    token = form['token'].value
                    # Simple token check
                    if token != TOKEN:
                        self.send_error(403, 'Forbidden: Invalid token')
                        return
                    filename = form['filename'].value
                    filedata = form['filedata'].value
                    # Security: Only allow updating scoreboard.xml
                    if filename != 'scoreboard.xml':
                        self.send_error(403, 'Forbidden: Only scoreboard.xml can be updated')
                        return
                    filepath = os.path.join('html', filename)
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(filedata)
                    self.send_response(200)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(b'OK')
                else:
                    self.send_error(400, 'Missing required fields')
            except Exception as e:
                self.send_error(500, str(e))
        else:
            self.send_error(404)

    def translate_path(self, path):
        # Serve files from the html/ directory
        root = os.path.join(os.getcwd(), 'html')
        # Get the default translated path
        default_path = super().translate_path(path)
        # Replace the current directory with html/
        if default_path.startswith(os.getcwd()):
            rel_path = os.path.relpath(default_path, os.getcwd())
            return os.path.join(root, rel_path)
        return default_path

if __name__ == '__main__':
    PORT = 8081
    with socketserver.TCPServer(("", PORT), MyHandler) as httpd:
        print(f"Serving scoreboard on port {PORT}")
        print("Controller: http://localhost:8081/scoreboard.html")
        print("Overlay: http://localhost:8081/index.html")
        httpd.serve_forever()