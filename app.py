import os
import subprocess
import uuid
import tempfile
from flask import Flask, render_template, request, send_file, jsonify

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/compile', methods=['POST'])
def compile_latex():
    data = request.json
    latex_code = data.get('code')

    if not latex_code:
        return jsonify({'error': 'No code provided'}), 400

    # Create a temporary directory for this compilation process
    # This prevents file conflicts between users
    with tempfile.TemporaryDirectory() as temp_dir:
        # Define file paths
        tex_file = os.path.join(temp_dir, 'document.tex')
        pdf_file = os.path.join(temp_dir, 'document.pdf')

        # Write the user's code to a .tex file
        with open(tex_file, 'w') as f:
            f.write(latex_code)

        try:
            # Run pdflatex command
            # -interaction=nonstopmode prevents the compiler from pausing on errors
            # -output-directory ensures output goes to our temp folder
            subprocess.run(
                ['pdflatex', '-interaction=nonstopmode', '-output-directory', temp_dir, tex_file],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30 # Prevent infinite loops
            )

            # Return the generated PDF
            if os.path.exists(pdf_file):
                return send_file(pdf_file, mimetype='application/pdf')
            else:
                return jsonify({'error': 'PDF generation failed. Check syntax.'}), 500

        except subprocess.CalledProcessError as e:
            # Capture the compilation error log
            error_log = e.stdout.decode('utf-8', errors='ignore')
            return jsonify({'error': 'Compilation Error', 'details': error_log}), 400
        except subprocess.TimeoutExpired:
            return jsonify({'error': 'Compilation timed out'}), 504

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)