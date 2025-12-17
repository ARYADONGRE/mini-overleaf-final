import os
import subprocess
import re
import shutil
from flask import Flask, render_template, request, send_file, jsonify

app = Flask(__name__)

# Base directory for storing user sessions
BASE_DIR = '/tmp/mini-overleaf'
if not os.path.exists(BASE_DIR):
    os.makedirs(BASE_DIR)

def parse_latex_log(log_content):
    """Finds the error message and line number in the log."""
    line_pattern = re.compile(r'^l\.(\d+)', re.MULTILINE)
    error_pattern = re.compile(r'^! (.*)$', re.MULTILINE)
    line_match = line_pattern.search(log_content)
    error_match = error_pattern.search(log_content)
    return (int(line_match.group(1)) if line_match else 0, 
            error_match.group(1) if error_match else "Unknown Error")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/files', methods=['GET'])
def list_files():
    """Returns a list of files uploaded by the current user."""
    session_id = request.args.get('session_id')
    if not session_id: return jsonify([])
    
    session_dir = os.path.join(BASE_DIR, session_id)
    if not os.path.exists(session_dir): return jsonify([])

    # List only relevant files (hide system/temp files)
    files = [f for f in os.listdir(session_dir) 
             if os.path.isfile(os.path.join(session_dir, f)) 
             and not f.endswith(('.aux', '.log', '.out', '.fls', '.fdb_latexmk'))]
    return jsonify(files)

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handles image uploads."""
    session_id = request.form.get('session_id')
    uploaded_files = request.files.getlist('file')
    
    if not session_id or not uploaded_files:
        return jsonify({'error': 'Missing data'}), 400
        
    session_dir = os.path.join(BASE_DIR, session_id)
    if not os.path.exists(session_dir):
        os.makedirs(session_dir)
        
    saved_files = []
    for file in uploaded_files:
        # Sanitize filename to prevent hacking
        filename = re.sub(r'[^a-zA-Z0-9_.-]', '', file.filename)
        file.save(os.path.join(session_dir, filename))
        saved_files.append(filename)
    
    return jsonify({'message': 'Uploaded', 'files': saved_files})

@app.route('/compile', methods=['POST'])
def compile_latex():
    """Compiles the LaTeX code using latexmk."""
    data = request.json
    code = data.get('code')
    session_id = data.get('session_id')

    if not session_id: return jsonify({'error': 'No Session ID'}), 400

    session_dir = os.path.join(BASE_DIR, session_id)
    if not os.path.exists(session_dir): os.makedirs(session_dir)

    tex_file = os.path.join(session_dir, 'document.tex')
    pdf_file = os.path.join(session_dir, 'document.pdf')
    log_file = os.path.join(session_dir, 'document.log')

    with open(tex_file, 'w') as f:
        f.write(code)

    try:
        # Run latexmk inside the session folder so it sees images
        subprocess.run(
            ['latexmk', '-pdf', '-interaction=nonstopmode', '-file-line-error', '-outdir=' + session_dir, tex_file],
            check=True, cwd=session_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45
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
        return jsonify({'error': 'Timeout', 'message': 'Compilation took too long'}), 504

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)