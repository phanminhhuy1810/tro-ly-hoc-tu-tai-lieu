"""Email + password accounts on top of the anonymous local sessions.

Registering turns the browser's anonymous learner into an account, so every
course, card and result made so far stays; logging in elsewhere opens the same
learner. Passwords are stored as salted scrypt hashes, never in plain text.
"""
import hashlib
import hmac
import re
import secrets
import time
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, Request, Response
from pydantic import Field

from .models import Model

ANONYMOUS = 'anonymous-local'
SESSION_SECONDS = 30 * 86400
EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
# A few wrong passwords are normal; a burst against one email is slowed down.
MAX_FAILURES, FAILURE_WINDOW = 8, 15 * 60


class Register(Model):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=200)
    name: str = Field(default='', max_length=60)


class Login(Model):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f'scrypt$16384$8$1${salt.hex()}${digest.hex()}'


def check_password(password, stored):
    try:
        kind, n, r, p, salt, digest = stored.split('$')
    except ValueError:
        return False
    if kind != 'scrypt':
        return False
    candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
    return hmac.compare_digest(candidate.hex(), digest)


def register_accounts(app, database):
    failures = {}

    def stamp():
        return datetime.now(timezone.utc).isoformat()

    def session_owner(db, request):
        token = request.cookies.get('study_session', '')
        row = db.execute('SELECT user_id FROM auth_sessions WHERE token_hash=? AND expires_at>?',
                         (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone()
        return row['user_id'] if row else None

    def start_session(db, owner, response):
        token = secrets.token_urlsafe(32)
        db.execute('INSERT INTO auth_sessions VALUES (?,?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), owner, int(time.time()) + SESSION_SECONDS, stamp()))
        response.set_cookie('study_session', token, httponly=True, samesite='strict', max_age=SESSION_SECONDS)

    def email_of(value):
        email = value.strip().lower()
        if not EMAIL.match(email) or email.endswith('@local.invalid'):
            raise HTTPException(422, 'Email chưa đúng dạng, ví dụ ten@gmail.com.')
        return email

    def public(row):
        signed_in = row is not None and row['password_hash'] != ANONYMOUS
        return {'signed_in': signed_in, 'email': row['email'] if signed_in else None,
                'name': row['display_name'] if signed_in else None}

    @app.get('/api/account')
    def account(request: Request):
        with database.connection() as db:
            owner = session_owner(db, request)
            row = db.execute('SELECT * FROM users WHERE id=?', (owner,)).fetchone() if owner else None
        return public(row)

    @app.post('/api/account/register')
    def register(body: Register, request: Request, response: Response):
        email = email_of(body.email)
        name = body.name.strip() or email.split('@')[0]
        with database.connection(write=True) as db:
            if db.execute('SELECT 1 FROM users WHERE email=?', (email,)).fetchone():
                raise HTTPException(409, 'Email này đã có tài khoản. Hãy đăng nhập.')
            owner = session_owner(db, request)
            current = db.execute('SELECT * FROM users WHERE id=?', (owner,)).fetchone() if owner else None
            if current is not None and current['password_hash'] != ANONYMOUS:
                raise HTTPException(409, 'Bạn đang đăng nhập rồi. Đăng xuất trước khi tạo tài khoản khác.')
            if current is not None:
                # Keep everything this browser learned so far: the anonymous learner becomes the account.
                db.execute('UPDATE users SET email=?,display_name=?,password_hash=? WHERE id=?', (email, name, hash_password(body.password), owner))
            else:
                owner = uuid.uuid4().hex
                db.execute('INSERT INTO users VALUES (?,?,?,?,?)', (owner, email, name, hash_password(body.password), stamp()))
            start_session(db, owner, response)
            return public(db.execute('SELECT * FROM users WHERE id=?', (owner,)).fetchone())

    @app.post('/api/account/login')
    def login(body: Login, response: Response):
        email = body.email.strip().lower()
        now = time.monotonic()
        recent = [t for t in failures.get(email, []) if now - t < FAILURE_WINDOW]
        if len(recent) >= MAX_FAILURES:
            raise HTTPException(429, 'Sai mật khẩu nhiều lần. Đợi 15 phút rồi thử lại.')
        with database.connection(write=True) as db:
            row = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
            if row is None or row['password_hash'] == ANONYMOUS or not check_password(body.password, row['password_hash']):
                failures[email] = recent + [now]
                raise HTTPException(401, 'Email hoặc mật khẩu chưa đúng.')
            failures.pop(email, None)
            start_session(db, row['id'], response)
            return public(row)

    @app.post('/api/account/logout')
    def logout(request: Request, response: Response):
        token = request.cookies.get('study_session', '')
        with database.connection(write=True) as db:
            db.execute('DELETE FROM auth_sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),))
        response.delete_cookie('study_session')
        return {'signed_in': False}
