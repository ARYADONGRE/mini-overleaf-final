import os
import subprocess
import shutil
import re
from flask import Flask, render_template, request, send_file, jsonify

app = Flask(__name__)

# Base directory for all user sessions
# On Render, /tmp is the only writable place
BASE_DIR = '/tmp/mini-overleaf'
if not os.path.exists(BASE_DIR):
    os.makedirs(BASE_DIR)

def parse_latex_log(log_content):
    error_pattern = re.compile(r'^! (.*)$', re.MULTILINE)
    line_pattern = re.compile(r'^l\.(\d+)', re.MULTILINE)
    error_match = error_pattern.search(log_content)
    line_match = line_pattern.search(log_content)
    return (int(line_match.group(1)) if line_match else 0, 
            error_match.group(1) if error_match else "Unknown Error")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    session_id = request.form.get('session_id')
    file = request.files.get('file')
    
    if not session_id or not file:
        return jsonify({'error': 'Missing data'}), 400
        
    # Create session folder if not exists
    session_dir = os.path.join(BASE_DIR, session_id)
    if not os.path.exists(session_dir):
        os.makedirs(session_dir)
        
    # Save the image
    filename = file.filename
    # Security: ensure filename is safe (basic check)
    filename = re.sub(r'[^a-zA-Z0-9_.-]', '', filename) 
    file.save(os.path.join(session_dir, filename))
    
    return jsonify({'message': 'Uploaded', 'filename': filename})

@app.route('/compile', methods=['POST'])
def compile_latex():
    data = request.json
    code = data.get('code')
    session_id = data.get('session_id')
    
    if not code or not session_id:
        return jsonify({'error': 'Missing code or session_id'}), 400

    # Ensure session directory exists
    session_dir = os.path.join(BASE_DIR, session_id)
    if not os.path.exists(session_dir):
        os.makedirs(session_dir)

    tex_file = os.path.join(session_dir, 'document.tex')
    pdf_file = os.path.join(session_dir, 'document.pdf')
    log_file = os.path.join(session_dir, 'document.log')

    with open(tex_file, 'w') as f:
        f.write(code)

    try:
        # Run latexmk inside the session directory
        subprocess.run(
            ['latexmk', '-pdf', '-interaction=nonstopmode', '-file-line-error', '-outdir=' + session_dir, tex_file],
            check=True,
            cwd=session_dir, # CRITICAL: Run "inside" the folder so it finds images
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=45
        )
        return send_file(pdf_file, mimetype='application/pdf')

    except subprocess.CalledProcessError:
        if os.path.exists(log_file):
            with open(log_file, 'r', errors='replace') as f:
                log_content = f.read()
            line_num, error_msg = parse_latex_log(log_content)
            return jsonify({'error': 'Failed', 'line': line_num, 'message': error_msg}), 400
        return jsonify({'error': 'System Error', 'message': 'Log not found'}), 500
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Timeout', 'message': 'Too long'}), 504

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)