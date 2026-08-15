from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from database import Database
import secrets
from functools import wraps
import json

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
db = Database()

# Хранилище для WebRTC сигнализации (в реальном проекте использовать Redis)
webrtc_signals = {}


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Not logged in'}), 401
        return f(*args, **kwargs)

    return decorated_function


# ===== СТРАНИЦЫ =====
@app.route('/')
def index():
    return render_template('index.html')


# ===== АУТЕНТИФИКАЦИЯ =====
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    if not username or not email or not password:
        return jsonify({'error': 'Все поля обязательны'}), 400

    user_id = db.create_user(username, email, password)
    if user_id:
        session['user_id'] = user_id
        session['username'] = username
        return jsonify({'success': True, 'user_id': user_id, 'username': username})
    else:
        return jsonify({'error': 'Пользователь уже существует'}), 400


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username_or_email = data.get('username')
    password = data.get('password')

    user = db.authenticate_user(username_or_email, password)
    if user:
        session['user_id'] = user[0]
        session['username'] = user[1]
        db.update_user_status(user[0], 'online')
        return jsonify({'success': True, 'user_id': user[0], 'username': user[1]})
    else:
        return jsonify({'error': 'Неверные данные'}), 400


@app.route('/api/logout', methods=['POST'])
def logout():
    if 'user_id' in session:
        db.update_user_status(session['user_id'], 'offline')
        # Удаляем из голосовых каналов
        db.leave_voice_channel(session['user_id'])
        session.clear()
    return jsonify({'success': True})


@app.route('/api/me')
def get_me():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    user = db.get_user(session['user_id'])
    return jsonify(user)


# ===== ДРУЗЬЯ =====
@app.route('/api/friends/search')
@login_required
def search_users():
    query = request.args.get('q', '')
    if len(query) < 2:
        return jsonify([])
    results = db.search_users(query)
    results = [u for u in results if u['id'] != session['user_id']]
    return jsonify(results)


@app.route('/api/friends/request', methods=['POST'])
@login_required
def send_friend_request():
    data = request.get_json()
    friend_id = data.get('friend_id')
    if not friend_id:
        return jsonify({'error': 'ID не указан'}), 400
    result = db.send_friend_request(session['user_id'], friend_id)
    if result:
        return jsonify({'success': True})
    return jsonify({'error': 'Ошибка'}), 400


@app.route('/api/friends/accept', methods=['POST'])
@login_required
def accept_friend_request():
    data = request.get_json()
    friend_id = data.get('friend_id')
    if not friend_id:
        return jsonify({'error': 'ID не указан'}), 400
    result = db.accept_friend_request(session['user_id'], friend_id)
    if result:
        return jsonify({'success': True})
    return jsonify({'error': 'Ошибка'}), 400


@app.route('/api/friends')
@login_required
def get_friends():
    friends = db.get_friends(session['user_id'])
    return jsonify(friends)


@app.route('/api/friends/requests')
@login_required
def get_friend_requests():
    requests = db.get_friend_requests(session['user_id'])
    return jsonify(requests)


# ===== ГРУППЫ =====
@app.route('/api/groups')
@login_required
def get_groups():
    groups = db.get_user_groups(session['user_id'])
    return jsonify(groups)


@app.route('/api/groups/create', methods=['POST'])
@login_required
def create_group():
    data = request.get_json()
    name = data.get('name')
    if not name:
        return jsonify({'error': 'Название не указано'}), 400
    group_id = db.create_group(name, session['user_id'])
    return jsonify({'id': group_id, 'name': name})


@app.route('/api/groups/<int:group_id>/members')
@login_required
def get_group_members(group_id):
    members = db.get_group_members(group_id)
    return jsonify(members)


@app.route('/api/groups/<int:group_id>/messages')
@login_required
def get_group_messages(group_id):
    messages = db.get_group_messages(group_id)
    return jsonify(messages)


@app.route('/api/groups/<int:group_id>/send', methods=['POST'])
@login_required
def send_group_message(group_id):
    data = request.get_json()
    message = data.get('message')
    if not message:
        return jsonify({'error': 'Сообщение не указано'}), 400
    msg_id = db.save_group_message(group_id, session['user_id'], message)
    return jsonify({'id': msg_id, 'message': message})


@app.route('/api/groups/invite', methods=['POST'])
@login_required
def invite_to_group():
    data = request.get_json()
    group_id = data.get('group_id')
    user_id = data.get('user_id')
    if not group_id or not user_id:
        return jsonify({'error': 'Недостаточно данных'}), 400
    result = db.create_invite(group_id, user_id, session['user_id'])
    if result:
        return jsonify({'success': True})
    return jsonify({'error': 'Ошибка'}), 400


@app.route('/api/groups/invites')
@login_required
def get_invites():
    invites = db.get_invites(session['user_id'])
    return jsonify(invites)


@app.route('/api/groups/invites/<int:invite_id>/accept', methods=['POST'])
@login_required
def accept_invite(invite_id):
    result = db.accept_invite(invite_id, session['user_id'])
    if result:
        return jsonify({'success': True})
    return jsonify({'error': 'Ошибка'}), 400


# ===== ГОЛОСОВЫЕ КАНАЛЫ =====
@app.route('/api/voice/join', methods=['POST'])
@login_required
def join_voice():
    data = request.get_json()
    group_id = data.get('group_id')
    if not group_id:
        return jsonify({'error': 'ID группы не указан'}), 400

    result = db.join_voice_channel(session['user_id'], group_id)
    if result:
        return jsonify({'success': True})
    return jsonify({'error': 'Ошибка'}), 400


@app.route('/api/voice/leave', methods=['POST'])
@login_required
def leave_voice():
    result = db.leave_voice_channel(session['user_id'])
    if result:
        return jsonify({'success': True})
    return jsonify({'error': 'Ошибка'}), 400


@app.route('/api/voice/status')
@login_required
def voice_status():
    # Получаем всех в голосовых каналах
    voice_users = db.get_voice_users()

    # Получаем информацию о группах
    result = {}
    for v in voice_users:
        group_id = v['group_id']
        if group_id not in result:
            result[group_id] = []
        result[group_id].append({
            'user_id': v['user_id'],
            'username': v['username'],
            'status': v['status']
        })

    return jsonify(result)


# ===== WEBRTC СИГНАЛИЗАЦИЯ =====
@app.route('/api/webrtc/offer', methods=['POST'])
@login_required
def webrtc_offer():
    data = request.get_json()
    target_user_id = data.get('target_user_id')
    offer = data.get('offer')

    if not target_user_id or not offer:
        return jsonify({'error': 'Недостаточно данных'}), 400

    # Сохраняем оффер для целевого пользователя
    key = f"offer_{target_user_id}"
    webrtc_signals[key] = {
        'from': session['user_id'],
        'from_username': session['username'],
        'offer': offer,
        'timestamp': secrets.token_hex(8)
    }

    return jsonify({'success': True})


@app.route('/api/webrtc/answer', methods=['POST'])
@login_required
def webrtc_answer():
    data = request.get_json()
    target_user_id = data.get('target_user_id')
    answer = data.get('answer')

    if not target_user_id or not answer:
        return jsonify({'error': 'Недостаточно данных'}), 400

    key = f"answer_{target_user_id}"
    webrtc_signals[key] = {
        'from': session['user_id'],
        'answer': answer,
        'timestamp': secrets.token_hex(8)
    }

    return jsonify({'success': True})


@app.route('/api/webrtc/poll')
@login_required
def webrtc_poll():
    user_id = session['user_id']
    result = {}

    # Проверяем офферы для этого пользователя
    offer_key = f"offer_{user_id}"
    if offer_key in webrtc_signals:
        result['offer'] = webrtc_signals[offer_key]
        del webrtc_signals[offer_key]

    # Проверяем ответы для этого пользователя
    answer_key = f"answer_{user_id}"
    if answer_key in webrtc_signals:
        result['answer'] = webrtc_signals[answer_key]
        del webrtc_signals[answer_key]

    # Проверяем ICE кандидаты
    ice_key = f"ice_{user_id}"
    if ice_key in webrtc_signals:
        result['ice'] = webrtc_signals[ice_key]
        del webrtc_signals[ice_key]

    return jsonify(result)


@app.route('/api/webrtc/ice', methods=['POST'])
@login_required
def webrtc_ice():
    data = request.get_json()
    target_user_id = data.get('target_user_id')
    candidate = data.get('candidate')

    if not target_user_id or not candidate:
        return jsonify({'error': 'Недостаточно данных'}), 400

    key = f"ice_{target_user_id}"
    if key not in webrtc_signals:
        webrtc_signals[key] = []
    webrtc_signals[key].append({
        'from': session['user_id'],
        'candidate': candidate,
        'timestamp': secrets.token_hex(8)
    })

    return jsonify({'success': True})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)