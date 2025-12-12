# TPP(Tank Path Planning)
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/get_adcs', methods=['POST'])
def get_adcs():
    request_data = request.get_json()
    print("request_data:", request_data)

    # Sample response data
    sample_response_data = {
        "WS_command": "W", # 전차 전진 / 후진 방향 제어
        "WS_weight": 0.4, # 전차 전진 / 후진 세기
        "AD_command": "D", # 전차 좌 / 우 회전 방향 제어
        "AD_weight": 0.1, # 전차 좌 / 우 회전 방향 세기
        "Head_waypoint": [15.0, 25.0, 0.0] # 현재 향하고 있는 waypoint
    }

    return jsonify(sample_response_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)