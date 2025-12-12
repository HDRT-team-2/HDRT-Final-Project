# TPP(Tank Path Planning)
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/get_adcs', methods=['POST'])
def get_adcs():
    request_data = request.get_json()
    
    # ✅ 전체 데이터 출력 금지! (키 값만 확인하거나, 이미지가 없는지 확인)
    # print("request_data:", request_data)  <-- 삭제 또는 주석 처리
    print("ADCS Called. Keys received:", list(request_data.keys())) # 안전하게 키만 출력

    # Sample response data
    sample_response_data = {
        "WS_command": "W", 
        "WS_weight": 1.0,
        "AD_command": "", 
        "AD_weight": 0.0, 
        "head_waypoint": [15.0, 25.0, 0.0] 
    }

    return jsonify(sample_response_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)