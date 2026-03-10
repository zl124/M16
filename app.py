from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, make_response
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import os
import sqlite3
import json
import logging
from datetime import timedelta, datetime
from pyproj import Transformer
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "jorge")
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=30)
app.config['REMEMBER_COOKIE_SECURE'] = False
app.config['REMEMBER_COOKIE_HTTPONLY'] = True

# ── Email Configuration ───────────────────────────────────────────
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', app.config['MAIL_USERNAME'])

mail = Mail(app)
serializer = URLSafeTimedSerializer(app.secret_key)

# ── Python logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class Database:
    def __init__(self):
        
        self.db_path = os.path.join(os.path.dirname(__file__), "geo_db.sqlite3")

        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  
        self.cursor = self.conn.cursor()        

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS pontos_recolha (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                morada TEXT NOT NULL,
                freguesia TEXT,
                horario TEXT,
                tipo_recolha TEXT,
                link TEXT,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                imagem BLOB,
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
                is_verified INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS mensagens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                email TEXT NOT NULL,
                assunto TEXT NOT NULL,
                mensagem TEXT NOT NULL,
                lida INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                acao TEXT NOT NULL,
                detalhes TEXT DEFAULT '',
                utilizador TEXT DEFAULT 'anon',
                ip TEXT DEFAULT '',
                status INTEGER DEFAULT 200,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self.conn.commit()
        self.check_auto_import()

    def check_auto_import(self):
        """Checks if the table is empty and imports data from JSON if needed."""
        self.cursor.execute("SELECT COUNT(*) FROM pontos_recolha")
        if self.cursor.fetchone()[0] == 0:
            json_path = os.path.join(os.path.dirname(__file__), "data", "a.json")
            if os.path.exists(json_path):
                print(f"Auto-importing data from {json_path}...")
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                transformer = Transformer.from_crs("epsg:27493", "epsg:4326")
                
                for item in data:
                    nome = item.get("TPRS_DESC", "Ponto de Recolha")
                    morada = f"{item.get('TOP_MOD_1', '')}, {item.get('PRSL_LOCAL', '')}".strip(", ")
                    freguesia = item.get("FRE_AB", "")
                    tipo = item.get("TPRS_DESC", "")
                    x, y = item.get("PRSL_X"), item.get("PRSL_Y")

                    if x is not None and y is not None:
                        lat, lon = transformer.transform(x, y)
                        horario_json = item.get("HORARIO", "")
                        self.add_ponto(nome, morada, freguesia, horario_json, tipo, "", lat, lon)
                
                print("Auto-import complete.")
            
        # Criar admin pré-definido se não existir
        self.cursor.execute("SELECT * FROM users WHERE email = 'Gabi@Mille.pt'")
        if not self.cursor.fetchone():
            from werkzeug.security import generate_password_hash
            hashed_pw = generate_password_hash('jorge123')
            self.cursor.execute("""
                INSERT INTO users (name, email, password, role, is_verified)
                VALUES (?, ?, ?, ?, ?)
            """, ('Administrador', 'Gabi@Mille.pt', hashed_pw, 'admin', 1))
            self.conn.commit()
            print("Admin pré-definido criado: Gabi@Mille.pt / jorge123")

    def add_ponto(self, nome, morada, freguesia, horario, tipo_recolha, link,
                  latitude, longitude, imagem=None, created_by=None):

        self.cursor.execute("""
            INSERT INTO pontos_recolha
            (nome, morada, freguesia, horario, tipo_recolha, link,
             latitude, longitude, imagem, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (nome, morada, freguesia, horario, tipo_recolha, link,
              latitude, longitude, sqlite3.Binary(imagem) if imagem else None, created_by))

        self.conn.commit()

    def get_pontos(self):
        self.cursor.execute(
            "SELECT id, nome, morada, freguesia, horario, tipo_recolha, link, latitude, longitude, (imagem IS NOT NULL) as tem_imagem, created_by, created_at FROM pontos_recolha ORDER BY created_at DESC"
        )
        return [dict(row) for row in self.cursor.fetchall()]

    def get_ponto_by_id(self, ponto_id):
        self.cursor.execute(
            "SELECT * FROM pontos_recolha WHERE id = ?",
            (ponto_id,)
        )
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def get_latest_ponto_timestamp(self):
        self.cursor.execute("SELECT MAX(created_at) as ts FROM pontos_recolha")
        row = self.cursor.fetchone()
        return row['ts'] if row else None

    def get_pontos_since(self, since_ts):
        self.cursor.execute(
            "SELECT COUNT(*) as cnt FROM pontos_recolha WHERE created_at > ?",
            (since_ts,)
        )
        row = self.cursor.fetchone()
        return row['cnt'] if row else 0

    def delete_ponto(self, ponto_id):
        self.cursor.execute(
            "DELETE FROM pontos_recolha WHERE id = ?",
            (ponto_id,)
        )
        self.conn.commit()

    def update_ponto(self, ponto_id, nome, morada, freguesia, horario, tipo_recolha, link, latitude, longitude, imagem=None):
        if imagem:
            self.cursor.execute("""
                UPDATE pontos_recolha
                SET nome=?, morada=?, freguesia=?, horario=?, tipo_recolha=?, link=?, latitude=?, longitude=?, imagem=?
                WHERE id=?
            """, (nome, morada, freguesia, horario, tipo_recolha, link, latitude, longitude, sqlite3.Binary(imagem), ponto_id))
        else:
            self.cursor.execute("""
                UPDATE pontos_recolha
                SET nome=?, morada=?, freguesia=?, horario=?, tipo_recolha=?, link=?, latitude=?, longitude=?
                WHERE id=?
            """, (nome, morada, freguesia, horario, tipo_recolha, link, latitude, longitude, ponto_id))
        self.conn.commit()


    def create_user(self, name, email, password, role='client', is_verified=0):
        try:
            self.cursor.execute("""
                INSERT INTO users (name, email, password, role, is_verified)
                VALUES (?, ?, ?, ?, ?)
            """, (name, email, password, role, is_verified))
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

    def verify_user(self, email):
        self.cursor.execute("UPDATE users SET is_verified=1 WHERE email=?", (email,))
        self.conn.commit()

    def get_all_verified_emails(self):
        self.cursor.execute("SELECT email FROM users WHERE is_verified=1")
        return [row['email'] for row in self.cursor.fetchall()]

    # --- Mensagens de Contacto ---

    def add_mensagem(self, nome, email, assunto, mensagem):
        self.cursor.execute("""
            INSERT INTO mensagens (nome, email, assunto, mensagem)
            VALUES (?, ?, ?, ?)
        """, (nome, email, assunto, mensagem))
        self.conn.commit()

    def get_mensagens(self):
        self.cursor.execute(
            "SELECT * FROM mensagens ORDER BY created_at DESC"
        )
        return [dict(row) for row in self.cursor.fetchall()]

    def get_mensagens_nao_lidas(self):
        self.cursor.execute("SELECT COUNT(*) as cnt FROM mensagens WHERE lida = 0")
        row = self.cursor.fetchone()
        return row['cnt'] if row else 0

    def marcar_mensagem_lida(self, msg_id):
        self.cursor.execute("UPDATE mensagens SET lida=1 WHERE id=?", (msg_id,))
        self.conn.commit()

    # --- Logs de Actividade ---

    def add_log(self, acao, detalhes='', utilizador='anon', ip='', status=200):
        try:
            self.cursor.execute("""
                INSERT INTO logs (acao, detalhes, utilizador, ip, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (acao, detalhes[:500], utilizador[:120], ip[:45], status,
                   datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')))
            self.conn.commit()
        except Exception:
            pass  # Nunca deixar o logging crashar a app

    def get_logs(self, limit=200):
        self.cursor.execute(
            "SELECT * FROM logs ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return [dict(row) for row in self.cursor.fetchall()]

    def get_stats(self):
        """Returns aggregated stats for the About page charts."""
        self.cursor.execute("SELECT COUNT(*) as total FROM pontos_recolha")
        total_pontos = self.cursor.fetchone()['total']

        self.cursor.execute("SELECT COUNT(*) as total FROM users")
        total_users = self.cursor.fetchone()['total']

        self.cursor.execute("SELECT COUNT(*) as total FROM mensagens")
        total_msgs = self.cursor.fetchone()['total']

        # Pontos por tipo (top 8)
        self.cursor.execute("""
            SELECT tipo_recolha, COUNT(*) as cnt
            FROM pontos_recolha
            WHERE tipo_recolha IS NOT NULL AND tipo_recolha != ''
            GROUP BY tipo_recolha
            ORDER BY cnt DESC
            LIMIT 8
        """)
        por_tipo = [dict(r) for r in self.cursor.fetchall()]

        # Pontos adicionados por mês (ultimos 6 meses)
        self.cursor.execute("""
            SELECT strftime('%Y-%m', created_at) as mes, COUNT(*) as cnt
            FROM pontos_recolha
            GROUP BY mes
            ORDER BY mes DESC
            LIMIT 6
        """)
        por_mes = list(reversed([dict(r) for r in self.cursor.fetchall()]))

        # Vistas de página por rota (admin only)
        por_rota = []
        try:
            from flask_login import current_user
            if current_user.is_authenticated and current_user.role == 'admin':
                self.cursor.execute("""
                    SELECT acao, COUNT(*) as cnt
                    FROM logs
                    WHERE status < 400
                    GROUP BY acao
                    ORDER BY cnt DESC
                    LIMIT 8
                """)
                por_rota = [dict(r) for r in self.cursor.fetchall()]
        except:
            pass

        return {
            'total_pontos': total_pontos,
            'total_users': total_users,
            'total_msgs': total_msgs,
            'por_tipo': por_tipo,
            'por_mes': por_mes,
            'por_rota': por_rota,
        }

    def get_logs_nao_vistos(self, since_minutes=60):
        self.cursor.execute("""
            SELECT COUNT(*) as cnt FROM logs
            WHERE created_at > datetime('now', ? || ' minutes')
        """, (f'-{since_minutes}',))
        row = self.cursor.fetchone()
        return row['cnt'] if row else 0

    def close(self):
        self.conn.close()

db = Database()

UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/ponto_imagem/<int:ponto_id>')
def serve_ponto_imagem(ponto_id):
    ponto = db.get_ponto_by_id(ponto_id)
    if ponto and ponto['imagem']:
        import io
        from flask import send_file
        return send_file(
            io.BytesIO(ponto['imagem']),
            mimetype='image/jpeg'
        )
    return redirect(url_for('static', filename='img/no-image.png'))

# Modelo de Usuário para Flask-Login
class User(UserMixin):
    def __init__(self, id, name, email, role, is_verified):
        self.id = id
        self.name = name
        self.email = email
        self.role = role
        self.is_verified = is_verified

@login_manager.user_loader
def load_user(user_id):
    user_data = db.get_user_by_id(user_id)
    if user_data:
        return User(user_data['id'], user_data['name'], user_data['email'], user_data['role'], user_data['is_verified'])
    return None

def send_email(subject, recipients, body_html):
    try:
        msg = Message(subject, recipients=recipients)
        msg.html = body_html
        mail.send(msg)
        return True
    except Exception as e:
        logger.error(f"Erro ao enviar email: {e}")
        return False

# ── Activity Logging ──────────────────────────────────────────────────
@app.after_request
def log_request(response):
    # Skip static files, images and API polling calls to reduce noise
    skip_prefixes = ('/static/', '/ponto_imagem/', '/api/novos_pontos')
    if not request.path.startswith(skip_prefixes):
        try:
            utilizador = current_user.email if current_user.is_authenticated else 'anon'
        except Exception:
            utilizador = 'anon'
        ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
        acao = f"{request.method} {request.path}"
        detalhes = ''
        if request.method == 'POST':
            safe_keys = [k for k in request.form.keys() if 'password' not in k.lower()]
            detalhes = ' | '.join(f"{k}={request.form.get(k,'')[:60]}" for k in safe_keys[:5])
        logger.info(f"[{response.status_code}] {acao} | user={utilizador} | ip={ip} | {detalhes}")
        db.add_log(acao, detalhes, utilizador, ip, response.status_code)
    return response

@app.route('/')
def index():
    pontos = db.get_pontos()
    return render_template('mapa.html', pontos=pontos)

@app.route('/info')
def main_info():
    return render_template('main.html')

@app.route('/pesquisa')
def pesquisa():
    pontos = db.get_pontos()
    return render_template('pesquisa.html', pontos=pontos)

@app.route('/contacto', methods=['GET', 'POST'])
def contacto():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        email = request.form.get('email', '').strip()
        assunto = request.form.get('assunto', '').strip()
        mensagem = request.form.get('mensagem', '').strip()
        if nome and email and assunto and mensagem:
            db.add_mensagem(nome, email, assunto, mensagem)
            flash('Mensagem enviada com sucesso! Entraremos em contacto em breve.', 'success')
        else:
            flash('Por favor preencha todos os campos.', 'error')
        return redirect(url_for('contacto'))
    return render_template('contacto.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = request.form.get('remember') == 'on'
        
        user_data = db.get_user_by_email(email)
        
        if user_data and check_password_hash(user_data['password'], password):
            if not user_data['is_verified']:
                flash('Por favor, verifique o seu email antes de fazer login.', 'error')
                return redirect(url_for('login'))
                
            user = User(user_data['id'], user_data['name'], user_data['email'], user_data['role'], user_data['is_verified'])
            login_user(user, remember=remember)
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('client_dashboard'))
        else:
            flash('Email ou senha inválidos.', 'error')
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Hash da senha
        hashed_password = generate_password_hash(password)
        
        # Cria usuário (Padrão: client, is_verified: 0)
        if db.create_user(name, email, hashed_password):
            token = serializer.dumps(email, salt='email-confirm')
            verify_url = url_for('verify_email', token=token, _external=True)
            
            html = render_template('email_verify.html', name=name, verify_url=verify_url)
            if send_email("Verifique a sua conta - E-Lixo Zero", [email], html):
                flash('Conta criada com sucesso! Verifique o seu email para ativar a conta.', 'success')
            else:
                flash('Conta criada, mas houve um erro ao enviar o email de verificação.', 'warning')
            return redirect(url_for('login'))
        else:
            flash('Erro ao criar conta. Email já existe?', 'error')
            
    return render_template('register.html')

@app.route('/verify/<token>')
def verify_email(token):
    try:
        email = serializer.loads(token, salt='email-confirm', max_age=3600)
    except SignatureExpired:
        flash('O link de verificação expirou.', 'error')
        return redirect(url_for('login'))
    except Exception:
        flash('Link de verificação inválido.', 'error')
        return redirect(url_for('login'))
        
    db.verify_user(email)
    flash('Conta verificada com sucesso! Já pode fazer login.', 'success')
    return redirect(url_for('login'))

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
    mensagens = db.get_mensagens()
    nao_lidas = db.get_mensagens_nao_lidas()
    return render_template('admin_dashboard.html', pontos=pontos, mensagens=mensagens, nao_lidas=nao_lidas)

@app.route('/client')
@login_required
def client_dashboard():
    return render_template('client_dashboard.html')

@app.route('/add_ponto', methods=['POST'])
@login_required
def add_ponto():
    if current_user.role != 'admin':
        flash("Apenas administradores podem adicionar pontos.", "error")
        return redirect(url_for('index'))
   
    imagem_file = request.files.get('imagem')
    imagem_data = None

    if imagem_file and imagem_file.filename != '':
        imagem_data = imagem_file.read()

    db.add_ponto(
        request.form['nome'],
        request.form['morada'],
        request.form.get('freguesia', ''),
        request.form.get('horario', ''),
        request.form.get('tipo_recolha', ''),
        request.form.get('link', ''),
        float(request.form['latitude']),
        float(request.form['longitude']),
        imagem_data,
        current_user.id
    )
    
    # Notificar utilizadores por email
    emails = db.get_all_verified_emails()
    if emails:
        html = render_template('email_novo_ponto.html', 
                               nome_ponto=request.form['nome'], 
                               morada=request.form['morada'],
                               tipo=request.form.get('tipo_recolha', 'Não especificado'))
        send_email("Novo Ponto de Recolha Adicionado!", emails, html)
    
    if current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    else:
        return redirect(url_for('client_dashboard'))

@app.route('/edit_ponto/<int:ponto_id>', methods=['GET', 'POST'])
@login_required
def edit_ponto(ponto_id):
    if current_user.role != 'admin':
        flash("Acesso negado.", "error")
        return redirect(url_for('index'))
    
    ponto = db.get_ponto_by_id(ponto_id)
    if not ponto:
        flash("Ponto não encontrado.", "warning")
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        imagem_file = request.files.get('imagem')
        imagem_data = None
        if imagem_file and imagem_file.filename != '':
            imagem_data = imagem_file.read()
        
        db.update_ponto(
            ponto_id,
            request.form['nome'],
            request.form['morada'],
            request.form.get('freguesia', ''),
            request.form.get('horario', ''),
            request.form.get('tipo_recolha', ''),
            request.form.get('link', ''),
            float(request.form['latitude']),
            float(request.form['longitude']),
            imagem_data
        )
        flash("Ponto atualizado com sucesso!")
        return redirect(url_for('admin_dashboard'))

    return render_template('edit_ponto.html', ponto=ponto)

@app.route('/delete_ponto/<int:ponto_id>')
@login_required
def delete_ponto(ponto_id):
    if current_user.role != 'admin':
        flash("Acesso negado.")
        return redirect(url_for('index'))
    
    db.delete_ponto(ponto_id)
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/marcar_lida/<int:msg_id>', methods=['POST'])
@login_required
def marcar_mensagem_lida(msg_id):
    if current_user.role != 'admin':
        return jsonify({'error': 'Acesso negado'}), 403
    db.marcar_mensagem_lida(msg_id)
    return redirect(url_for('admin_dashboard') + '#mensagens')

# API para notificação de novos pontos
@app.route('/api/novos_pontos')
def api_novos_pontos():
    latest_ts = db.get_latest_ponto_timestamp()
    since_ts = request.args.get('since', '')
    count = 0
    if since_ts and latest_ts:
        count = db.get_pontos_since(since_ts)
    return jsonify({'latest_ts': latest_ts, 'novos': count})

# API para estatísticas (página Sobre + admin)
@app.route('/api/stats')
def api_stats():
    return jsonify(db.get_stats())

# API para logs de actividade (admin only)
@app.route('/admin/api/logs')
@login_required
def api_logs():
    if current_user.role != 'admin':
        return jsonify({'error': 'Acesso negado'}), 403
    limit = int(request.args.get('limit', 100))
    logs = db.get_logs(limit)
    return jsonify(logs)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)