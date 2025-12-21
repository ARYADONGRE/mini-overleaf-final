import os
import subprocess
import re
import shutil
from flask import Flask, render_template, request, send_file, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, login_user, LoginManager, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'change-this-to-something-secret'

# --- DATABASE CONFIGURATION ---
db_url = os.environ.get('DATABASE_URL')

if db_url:
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
else:
    db_url = 'sqlite:///site.db'

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

BASE_DIR = '/tmp/mini-overleaf/projects'
if not os.path.exists(BASE_DIR):
    os.makedirs(BASE_DIR)

# --- DATABASE MODELS ---
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    # FIX: Increased size from 60 to 255 to hold long password hashes
    password = db.Column(db.String(255), nullable=False)
    projects = db.relationship('Project', backref='author', lazy=True)

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def get_project_path(project_id):
    path = os.path.join(BASE_DIR, str(project_id))
    if not os.path.exists(path):
        os.makedirs(path)
    return path

def parse_latex_log(log_content):
    line_pattern = re.compile(r'^l\.(\d+)', re.MULTILINE)
    error_pattern = re.compile(r'^! (.*)$', re.MULTILINE)
    line_match = line_pattern.search(log_content)
    error_match = error_pattern.search(log_content)
    return (int(line_match.group(1)) if line_match else 0, 
            error_match.group(1) if error_match else "Unknown Error")

# --- RESET DATABASE ROUTE ---
# FIX: Added db.drop_all() to remove the old 'size 60' table
@app.route('/setup-db')
def setup_db():
    try:
        with app.app_context():
            db.drop_all()   # Deletes old tables with wrong schema
            db.create_all() # Creates new tables with correct schema
        return "<h3>Database Reset & Fixed!</h3> <a href='/register'>Click here to Register</a>"
    except Exception as e:
        return f"<h3>Error:</h3> <p>{str(e)}</p>"

# --- AUTH ROUTES ---
@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists')
            return redirect(url_for('register'))
            
        hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, email=email, password=hashed_pw)
        
        try:
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)
            return redirect(url_for('dashboard'))
        except Exception as e:
            return f"Database Error: {e}"

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Login Unsuccessful. Check email and password')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- PROJECT MANAGEMENT ---
@app.route('/dashboard')
@login_required
def dashboard():
    projects = Project.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', projects=projects, name=current_user.username)

@app.route('/create_project', methods=['POST'])
@login_required
def create_project():
    name = request.form.get('project_name')
    if name:
        new_proj = Project(name=name, author=current_user)
        db.session.add(new_proj)
        db.session.commit()
        get_project_path(new_proj.id)
    return redirect(url_for('dashboard'))

@app.route('/project/<int:project_id>')
@login_required
def open_project(project_id):
    project = Project.query.get_or_404(project_id)
    if project.author != current_user:
        return "Unauthorized", 403
    
    path = get_project_path(project_id)
    tex_file = os.path.join(path, 'document.tex')
    
    code = ""
    if os.path.exists(tex_file):
        with open(tex_file, 'r') as f:
            code = f.read()
    else:
        code = r"\documentclass{article}" + "\n" + r"\begin{document}" + "\n" + "Hello World!\n" + r"\end{document}"
        with open(tex_file, 'w') as f:
            f.write(code)
            
    return render_template('editor.html', project=project, code=code)

# --- FILE API ---
@app.route('/files/<int:project_id>')
@login_required
def list_files(project_id):
    project = Project.query.get_or_404(project_id)
    if project.author != current_user: return jsonify([])
    
    p_dir = get_project_path(project_id)
    file_list = []
    
    for root, dirs, files in os.walk(p_dir):
        for name in dirs:
            rel = os.path.relpath(os.path.join(root, name), p_dir)
            file_list.append({'path': rel, 'type': 'folder'})
            
    for root, dirs, files in os.walk(p_dir):
        for name in files:
            rel = os.path.relpath(os.path.join(root, name), p_dir)
            if not name.endswith(('.aux', '.log', '.out', '.fls', '.fdb_latexmk', '.synctex.gz')):
                file_list.append({'path': rel, 'type': 'file'})
                
    file_list.sort(key=lambda x: (x['type'] == 'file', x['path']))
    return jsonify(file_list)

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    pid = request.form.get('project_id')
    target = request.form.get('target_folder', '')
    files = request.files.getlist('file')
    
    project = Project.query.get(pid)
    if not project or project.author != current_user: return jsonify({'error': '403'}), 403
    
    save_dir = os.path.join(get_project_path(pid), target)
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    
    for f in files:
        safe_name = re.sub(r'[^a-zA-Z0-9_.-]', '', f.filename)
        f.save(os.path.join(save_dir, safe_name))
    return jsonify({'message': 'Uploaded'})

@app.route('/create_folder', methods=['POST'])
@login_required
def create_folder():
    data = request.json
    pid = data.get('project_id')
    name = data.get('folder_name').replace('..', '')
    
    project = Project.query.get(pid)
    if not project or project.author != current_user: return jsonify({'error': '403'}), 403
    
    os.makedirs(os.path.join(get_project_path(pid), name), exist_ok=True)
    return jsonify({'message': 'Created'})

@app.route('/delete', methods=['POST'])
@login_required
def delete_item():
    data = request.json
    pid = data.get('project_id')
    path = data.get('path').replace('..', '')
    
    project = Project.query.get(pid)
    if not project or project.author != current_user: return jsonify({'error': '403'}), 403
    
    full = os.path.join(get_project_path(pid), path)
    if os.path.isfile(full):
        os.remove(full)
    elif os.path.isdir(full):
        shutil.rmtree(full)
    return jsonify({'message': 'Deleted'})

@app.route('/compile', methods=['POST'])
@login_required
def compile_tex():
    data = request.json
    pid = data.get('project_id')
    code = data.get('code')
    
    project = Project.query.get(pid)
    if not project or project.author != current_user: return jsonify({'error': '403'}), 403
    
    p_dir = get_project_path(pid)
    tex_file = os.path.join(p_dir, 'document.tex')
    pdf_file = os.path.join(p_dir, 'document.pdf')
    log_file = os.path.join(p_dir, 'document.log')
    
    with open(tex_file, 'w') as f:
        f.write(code)
    
    try:
        subprocess.run(
            ['latexmk', '-pdf', '-interaction=nonstopmode', '-file-line-error', '-outdir=' + p_dir, tex_file],
            check=True, cwd=p_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45
        )
        return send_file(pdf_file, mimetype='application/pdf')

    except subprocess.CalledProcessError:
        if os.path.exists(log_file):
            with open(log_file, 'r', errors='replace') as f:
                log = f.read()
            l, m = parse_latex_log(log)
            return jsonify({'error': 'Failed', 'line': l, 'message': m}), 400
        return jsonify({'error': 'Error', 'message': 'Unknown Compilation Error'}), 500
        
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Timeout', 'message': 'Compilation took too long'}), 504

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)