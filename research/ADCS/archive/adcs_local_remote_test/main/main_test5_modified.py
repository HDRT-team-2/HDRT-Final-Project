from flask import Flask, request, jsonify
import math

app = Flask(__name__)

# ============================================================
# 1. 제어 파라미터 (튜닝 가이드 포함)
# ============================================================
# [주행 - 가변 룩어헤드]
LOOKAHEAD_MIN = 5.0      
LOOKAHEAD_MAX = 15.0     
SPEED_FOR_MAX_L = 18.0          # 이 속도(m/s) 이상일 때 MAX 거리를 봅니다 (약 65km/h)
SPEED_LOOKAHEAD_DIST = 25.0     # 곡률 예측을 위해 미리 스캔하는 거리

# [도착 판정 & 정밀 제어]
GOAL_THRESHOLD = 7.0            # 일반 경유지: {GOAL_THRESHOLD}m 이내면 "도착 판정", 통과하고 다음 점으로
FINAL_GOAL_THRESHOLD = 3.0      # 최종 진입: 마지막 점 3m 이내면 '정밀 주차 모드' 발동
PARKING_THRESHOLD = 2           # 최종 도착: ( )m 이내에 들어와야만 '완전 정지(STOP)' 인정
LIMIT = 0.20                    # 도착 임박 감속력 비율

# [속도 제한]
MAX_SPEED_WEIGHT = 40.0 / 70.0   # 최대 속도 (1.0 = 풀악셀)
MIN_SPEED_WEIGHT = 8.0 / 70.0    # 최소 속도

# [조향 PD 게인]
KP_STEER = 0.05   # P항
KD_STEER = 0.005  # D항

# 제어 임계값
STRAIGHT_ANGLE_THRESHOLD = 2.0  # 이 각도(degree) 이내면 '직진'으로 간주하고 가속
APPROACH_DISTANCE = 25.0        # 목적지 {APPROACH_DISTANCE}m 남으면 '접근 모드' 발동

# ============================================================
# 2. 전역 변수 (상태 저장)
# ============================================================
prev_angle_error = 0.0   
prev_time = None         
prev_x = None            
prev_z = None            
prev_dt = 0.033          

# 현재 주행 중인 경로를 기억하기 위한 전역 변수 추가
current_active_waypoints = [] 


# ============================================================
# (0) 유틸리티: 데이터 포맷 정규화
# ============================================================
def normalize_waypoint(wp, default_y=0.0):
    if isinstance(wp, dict):
        return {"x": wp.get("x", 0.0), "y": wp.get("y", default_y), "z": wp.get("z", 0.0)}
    elif isinstance(wp, (list, tuple)) and len(wp) >= 3:
        return {"x": wp[0], "y": wp[1], "z": wp[2]}
    return {"x": 0.0, "y": default_y, "z": 0.0}

def normalize_waypoints_list(raw_list, default_y=0.0):
    if not isinstance(raw_list, list): return []
    return [normalize_waypoint(wp, default_y) for wp in raw_list]


# ============================================================
# (1) 웨이포인트 관리 로직
# ============================================================
def select_waypoint(player_x, player_z, waypoints):
    if not waypoints:
        return None, []

    current = waypoints[0]
    is_final_waypoint = (len(waypoints) == 1)

    dx = current["x"] - player_x
    dz = current["z"] - player_z
    dist = math.sqrt(dx*dx + dz*dz)

    # 마지막 점은 거리가 가까워져도 절대 삭제(pop)하지 않음
    if is_final_waypoint:
        return current, waypoints

    # 일반 경유지는 {GOAL_THRESHOLD}m 이내로 접근하면 '통과'로 간주하고 삭제
    if dist <= GOAL_THRESHOLD:
        waypoints.pop(0)
        if not waypoints:
            return None, []
        return waypoints[0], waypoints

    return current, waypoints


# ============================================================
# (2) 속도 및 DT 계산 (Low Pass Filter 적용)
# ============================================================
def estimate_speed_from_pos(time_now, x_now, z_now):
    global prev_time, prev_x, prev_z, prev_dt

    if prev_time is None:
        prev_time, prev_x, prev_z = time_now, x_now, z_now
        return 0.0, 0.033

    raw_dt = time_now - prev_time
    if raw_dt <= 1e-4: raw_dt = 0.033

    # [LPF]
    dt = 0.7 * raw_dt + 0.3 * prev_dt
    prev_dt = dt

    dx = x_now - prev_x
    dz = z_now - prev_z
    speed = math.sqrt(dx*dx + dz*dz) / dt

    prev_time, prev_x, prev_z = time_now, x_now, z_now
    return speed, dt 


# ============================================================
# (3) 룩어헤드 및 곡률 계산
# ============================================================
def compute_dynamic_lookahead(speed_mps):
    ratio = max(0.0, min(speed_mps / SPEED_FOR_MAX_L, 1.0))
    return LOOKAHEAD_MIN + (LOOKAHEAD_MAX - LOOKAHEAD_MIN) * ratio

def compute_lookahead_point(player_x, player_z, waypoints, speed_mps):
    if not waypoints: return None
    
    L = compute_dynamic_lookahead(speed_mps)
    remain = L
    prev_x, prev_z = player_x, player_z

    for wp in waypoints:
        wx, wz = wp["x"], wp["z"]
        seg_len = math.sqrt((wx - prev_x)**2 + (wz - prev_z)**2)
        if seg_len < 1e-6: continue
        
        if seg_len >= remain:
            t = remain / seg_len
            return {"x": prev_x + (wx-prev_x)*t, "z": prev_z + (wz-prev_z)*t}
        remain -= seg_len
        prev_x, prev_z = wx, wz

    return {"x": waypoints[-1]["x"], "z": waypoints[-1]["z"]}

def compute_curvature_factor(player_x, player_z, waypoints):
    if len(waypoints) < 2: return 0.0
    dx1, dz1 = waypoints[0]["x"] - player_x, waypoints[0]["z"] - player_z
    dx2, dz2 = waypoints[1]["x"] - waypoints[0]["x"], waypoints[1]["z"] - waypoints[0]["z"]
    ang1 = math.atan2(dz1, dx1)
    ang2 = math.atan2(dz2, dx2)
    diff = abs(ang1 - ang2)
    while diff > math.pi: diff -= 2*math.pi
    while diff < -math.pi: diff += 2*math.pi
    return abs(diff)


# ============================================================
# (4) 예측 속도 제어
# ============================================================
def calculate_predictive_speed_weight(waypoints):
    if len(waypoints) < 3: return 1.0
    scan_dist = 0.0
    max_curve = 0.0
    
    for i in range(len(waypoints) - 2):
        wp1, wp2, wp3 = waypoints[i], waypoints[i+1], waypoints[i+2]
        scan_dist += math.sqrt((wp2['x']-wp1['x'])**2 + (wp2['z']-wp1['z'])**2)
        if scan_dist > SPEED_LOOKAHEAD_DIST: break
        
        ang1 = math.atan2(wp2['z']-wp1['z'], wp2['x']-wp1['x'])
        ang2 = math.atan2(wp3['z']-wp2['z'], wp3['x']-wp2['x'])
        diff = abs(ang1 - ang2)
        while diff > math.pi: diff -= 2*math.pi
        while diff < -math.pi: diff += 2*math.pi
        if abs(diff) > max_curve: max_curve = abs(diff)

    if max_curve < 0.2: return 1.0
    elif max_curve > 1.0: return 0.3
    else: return 1.0 - (0.7 * (max_curve - 0.2) / 0.8)


# ============================================================
# (5) 조향 제어 (PD Control)
# ============================================================
def steering_pd(angle_error, dt):
    global prev_angle_error
    if dt <= 0.0001: dt = 0.033

    P = KP_STEER * angle_error
    derivative = (angle_error - prev_angle_error) / dt
    D = KD_STEER * derivative

    prev_angle_error = angle_error
    
    return max(-1.0, min(1.0, P + D))

def smooth_speed_control(steer_cmd, predictive_weight=1.0, angle_error=0.0):
    if abs(angle_error) < STRAIGHT_ANGLE_THRESHOLD:
        return MAX_SPEED_WEIGHT

    curvature = abs(steer_cmd)
    reactive_weight = 1.0 / (1.0 + 1.8 * curvature)
    weight = min(reactive_weight, predictive_weight)
    
    if weight < MIN_SPEED_WEIGHT: weight = MIN_SPEED_WEIGHT
    if weight > MAX_SPEED_WEIGHT: weight = MAX_SPEED_WEIGHT
    return weight


# ============================================================
# (7) ADCS 메인 제어함수 (하이브리드 로직)
# ============================================================
def path_tracking(px, py, pz, yaw_deg, waypoints, speed_mps, dt):
    
    # 전역 변수(리스트)를 직접 수정하게 됨 (pop 등)
    head_wp, waypoints = select_waypoint(px, pz, waypoints)
    
    if head_wp is None:
        return "STOP", 1.0, "", 0.0, None

    dx = head_wp["x"] - px
    dz = head_wp["z"] - pz
    dist = math.sqrt(dx*dx + dz*dz)
    is_final_leg = (len(waypoints) <= 1)
    
    # --------------------------------------------------------
    # [MODE 1] 정밀 진입 모드
    # --------------------------------------------------------
    if is_final_leg and dist <= FINAL_GOAL_THRESHOLD:
        
        # A. 목표 달성 (0.5m 이내) -> 완전 정지
        if dist <= PARKING_THRESHOLD:
            return "STOP", 1.0, "", 0.0, head_wp
        
        # B. 정밀 제어
        look_x, look_z = head_wp["x"], head_wp["z"]
        desired_speed = dist * 0.8 
        
        if speed_mps > (desired_speed + 0.5):
             WS_command = "S"
             WS_weight = 0.4 
        elif speed_mps > desired_speed:
             WS_command = "W"
             WS_weight = 0.0 
        else:
             WS_command = "W"
             target_weight = max(0.15, min(0.6, dist * 0.2))
             WS_weight = target_weight
             
        target_angle = math.degrees(math.atan2(look_x - px, look_z - pz)) % 360
        angle_error = (target_angle - yaw_deg + 540.0) % 360.0 - 180.0
        steer_cmd = steering_pd(angle_error, dt)

    # --------------------------------------------------------
    # [MODE 2] 일반 주행 모드
    # --------------------------------------------------------
    else:
        curve_factor = compute_curvature_factor(px, pz, waypoints)
        eff_speed = speed_mps if curve_factor <= 0.5 else 0.0 
        
        lookahead = compute_lookahead_point(px, pz, waypoints, eff_speed)
        if lookahead is None: lookahead = head_wp
        look_x, look_z = lookahead["x"], lookahead["z"]
        
        target_angle = math.degrees(math.atan2(look_x - px, look_z - pz)) % 360
        angle_error = (target_angle - yaw_deg + 540.0) % 360.0 - 180.0
        steer_cmd = steering_pd(angle_error, dt)
        
        pred_w = calculate_predictive_speed_weight(waypoints)
        
        WS_command = "W"
        WS_weight = smooth_speed_control(steer_cmd, pred_w, angle_error)

        # [접근 감속]
        if is_final_leg:
            final_wp = waypoints[-1]
            dist_to_final = math.sqrt((final_wp["x"] - px)**2 + (final_wp["z"] - pz)**2)
            
            if dist_to_final <= APPROACH_DISTANCE:
                limit = LIMIT
                if WS_weight > limit:
                    WS_weight = limit

    if steer_cmd > 0: AD_command = "D"
    elif steer_cmd < 0: AD_command = "A"
    else: AD_command = ""
    
    return WS_command, WS_weight, AD_command, abs(steer_cmd), head_wp


# ============================================================
# Flask Endpoint
# ============================================================
@app.route('/get_adcs', methods=['POST'])
def get_adcs():
    global current_active_waypoints # 전역 변수 - [웨이포인트 저장소] 사용

    data = request.get_json(force=True)
    print('@@@@IBSM이 ADCS에 주는 데이터 : \n', data)
    
    ally_pos = data.get("ally_body_pos", {})
    ally_angle = data.get("ally_body_angle", {})
    waypoints_raw = data.get("waypoints", [])
    time_now = float(data.get("time", 0.0))

    px = float(ally_pos.get("x", 0.0))
    py = float(ally_pos.get("y", 0.0))
    pz = float(ally_pos.get("z", 0.0))
    yaw = float(ally_angle.get("x", 0.0)) 

    speed_mps, dt = estimate_speed_from_pos(time_now, px, pz)

    # 웨이포인트 갱신 로직 :
    # 빈 리스트가 아닐 때만 업데이트하고, 빈 리스트면 기존 경로 유지
    if waypoints_raw:
        current_active_waypoints = normalize_waypoints_list(waypoints_raw, default_y=py)
        print(f"경로 갱신됨 ({len(current_active_waypoints)} points)")
    
    # 추적 함수에는 항상 전역 변수(current_active_waypoints)를 전달
    WS_cmd, WS_w, AD_cmd, AD_w, head_wp = path_tracking(
        px, py, pz, yaw, current_active_waypoints, speed_mps, dt
    )
    
    if head_wp is None:
        head_wp = {"x": px, "y": py, "z": pz}

    response = {
        "WS_command": WS_cmd,
        "WS_weight": WS_w,
        "AD_command": AD_cmd,
        "AD_weight": AD_w,
        "head_waypoint": {
            "x": head_wp["x"],
            "y": head_wp.get("y", py),
            "z": head_wp["z"],
        }
    }
    
    print('\n@@@@@@@@@@ 현재 추종 중인 웨이포인트 :', current_active_waypoints)
    print("@@@@ ADCS 가 IBSM 에게 주는 데이터")
    print(response)
    return jsonify(response)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)