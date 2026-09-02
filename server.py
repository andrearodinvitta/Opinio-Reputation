#!/usr/bin/env python3
"""
Opinio / Reputation Shield Backend Server
Multi-tenant reputation management web application for local businesses.
Features:
- Access Request & Strict Superadmin Approval System (No open registration)
- Smart Review Funnel (4-5 Stars -> Google Reviews direct / 1-3 Stars -> Private Feedback Interception)
- Business Dashboard with Real-time Analytics, WhatsApp Resolution, and Branding Customizer
- Printable QR Stand / Table Tent Generator & NFC Tap Support
- Role-based Authentication (Superadmin & Business)
"""

import os
import sys
import json
import sqlite3
import hashlib
import secrets
import mimetypes
import re
import socket
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs, quote, unquote
from http.server import HTTPServer, BaseHTTPRequestHandler

try:
    import qrcode
    import qrcode.image.svg
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")

# Support for Vercel / Serverless environments (/tmp is writable)
if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    DB_PATH = os.environ.get("DB_PATH", "/tmp/reputation.db")
    bundled_db = os.path.join(BASE_DIR, "reputation.db")
    if not os.path.exists(DB_PATH) and os.path.exists(bundled_db):
        try:
            import shutil
            shutil.copy2(bundled_db, DB_PATH)
            print(f"[Vercel] Seeded database copied to {DB_PATH}")
        except Exception as e:
            print(f"[Vercel DB Copy Note] {e}")
else:
    DB_PATH = os.path.join(BASE_DIR, "reputation.db")

PORT = int(os.environ.get("PORT", 8080))

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def slugify(text: str) -> str:
    text = (text or '').lower().strip()
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u', 'ü': 'u', 'ñ': 'n',
        'à': 'a', 'è': 'e', 'ì': 'i', 'ò': 'o', 'ù': 'u', 'ç': 'c'
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    slug = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    return slug or "negocio"

def get_public_base_url():
    tunnel_log = os.path.join(BASE_DIR, "tunnel.log")
    if os.path.exists(tunnel_log):
        try:
            with open(tunnel_log, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                matches = re.findall(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', content)
                if matches:
                    return matches[-1]
        except Exception:
            pass
    return f"http://{get_local_ip()}:{PORT}"

# ---------------------------------------------------------------------------
# Password & Database Management
# ---------------------------------------------------------------------------

def hash_password(password: str, salt: str = None) -> str:
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
    return f"{salt}${hashed}"

def verify_password(password: str, stored_hash: str) -> bool:
    try:
        if not stored_hash or '$' not in stored_hash:
            return False
        salt, hashed = stored_hash.split('$', 1)
        check = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
        return secrets.compare_digest(hashed, check)
    except Exception:
        return False

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # 1. Superadmins table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS superadmins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        name TEXT DEFAULT 'Super Administrador',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Access requests (Strict approval workflow)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS access_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        applicant_name TEXT NOT NULL,
        business_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT NOT NULL,
        category TEXT DEFAULT 'General',
        city TEXT DEFAULT '',
        google_maps_url TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
        rejection_reason TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        processed_at TIMESTAMP
    );
    """)

    # 3. Businesses table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS businesses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slug TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        google_review_url TEXT DEFAULT '',
        logo_url TEXT DEFAULT '',
        primary_color TEXT DEFAULT '#4F46E5',
        accent_color TEXT DEFAULT '#EC4899',
        welcome_title TEXT DEFAULT '¡Gracias por visitarnos!',
        welcome_subtitle TEXT DEFAULT 'Tu opinión es muy importante para seguir mejorando.',
        notification_email TEXT DEFAULT '',
        notify_on_negative INTEGER DEFAULT 1,
        phone TEXT DEFAULT '',
        category TEXT DEFAULT 'General',
        city TEXT DEFAULT '',
        status TEXT DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
        request_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (request_id) REFERENCES access_requests (id) ON DELETE SET NULL
    );
    """)

    # Ensure status column exists if migrated
    try:
        cursor.execute("ALTER TABLE businesses ADD COLUMN status TEXT DEFAULT 'active';")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE businesses ADD COLUMN phone TEXT DEFAULT '';")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE businesses ADD COLUMN category TEXT DEFAULT 'General';")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE businesses ADD COLUMN city TEXT DEFAULT '';")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE businesses ADD COLUMN request_id INTEGER;")
    except sqlite3.OperationalError:
        pass

    # 4. Reviews table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id INTEGER NOT NULL,
        rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
        sentiment TEXT NOT NULL CHECK (sentiment IN ('positive', 'negative')),
        category TEXT DEFAULT 'General',
        customer_name TEXT DEFAULT '',
        customer_contact TEXT DEFAULT '',
        customer_email TEXT DEFAULT '',
        comment TEXT DEFAULT '',
        status TEXT DEFAULT 'new' CHECK (status IN ('new', 'contacted', 'resolved', 'archived')),
        internal_notes TEXT DEFAULT '',
        user_agent TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (business_id) REFERENCES businesses (id) ON DELETE CASCADE
    );
    """)

    try:
        cursor.execute("ALTER TABLE reviews ADD COLUMN category TEXT DEFAULT 'General';")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE reviews ADD COLUMN customer_email TEXT DEFAULT '';")
    except sqlite3.OperationalError:
        pass

    # 5. Sessions table (Role: superadmin or business)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('superadmin', 'business')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NOT NULL
    );
    """)

    # 6. Email notifications log
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS email_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id INTEGER DEFAULT NULL,
        to_email TEXT NOT NULL,
        subject TEXT NOT NULL,
        body TEXT NOT NULL,
        customer_name TEXT,
        rating INTEGER,
        log_type TEXT DEFAULT 'feedback_alert',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (business_id) REFERENCES businesses (id) ON DELETE CASCADE
    );
    """)

    # Check if business_id has NOT NULL constraint and migrate if needed
    try:
        cursor.execute("PRAGMA table_info(email_logs);")
        cols = {row['name']: dict(row) for row in cursor.fetchall()}
        if cols.get('business_id', {}).get('notnull') == 1 or 'log_type' not in cols:
            cursor.execute("CREATE TABLE email_logs_temp AS SELECT * FROM email_logs;")
            cursor.execute("DROP TABLE email_logs;")
            cursor.execute("""
            CREATE TABLE email_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_id INTEGER DEFAULT NULL,
                to_email TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                customer_name TEXT,
                rating INTEGER,
                log_type TEXT DEFAULT 'feedback_alert',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (business_id) REFERENCES businesses (id) ON DELETE CASCADE
            );
            """)
            cursor.execute("""
            INSERT INTO email_logs (id, business_id, to_email, subject, body, customer_name, rating, created_at)
            SELECT id, business_id, to_email, subject, body, customer_name, rating, created_at FROM email_logs_temp;
            """)
            cursor.execute("DROP TABLE email_logs_temp;")
            print("[DB] Migrated email_logs table to support nullable business_id.")
    except Exception as e:
        print(f"[DB Migration Note] {e}")

    # Seed Superadmin if not exists
    cursor.execute("SELECT COUNT(*) as count FROM superadmins")
    if cursor.fetchone()['count'] == 0:
        admin_pw = hash_password("admin123")
        cursor.execute("""
        INSERT INTO superadmins (email, password_hash, name)
        VALUES ('admin@opinio.app', ?, 'Super Administrador')
        """, (admin_pw,))
        print("[DB] Superadmin seeded: admin@opinio.app / admin123")

    # Seed Sample Businesses & Access Requests if empty
    cursor.execute("SELECT COUNT(*) as count FROM businesses")
    if cursor.fetchone()['count'] == 0:
        seed_data(cursor)

    conn.commit()
    conn.close()
    print("[DB] SQLite database initialized successfully.")

def seed_data(cursor):
    print("[DB] Seeding default businesses and access requests...")
    default_pw = hash_password("admin123")
    now = datetime.now()

    # 1. Seed sample pending access requests
    sample_requests = [
        ("Dr. Alejandro Morales", "Clínica Dental Sonrisas", "contacto@clinicasonrisas.es", "+34 654 987 321", "Salud / Clínica", "Madrid", "https://maps.google.com/?q=clinica+dental+madrid", "Queremos evitar que pacientes descontentos con los tiempos de espera nos bajen la media en Google.", "pending", ""),
        ("Marcos Fernández", "Taller Mecánico AutoFix Pro", "taller@autofixpro.es", "+34 688 223 344", "Automoción / Taller", "Barcelona", "https://maps.google.com/?q=autofix+barcelona", "Necesitamos filtrar opiniones tras las entregas de reparaciones.", "pending", ""),
        ("Elena Castaño", "Boutique Hotel & Spa Mirador", "reservas@hotelmirador.com", "+34 611 556 677", "Hostelería / Hotel", "Sevilla", "https://maps.google.com/?q=hotel+mirador+sevilla", "Gestionar feedback antes del checkout de los huéspedes.", "approved", "")
    ]

    for req in sample_requests:
        cursor.execute("""
        INSERT INTO access_requests (applicant_name, business_name, email, phone, category, city, google_maps_url, notes, status, rejection_reason, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (req[0], req[1], req[2], req[3], req[4], req[5], req[6], req[7], req[8], req[9], (now - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')))

    # 2. Seed active sample businesses
    # Business 1: Soraya Nails & Spa
    cursor.execute("""
    INSERT INTO businesses (
        slug, name, email, password_hash, google_review_url,
        primary_color, accent_color, welcome_title, welcome_subtitle,
        notification_email, notify_on_negative, phone, category, city, status
    ) VALUES (
        'soraya-nails', 'Soraya Nails & Spa', 'soraya@example.com', ?,
        'https://search.google.com/local/writereview?placeid=ChIJN1t_tDeuEmsRUsoyG83frY4',
        '#E11D48', '#FDA4AF', '¿Qué te pareció tu cita de hoy?',
        'Nos encanta consentirte. Déjanos tu calificación con estrellas.',
        'soraya@example.com', 1, '+34 600 123 456', 'Belleza & Estética', 'Valencia', 'active'
    );
    """, (default_pw,))
    b1_id = cursor.lastrowid

    # Business 2: Trattoria Bella Vista
    cursor.execute("""
    INSERT INTO businesses (
        slug, name, email, password_hash, google_review_url,
        primary_color, accent_color, welcome_title, welcome_subtitle,
        notification_email, notify_on_negative, phone, category, city, status
    ) VALUES (
        'bella-vista', 'Bella Vista Trattoria', 'bellavista@example.com', ?,
        'https://search.google.com/local/writereview?placeid=ChIJN1t_tDeuEmsRUsoyG83frY4',
        '#059669', '#10B981', '¿Cómo estuvo tu cena hoy?',
        'Tu experiencia gastronómica es nuestra pasión. Valora nuestro servicio.',
        'gerencia@bellavista.com', 1, '+34 677 889 900', 'Restaurante / Cafetería', 'Madrid', 'active'
    );
    """, (default_pw,))
    b2_id = cursor.lastrowid

    reviews_data = [
        (b1_id, 5, 'positive', 'Calidad del servicio', 'Camila R.', '', '', '', 'resolved', 1),
        (b1_id, 5, 'positive', 'Atención y personal', 'Valeria M.', '', '', '', 'resolved', 2),
        (b1_id, 4, 'positive', 'Instalaciones y ambiente', 'Lucía P.', '', '', '', 'resolved', 3),
        (b1_id, 2, 'negative', 'Calidad del servicio', 'Mariana Torres', '+34612345678', 'mariana.torres@gmail.com', 'La manicura se empezó a descascarillar a los dos días y la espera fue de 25 minutos.', 'new', 0),
        (b1_id, 1, 'negative', 'Atención y personal', 'Sofía Gómez', '+34699332211', 'sofia.gomez@gmail.com', 'El trato en recepción fue un poco seco y no tenían el tono de esmalte que reservé.', 'contacted', 4),
        (b1_id, 5, 'positive', 'Atención y personal', 'Elena Ruiz', '', '', '', 'resolved', 5),
        (b1_id, 5, 'positive', 'Calidad del servicio', 'Claudia N.', '', '', '', 'resolved', 6),
        (b1_id, 3, 'negative', 'Instalaciones y ambiente', 'Ana Belén', '+34699112233', '', 'El resultado final estuvo bien pero en el salón hacía demasiado calor y el aire no funcionaba.', 'resolved', 7),
        (b1_id, 5, 'positive', 'Calidad del servicio', 'Paula Sánchez', '', '', '', 'resolved', 8),

        (b2_id, 5, 'positive', 'Calidad del servicio', 'Carlos M.', '', '', '', 'resolved', 1),
        (b2_id, 5, 'positive', 'Atención y personal', 'Javier Ortiz', '', '', '', 'resolved', 2),
        (b2_id, 2, 'negative', 'Tiempo de espera', 'Gonzalo Vidal', '+34644556677', 'gonzalo.vidal@empresa.es', 'La pasta trufada llegó casi fría y tardaron 40 min en traer la cuenta.', 'new', 0),
        (b2_id, 4, 'positive', 'Calidad del servicio', 'Marta L.', '', '', '', 'resolved', 3),
    ]

    for b_id, rating, sentiment, cat, name, contact, email, comment, status, days_ago in reviews_data:
        date_str = (now - timedelta(days=days_ago, hours=rating)).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("""
        INSERT INTO reviews (business_id, rating, sentiment, category, customer_name, customer_contact, customer_email, comment, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (b_id, rating, sentiment, cat, name, contact, email, comment, status, date_str))

# ---------------------------------------------------------------------------
# HTTP Handler & Router
# ---------------------------------------------------------------------------

class RequestHandler(BaseHTTPRequestHandler):

    def send_json(self, data, status=200, cookie=None):
        body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, PATCH, DELETE, OPTIONS')
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, message, status=400):
        self.send_json({"error": message, "success": False}, status=status)

    def read_json_body(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                return {}
            raw_body = self.rfile.read(content_length).decode('utf-8')
            return json.loads(raw_body)
        except Exception as e:
            print(f"[Error reading JSON] {e}")
            return None

    def get_token_from_request(self, preferred_cookie_name='session_token'):
        auth_header = self.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            return auth_header[7:].strip()

        cookie_header = self.headers.get('Cookie', '')
        cookies = {}
        for cookie in cookie_header.split(';'):
            if '=' in cookie:
                k, v = cookie.strip().split('=', 1)
                cookies[k.strip()] = v.strip()

        if preferred_cookie_name in cookies and cookies[preferred_cookie_name]:
            return cookies[preferred_cookie_name]

        for c in ('session_token', 'admin_token'):
            if c in cookies and cookies[c]:
                return cookies[c]

        parsed = urlparse(self.path)
        q = parse_qs(parsed.query)
        if 'token' in q and q['token']:
            return q['token'][0].strip()
        return None

    def get_auth_business(self):
        token = self.get_token_from_request(preferred_cookie_name='session_token')
        if not token:
            return None
        conn = get_db()
        cursor = conn.cursor()
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("SELECT * FROM sessions WHERE token = ? AND expires_at > ?", (token, now_str))
        session = cursor.fetchone()
        if not session:
            conn.close()
            return None

        if session['role'] == 'business':
            cursor.execute("SELECT * FROM businesses WHERE id = ?", (session['user_id'],))
            biz = cursor.fetchone()
            conn.close()
            if not biz:
                return None
            biz_dict = dict(biz)
            if biz_dict.get('status') == 'suspended':
                return {"_is_suspended": True}
            return biz_dict

        conn.close()
        return None

    def get_auth_superadmin(self):
        token = self.get_token_from_request(preferred_cookie_name='admin_token')
        if not token:
            return None
        conn = get_db()
        cursor = conn.cursor()
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("SELECT * FROM sessions WHERE token = ? AND expires_at > ?", (token, now_str))
        session = cursor.fetchone()
        if not session:
            conn.close()
            return None

        if session['role'] == 'superadmin':
            cursor.execute("SELECT id, email, name, created_at FROM superadmins WHERE id = ?", (session['user_id'],))
            admin = cursor.fetchone()
            conn.close()
            return dict(admin) if admin else None

        conn.close()
        return None

    def serve_file(self, filepath, content_type=None):
        if not os.path.exists(filepath) or os.path.isdir(filepath):
            self.send_error(404, "File not found")
            return

        if not content_type:
            content_type, _ = mimetypes.guess_type(filepath)
            if not content_type:
                content_type = 'text/plain'

        with open(filepath, 'rb') as f:
            content = f.read()

        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(content)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, PATCH, DELETE, OPTIONS')
        self.end_headers()

    # -----------------------------------------------------------------------
    # GET Requests
    # -----------------------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # -------------------------------------------------------------------
        # 1. PUBLIC API: Public Funnel Data (/api/funnel/<slug>)
        # -------------------------------------------------------------------
        if path.startswith('/api/funnel/'):
            # QR Code Generation (SVG or PNG)
            if path.endswith('/qr.svg'):
                slug = path[len('/api/funnel/'):-len('/qr.svg')].strip('/')
                host = self.headers.get('Host') or f"localhost:{PORT}"
                scheme = 'https' if self.headers.get('X-Forwarded-Proto') == 'https' else 'http'
                full_url = f"{scheme}://{host}/r/{slug}"

                if HAS_QRCODE:
                    qr = qrcode.QRCode(
                        version=None,
                        error_correction=qrcode.constants.ERROR_CORRECT_M,
                        box_size=10,
                        border=2,
                        image_factory=qrcode.image.svg.SvgPathImage
                    )
                    qr.add_data(full_url)
                    qr.make(fit=True)
                    img = qr.make_image()
                    svg_data = img.to_string()
                    self.send_response(200)
                    self.send_header('Content-Type', 'image/svg+xml')
                    self.send_header('Cache-Control', 'public, max-age=86400')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(svg_data)
                    return

            slug = path[len('/api/funnel/'):].strip().strip('/')
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
            SELECT id, slug, name, google_review_url, logo_url, primary_color, accent_color,
                   welcome_title, welcome_subtitle, status FROM businesses WHERE slug = ?
            """, (slug,))
            row = cursor.fetchone()
            conn.close()

            if not row:
                self.send_error_json("Comercio no encontrado", 404)
                return

            biz_dict = dict(row)
            if not biz_dict.get('google_review_url'):
                biz_dict['google_review_url'] = f"https://www.google.com/search?q={quote(biz_dict['name'] + ' opiniones google')}"

            if biz_dict.get('status') == 'suspended':
                self.send_json({
                    "success": False,
                    "suspended": True,
                    "business": {"name": biz_dict['name'], "status": "suspended"},
                    "error": "Este portal de opiniones se encuentra temporalmente inactivo."
                }, status=403)
                return

            self.send_json({"success": True, "business": biz_dict})
            return

        # -------------------------------------------------------------------
        # 2. BUSINESS API: Profile, Stats, Reviews
        # -------------------------------------------------------------------
        if path == '/api/business/profile':
            business = self.get_auth_business()
            if not business:
                self.send_error_json("No autenticado", 401)
                return
            if business.get('_is_suspended'):
                self.send_error_json("Tu cuenta ha sido suspendida. Contacta con el superadministrador.", 403)
                return

            del business['password_hash']
            business['public_base_url'] = get_public_base_url()
            business['local_base_url'] = f"http://{get_local_ip()}:{PORT}"
            self.send_json({"success": True, "business": business})
            return

        if path == '/api/business/stats':
            business = self.get_auth_business()
            if not business:
                self.send_error_json("No autenticado", 401)
                return
            if business.get('_is_suspended'):
                self.send_error_json("Cuenta suspendida", 403)
                return

            conn = get_db()
            cursor = conn.cursor()
            b_id = business['id']

            cursor.execute("SELECT COUNT(*) as total FROM reviews WHERE business_id = ?", (b_id,))
            total_reviews = cursor.fetchone()['total']

            cursor.execute("""
            SELECT rating, COUNT(*) as count FROM reviews
            WHERE business_id = ?
            GROUP BY rating ORDER BY rating ASC
            """, (b_id,))
            dist_map = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
            for row in cursor.fetchall():
                dist_map[row['rating']] = row['count']

            positive_count = dist_map[4] + dist_map[5]
            negative_count = dist_map[1] + dist_map[2] + dist_map[3]

            satisfaction_rate = round((positive_count / total_reviews * 100), 1) if total_reviews > 0 else 100.0
            avg_rating = round(sum(k * v for k, v in dist_map.items()) / total_reviews, 2) if total_reviews > 0 else 5.0

            cursor.execute("""
            SELECT COUNT(*) as count FROM reviews
            WHERE business_id = ? AND sentiment = 'negative' AND status = 'new'
            """, (b_id,))
            pending_count = cursor.fetchone()['count']

            cursor.execute("""
            SELECT category, COUNT(*) as count FROM reviews
            WHERE business_id = ? AND sentiment = 'negative' AND category != ''
            GROUP BY category ORDER BY count DESC LIMIT 5
            """, (b_id,))
            categories_summary = [dict(r) for r in cursor.fetchall()]

            # Timeline data (last 7 days)
            cursor.execute("""
            SELECT strftime('%Y-%m-%d', created_at) as day,
                   SUM(CASE WHEN sentiment = 'positive' THEN 1 ELSE 0 END) as positive,
                   SUM(CASE WHEN sentiment = 'negative' THEN 1 ELSE 0 END) as negative
            FROM reviews
            WHERE business_id = ?
            GROUP BY day ORDER BY day DESC LIMIT 7
            """, (b_id,))
            timeline_rows = [dict(r) for r in cursor.fetchall()]

            conn.close()

            stats = {
                "total_ratings": total_reviews,
                "positive_count": positive_count,
                "negative_count": negative_count,
                "diverted_negative_count": negative_count,
                "satisfaction_rate": satisfaction_rate,
                "average_rating": avg_rating,
                "pending_attention": pending_count,
                "distribution": dist_map,
                "categories_summary": categories_summary,
                "timeline": timeline_rows
            }
            self.send_json({"success": True, "stats": stats})
            return

        if path == '/api/business/reviews':
            business = self.get_auth_business()
            if not business:
                self.send_error_json("No autenticado", 401)
                return
            if business.get('_is_suspended'):
                self.send_error_json("Cuenta suspendida", 403)
                return

            sentiment_filter = query.get('sentiment', [None])[0]
            status_filter = query.get('status', [None])[0]
            rating_filter = query.get('rating', [None])[0]
            search_query = query.get('q', [None])[0]

            sql = "SELECT * FROM reviews WHERE business_id = ?"
            params = [business['id']]

            if sentiment_filter in ('positive', 'negative'):
                sql += " AND sentiment = ?"
                params.append(sentiment_filter)
            if status_filter in ('new', 'contacted', 'resolved', 'archived'):
                sql += " AND status = ?"
                params.append(status_filter)
            if rating_filter and rating_filter.isdigit():
                sql += " AND rating = ?"
                params.append(int(rating_filter))
            if search_query:
                sql += " AND (customer_name LIKE ? OR customer_contact LIKE ? OR comment LIKE ?)"
                like_term = f"%{search_query.strip()}%"
                params.extend([like_term, like_term, like_term])

            sql += " ORDER BY created_at DESC"

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(sql, tuple(params))
            reviews = [dict(r) for r in cursor.fetchall()]
            conn.close()

            self.send_json({"success": True, "reviews": reviews})
            return

        # Export CSV endpoint
        if path == '/api/business/reviews/export.csv':
            business = self.get_auth_business()
            if not business:
                self.send_error_json("No autenticado", 401)
                return
            if business.get('_is_suspended'):
                self.send_error_json("Cuenta suspendida", 403)
                return

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM reviews WHERE business_id = ? ORDER BY created_at DESC", (business['id'],))
            reviews = cursor.fetchall()
            conn.close()

            lines = ["ID,Fecha,Estrellas,Sentimiento,Categoría,Cliente,Contacto,Email,Comentario,Estado,Notas"]
            for r in reviews:
                def clean(v):
                    return f'"{str(v or "").replace(chr(34), chr(34)+chr(34))}"'
                lines.append(f"{r['id']},{clean(r['created_at'])},{r['rating']},{clean(r['sentiment'])},{clean(r['category'])},{clean(r['customer_name'])},{clean(r['customer_contact'])},{clean(r['customer_email'])},{clean(r['comment'])},{clean(r['status'])},{clean(r['internal_notes'])}")

            csv_content = "\n".join(lines).encode('utf-8-sig')
            self.send_response(200)
            self.send_header('Content-Type', 'text/csv; charset=utf-8')
            self.send_header('Content-Disposition', f'attachment; filename="feedback_{business["slug"]}_{datetime.now().strftime("%Y%m%d")}.csv"')
            self.send_header('Content-Length', str(len(csv_content)))
            self.end_headers()
            self.wfile.write(csv_content)
            return

        if path == '/api/business/email-logs':
            business = self.get_auth_business()
            if not business:
                self.send_error_json("No autenticado", 401)
                return
            if business.get('_is_suspended'):
                self.send_error_json("Cuenta suspendida", 403)
                return

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
            SELECT * FROM email_logs WHERE business_id = ? ORDER BY created_at DESC LIMIT 50
            """, (business['id'],))
            logs = [dict(r) for r in cursor.fetchall()]
            conn.close()

            self.send_json({"success": True, "logs": logs})
            return

        # -------------------------------------------------------------------
        # 3. SUPERADMIN API: Requests, Businesses, Global Stats
        # -------------------------------------------------------------------
        if path == '/api/admin/me':
            admin = self.get_auth_superadmin()
            if not admin:
                self.send_error_json("No autenticado como superadministrador", 401)
                return
            self.send_json({"success": True, "admin": admin})
            return

        if path == '/api/admin/requests':
            admin = self.get_auth_superadmin()
            if not admin:
                self.send_error_json("No autorizado", 403)
                return

            status_filter = query.get('status', ['all'])[0]
            sql = "SELECT * FROM access_requests"
            params = []
            if status_filter in ('pending', 'approved', 'rejected'):
                sql += " WHERE status = ?"
                params.append(status_filter)
            sql += " ORDER BY created_at DESC"

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(sql, tuple(params))
            requests = [dict(r) for r in cursor.fetchall()]

            cursor.execute("SELECT COUNT(*) as count FROM access_requests WHERE status = 'pending'")
            pending_count = cursor.fetchone()['count']
            conn.close()

            self.send_json({"success": True, "requests": requests, "pending_count": pending_count})
            return

        if path == '/api/admin/businesses':
            admin = self.get_auth_superadmin()
            if not admin:
                self.send_error_json("No autorizado", 403)
                return

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
            SELECT b.*,
                   COUNT(r.id) as total_reviews,
                   SUM(CASE WHEN r.sentiment = 'positive' THEN 1 ELSE 0 END) as positive_reviews,
                   SUM(CASE WHEN r.sentiment = 'negative' THEN 1 ELSE 0 END) as negative_reviews,
                   AVG(r.rating) as avg_rating
            FROM businesses b
            LEFT JOIN reviews r ON b.id = r.business_id
            GROUP BY b.id
            ORDER BY b.created_at DESC
            """)
            businesses = []
            for row in cursor.fetchall():
                d = dict(row)
                del d['password_hash']
                d['avg_rating'] = round(d['avg_rating'], 1) if d['avg_rating'] else 5.0
                businesses.append(d)
            conn.close()

            self.send_json({"success": True, "businesses": businesses})
            return

        if path == '/api/admin/stats':
            admin = self.get_auth_superadmin()
            if not admin:
                self.send_error_json("No autorizado", 403)
                return

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as total FROM businesses")
            total_businesses = cursor.fetchone()['total']

            cursor.execute("SELECT COUNT(*) as active FROM businesses WHERE status = 'active'")
            active_businesses = cursor.fetchone()['active']

            cursor.execute("SELECT COUNT(*) as pending FROM access_requests WHERE status = 'pending'")
            pending_requests = cursor.fetchone()['pending']

            cursor.execute("SELECT COUNT(*) as total FROM reviews")
            total_reviews = cursor.fetchone()['total']

            cursor.execute("SELECT COUNT(*) as positive FROM reviews WHERE sentiment = 'positive'")
            positive_reviews = cursor.fetchone()['positive']

            cursor.execute("SELECT COUNT(*) as negative FROM reviews WHERE sentiment = 'negative'")
            negative_reviews = cursor.fetchone()['negative']

            satisfaction_rate = round((positive_reviews / total_reviews * 100), 1) if total_reviews > 0 else 100.0

            cursor.execute("SELECT * FROM email_logs ORDER BY created_at DESC LIMIT 20")
            recent_emails = [dict(r) for r in cursor.fetchall()]

            conn.close()

            self.send_json({
                "success": True,
                "stats": {
                    "total_businesses": total_businesses,
                    "active_businesses": active_businesses,
                    "pending_requests": pending_requests,
                    "total_reviews": total_reviews,
                    "positive_reviews": positive_reviews,
                    "negative_reviews": negative_reviews,
                    "satisfaction_rate": satisfaction_rate
                },
                "recent_emails": recent_emails
            })
            return

        # -------------------------------------------------------------------
        # HTML Page Routes
        # -------------------------------------------------------------------
        if path.startswith('/r/') or path.startswith('/feedback/'):
            self.serve_file(os.path.join(PUBLIC_DIR, "funnel.html"), "text/html; charset=utf-8")
            return

        if path in ('/admin', '/superadmin', '/admin/dashboard'):
            self.serve_file(os.path.join(PUBLIC_DIR, "admin.html"), "text/html; charset=utf-8")
            return

        if path in ('/dashboard', '/portal', '/dashboard/reviews', '/dashboard/settings', '/dashboard/qr'):
            self.serve_file(os.path.join(PUBLIC_DIR, "dashboard.html"), "text/html; charset=utf-8")
            return

        if path in ('/login', '/acceso'):
            self.serve_file(os.path.join(PUBLIC_DIR, "auth.html"), "text/html; charset=utf-8")
            return

        if path in ('/', '/index.html', '/solicitar-acceso'):
            self.serve_file(os.path.join(PUBLIC_DIR, "index.html"), "text/html; charset=utf-8")
            return

        # Static assets
        clean_path = path.lstrip('/')
        target_file = os.path.join(PUBLIC_DIR, clean_path)
        if os.path.isfile(target_file):
            self.serve_file(target_file)
            return

        self.send_error(404, "Page Not Found")

    # -----------------------------------------------------------------------
    # POST Requests
    # -----------------------------------------------------------------------
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self.read_json_body()
        if body is None:
            self.send_error_json("JSON inválido", 400)
            return

        # -------------------------------------------------------------------
        # 1. PUBLIC: Access Request Submission ("Solicitar Acceso")
        # -------------------------------------------------------------------
        if path == '/api/access-requests/submit':
            applicant_name = (body.get('applicant_name') or '').strip()
            business_name = (body.get('business_name') or '').strip()
            email = (body.get('email') or '').strip().lower()
            phone = (body.get('phone') or '').strip()
            category = (body.get('category') or 'General').strip()
            city = (body.get('city') or '').strip()
            google_maps_url = (body.get('google_maps_url') or '').strip()
            notes = (body.get('notes') or '').strip()

            if not applicant_name or not business_name or not email or not phone:
                self.send_error_json("Nombre, nombre del negocio, email y teléfono son obligatorios.")
                return

            conn = get_db()
            cursor = conn.cursor()

            # Check if business email is already registered
            cursor.execute("SELECT id FROM businesses WHERE email = ?", (email,))
            if cursor.fetchone():
                conn.close()
                self.send_error_json("Ya existe un negocio registrado con este correo. Puedes iniciar sesión.", 409)
                return

            # Check if request already exists
            cursor.execute("SELECT id, status FROM access_requests WHERE email = ?", (email,))
            existing = cursor.fetchone()
            if existing:
                if existing['status'] == 'pending':
                    conn.close()
                    self.send_json({
                        "success": True,
                        "already_pending": True,
                        "message": "Tu solicitud ya se encuentra en proceso de revisión. Te contactaremos en cuanto sea aprobada."
                    })
                    return
                elif existing['status'] == 'approved':
                    conn.close()
                    self.send_error_json("Tu solicitud previa ya fue aprobada. Por favor ingresa a través del acceso a clientes.", 409)
                    return

            try:
                cursor.execute("""
                INSERT INTO access_requests (applicant_name, business_name, email, phone, category, city, google_maps_url, notes, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """, (applicant_name, business_name, email, phone, category, city, google_maps_url, notes))
                req_id = cursor.lastrowid

                # Log confirmation notification
                cursor.execute("""
                INSERT INTO email_logs (business_id, to_email, subject, body, customer_name, log_type)
                VALUES (NULL, ?, ?, ?, ?, 'request_received')
                """, (
                    email,
                    "📋 Solicitud de acceso recibida | Opinio Reputation",
                    f"Hola {applicant_name},\n\nHemos recibido tu solicitud para dar de alta {business_name}.\nNuestro equipo de administradores revisará los datos y recibirás tus credenciales de acceso tras la aprobación.\n\n¡Gracias por tu confianza!",
                    applicant_name
                ))

                conn.commit()
                conn.close()

                self.send_json({
                    "success": True,
                    "request_id": req_id,
                    "message": "¡Solicitud enviada con éxito! Tu cuenta está en revisión y el administrador te contactará para darte acceso."
                })
            except Exception as e:
                conn.close()
                self.send_error_json(f"Error al registrar solicitud: {str(e)}", 500)
            return

        # -------------------------------------------------------------------
        # 1b. AUTH: Business Direct Registration ("Crear Cuenta")
        # -------------------------------------------------------------------
        if path == '/api/auth/register':
            applicant_name = (body.get('applicant_name') or body.get('name') or '').strip()
            business_name = (body.get('business_name') or '').strip()
            email = (body.get('email') or '').strip().lower()
            password = body.get('password') or ''
            phone = (body.get('phone') or '').strip()
            category = (body.get('category') or 'General').strip()
            city = (body.get('city') or '').strip()
            google_maps_url = (body.get('google_maps_url') or '').strip()

            if not business_name:
                self.send_error_json("El nombre del negocio es obligatorio.")
                return
            if not email or '@' not in email:
                self.send_error_json("Debes ingresar un correo electrónico válido.")
                return
            if not password or len(password) < 4:
                self.send_error_json("La contraseña debe tener al menos 4 caracteres.")
                return

            if not applicant_name:
                applicant_name = business_name

            conn = get_db()
            cursor = conn.cursor()

            # Check if business already exists
            cursor.execute("SELECT id FROM businesses WHERE email = ?", (email,))
            if cursor.fetchone():
                conn.close()
                self.send_error_json("Ya existe una cuenta registrada con este correo. Por favor inicia sesión.", 409)
                return

            # Generate unique slug
            raw_slug = slugify(business_name)
            slug = raw_slug
            counter = 1
            while True:
                cursor.execute("SELECT id FROM businesses WHERE slug = ?", (slug,))
                if not cursor.fetchone():
                    break
                counter += 1
                slug = f"{raw_slug}-{counter}"

            hashed_pw = hash_password(password)
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            try:
                # 1. Insert or update access request
                cursor.execute("SELECT id FROM access_requests WHERE email = ?", (email,))
                existing_req = cursor.fetchone()
                if existing_req:
                    req_id = existing_req['id']
                    cursor.execute("""
                    UPDATE access_requests
                    SET applicant_name = ?, business_name = ?, phone = ?, category = ?, city = ?,
                        google_maps_url = ?, status = 'approved', processed_at = ?
                    WHERE id = ?
                    """, (applicant_name, business_name, phone, category, city, google_maps_url, now_str, req_id))
                else:
                    cursor.execute("""
                    INSERT INTO access_requests (applicant_name, business_name, email, phone, category, city, google_maps_url, status, processed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'approved', ?)
                    """, (applicant_name, business_name, email, phone, category, city, google_maps_url, now_str))
                    req_id = cursor.lastrowid

                # 2. Create business
                cursor.execute("""
                INSERT INTO businesses (
                    slug, name, email, password_hash, google_review_url,
                    notification_email, phone, category, city, status, request_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
                """, (
                    slug, business_name, email, hashed_pw,
                    google_maps_url, email, phone, category, city, req_id
                ))
                business_id = cursor.lastrowid

                # 3. Create active session token
                token = secrets.token_hex(32)
                expires = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute("""
                INSERT INTO sessions (token, user_id, role, expires_at)
                VALUES (?, ?, 'business', ?)
                """, (token, business_id, expires))

                # 4. Log welcome notification
                cursor.execute("""
                INSERT INTO email_logs (business_id, to_email, subject, body, customer_name, log_type)
                VALUES (?, ?, ?, ?, ?, 'direct_registration')
                """, (
                    business_id,
                    email,
                    f"🎉 ¡Bienvenido a Opinio! Tu cuenta para {business_name} está lista",
                    f"Hola {applicant_name},\n\nTu cuenta para '{business_name}' ha sido creada exitosamente.\n\n- Panel de Control: /dashboard\n- Enlace público para tus clientes: /r/{slug}\n\n¡Comienza ahora a proteger y potenciar tu reputación!",
                    applicant_name
                ))

                conn.commit()

                cursor.execute("SELECT * FROM businesses WHERE id = ?", (business_id,))
                biz = cursor.fetchone()
                biz_dict = dict(biz)
                del biz_dict['password_hash']
                conn.close()

                cookie_header = f"session_token={token}; Path=/; Max-Age={30*24*60*60}; SameSite=Lax"
                self.send_json({
                    "success": True,
                    "token": token,
                    "business": biz_dict,
                    "redirect": "/dashboard",
                    "message": "¡Cuenta creada exitosamente! Bienvenido a tu panel."
                }, status=201, cookie=cookie_header)
            except Exception as e:
                conn.close()
                self.send_error_json(f"Error al registrar la cuenta: {str(e)}", 500)
            return

        # -------------------------------------------------------------------
        # 2. AUTH: Business Login (Only Approved & Active Accounts)
        # -------------------------------------------------------------------
        if path == '/api/auth/login':
            email = (body.get('email') or '').strip().lower()
            password = body.get('password') or ''

            if not email or not password:
                self.send_error_json("Debes ingresar correo y contraseña.")
                return

            conn = get_db()
            cursor = conn.cursor()

            # Query business
            cursor.execute("SELECT * FROM businesses WHERE email = ?", (email,))
            business = cursor.fetchone()

            if not business:
                # Check if there's a pending access request
                cursor.execute("SELECT * FROM access_requests WHERE email = ? AND status = 'pending'", (email,))
                pending_req = cursor.fetchone()
                conn.close()
                if pending_req:
                    self.send_error_json("Tu solicitud previa está en revisión. Si deseas acceder de inmediato, regístrate en la pestaña 'Crear Cuenta' con tu contraseña.", 403)
                else:
                    self.send_error_json("No existe una cuenta registrada con este correo. Puedes crear una cuenta nueva en la pestaña 'Crear Cuenta'.", 401)
                return

            if not verify_password(password, business['password_hash']):
                conn.close()
                self.send_error_json("Contraseña incorrecta.", 401)
                return

            if business['status'] == 'suspended':
                conn.close()
                self.send_error_json("Tu cuenta ha sido desactivada/suspendida por el administrador. Contacta a soporte para reactivarla.", 403)
                return

            token = secrets.token_hex(32)
            expires = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("""
            INSERT INTO sessions (token, user_id, role, expires_at)
            VALUES (?, ?, 'business', ?)
            """, (token, business['id'], expires))
            conn.commit()

            business_dict = dict(business)
            del business_dict['password_hash']
            conn.close()

            cookie_header = f"session_token={token}; Path=/; Max-Age={30*24*60*60}; SameSite=Lax"
            self.send_json({
                "success": True,
                "token": token,
                "business": business_dict
            }, cookie=cookie_header)
            return

        # -------------------------------------------------------------------
        # 3. AUTH: Superadmin Login
        # -------------------------------------------------------------------
        if path == '/api/admin/login':
            email = (body.get('email') or '').strip().lower()
            password = body.get('password') or ''

            if not email or not password:
                self.send_error_json("Debes ingresar correo y contraseña.")
                return

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM superadmins WHERE email = ?", (email,))
            admin = cursor.fetchone()

            if not admin or not verify_password(password, admin['password_hash']):
                conn.close()
                self.send_error_json("Credenciales de superadministrador incorrectas.", 401)
                return

            token = secrets.token_hex(32)
            expires = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("""
            INSERT INTO sessions (token, user_id, role, expires_at)
            VALUES (?, ?, 'superadmin', ?)
            """, (token, admin['id'], expires))
            conn.commit()

            admin_dict = dict(admin)
            del admin_dict['password_hash']
            conn.close()

            cookie_header = f"admin_token={token}; Path=/; Max-Age={7*24*60*60}; SameSite=Lax"
            self.send_json({
                "success": True,
                "token": token,
                "admin": admin_dict
            }, cookie=cookie_header)
            return

        # -------------------------------------------------------------------
        # 4. SUPERADMIN ACTIONS: Approve & Reject Requests, Suspend/Reactivate
        # -------------------------------------------------------------------
        if path.startswith('/api/admin/requests/') and path.endswith('/approve'):
            admin = self.get_auth_superadmin()
            if not admin:
                self.send_error_json("No autorizado", 403)
                return

            try:
                req_id = int(path.split('/')[4])
            except ValueError:
                self.send_error_json("ID inválido", 400)
                return

            custom_password = (body.get('initial_password') or '').strip()
            temp_password = custom_password if custom_password else secrets.token_hex(4) + "!"
            hashed_pw = hash_password(temp_password)

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM access_requests WHERE id = ?", (req_id,))
            req = cursor.fetchone()

            if not req:
                conn.close()
                self.send_error_json("Solicitud no encontrada", 404)
                return

            # Generate unique slug
            raw_slug = slugify(req['business_name'])
            slug = raw_slug
            counter = 1
            while True:
                cursor.execute("SELECT id FROM businesses WHERE slug = ?", (slug,))
                if not cursor.fetchone():
                    break
                counter += 1
                slug = f"{raw_slug}-{counter}"

            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            try:
                # Create business
                cursor.execute("""
                INSERT INTO businesses (
                    slug, name, email, password_hash, google_review_url,
                    notification_email, phone, category, city, status, request_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
                """, (
                    slug, req['business_name'], req['email'], hashed_pw,
                    req['google_maps_url'] or '', req['email'], req['phone'],
                    req['category'], req['city'], req_id
                ))
                business_id = cursor.lastrowid

                # Mark request approved
                cursor.execute("""
                UPDATE access_requests
                SET status = 'approved', processed_at = ?
                WHERE id = ?
                """, (now_str, req_id))

                # Log welcome email with credentials
                welcome_subject = f"🎉 ¡Tu cuenta ha sido aprobada! Acceso a Opinio para {req['business_name']}"
                welcome_body = f"""Hola {req['applicant_name']},\n\nNos complace informarte que tu solicitud de acceso para '{req['business_name']}' ha sido APROBADA.\n\nTus credenciales de acceso:\n- URL del Panel: http://localhost:{PORT}/login\n- Usuario / Email: {req['email']}\n- Contraseña Inicial: {temp_password}\n- Enlace público para tus clientes: http://localhost:{PORT}/r/{slug}\n\nTe recomendamos iniciar sesión y configurar tu enlace directo de Google Reviews y personalizar los colores de tu marca.\n\n¡Bienvenido a bordo!"""

                cursor.execute("""
                INSERT INTO email_logs (business_id, to_email, subject, body, customer_name, log_type)
                VALUES (?, ?, ?, ?, ?, 'account_approved')
                """, (business_id, req['email'], welcome_subject, welcome_body, req['applicant_name']))

                conn.commit()
                conn.close()

                self.send_json({
                    "success": True,
                    "message": "Solicitud aprobada y cuenta creada exitosamente.",
                    "credentials": {
                        "business_id": business_id,
                        "business_name": req['business_name'],
                        "email": req['email'],
                        "temporary_password": temp_password,
                        "slug": slug,
                        "login_url": f"/login",
                        "funnel_url": f"/r/{slug}"
                    }
                })
            except sqlite3.IntegrityError as e:
                conn.close()
                self.send_error_json(f"Ya existe un negocio registrado con este correo o slug ({str(e)}).", 409)
            return

        if path.startswith('/api/admin/requests/') and path.endswith('/reject'):
            admin = self.get_auth_superadmin()
            if not admin:
                self.send_error_json("No autorizado", 403)
                return

            try:
                req_id = int(path.split('/')[4])
            except ValueError:
                self.send_error_json("ID inválido", 400)
                return

            reason = (body.get('reason') or 'No cumple con los requisitos del servicio en este momento.').strip()
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM access_requests WHERE id = ?", (req_id,))
            req = cursor.fetchone()

            if not req:
                conn.close()
                self.send_error_json("Solicitud no encontrada", 404)
                return

            cursor.execute("""
            UPDATE access_requests
            SET status = 'rejected', rejection_reason = ?, processed_at = ?
            WHERE id = ?
            """, (reason, now_str, req_id))

            # Log rejection email
            cursor.execute("""
            INSERT INTO email_logs (business_id, to_email, subject, body, customer_name, log_type)
            VALUES (NULL, ?, ?, ?, ?, 'request_rejected')
            """, (
                req['email'],
                "Estado de tu solicitud | Opinio Reputation",
                f"Hola {req['applicant_name']},\n\nGracias por tu interés en Opinio. Lamentamos informarte que tu solicitud no ha podido ser aceptada en este momento.\nMotivo: {reason}\n\nSi crees que se trata de un error, por favor contáctanos.",
                req['applicant_name']
            ))

            conn.commit()
            conn.close()

            self.send_json({"success": True, "message": "Solicitud rechazada correctamente."})
            return

        if path.startswith('/api/admin/businesses/') and path.endswith('/toggle-status'):
            admin = self.get_auth_superadmin()
            if not admin:
                self.send_error_json("No autorizado", 403)
                return

            try:
                b_id = int(path.split('/')[4])
            except ValueError:
                self.send_error_json("ID inválido", 400)
                return

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, status FROM businesses WHERE id = ?", (b_id,))
            biz = cursor.fetchone()
            if not biz:
                conn.close()
                self.send_error_json("Negocio no encontrado", 404)
                return

            new_status = 'suspended' if biz['status'] == 'active' else 'active'
            cursor.execute("UPDATE businesses SET status = ? WHERE id = ?", (new_status, b_id))

            # If suspending, terminate active sessions
            if new_status == 'suspended':
                cursor.execute("DELETE FROM sessions WHERE user_id = ? AND role = 'business'", (b_id,))

            conn.commit()
            conn.close()

            self.send_json({
                "success": True,
                "new_status": new_status,
                "message": f"Negocio '{biz['name']}' ahora está {new_status.upper()}."
            })
            return

        if path.startswith('/api/admin/businesses/') and path.endswith('/reset-password'):
            admin = self.get_auth_superadmin()
            if not admin:
                self.send_error_json("No autorizado", 403)
                return

            try:
                b_id = int(path.split('/')[4])
            except ValueError:
                self.send_error_json("ID inválido", 400)
                return

            new_pw = (body.get('new_password') or '').strip() or secrets.token_hex(4) + "!"
            hashed = hash_password(new_pw)

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE businesses SET password_hash = ? WHERE id = ?", (hashed, b_id))
            cursor.execute("DELETE FROM sessions WHERE user_id = ? AND role = 'business'", (b_id,))
            conn.commit()
            conn.close()

            self.send_json({
                "success": True,
                "temporary_password": new_pw,
                "message": "Contraseña restablecida con éxito."
            })
            return

        if path.startswith('/api/admin/businesses/') and path.endswith('/impersonate'):
            admin = self.get_auth_superadmin()
            if not admin:
                self.send_error_json("No autorizado", 403)
                return

            try:
                b_id = int(path.split('/')[4])
            except ValueError:
                self.send_error_json("ID inválido", 400)
                return

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, slug FROM businesses WHERE id = ?", (b_id,))
            biz = cursor.fetchone()
            if not biz:
                conn.close()
                self.send_error_json("Negocio no encontrado", 404)
                return

            token = secrets.token_hex(32)
            expires = (datetime.now() + timedelta(hours=4)).strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("""
            INSERT INTO sessions (token, user_id, role, expires_at)
            VALUES (?, ?, 'business', ?)
            """, (token, b_id, expires))
            conn.commit()
            conn.close()

            cookie_header = f"session_token={token}; Path=/; Max-Age={4*60*60}; SameSite=Lax"
            self.send_json({
                "success": True,
                "token": token,
                "redirect": "/dashboard",
                "business": dict(biz)
            }, cookie=cookie_header)
            return

        # -------------------------------------------------------------------
        # 5. LOGOUT
        # -------------------------------------------------------------------
        if path in ('/api/auth/logout', '/api/admin/logout'):
            auth_header = self.headers.get('Authorization', '')
            token = auth_header[7:].strip() if auth_header.startswith('Bearer ') else None
            if not token:
                cookie_header = self.headers.get('Cookie', '')
                for cookie in cookie_header.split(';'):
                    if '=' in cookie:
                        k, v = cookie.strip().split('=', 1)
                        if k.strip() in ('session_token', 'admin_token'):
                            token = v.strip()
                            break

            if token:
                conn = get_db()
                conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
                conn.commit()
                conn.close()

            clear_cookies = "session_token=; Path=/; Max-Age=0; SameSite=Lax\r\nSet-Cookie: admin_token=; Path=/; Max-Age=0; SameSite=Lax"
            self.send_json({"success": True, "message": "Sesión cerrada con éxito"}, cookie=clear_cookies)
            return

        # -------------------------------------------------------------------
        # 6. PUBLIC FUNNEL: Rating Step 1 (1-5 stars)
        # -------------------------------------------------------------------
        if path.startswith('/api/funnel/') and path.endswith('/rating'):
            parts = path.split('/')
            slug = parts[3]
            try:
                rating = int(body.get('rating', 0))
            except ValueError:
                rating = 0

            if rating < 1 or rating > 5:
                self.send_error_json("La calificación debe ser de 1 a 5 estrellas.")
                return

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM businesses WHERE slug = ?", (slug,))
            business = cursor.fetchone()
            if not business:
                conn.close()
                self.send_error_json("Negocio no encontrado", 404)
                return

            if business['status'] == 'suspended':
                conn.close()
                self.send_error_json("Este negocio no se encuentra activo.", 403)
                return

            sentiment = 'positive' if rating >= 4 else 'negative'
            user_agent = self.headers.get('User-Agent', '')

            cursor.execute("""
            INSERT INTO reviews (business_id, rating, sentiment, user_agent, status)
            VALUES (?, ?, ?, ?, 'new')
            """, (business['id'], rating, sentiment, user_agent))
            review_id = cursor.lastrowid
            conn.commit()
            conn.close()

            response_data = {
                "success": True,
                "review_id": review_id,
                "rating": rating,
                "sentiment": sentiment,
            }

            if sentiment == 'positive':
                g_url = business['google_review_url']
                if not g_url:
                    g_url = f"https://www.google.com/search?q={quote(business['name'] + ' opiniones google')}"
                response_data["google_review_url"] = g_url
                response_data["message"] = "¡Muchas gracias! Ayúdanos compartiendo tu experiencia en Google."
                response_data["suggested_chips"] = [
                    "Excelente atención y amabilidad",
                    "Calidad insuperable, muy recomendable",
                    "Servicio rápido, limpio y profesional",
                    "100% Satisfecho con la experiencia"
                ]
            else:
                response_data["message"] = "Sentimos que no haya sido una experiencia de 5 estrellas. Queremos solucionarlo."

            self.send_json(response_data)
            return

        # -------------------------------------------------------------------
        # 7. PUBLIC FUNNEL: Feedback Step 2 (Private Negative Review)
        # -------------------------------------------------------------------
        if path.startswith('/api/funnel/') and path.endswith('/feedback'):
            parts = path.split('/')
            slug = parts[3]
            review_id = body.get('review_id')
            customer_name = (body.get('customer_name') or '').strip()
            customer_contact = (body.get('customer_contact') or '').strip()
            customer_email = (body.get('customer_email') or '').strip()
            category = (body.get('category') or 'General').strip()
            comment = (body.get('comment') or '').strip()

            if not comment:
                self.send_error_json("Por favor ingresa tu comentario para ayudarnos a mejorar.")
                return

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM businesses WHERE slug = ?", (slug,))
            business = cursor.fetchone()
            if not business:
                conn.close()
                self.send_error_json("Negocio no encontrado", 404)
                return

            if review_id:
                cursor.execute("""
                UPDATE reviews
                SET customer_name = ?, customer_contact = ?, customer_email = ?, category = ?, comment = ?
                WHERE id = ? AND business_id = ?
                """, (customer_name, customer_contact, customer_email, category, comment, review_id, business['id']))
            else:
                cursor.execute("""
                INSERT INTO reviews (business_id, rating, sentiment, category, customer_name, customer_contact, customer_email, comment, status)
                VALUES (?, 2, 'negative', ?, ?, ?, ?, ?, 'new')
                """, (business['id'], category, customer_name, customer_contact, customer_email, comment))
                review_id = cursor.lastrowid

            if business['notify_on_negative']:
                recipient = business['notification_email'] or business['email']
                subject = f"⚠️ ALERTA DE REPUTACIÓN: Nuevo feedback privado ({customer_name or 'Cliente'})"
                email_body = f"""Hola {business['name']},\n\nUn cliente ha dejado una opinión privada en tu embudo:\n- Cliente: {customer_name or 'Anónimo'}\n- Teléfono/WhatsApp: {customer_contact or 'No especificado'}\n- Email: {customer_email or 'No especificado'}\n- Motivo/Categoría: {category}\n- Comentario:\n"{comment}"\n\n🛡️ Esta opinión NO fue publicada en Google Reviews. Te sugerimos contactar al cliente de inmediato para convertir esta experiencia en una oportunidad de fidelización.\n\nAccede a tu panel para gestionar este caso:\nhttp://localhost:{PORT}/dashboard"""

                cursor.execute("""
                INSERT INTO email_logs (business_id, to_email, subject, body, customer_name, rating, log_type)
                VALUES (?, ?, ?, ?, ?, 2, 'feedback_alert')
                """, (business['id'], recipient, subject, email_body, customer_name))
                print(f"[EMAIL DISPATCHED] To: {recipient} | Subject: {subject}")

            conn.commit()
            conn.close()

            self.send_json({
                "success": True,
                "message": "Tu mensaje ha sido entregado en privado a la gerencia del negocio. ¡Muchas gracias por tu tiempo y sinceridad!"
            })
            return

        self.send_error(404, "Endpoint not found")

    # -----------------------------------------------------------------------
    # PUT Requests
    # -----------------------------------------------------------------------
    def do_PUT(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self.read_json_body()
        if body is None:
            self.send_error_json("JSON inválido", 400)
            return

        if path == '/api/business/profile':
            business = self.get_auth_business()
            if not business:
                self.send_error_json("No autenticado", 401)
                return
            if business.get('_is_suspended'):
                self.send_error_json("Cuenta suspendida", 403)
                return

            name = (body.get('name') or business['name']).strip()
            google_review_url = (body.get('google_review_url') or '').strip()
            logo_url = (body.get('logo_url') or '').strip()
            primary_color = (body.get('primary_color') or '#4F46E5').strip()
            accent_color = (body.get('accent_color') or '#EC4899').strip()
            welcome_title = (body.get('welcome_title') or '').strip()
            welcome_subtitle = (body.get('welcome_subtitle') or '').strip()
            notification_email = (body.get('notification_email') or business['email']).strip()
            phone = (body.get('phone') or business.get('phone', '')).strip()
            notify_on_negative = 1 if body.get('notify_on_negative', True) else 0

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE businesses SET
                name = ?, google_review_url = ?, logo_url = ?,
                primary_color = ?, accent_color = ?,
                welcome_title = ?, welcome_subtitle = ?,
                notification_email = ?, phone = ?, notify_on_negative = ?
            WHERE id = ?
            """, (name, google_review_url, logo_url, primary_color, accent_color,
                  welcome_title, welcome_subtitle, notification_email, phone, notify_on_negative,
                  business['id']))
            conn.commit()
            conn.close()

            self.send_json({"success": True, "message": "Configuración de marca actualizada exitosamente."})
            return

        self.send_error(404, "Endpoint not found")

    # -----------------------------------------------------------------------
    # PATCH Requests
    # -----------------------------------------------------------------------
    def do_PATCH(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self.read_json_body()

        if path.startswith('/api/business/reviews/'):
            business = self.get_auth_business()
            if not business:
                self.send_error_json("No autenticado", 401)
                return
            if business.get('_is_suspended'):
                self.send_error_json("Cuenta suspendida", 403)
                return

            try:
                review_id = int(path.split('/')[-1])
            except ValueError:
                self.send_error_json("ID de reseña inválido", 400)
                return

            status = body.get('status')
            internal_notes = body.get('internal_notes')

            conn = get_db()
            cursor = conn.cursor()

            updates = []
            params = []
            if status in ('new', 'contacted', 'resolved', 'archived'):
                updates.append("status = ?")
                params.append(status)
            if internal_notes is not None:
                updates.append("internal_notes = ?")
                params.append(internal_notes)

            if not updates:
                conn.close()
                self.send_error_json("Nada que actualizar", 400)
                return

            params.extend([review_id, business['id']])
            cursor.execute(f"UPDATE reviews SET {', '.join(updates)} WHERE id = ? AND business_id = ?", tuple(params))
            conn.commit()
            conn.close()

            self.send_json({"success": True, "message": "Opinión actualizada correctamente."})
            return

        self.send_error(404, "Endpoint not found")

    # -----------------------------------------------------------------------
    # DELETE Requests
    # -----------------------------------------------------------------------
    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith('/api/admin/businesses/'):
            admin = self.get_auth_superadmin()
            if not admin:
                self.send_error_json("No autorizado", 403)
                return

            try:
                b_id = int(path.split('/')[-1])
            except ValueError:
                self.send_error_json("ID inválido", 400)
                return

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM businesses WHERE id = ?", (b_id,))
            cursor.execute("DELETE FROM sessions WHERE user_id = ? AND role = 'business'", (b_id,))
            conn.commit()
            conn.close()

            self.send_json({"success": True, "message": "Negocio eliminado del sistema."})
            return

        self.send_error(404, "Endpoint not found")

def run(port=PORT):
    init_db()
    server_address = ('', port)
    httpd = HTTPServer(server_address, RequestHandler)
    print(f"Opinio Server running on port {port} (http://localhost:{port})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[Server shutting down]")
        httpd.server_close()

if __name__ == '__main__':
    run(PORT)
