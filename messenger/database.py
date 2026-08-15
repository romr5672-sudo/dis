import sqlite3
import hashlib
import datetime


class Database:
    def __init__(self, db_name='messenger.db'):
        self.db_name = db_name
        self.init_db()

    def init_db(self):
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            c.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    status TEXT DEFAULT 'online',
                    last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            c.execute('''
                CREATE TABLE IF NOT EXISTS friends (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    friend_id INTEGER,
                    status TEXT DEFAULT 'pending',
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (friend_id) REFERENCES users (id),
                    UNIQUE(user_id, friend_id)
                )
            ''')
            c.execute('''
                CREATE TABLE IF NOT EXISTS groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    owner_id INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (owner_id) REFERENCES users (id)
                )
            ''')
            c.execute('''
                CREATE TABLE IF NOT EXISTS group_members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER,
                    user_id INTEGER,
                    role TEXT DEFAULT 'member',
                    FOREIGN KEY (group_id) REFERENCES groups (id),
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    UNIQUE(group_id, user_id)
                )
            ''')
            c.execute('''
                CREATE TABLE IF NOT EXISTS group_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER,
                    user_id INTEGER,
                    message TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (group_id) REFERENCES groups (id),
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            c.execute('''
                CREATE TABLE IF NOT EXISTS group_invites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER,
                    invited_user_id INTEGER,
                    inviter_id INTEGER,
                    status TEXT DEFAULT 'pending',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    expires_at DATETIME,
                    FOREIGN KEY (group_id) REFERENCES groups (id),
                    FOREIGN KEY (invited_user_id) REFERENCES users (id),
                    FOREIGN KEY (inviter_id) REFERENCES users (id)
                )
            ''')
            # Таблица для голосовых каналов
            c.execute('''
                CREATE TABLE IF NOT EXISTS voice_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE,
                    group_id INTEGER,
                    joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (group_id) REFERENCES groups (id)
                )
            ''')
            conn.commit()

    def create_user(self, username, email, password):
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        try:
            with sqlite3.connect(self.db_name) as conn:
                c = conn.cursor()
                c.execute('INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
                          (username, email, password_hash))
                conn.commit()
                return c.lastrowid
        except sqlite3.IntegrityError:
            return None

    def authenticate_user(self, username_or_email, password):
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            c.execute('SELECT id, username FROM users WHERE (username = ? OR email = ?) AND password_hash = ?',
                      (username_or_email, username_or_email, password_hash))
            return c.fetchone()

    def get_user(self, user_id):
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            c.execute('SELECT id, username, email, status, last_seen FROM users WHERE id = ?', (user_id,))
            r = c.fetchone()
            if r:
                return {'id': r[0], 'username': r[1], 'email': r[2], 'status': r[3], 'last_seen': r[4]}
            return None

    def update_user_status(self, user_id, status):
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            c.execute('UPDATE users SET status = ?, last_seen = CURRENT_TIMESTAMP WHERE id = ?', (status, user_id))
            conn.commit()

    def search_users(self, query):
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            c.execute('SELECT id, username, status FROM users WHERE username LIKE ? LIMIT 10', (f'%{query}%',))
            return [{'id': r[0], 'username': r[1], 'status': r[2]} for r in c.fetchall()]

    def send_friend_request(self, user_id, friend_id):
        try:
            with sqlite3.connect(self.db_name) as conn:
                c = conn.cursor()
                c.execute('INSERT INTO friends (user_id, friend_id) VALUES (?, ?)', (user_id, friend_id))
                conn.commit()
                return True
        except:
            return False

    def accept_friend_request(self, user_id, friend_id):
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            c.execute('UPDATE friends SET status = ? WHERE user_id = ? AND friend_id = ? AND status = ?',
                      ('accepted', friend_id, user_id, 'pending'))
            conn.commit()
            return c.rowcount > 0

    def get_friends(self, user_id, status='accepted'):
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT u.id, u.username, u.status
                FROM friends f
                JOIN users u ON u.id = CASE WHEN f.user_id = ? THEN f.friend_id ELSE f.user_id END
                WHERE (f.user_id = ? OR f.friend_id = ?) AND f.status = ?
            ''', (user_id, user_id, user_id, status))
            return [{'id': r[0], 'username': r[1], 'status': r[2]} for r in c.fetchall()]

    def get_friend_requests(self, user_id):
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT u.id, u.username
                FROM friends f
                JOIN users u ON u.id = f.user_id
                WHERE f.friend_id = ? AND f.status = 'pending'
            ''', (user_id,))
            return [{'id': r[0], 'username': r[1]} for r in c.fetchall()]

    def create_group(self, name, owner_id):
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            c.execute('INSERT INTO groups (name, owner_id) VALUES (?, ?)', (name, owner_id))
            group_id = c.lastrowid
            c.execute('INSERT INTO group_members (group_id, user_id, role) VALUES (?, ?, ?)',
                      (group_id, owner_id, 'admin'))
            conn.commit()
            return group_id

    def get_user_groups(self, user_id):
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT g.id, g.name, gm.role
                FROM groups g
                JOIN group_members gm ON gm.group_id = g.id
                WHERE gm.user_id = ?
            ''', (user_id,))
            return [{'id': r[0], 'name': r[1], 'role': r[2]} for r in c.fetchall()]

    def get_group_members(self, group_id):
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT u.id, u.username, u.status, gm.role
                FROM group_members gm
                JOIN users u ON u.id = gm.user_id
                WHERE gm.group_id = ?
            ''', (group_id,))
            return [{'id': r[0], 'username': r[1], 'status': r[2], 'role': r[3]} for r in c.fetchall()]

    def save_group_message(self, group_id, user_id, message):
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            c.execute('INSERT INTO group_messages (group_id, user_id, message) VALUES (?, ?, ?)',
                      (group_id, user_id, message))
            conn.commit()
            return c.lastrowid

    def get_group_messages(self, group_id, limit=50):
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT gm.id, gm.message, gm.created_at, u.id, u.username
                FROM group_messages gm
                JOIN users u ON u.id = gm.user_id
                WHERE gm.group_id = ?
                ORDER BY gm.created_at DESC LIMIT ?
            ''', (group_id, limit))
            results = c.fetchall()
            return [{'id': r[0], 'message': r[1], 'timestamp': r[2], 'user_id': r[3], 'username': r[4]}
                    for r in reversed(results)]

    def create_invite(self, group_id, invited_user_id, inviter_id):
        expires_at = datetime.datetime.now() + datetime.timedelta(days=7)
        try:
            with sqlite3.connect(self.db_name) as conn:
                c = conn.cursor()
                c.execute('''
                    INSERT INTO group_invites (group_id, invited_user_id, inviter_id, expires_at)
                    VALUES (?, ?, ?, ?)
                ''', (group_id, invited_user_id, inviter_id, expires_at))
                conn.commit()
                return True
        except:
            return False

    def get_invites(self, user_id):
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT gi.id, gi.group_id, g.name, u.username
                FROM group_invites gi
                JOIN groups g ON g.id = gi.group_id
                JOIN users u ON u.id = gi.inviter_id
                WHERE gi.invited_user_id = ? AND gi.status = 'pending'
            ''', (user_id,))
            return [{'id': r[0], 'group_id': r[1], 'group_name': r[2], 'inviter': r[3]} for r in c.fetchall()]

    def accept_invite(self, invite_id, user_id):
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            c.execute('SELECT group_id, invited_user_id FROM group_invites WHERE id = ?', (invite_id,))
            invite = c.fetchone()
            if not invite or invite[1] != user_id:
                return False
            try:
                c.execute('INSERT INTO group_members (group_id, user_id) VALUES (?, ?)', (invite[0], user_id))
                c.execute('UPDATE group_invites SET status = ? WHERE id = ?', ('accepted', invite_id))
                conn.commit()
                return True
            except:
                return False

    # ===== ГОЛОСОВЫЕ КАНАЛЫ =====
    def join_voice_channel(self, user_id, group_id):
        try:
            with sqlite3.connect(self.db_name) as conn:
                c = conn.cursor()
                # Удаляем из предыдущего канала
                c.execute('DELETE FROM voice_channels WHERE user_id = ?', (user_id,))
                c.execute('INSERT INTO voice_channels (user_id, group_id) VALUES (?, ?)', (user_id, group_id))
                conn.commit()
                return True
        except:
            return False

    def leave_voice_channel(self, user_id):
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            c.execute('DELETE FROM voice_channels WHERE user_id = ?', (user_id,))
            conn.commit()
            return c.rowcount > 0

    def get_voice_users(self):
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT vc.user_id, vc.group_id, u.username, u.status
                FROM voice_channels vc
                JOIN users u ON u.id = vc.user_id
            ''')
            return [{'user_id': r[0], 'group_id': r[1], 'username': r[2], 'status': r[3]} for r in c.fetchall()]

    def get_voice_users_in_group(self, group_id):
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT vc.user_id, u.username, u.status
                FROM voice_channels vc
                JOIN users u ON u.id = vc.user_id
                WHERE vc.group_id = ?
            ''', (group_id,))
            return [{'user_id': r[0], 'username': r[1], 'status': r[2]} for r in c.fetchall()]