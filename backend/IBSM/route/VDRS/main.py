# VDRS(Visual Detection Raning System)
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/get_vdrs', methods=['POST'])
def get_vdrs():
    request_data = request.get_json()
    print("request_data:", request_data)

    # Sample response data
    sample_response_data = {
        "class": "TANK", # 객체 탐지 클래스
        "object_pos": [10.0, 20.0, 0.0], # 객체 X, Y, Z 좌표
        "object_angle_xy": [0.0, 90.0], # 객체 수평, 수직 각도
    }

    return jsonify(sample_response_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)