from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import os
import sqlite3

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_aqui'  # Troque por uma chave segura em produção

# Configuração do Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class Database:
    def __init__(self):
        # Database path relative to the app file
        self.db_path = os.path.join(os.path.dirname(__file__), "geo_db.sqlite3")

        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  
        self.cursor = self.conn.cursor()

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS pontos_recolha (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                morada TEXT NOT NULL,
                horario TEXT,
                tipo_recolha TEXT,
                link TEXT,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                imagem TEXT,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'client',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self.conn.commit()

    def add_ponto(self, nome, morada, horario, tipo_recolha, link,
                  latitude, longitude, imagem=None, created_by=None):

        self.cursor.execute("""
            INSERT INTO pontos_recolha
            (nome, morada, horario, tipo_recolha, link,
             latitude, longitude, imagem, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (nome, morada, horario, tipo_recolha, link,
              latitude, longitude, imagem, created_by))

        self.conn.commit()

    def get_pontos(self):
        self.cursor.execute(
            "SELECT * FROM pontos_recolha ORDER BY created_at DESC"
        )
        return [dict(row) for row in self.cursor.fetchall()]

    def get_ponto_by_id(self, ponto_id):
        self.cursor.execute(
            "SELECT * FROM pontos_recolha WHERE id = ?",
            (ponto_id,)
        )
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def delete_ponto(self, ponto_id):
        self.cursor.execute(
            "DELETE FROM pontos_recolha WHERE id = ?",
            (ponto_id,)
        )
        self.conn.commit()


    def create_user(self, name, email, password, role='client'):
        try:
            self.cursor.execute("""
                INSERT INTO users (name, email, password, role)
                VALUES (?, ?, ?, ?)
            """, (name, email, password, role))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_user_by_email(self, email):
        self.cursor.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        )
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def get_user_by_id(self, user_id):
        self.cursor.execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,)
        )
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def close(self):
        self.conn.close()

db = Database()

UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Modelo de Usuário para Flask-Login
class User(UserMixin):
    def __init__(self, id, name, email, role):
        self.id = id
        self.name = name
        self.email = email
        self.role = role

@login_manager.user_loader
def load_user(user_id):
    user_data = db.get_user_by_id(user_id)
    if user_data:
        return User(user_data['id'], user_data['name'], user_data['email'], user_data['role'])
    return None

@app.route('/')
def index():
    # Rota pública continua sendo o mapa
    pontos = db.get_pontos()
    return render_template('mapa.html', pontos=pontos)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user_data = db.get_user_by_email(email)
        
        if user_data and check_password_hash(user_data['password'], password):
            user = User(user_data['id'], user_data['name'], user_data['email'], user_data['role'])
            login_user(user)
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('client_dashboard'))
        else:
            flash('Email ou senha inválidos.')
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Hash da senha
        hashed_password = generate_password_hash(password)
        
        # Cria usuário (Padrão: client)
        if db.create_user(name, email, hashed_password):
            flash('Conta criada com sucesso! Faça login.')
            return redirect(url_for('login'))
        else:
            flash('Erro ao criar conta. Email já existe?')
            
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/admin')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        return redirect(url_for('client_dashboard'))
    
    pontos = db.get_pontos()
    return render_template('admin_dashboard.html', pontos=pontos)

@app.route('/client')
@login_required
def client_dashboard():
    return render_template('client_dashboard.html')

@app.route('/add_ponto', methods=['POST'])
@login_required
def add_ponto():
    # Permitir que admin e clientes adicionem pontos? 
    # Vou permitir ambos, mas idealmente admin modera.
    
    imagem_file = request.files.get('imagem')
    imagem_filename = None

    if imagem_file and imagem_file.filename != '':
        imagem_filename = secure_filename(imagem_file.filename)
        imagem_file.save(os.path.join(app.config['UPLOAD_FOLDER'], imagem_filename))
        # Caminho relativo para salvar no BD
        imagem_filename = f"static/uploads/{imagem_filename}" # Ajuste para URL correta no template

    db.add_ponto(
        request.form['nome'],
        request.form['morada'],
        request.form.get('horario', ''),
        request.form.get('tipo_recolha', ''),
        request.form.get('link', ''),
        float(request.form['latitude']),
        float(request.form['longitude']),
        imagem_filename,
        current_user.id
    )
    
    if current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    else:
        return redirect(url_for('client_dashboard'))

@app.route('/delete_ponto/<int:ponto_id>')
@login_required
def delete_ponto(ponto_id):
    if current_user.role != 'admin':
        flash('Acesso negado.')
        return redirect(url_for('index'))
    
    db.delete_ponto(ponto_id)
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
X