from flask import Flask, request, jsonify
import math

app = Flask(__name__)

# ============================================================
# 1. 제어 파라미터 (튜닝 가이드 포함)
# ============================================================
# [주행 - 가변 룩어헤드]
# 역할: 전차가 바라보는 목표 지점의 거리 (사람의 시선과 같음)
# 튜닝: 
#  - MIN 값을 줄이면: 장애물을 더 잘 피하지만 핸들이 예민해짐 (좌우 흔들림 증가)
#  - MAX 값을 늘리면: 고속에서 부드럽게 주행하지만 코너를 크게 돌게 됨 (안쪽 파고듦 감소)
LOOKAHEAD_MIN = 5.0      
LOOKAHEAD_MAX = 15.0     
SPEED_FOR_MAX_L = 18.0          # 이 속도(m/s) 이상일 때 MAX 거리를 봅니다 (약 65km/h)
SPEED_LOOKAHEAD_DIST = 40.0     # 곡률 예측을 위해 미리 스캔하는 거리 (먼 미래를 보는 눈)

# [도착 판정 & 정밀 제어]
# 역할: 웨이포인트를 통과했다고 판단하는 기준 거리
# 튜닝:
#  - GOAL_THRESHOLD를 줄이면: 웨이포인트를 더 정확하게 찍고 지나가려 함 (지그재그 주행 유발 가능)
#  - FINAL_GOAL_THRESHOLD를 늘리면: 정밀 제어(감속)를 더 일찍 시작함 (안전하지만 답답할 수 있음)
GOAL_THRESHOLD = 7.0            # 일반 경유지: 7m 이내면 통과하고 다음 점으로
FINAL_GOAL_THRESHOLD = 1.5      # 최종 진입: 마지막 점 3m 이내면 '정밀 주차 모드' 발동
FCS_PRECISION_THRESHOLD = 0.5   # 최종 완료: ( )m 이내에 들어와야만 '완전 정지(STOP)' 인정
LIMIT = 0.35                    # 도착 임박 감속력 비율 : 정밀한 공격지점 주차를 위한 감속 비율

# [속도 제한]
# 역할: 전차의 악셀 페달을 밟는 정도 (0.0 ~ 1.0)
MAX_SPEED_WEIGHT = 40.0 / 70.0   # 최대 속도 (1.0 = 풀악셀)
MIN_SPEED_WEIGHT = 20.0 / 70.0    # 최소 속도 (너무 느리면 시동 꺼지듯 멈추는 것 방지)

# [조향 PD 게인]
# 역할: 핸들을 돌리는 힘과 반응 속도 조절
# 튜닝:
#  - KP (스프링):   값을 키우면 경로로 빨리 복귀하지만, 너무 크면 좌우로 팅팅거림
#  - KD (댐퍼):     값을 키우면 진동을 잡지만, 너무 크면 핸들이 뻑뻑해져서 코너를 못 돔
KP_STEER = 0.05   # P항: 경로 복귀력 (현재 오차 비례)
KD_STEER = 0.005  # D항: 진동 억제력 (오차 변화 속도 비례, dt 보정됨)

# 제어 임계값
# 튜닝:
#  - THRESHOLD를 키우면: 웬만한 커브에서도 감속 안 하고 달림 (빠르지만 위험)
#  - DISTANCE를 늘리면: 더 멀리서부터 천천히 감속해서감 (안전하지만 도착이 늦음)
STRAIGHT_ANGLE_THRESHOLD = 2.0  # 이 각도(도) 이내면 '직진'으로 간주하고 가속
APPROACH_DISTANCE = 25.0        # 목적지 {}m 남으면 '접근 모드' 발동 (속도 35% 제한)

# ============================================================
# 2. 전역 변수 (상태 저장)
# ============================================================
prev_angle_error = 0.0   # D항 계산을 위한 이전 오차
prev_time = None         # dt 계산을 위한 이전 시간
prev_x = None            # 속도 계산용 이전 위치 X
prev_z = None            # 속도 계산용 이전 위치 Z
prev_dt = 0.033          # dt 노이즈 필터링용 (초기값 30FPS 기준)


# ============================================================
# (0) 유틸리티: 데이터 포맷 정규화
# ============================================================
def normalize_waypoint(wp, default_y=0.0):
    if isinstance(wp, dict):
        return {"x": float(wp.get("x", 0.0)), "y": float(wp.get("y", default_y)), "z": float(wp.get("z", 0.0))}
    elif isinstance(wp, (list, tuple)) and len(wp) >= 3:
        return {"x": float(wp[0]), "y": float(wp[1]), "z": float(wp[2])}
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

    # [중요] 마지막 점은 거리가 가까워져도 절대 삭제(pop)하지 않음
    # 이유: 정밀 주차 모드에서 (FCS_PRECISION_THRESHOLD)m 될 때까지 계속 써야 하기 때문
    if is_final_waypoint:
        return current, waypoints

    # 일반 경유지는 (GOAL_THRESHOLD)m 이내로 접근하면 '통과'로 간주하고 삭제
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

    # 시뮬레이터 통신 렉으로 인해 시간이 튀는 것을 방지
    raw_dt = time_now - prev_time
    if raw_dt <= 1e-4: raw_dt = 0.033

    # [LPF] 현재 dt와 이전 dt를 7:3 비율로 섞어서 부드럽게 만듦
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
    # 속도가 빠를수록 더 멀리 봄 (비례 제어)
    ratio = max(0.0, min(speed_mps / SPEED_FOR_MAX_L, 1.0))
    return LOOKAHEAD_MIN + (LOOKAHEAD_MAX - LOOKAHEAD_MIN) * ratio

def compute_lookahead_point(player_x, player_z, waypoints, speed_mps):
    if not waypoints: return None
    
    L = compute_dynamic_lookahead(speed_mps)
    remain = L
    prev_x, prev_z = player_x, player_z

    # 경로 선분 위에서 L미터 앞의 점을 찾아냄 (보간법)
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
    # 현재 위치 바로 앞의 도로가 얼마나 꺾여있는지 계산 (급커브 감지)
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
# (4) 예측 속도 제어 (먼 미래 보기)
# ============================================================
def calculate_predictive_speed_weight(waypoints):
    # (APPROACH_DISTANCE)m 앞까지의 경로를 미리 스캔해서 급커브가 있으면 미리 감속
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

    # P항: 현재 오차만큼 꺾음
    P = KP_STEER * angle_error
    
    # D항: 오차의 변화 속도(각속도)에 저항함 (진동 방지)
    # [중요] dt로 나누어주어야 렉이 걸려도 물리적으로 일정한 힘을 냄
    derivative = (angle_error - prev_angle_error) / dt
    D = KD_STEER * derivative

    prev_angle_error = angle_error
    
    return max(-1.0, min(1.0, P + D))

def smooth_speed_control(steer_cmd, predictive_weight=1.0, angle_error=0.0):
    # [직진 부스터] 오차가 2도 이내면 무조건 가속 (속도 향상 핵심)
    if abs(angle_error) < STRAIGHT_ANGLE_THRESHOLD:
        return MAX_SPEED_WEIGHT

    # 핸들을 많이 꺾을수록 속도를 줄임 (전복 방지)
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
    
    head_wp, waypoints = select_waypoint(px, pz, waypoints)
    
    if head_wp is None:
        return "STOP", 1.0, "", 0.0, None

    dx = head_wp["x"] - px
    dz = head_wp["z"] - pz
    dist = math.sqrt(dx*dx + dz*dz)
    is_final_leg = (len(waypoints) <= 1)
    
#  path_tracking 함수 내 정밀 제어 로직
    # --------------------------------------------------------
    # [MODE 1] 정밀 진입 모드 (2m 이내 & 마지막 점)
    # --------------------------------------------------------
    if is_final_leg and dist <= FINAL_GOAL_THRESHOLD:
        
        if dist <= FCS_PRECISION_THRESHOLD:
            return "STOP", 1.0, "", 0.0, head_wp
        
        look_x, look_z = head_wp["x"], head_wp["z"]
        
        # [개선] 너무 느리지 않게 최소 속도 보장
        # 거리가 가까워져도 최소 0.3의 힘으로 밀어줌
        target_weight = max(0.3, min(0.8, dist * 0.4)) 
        
        # 목표 속도 (거리 * 1.5로 상향)
        desired_speed = dist * 1.5
        
        if speed_mps > (desired_speed + 0.5):
             WS_command = "S"
             WS_weight = 0.5
        elif speed_mps > desired_speed:
             WS_command = "W" # Coasting
             WS_weight = 0.0
        else:
             WS_command = "W"
             WS_weight = target_weight
             
        # 조향 계산 (동일)
        target_angle = math.degrees(math.atan2(look_x - px, look_z - pz)) % 360
        angle_error = (target_angle - yaw_deg + 540.0) % 360.0 - 180.0
        steer_cmd = steering_pd(angle_error, dt)

    # --------------------------------------------------------
    # [MODE 2] 일반 주행 모드 (그 외)
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
        
        # 직진 구간 가속 적용
        WS_command = "W"
        WS_weight = smooth_speed_control(steer_cmd, pred_w, angle_error)

        # --------------------------------------------------------
        # [접근 감속] {APPROACH_DISTANCE}m 전방부터 관성 죽이기
        # --------------------------------------------------------
        if is_final_leg:
            final_wp = waypoints[-1]
            dist_to_final = math.sqrt((final_wp["x"] - px)**2 + (final_wp["z"] - pz)**2)
            
            # {APPROACH_DISTANCE}m 안쪽이면 속도를 최대 {LIMIT}%로 제한
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
    try:
        data = request.get_json(force=True)
        print('@@@@@@@ IBSM ======> ADCS 데이터 주는값\n', data)
        
        ally_pos = data.get("ally_body_pos", {})
        ally_angle = data.get("ally_body_angle", {})
        waypoints_raw = data.get("waypoints", [])
        time_now = float(data.get("time", 0.0))

        px = float(ally_pos.get("x", 0.0))
        py = float(ally_pos.get("y", 0.0))
        pz = float(ally_pos.get("z", 0.0))
        yaw = float(ally_angle.get("x", 0.0)) 

        speed_mps, dt = estimate_speed_from_pos(time_now, px, pz)
        waypoints = normalize_waypoints_list(waypoints_raw, default_y=py)

        WS_cmd, WS_w, AD_cmd, AD_w, head_wp = path_tracking(
            px, py, pz, yaw, waypoints, speed_mps, dt
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
        
        print('\n\n@@@@@@@@@@웨이포인트 좌표 : \n', waypoints)
        print("@@@@ ADCS 가 IBSM 에게 주는 데이터")
        print(response,'\n\n')
        return jsonify(response)

    except Exception as e:
        print(f"[ADCS Error] {e}")
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)