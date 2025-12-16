from flask import Flask, request, jsonify
import math

app = Flask(__name__)

# ============================================================
# [설정] 제어 파라미터 (PID_mid_light_complete.py의 단순 P 제어 기반)
# 시뮬레이터 좌표계 정의: X: 동서, Y: 고도, Z: 남북
# ============================================================
# Waypoint 관리: 이 거리(m) 이내에 웨이포인트에 도달하면 다음으로 넘어감
GOAL_THRESHOLD = 8.0 

# 차량 물리적 최대 속도 (WS_weight=1.0일 때 65.0 km/h)
MAX_PHYSICAL_SPEED_KMH = 65.0 

# 목표 속도 상한선 (40 km/h -> weight: 40/65 ≈ 0.615)
MAX_TARGET_SPEED_KMH = 40.0
MAX_FORWARD_WEIGHT = MAX_TARGET_SPEED_KMH / MAX_PHYSICAL_SPEED_KMH

# 직진시 최대 전진 가중치 (0.6 * (1 - 0) = 0.6)
MAX_STRAIGHT_WEIGHT = 0.6
if MAX_STRAIGHT_WEIGHT > MAX_FORWARD_WEIGHT:
    MAX_STRAIGHT_WEIGHT = MAX_FORWARD_WEIGHT 

# 조향(Steering) P Gain 기준 (60도 각도 차이일 때 AD_weight=1.0)
STEERING_ANGLE_DIVISOR = 60.0 
STEERING_DEADZONE = 10.0 # 10도 이내면 조향 입력 제거

# ============================================================
# [전역 상태] (위치 기반 속도 계산용)
# ============================================================
prev_time = None 
prev_x = None  
prev_z = None

# ============================================================
# 유틸리티 함수
# ============================================================
def normalize_waypoint(wp, default_y=0.0):
    """단일 웨이포인트 데이터를 딕셔너리 형태로 정규화"""
    # X와 Z를 수평 좌표로 사용하고, Y는 고도(altitude)로 사용합니다.
    if isinstance(wp, dict):
        return {"x": float(wp.get("x", 0.0)), "y": float(wp.get("y", default_y)), "z": float(wp.get("z", 0.0))}
    elif isinstance(wp, (list, tuple)) and len(wp) >= 3:
        return {"x": float(wp[0]), "y": float(wp[1]), "z": float(wp[2])}
    else:
        return {"x": 0.0, "y": default_y, "z": 0.0}

def normalize_waypoints_list(raw_list, default_y=0.0):
    """웨이포인트 리스트를 정규화"""
    if not isinstance(raw_list, list):
        return []
    return [normalize_waypoint(wp, default_y) for wp in raw_list]

def estimate_speed_from_position(time_now, x_now, z_now):
    """
    [수정] 신뢰도가 낮은 Player_Speed 대신, 위치 변화를 기반으로 속도를 계산합니다.
    (LPF 없이 순수하게 위치 변화량/시간을 사용합니다.)
    """
    global prev_time, prev_x, prev_z

    if prev_time is None:
        # 초기화 단계
        prev_time = time_now
        prev_x = x_now
        prev_z = z_now
        return 0.0, 0.0

    dt = time_now - prev_time
    
    # 시간이 역전되거나 너무 짧으면 현재 속도 유지 (0.0 반환)
    if dt <= 1e-6:
        return 0.0, 0.0

    # X-Z 평면에서의 이동 거리 계산
    dx = x_now - prev_x
    dz = z_now - prev_z
    distance = math.sqrt(dx*dx + dz*dz)

    raw_speed = distance / dt

    # 상태 업데이트
    prev_time = time_now
    prev_x = x_now
    prev_z = z_now

    return raw_speed, dt

# ============================================================
# (1) Path Tracking Logic (Simple P Steering + Coupled Speed)
# ============================================================
def get_adcs_commands(player_x, player_z, yaw, waypoints):
    """
    PID_mid_light_complete.py의 주행 로직을 기반으로 WS/AD 명령 및 웨이트 계산.
    """
    
    WS_command, WS_weight, AD_command, AD_weight = "", 0.0, "", 0.0
    head_wp = None

    # 1. Waypoint Pop 및 선택 (GOAL_THRESHOLD 기반)
    current_waypoints = waypoints[:]
    
    while current_waypoints:
        head_wp = current_waypoints[0]
        dx = head_wp["x"] - player_x # 동서 방향 차이
        dz = head_wp["z"] - player_z # 남북 방향 차이
        distance = math.sqrt(dx*dx + dz*dz) # 수평 거리 계산 (Y 무시)

        if distance <= GOAL_THRESHOLD:
            current_waypoints.pop(0)
            if not current_waypoints:
                head_wp = None
                break
            continue
        break
    
    if head_wp is None:
        WS_command, WS_weight = "STOP", 1.0
        return WS_command, WS_weight, AD_command, AD_weight, head_wp

    # 2. 조향 각도 계산
    dx = head_wp["x"] - player_x
    dz = head_wp["z"] - player_z
    
    # Z축(+)을 0도로 보는 좌표계에서 목표 각도 계산
    target_angle_rad = math.atan2(dx, dz)
    target_angle = math.degrees(target_angle_rad)
    
    # 0 ~ 360도 범위로 정규화
    target_angle = (target_angle + 360) % 360
    
    # 현재 차체 yaw와의 각도 오차 (-180 ~ 180)
    angle_diff = (target_angle - yaw + 540) % 360 - 180
    abs_angle_diff = abs(angle_diff)

    # 3. 조향 명령 (AD)
    if abs_angle_diff > STEERING_DEADZONE:
        turn_weight = min(abs_angle_diff / STEERING_ANGLE_DIVISOR, 1.0)
        if angle_diff > 0:
            AD_command, AD_weight = "D", turn_weight # D: 우회전 (시계 방향)
        else:
            AD_command, AD_weight = "A", turn_weight # A: 좌회전 (반시계 방향)
    else:
        AD_command, AD_weight = "", 0.0

    # 4. 속도 명령 (WS) - 각도 차이 기반 속도 조절 (Speed-Steering Coupling)
    angle_norm = min(abs_angle_diff / 90.0, 1.0)  
    
    forward_weight = MAX_STRAIGHT_WEIGHT * (1.0 - angle_norm) 
    forward_weight = min(forward_weight, MAX_FORWARD_WEIGHT)

    if forward_weight > 0.05:
        WS_command, WS_weight = "W", forward_weight
    else:
        WS_command, WS_weight = "", 0.0
        
    return WS_command, WS_weight, AD_command, AD_weight, head_wp

# ============================================================
# 메인 로직
# ============================================================
app = Flask(__name__)

# IBSM이 주행 명령을 요청하는 주 엔드포인트
@app.route('/get_adcs', methods=['POST'])
def get_adcs():
    try:
        data = request.get_json(force=True)
        
        print('@@@@@@@@@@@@@@@@@@@@@@IBSM이 준 데이터\n', data)

        ally_pos = data.get("ally_body_pos", {})
        ally_angle = data.get("ally_body_angle", {})
        waypoints_raw = data.get("waypoints", [])
        time_now = float(data.get("time", 0.0)) # 시간 정보 수신

        # 현재 차량 위치 및 방향 (Yaw) - X: 동서, Y: 고도, Z: 남북
        px = float(ally_pos.get("x", 0.0))
        py = float(ally_pos.get("y", 0.0))
        pz = float(ally_pos.get("z", 0.0))
        yaw = float(ally_angle.get("x", 0.0)) # Yaw는 'x' 키로 들어옴

        # 1. 위치 기반 속도 계산 (신뢰도 높은 자체 계산)
        speed_mps, dt = estimate_speed_from_position(time_now, px, pz)

        waypoints = normalize_waypoints_list(waypoints_raw, default_y=py)
        
        # 2. 주행 명령 계산
        WS_cmd, WS_weight, AD_cmd, AD_weight, head_wp = get_adcs_commands(
            px, pz, yaw, waypoints
        )

        if head_wp is None:
            stop_response = {"WS_command": "STOP", "WS_weight": 1.0, "AD_command": "", "AD_weight": 0.0}
            return jsonify(stop_response)

        response = {
            "WS_command": WS_cmd,
            "WS_weight": WS_weight,
            "AD_command": AD_cmd,
            "AD_weight": AD_weight,
            "head_waypoint": {
                "x": head_wp["x"],
                "y": head_wp.get("y", py),
                "z": head_wp["z"],
            },
            # 디버깅 용으로 IBSM에 자체 계산 속도 반환 (선택적)
            "calculated_speed_mps": speed_mps 
        }
        
        print('@@@@@ IBSM에 주는 데이터')
        return jsonify(response)

    except Exception as e:
        print(f"Error in ADCS: {e}")
        return jsonify({"WS_command": "W", "WS_weight": 0.0, "AD_command": "", "AD_weight": 0.0})

if __name__ == '__main__':
    print("🚀 ADCS 서버 시작. 포트 5000에서 요청을 기다립니다.")
    app.run(host="0.0.0.0", port=5000)