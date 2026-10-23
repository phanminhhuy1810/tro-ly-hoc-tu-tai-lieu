"""Google Identity Services: verified ID tokens and a one-use, session-bound nonce.

Google's subject identifies the account, never an email supplied by the browser.
Existing password accounts require an explicit connection while signed in.
"""
import hashlib
import os
import secrets
import time
from datetime import datetime, timezone
from functools import partial

from fastapi import HTTPException, Request, Response
from google.auth.exceptions import GoogleAuthError, TransportError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from pydantic import Field

from .accounts import ANONYMOUS, EMAIL
from .models import Model


class GoogleCredential(Model):
    credential: str = Field(min_length=20, max_length=16384)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def register_google_accounts(app, database, session_owner, start_session, public):
    client_id = os.environ.get('STUDY_GOOGLE_CLIENT_ID', '').strip()

    def configured():
        if not client_id:
            raise HTTPException(503, 'Đăng nhập Google chưa được kết nối. Bạn vẫn có thể dùng email và mật khẩu.')

    @app.get('/api/account/google/config')
    def config():
        return {'enabled': bool(client_id), 'client_id': client_id or None}

    @app.post('/api/account/google/challenge')
    def challenge(request: Request):
        configured()
        nonce = secrets.token_urlsafe(32)
        now = int(time.time())
        session_hash = digest(request.cookies.get('study_session', ''))
        with database.connection(write=True) as db:
            if not session_owner(db, request):
                raise HTTPException(401, 'Mở lại trang đăng nhập rồi thử Google nhé.')
            db.execute('DELETE FROM google_login_challenges WHERE expires_at<=?', (now,))
            db.execute('DELETE FROM google_login_challenges WHERE session_hash=? AND nonce_hash NOT IN '
                       '(SELECT nonce_hash FROM google_login_challenges WHERE session_hash=? ORDER BY expires_at DESC LIMIT 4)',
                       (session_hash, session_hash))
            db.execute('INSERT INTO google_login_challenges VALUES (?,?,?)', (digest(nonce), session_hash, now + 600))
        return {'nonce': nonce}

    @app.post('/api/account/google')
    def google_login(body: GoogleCredential, request: Request, response: Response):
        configured()
        # Do not send a token for verification if this browser has no active session.
        with database.connection() as db:
            if not session_owner(db, request):
                raise HTTPException(401, 'Mở lại trang đăng nhập rồi thử Google nhé.')
        try:
            claims = id_token.verify_oauth2_token(body.credential, partial(GoogleRequest(), timeout=10), audience=client_id)
        except TransportError:
            raise HTTPException(503, 'Chưa kết nối được Google. Thử lại sau một chút nhé.') from None
        except (ValueError, GoogleAuthError):
            raise HTTPException(401, 'Google chưa xác nhận được lượt đăng nhập này. Hãy thử lại.') from None
        email = claims.get('email', '')
        subject = claims.get('sub', '')
        nonce = claims.get('nonce', '')
        if (claims.get('email_verified') is not True or not isinstance(email, str) or not EMAIL.fullmatch(email)
                or email.lower().endswith('@local.invalid') or not isinstance(subject, str) or not 1 <= len(subject) <= 255
                or not isinstance(nonce, str) or not 1 <= len(nonce) <= 200
                or claims.get('azp', client_id) != client_id):
            raise HTTPException(401, 'Tài khoản Google chưa có email được xác minh hoặc lượt đăng nhập không hợp lệ.')
        email = email.strip().lower()
        name = claims.get('name')
        name = name.strip()[:60] if isinstance(name, str) and name.strip() else email.split('@')[0][:60]
        session_hash = digest(request.cookies.get('study_session', ''))
        with database.connection(write=True) as db:
            owner = session_owner(db, request)
            pending = db.execute('SELECT 1 FROM google_login_challenges WHERE nonce_hash=? AND session_hash=? AND expires_at>?',
                                 (digest(nonce), session_hash, int(time.time()))).fetchone()
            if not owner or not pending:
                raise HTTPException(401, 'Lượt đăng nhập Google đã hết hạn hoặc đã dùng. Mở lại trang để thử tiếp.')
            current = db.execute('SELECT * FROM users WHERE id=?', (owner,)).fetchone()
            linked = db.execute('SELECT user_id FROM google_identities WHERE subject=?', (subject,)).fetchone()
            current_signed_in = current['password_hash'] != ANONYMOUS
            if current_signed_in:
                if current['email'] != email or (linked and linked['user_id'] != owner):
                    raise HTTPException(409, 'Hãy chọn Google có cùng email với tài khoản bạn đang kết nối.')
                previous = db.execute('SELECT subject FROM google_identities WHERE user_id=?', (owner,)).fetchone()
                if previous and previous['subject'] != subject:
                    raise HTTPException(409, 'Tài khoản này đã kết nối với một Google khác.')
            elif linked:
                owner = linked['user_id']
            else:
                if db.execute('SELECT 1 FROM users WHERE email=?', (email,)).fetchone():
                    raise HTTPException(409, 'Email này đã có tài khoản. Đăng nhập bằng mật khẩu, rồi kết nối Google ở trang tài khoản.')
                # Upgrade the anonymous learner, preserving their courses and progress.
                db.execute('UPDATE users SET email=?,display_name=?,password_hash=? WHERE id=?',
                           (email, name, 'google-only', owner))
            db.execute('INSERT OR IGNORE INTO google_identities VALUES (?,?,?)',
                       (subject, owner, datetime.now(timezone.utc).isoformat()))
            db.execute('DELETE FROM google_login_challenges WHERE nonce_hash=?', (digest(nonce),))
            # Rotate this session; a previous anonymous cookie cannot access the new account.
            db.execute('DELETE FROM auth_sessions WHERE token_hash=?', (session_hash,))
            start_session(db, owner, response, secure=request.url.scheme == 'https')
            return {**public(db.execute('SELECT * FROM users WHERE id=?', (owner,)).fetchone()), 'google_linked': True}
