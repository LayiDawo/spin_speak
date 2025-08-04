import os, json, random
from flask import Flask, render_template, request, redirect, jsonify, session
from flask_socketio import SocketIO, join_room, leave_room, emit

connected_clients = 0


app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")  # enable CORS for dev

team_timers = {}  # e.g., {'Teaching Team': datetime object}
ROUND_DURATION = 60  # seconds

TEAM_FILE = 'data/teams.json'
QUESTION_FILE = 'data/questions.json'
STATE_FILE = 'data/game_state.json'

def load_json(path, default=None):
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return default
    return default


def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        team_name = request.form.get('team_name')
        team_role = request.form.get('team_role')  # e.g., Leader
        user_role = request.form.get('role')       # e.g., admin or participant
        question = request.form.get('question')

        # Validate required fields
        if not all([team_name, team_role, user_role, name]):
            return "Error: Missing team, team role, role, or name.", 400

    # Save session data
        session['name'] = name
        session['team'] = team_name
        session['team_role'] = team_role
        session['role'] = user_role

    # Load participants
        try:
            with open('data/participants.json', 'r') as f:
                participants = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            participants = []

        # Update or add participant
        found = False
        for participant in participants:
            # Match by team, team_role (to identify user uniquely)
            if participant['team'] == team_name and participant['role'] == team_role:
                participant['name'] = name
                participant['user_role'] = user_role  # store user role here
                found = True
                break

        if not found:
            participants.append({
                "team": team_name,
                "role": team_role,
                "name": name,
                "user_role": user_role
            })

        # Save updated participant list
        with open('data/participants.json', 'w') as f:
            json.dump(participants, f, indent=2)

        # Save question if provided
        if question:
            try:
                with open('data/questions.json', 'r') as f:
                    questions = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                questions = []

            questions.append({
                "team": team_name,
                "question": question
            })

            with open('data/questions.json', 'w') as f:
                json.dump(questions, f, indent=2)

        # Redirect appropriately
        if user_role == 'admin':
            return redirect('/admin')
        else:
            return redirect('/waiting-room')

    return render_template('register.html')


@app.route('/waiting-room')
def waiting_room():
    role = request.args.get("role", "student")  # ideally from session in a real app
    return render_template('waiting.html', role=role)


@app.route('/admin/start', methods=['POST'])
def admin_start():
    teams = load_json(TEAM_FILE)
    active_teams = [team['team_name'] for team in teams if 'feedback' not in team['team_name'].lower()]
    
    game_state = {
        'round': 1,
        'remaining_teams': active_teams,
        'spun_teams': [],
        'started': True
    }
    save_json(STATE_FILE, game_state)
    set_game_status(started=True, round_num=1)

    return jsonify({'success': True})

@app.route('/admin')
def admin_page():
    return render_template('admin.html')


@app.route('/spin')
def spin():
    role = session.get('role', 'guest')
    return render_template('spin.html', role=role)

@app.route('/get-role')
def get_role():
    # Get identifying info from session
    name = session.get('name')
    team_name = session.get('team')
    team_role = session.get('team_role')

    # If any identifying info missing, default role
    if not all([name, team_name, team_role]):
        return jsonify({'role': 'participant'})

    # Load participants.json
    participants = load_json('data/participants.json', [])

    # Find matching participant entry and return their stored user_role
    for p in participants:
        if (
            p.get('name') == name and
            p.get('team') == team_name and
            p.get('role') == team_role
        ):
            return jsonify({'role': p.get('user_role', 'participant')})

    # Fallback default role if not found
    return jsonify({'role': 'participant'})



@app.route('/api/spin', methods=['POST'])
def api_spin():
    state = load_json(STATE_FILE, {})
    teams = state.get('remaining_teams', [])

    if not teams:
        state['round'] += 1
        teams = load_json(TEAM_FILE)
        teams = [t['team_name'] for t in teams if 'feedback' not in t['team_name'].lower()]
        state['remaining_teams'] = teams
        state['spun_teams'] = []
        save_json(STATE_FILE, state)
        return jsonify({'round_reset': True, 'round': state['round']})

    selected = random.choice(teams)
    teams.remove(selected)
    state['spun_teams'].append(selected)
    state['remaining_teams'] = teams
    save_json(STATE_FILE, state)

    return jsonify({'team': selected, 'round_reset': False})

@app.route('/api/reset', methods=['POST'])
def api_reset():
    teams = load_json(TEAM_FILE)
    active_teams = [team['team_name'] for team in teams if 'feedback' not in team['team_name'].lower()]
    state = {
        'round': 1,
        'remaining_teams': active_teams,
        'spun_teams': [],
        'started': False
    }
    save_json(STATE_FILE, state)
    return jsonify({'status': 'reset'})

@app.route('/api/remove_team', methods=['POST'])
def api_remove_team():
    data = request.json
    team_to_remove = data.get('team')
    if not team_to_remove:
        return jsonify({"error": "Missing team"}), 400

    state = load_json(STATE_FILE, {})
    remaining = state.get('remaining_teams', [])
    spun = state.get('spun_teams', [])

    if team_to_remove in remaining:
        remaining.remove(team_to_remove)
    if team_to_remove in spun:
        spun.remove(team_to_remove)

    state['remaining_teams'] = remaining
    state['spun_teams'] = spun
    save_json(STATE_FILE, state)

    return jsonify({"status": "removed"})

@app.route('/team-question/<team_name>')
def team_question(team_name):
    from datetime import datetime

    if not get_team_timer(team_name):
        set_team_timer(team_name, datetime.utcnow())

    questions = load_json(QUESTION_FILE, [])
    question_obj = next((q for q in questions if q['team'] == team_name), None)
    if not question_obj:
        return f"No question found for {team_name}", 404

    words_pool = question_obj.get('question', '').split()

    participants = load_json('data/participants.json', [])
    team_members = [p['name'] for p in participants if p['team'] == team_name]

    return render_template('questions.html',
                           team=team_name,
                           question=question_obj['question'],
                           words_pool=words_pool,
                           members=team_members)


GAME_STATUS_FILE = 'data/game_status.json'

def get_game_status():
    if os.path.exists(GAME_STATUS_FILE):
        with open(GAME_STATUS_FILE, 'r') as f:
            return json.load(f)
    return {"started": False, "round": 1}

def set_game_status(started=False, round_num=1):
    with open(GAME_STATUS_FILE, 'w') as f:
        json.dump({"started": started, "round": round_num}, f)


@app.route('/game-status')
def game_status():
    status = {"started": False}
    if os.path.exists(GAME_STATUS_FILE):
        with open(GAME_STATUS_FILE, 'r') as f:
            data = json.load(f)
            # Your file might have a key like "started" or "game_started" - be consistent
            status["started"] = data.get("started", False)  # use your actual key
    return jsonify(status)

@app.route('/start-game', methods=['POST'])
def start_game():
    status = load_json('data/game_status.json', {})
    status['game_started'] = True
    save_json('data/game_status.json', status)
    return jsonify({'success': True})


@app.route('/get_teams')
def get_teams():
    teams = load_json(TEAM_FILE)
    return jsonify(teams)

GAME_STATE_FILE = 'data/game_state.json'
def get_game_state():
    if os.path.exists(GAME_STATE_FILE):
        with open(GAME_STATE_FILE, 'r') as f:
            return json.load(f)
    return {"started": False, "round": 1}

def set_game_state(state):
    with open(GAME_STATE_FILE, 'w') as f:
        json.dump(state, f)

team_word_orders = {}

@socketio.on('join_team')
def handle_join_team(data):
    team = data.get('team')
    if team:
        join_room(team)
        print(f"User joined team room: {team}")

        # Send current order to user who just joined
        order = team_word_orders.get(team)
        if order:
            emit('order_updated', {'team': team, 'order': order}, room=request.sid)

@socketio.on('update_order')
def handle_update_order(data):
    team = data.get('team')
    order = data.get('order')
    if team and order:
        # Save latest order
        team_word_orders[team] = order

        # Broadcast new order to all except sender
        emit('order_updated', {'team': team, 'order': order}, room=team, include_self=False)
        print(f"Broadcasted new order for team {team}: {order}")

@socketio.on('update_sentence')
def handle_update(data):
    team = data.get('team')
    words = data.get('words', [])
    emit('sync_sentence', {'team': team, 'words': words}, broadcast=True)

@socketio.on('reset_sentence')
def handle_reset(data):
    team = data.get('team')
    if team:
        socketio.emit('order_updated', {'team': team, 'order': []})

from datetime import datetime



@app.route('/api/time_left/<team_name>')
def get_time_left(team_name):
    from datetime import datetime

    start_str = get_team_timer(team_name)
    if start_str:
        start_time = datetime.fromisoformat(start_str)
    else:
        start_time = datetime.utcnow()
        set_team_timer(team_name, start_time)

    elapsed = (datetime.utcnow() - start_time).total_seconds()
    time_left = max(0, ROUND_DURATION - int(elapsed))
    return jsonify({'time_left': time_left})

TIMER_FILE = 'data/timers.json'

def get_team_timer(team_name):
    timers = load_json(TIMER_FILE, {})
    return timers.get(team_name)

def set_team_timer(team_name, start_time):
    timers = load_json(TIMER_FILE, {})
    timers[team_name] = start_time.isoformat()
    save_json(TIMER_FILE, timers)

@app.route('/api/reset_timer/<team_name>', methods=['POST'])
def reset_timer(team_name):
    set_team_timer(team_name, datetime.utcnow())
    return jsonify({'status': 'reset', 'team': team_name})

@socketio.on('connect')
def handle_connect():
    global connected_clients
    connected_clients += 1
    print(f'Client connected. Total: {connected_clients}')

@socketio.on('disconnect')
def handle_disconnect():
    global connected_clients
    connected_clients -= 1
    print(f'Client disconnected. Total: {connected_clients}')

    if connected_clients <= 0:
        # No users left - reset game
        reset_game_state()
        print("All clients disconnected. Game state reset.")

def reset_game_state():
    teams = load_json(TEAM_FILE)
    active_teams = [team['team_name'] for team in teams if 'feedback' not in team['team_name'].lower()]
    
    # Reset game_state.json
    state = {
        'round': 1,
        'remaining_teams': active_teams,
        'spun_teams': [],
        'started': False
    }
    save_json(STATE_FILE, state)

    # Reset game_status.json
    set_game_status(started=False, round_num=1)
    
    # Optionally reset other files like timers.json if needed

@socketio.on('start_spin')
def handle_start_spin():
    # Load game state
    state = load_json(STATE_FILE, {})
    teams = state.get('remaining_teams', [])

    if not teams:
        # Reset round logic as in your /api/spin endpoint
        state['round'] = state.get('round', 1) + 1
        all_teams = load_json(TEAM_FILE)
        active_teams = [t['team_name'] for t in all_teams if 'feedback' not in t['team_name'].lower()]
        state['remaining_teams'] = active_teams
        state['spun_teams'] = []
        save_json(STATE_FILE, state)
        emit('round_reset', {'round': state['round']}, broadcast=True)
        return

    selected = random.choice(teams)
    teams.remove(selected)
    spun_teams = state.get('spun_teams', [])
    spun_teams.append(selected)
    state['remaining_teams'] = teams
    state['spun_teams'] = spun_teams
    save_json(STATE_FILE, state)

    # Broadcast to all clients who was selected
    emit('spin_result', {'team': selected}, broadcast=True)

@app.route('/api/teams_left')
def teams_left():
    state = load_json(STATE_FILE, {})
    return jsonify(state.get("remaining_teams", []))


# Replace app.run() with socketio.run()
if __name__ == '__main__':
    socketio.run(app, debug=True)
