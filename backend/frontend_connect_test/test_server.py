"""
Frontend 연결 테스트용 Mock WebSocket 서버

사용법:
    python test_server.py

주의:
    - Frontend 테스트 전용
    - 실제 배포 시 이 폴더 전체 삭제
    - Mock 데이터 생성 부분만 실제 로직으로 교체
"""

from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import time
import threading
from mock import generate_mock_detection, generate_mock_position, generate_mock_fire

# Flask 앱 생성
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# 전송 상태 플래그
sending_detection = False
sending_position = False

# ============================================
# HTTP 엔드포인트
# ============================================


@app.route('/api/target', methods=['POST'])
def receive_target():
    """
    목표 위치 수신
    Frontend에서 목표 설정 시 호출
    """
    data = request.get_json()
    print(f"[Mock] 목표 위치 전체 데이터: {data}")
    return jsonify({"status": "success", "received": data})

@app.route('/health', methods=['GET'])
def health_check():
    """서버 상태 확인"""
    return jsonify({"status": "ok", "message": "Mock server running"})

# ============================================
# WebSocket - Detection
# ============================================

@socketio.on('connect')
def handle_connect():
    """클라이언트 연결"""
    print('[Mock] Frontend 연결됨')
    emit('connected', {'message': 'Connected to mock backend'})
    
    # 자동으로 Detection 전송 시작
    global sending_detection, sending_position
    sending_detection = True
    sending_position = True
    print('[Mock] Detection 자동 전송 시작')
    print('[Mock] Position 자동 전송 시작')
    threading.Thread(target=send_detection_loop, daemon=True).start()
    threading.Thread(target=send_position_loop, daemon=True).start()

@socketio.on('disconnect')
def handle_disconnect():
    """클라이언트 연결 해제"""
    global sending_detection, sending_position
    sending_detection = False
    sending_position = False
    print('[Mock] Frontend 연결 해제')

@socketio.on('start_detection')
def handle_start_detection():
    """Detection 데이터 전송 시작"""
    global sending_detection
    sending_detection = True
    print('[Mock] Detection 전송 시작')
    threading.Thread(target=send_detection_loop, daemon=True).start()

@socketio.on('stop_detection')
def handle_stop_detection():
    """Detection 데이터 전송 중지"""
    global sending_detection
    sending_detection = False
    print('[Mock] Detection 전송 중지')

def send_detection_loop():
    """Detection Mock 데이터 주기적 전송"""
    global sending_detection
    while sending_detection:
        # TODO: 실제 개발 시 아래 Mock 부분을 실제 로직으로 교체
        data = generate_mock_detection()  # <- Mock (삭제 예정)
        # data = get_real_detection()     # <- 실제 로직 (추가 예정)
        
        socketio.emit('detection', data)
        print(f"[Mock] Detection 전송: {len(data['objects'])}개 객체")
        time.sleep(0.5)  # 0.5초마다

# ============================================
# WebSocket - Position
# ============================================

@socketio.on('start_position')
def handle_start_position():
    """Position 데이터 전송 시작"""
    global sending_position
    sending_position = True
    print('[Mock] Position 전송 시작')
    threading.Thread(target=send_position_loop, daemon=True).start()

@socketio.on('stop_position')
def handle_stop_position():
    """Position 데이터 전송 중지"""
    global sending_position
    sending_position = False
    print('[Mock] Position 전송 중지')

def send_position_loop():
    """Position Mock 데이터 주기적 전송"""
    global sending_position
    while sending_position:
        # TODO: 실제 개발 시 아래 Mock 부분을 실제 로직으로 교체
        data = generate_mock_position()  # <- Mock (삭제 예정)
        # data = get_real_position()     # <- 실제 로직 (추가 예정)
        
        socketio.emit('position', data)
        time.sleep(0.1)  # 0.1초마다

# ============================================
# WebSocket - Fire
# ============================================

@socketio.on('fire')
def handle_fire(data):
    """발포 명령 수신"""
    target_id = data.get('target_tracking_id')
    print(f"[Mock] 발포 명령 수신: target_id={target_id}")
    
    # 발포 결과 생성
    result = generate_mock_fire(target_id)
    emit('fire_result', result)

# ============================================
# 서버 실행
# ============================================

if __name__ == '__main__':
    print('=' * 60)
    print('[Mock Server] Frontend 테스트 서버 시작')
    print('=' * 60)
    print('HTTP:      http://localhost:5000')
    print('WebSocket: ws://localhost:5000')
    print('')
    print('주의: 테스트 전용 서버입니다.')
    print('실제 배포 시 이 폴더 전체를 삭제하세요.')
    print('=' * 60)
    
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)