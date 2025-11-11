# TPP(Tank Path Planning)
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/get_tpp', methods=['POST'])
def get_tpp():
    request_data = request.get_json()
    print("request_data:", request_data)

    # Sample response data
    sample_response_data = {
        "waypoints_list": [ # 목표 이동 지점으로 가기 위한 경로 목록
            [0.0, 0.0, 0.0],
            [5.0, 10.0, 0.0],
            [10.0, 20.0, 0.0]
        ],
        "target_pos": [10.0, 20.0, 0.0], # 목적지 X, Y, Z 좌표
    }

    return jsonify(sample_response_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)