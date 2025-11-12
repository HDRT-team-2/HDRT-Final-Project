# FCS(Fire Control System)
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/get_fcs', methods=['POST'])
def get_fcs():
    request_data = request.get_json()
    print("request_data:", request_data)

    # Sample response data
    sample_response_data = {
        "QE_command": "E", # 포탑 좌 / 우 회전 방향 제어
        "QE_weight": 0.1, # 포탑 좌 / 우 회전 세기
        "RF_command": "F", # 포탑 상 / 하 회전 방향 제어
        "RF_weight": 0.1, # 포탑 상 / 하 회전 세기
        "fire_command": True, # 사격 여부
        "fire_target_pos": [15.0, 25.0, 0.0], # 사격 대상
        "new_fire_point_pos": [12.0, 22.0, 0.0] # 현 위치 즉시 사격 불가 시 사격 가능 지점
    }

    return jsonify(sample_response_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)