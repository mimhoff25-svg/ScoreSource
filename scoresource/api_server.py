from flask import Flask, request, jsonify

app = Flask(__name__)

# In-memory placeholder for the current game (replace with your actual logic)
current_game = {
    'game_id': None,
    'score': None
}

@app.route('/api/set_current_game', methods=['POST'])
def set_current_game():
    data = request.json
    current_game['game_id'] = data.get('game_id')
    current_game['score'] = data.get('score')
    return jsonify({'status': 'success', 'current_game': current_game})

@app.route('/api/get_current_game', methods=['GET'])
def get_current_game():
    return jsonify({'current_game': current_game})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
