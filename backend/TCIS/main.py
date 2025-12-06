"""
TCIS Server - Frontend 통신 전용
IBSM으로부터 Push 받아서 Frontend로 WebSocket 전송
"""

from flask import Flask, request, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ============================================
# IBSM으로부터 데이터 수신
# ============================================

@app.route('/internal/detection', methods=['POST'])
def receive_detection():
    """
    IBSM이 탐지 객체 배열 전송 시
    
    IBSM에서 보내야 하는 형식 (배열):
    [
        {"tracking_id": 1001, "class_id": 1, "x": 100.5, "z": 200.3, "alive": true},
        {"tracking_id": 1002, "class_id": 2, "x": 150.0, "z": 250.0, "alive": true},
        ...
    ]
    
    Frontend로 전송되는 형식:
    {
        "type": "detection_update",
        "objects": [{ tracking_id, class_id, x, z, alive }, ...]
    }
    """
    objects = request.get_json()
    
    # 배열인지 검증
    if not isinstance(objects, list):
        print(f"[Detection] 배열이 아닌 데이터 형식: {type(objects)}")
        return '', 400
    
    # Frontend로 즉시 전송
    socketio.emit('detection', {
        "type": "detection_update",
        "objects": objects
    })
    
    print(f"[Detection] {len(objects)}개 객체 → Frontend 전송")
    
    return '', 204  # No Content (빠른 응답)


@app.route('/internal/position', methods=['POST'])
def receive_position():
    """
    IBSM이 내 탱크 위치 데이터 전송 시
    
    IBSM에서 보내야 하는 형식:
    {
        "tanks": [
            {
                "tank_id": "17TK-101",
                "x": -50.0,
                "y": -100.0
            }
        ]
    }
    
    Frontend로 전송되는 형식:
    {
        "type": "position_update",
        "tanks": [{ tank_id, x, y }, ...]
    }
    """
    data = request.get_json()
    
    socketio.emit('position', {
        "type": "position_update",
        "tanks": data.get('tanks', [])
    })
    
    print(f"[Position] {len(data.get('tanks', []))}개 탱크 위치 수신")
    
    return '', 204


@app.route('/internal/fire', methods=['POST'])
def receive_fire():
    """
    IBSM이 발포 이벤트 전송 시
    
    IBSM에서 보내야 하는 형식 (발사):
    {
        "type": "fire_event",
        "fire": {
            "target_tracking_id": 1001,
            "ally_id": "17TK-101",
            "class_id": 5
        }
    }
    
    IBSM에서 보내야 하는 형식 (명중 결과):
    {
        "type": "hit_result",
        "data": {
            "target_tracking_id": 1001,
            "result": "hit"  # 'hit' | 'miss'
        }
    }
    
    Frontend로 전송되는 형식:
    - 발사: { "type": "fire_event", "fire": { ... } }
    - 명중: { "type": "hit_result", "data": { ... } }
    """
    data = request.get_json()
    
    # IBSM이 보낸 데이터를 그대로 Frontend로 전달
    socketio.emit('fire', data)
    
    if data.get('type') == 'fire_event':
        print(f"🔥 [Fire] 발포 이벤트 수신: ally_id={data.get('fire', {}).get('ally_id')}, target={data.get('fire', {}).get('target_tracking_id')}")
    elif data.get('type') == 'hit_result':
        print(f"🎯 [Fire] 명중 결과 수신: target={data.get('data', {}).get('target_tracking_id')}, result={data.get('data', {}).get('result')}")
    
    return '', 204


@app.route('/internal/mission', methods=['POST'])
def receive_mission():
    """
    IBSM이 미션 데이터 전송 시
    
    IBSM에서 보내야 하는 형식:
    {
        "mission": "attack"  # 'attack' | 'search' | 'defence'
    }
    
    Frontend로 전송되는 형식:
    {
        "type": "mission_update",
        "mission": "attack"  # 'attack' | 'search' | 'defence'
    }
    """
    data = request.get_json()
    
    socketio.emit('mission', {
        "type": "mission_update",
        "mission": data.get('mission', 'defence')
    })
    
    print(f"[Mission] 미션 수신: {data.get('mission')}")
    
    return '', 204


# ============================================
# WebSocket 이벤트
# ============================================

connected_clients = set()

@socketio.on('connect')
def handle_connect():
    connected_clients.add(request.sid)
    print(f"\n{'='*60}")
    print(f"Frontend 연결됨: {request.sid}")
    print(f"현재 연결된 클라이언트 수: {len(connected_clients)}")
    print(f"{'='*60}\n")


@socketio.on('disconnect')
def handle_disconnect():
    connected_clients.discard(request.sid)
    print(f"\n{'='*60}")
    print(f"Frontend 연결 해제: {request.sid}")
    print(f"현재 연결된 클라이언트 수: {len(connected_clients)}")
    print(f"{'='*60}\n")


# ============================================
# Frontend → IBSM (역방향 통신)
# ============================================

@app.route('/api/target', methods=['POST'])
def set_target():
    """
    Frontend에서 목표 위치 받아서 IBSM로 전달
    
    Frontend가 보내는 형식:
    {
        "x": 100.5,
        "z": 200.3,
        "mission": "combat"  # 'defense' | 'combat'
    }
    
    IBSM으로 전달해야 하는 형식 (구현 해야함):
    POST http://127.0.0.1:5000/api/set-target
    { "x": 100.5, "z": 200.3, "mission": "combat" }
    """
    data = request.get_json()
    
    print(f"\n{'='*60}")
    print(f"[Target] Frontend에서 데이터 수신")
    print(f"   - X: {data.get('x')}")
    print(f"   - Z: {data.get('z')}")
    print(f"   - Mission: {data.get('mission')}")
    print(f"   - 전체 데이터: {data}")
    print(f"{'='*60}\n")
    
    # TODO: IBSM으로 전달 (IBSM에 /api/set-target 엔드포인트 필요)
    # import requests
    # try:
    #     requests.post('http://127.0.0.1:5000/api/set-target', json=data, timeout=0.5)
    # except:
    #     pass
    
    return jsonify({"status": "ok", "message": "목표 위치 수신 완료"})


@app.route('/health', methods=['GET'])
def health():
    """헬스체크"""
    return jsonify({"status": "ok", "service": "TCIS"})


# ============================================
# 서버 실행
# ============================================

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5001, debug=False)
