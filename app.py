import os
import subprocess
import re
import shutil
from flask import Flask, render_template, request, send_file, jsonify

app = Flask(__name__)

BASE_DIR = '/tmp/mini-overleaf'
if not os.path.exists(BASE_DIR):
    os.makedirs(BASE_DIR)

def parse_latex_log(log_content):
    line_pattern = re.compile(r'^l\.(\d+)', re.MULTILINE)
    error_pattern = re.compile(r'^! (.*)$', re.MULTILINE)
    line_match = line_pattern.search(log_content)
    error_match = error_pattern.search(log_content)
    return (int(line_match.group(1)) if line_match else 0, 
            error_match.group(1) if error_match else "Unknown Error")

@app.route('/')
def index():
    return render_template('index.html')

# --- Recursive File Listing (Finds files inside folders) ---
@app.route('/files', methods=['GET'])
def list_files():
    session_id = request.args.get('session_id')
    if not session_id: return jsonify([])
    
    session_dir = os.path.join(BASE_DIR, session_id)
    if not os.path.exists(session_dir): return jsonify([])

    file_list = []
    
    # 1. Walk through directories to find subfolders
    for root, dirs, files in os.walk(session_dir):
        for name in dirs:
            rel_path = os.path.relpath(os.path.join(root, name), session_dir)
            file_list.append({'path': rel_path, 'type': 'folder'})
            
    # 2. Walk through directories to find files
    for root, dirs, files in os.walk(session_dir):
        for name in files:
            rel_path = os.path.relpath(os.path.join(root, name), session_dir)
            # Filter out junk system files
            if not name.endswith(('.aux', '.log', '.out', '.fls', '.fdb_latexmk', '.synctex.gz')):
                file_list.append({'path': rel_path, 'type': 'file'})

    # Sort: Folders first, then files
    file_list.sort(key=lambda x: (x['type'] == 'file', x['path']))
    return jsonify(file_list)

# --- Create Folder ---
@app.route('/create_folder', methods=['POST'])
def create_folder():
    data = request.json
    session_id = data.get('session_id')
    folder_name = data.get('folder_name')
    
    if not session_id or not folder_name: return jsonify({'error': 'Missing data'}), 400
    
    # Security: Remove ".." to prevent hacking
    clean_name = folder_name.replace('..', '')
    target_path = os.path.join(BASE_DIR, session_id, clean_name)
    
    try:
        os.makedirs(target_path, exist_ok=True)
        return jsonify({'message': 'Created'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- Delete Item ---
@app.route('/delete', methods=['POST'])
def delete_item():
    data = request.json
    session_id = data.get('session_id')
    target_path = data.get('path')
    
    if not session_id or not target_path: return jsonify({'error': 'Missing data'}), 400
    if '..' in target_path: return jsonify({'error': 'Invalid path'}), 400
    
    full_path = os.path.join(BASE_DIR, session_id, target_path)
    
    try:
        if os.path.isfile(full_path):
            os.remove(full_path)
        elif os.path.isdir(full_path):
            shutil.rmtree(full_path)
        return jsonify({'message': 'Deleted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- Upload (Supports Target Folder) ---
@app.route('/upload', methods=['POST'])
def upload_file():
    session_id = request.form.get('session_id')
    target_folder = request.form.get('target_folder', '') 
    uploaded_files = request.files.getlist('file')
    
    if not session_id: return jsonify({'error': 'Missing session'}), 400
        
    upload_dir = os.path.join(BASE_DIR, session_id, target_folder)
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)
        
    for file in uploaded_files:
        filename = re.sub(r'[^a-zA-Z0-9_.-]', '', file.filename)
        file.save(os.path.join(upload_dir, filename))
    
    return jsonify({'message': 'Uploaded'})

@app.route('/compile', methods=['POST'])
def compile_latex():
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
        # Run latexmk inside the session directory
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
        return jsonify({'error': 'Timeout', 'message': 'Too long'}), 504

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)