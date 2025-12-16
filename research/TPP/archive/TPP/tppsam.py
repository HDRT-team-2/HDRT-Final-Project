# TPP(Tank Path Planning)
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/get_tpp', methods=['POST'])
def get_tpp():
    request_data = request.get_json()
    print("request_data:", request_data)

    # Sample response data (dict 형태로 수정)
    sample_response_data = {
        "waypoints": [
            {"x": 0.0,  "y": 0.0,  "z": 0.0},
            {"x": 5.0,  "y": 10.0, "z": 0.0},
            {"x": 10.0, "y": 20.0, "z": 0.0}
        ],
        "target_pos": {"x": 10.0, "y": 20.0, "z": 0.0}
    }

    return jsonify(sample_response_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
