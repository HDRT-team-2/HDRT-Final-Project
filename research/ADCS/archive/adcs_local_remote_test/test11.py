from flask import Flask, request, jsonify
import math

app = Flask(__name__)

# ============================================================
# 제어 파라미터
# ============================================================
LOOKAHEAD_BASE = 7.0     # 기존: 10 → 변경: 동적 L 계산의 base
LOOKAHEAD_K = 0.4        # 속도 기반 L 증가량
GOAL_THRESHOLD = 8.0
MAX_SPEED_WEIGHT = 1.0
MIN_SPEED_WEIGHT = 0.05

# PD Steering Gains
KP_STEER = 0.03          # 새로 추가된 P 게인 (각도 에러 비례 조향)
KD_STEER = 0.12          # 새로 추가된 D 게인 (각도 변화율 감쇠)

# 이전 각도 에러 저장 (D항 계산용)
prev_angle_error = 0.0


# ============================================================
# 1) waypoint pop
# ============================================================
def select_waypoint(player_x, player_z, waypoints):
    if not waypoints:
        return None, waypoints

    current = waypoints[0]

    dx = current["x"] - player_x
    dz = current["z"] - player_z
    dist = math.sqrt(dx*dx + dz*dz)

    if dist <= GOAL_THRESHOLD:
        waypoints.pop(0)
        if not waypoints:
            return None, waypoints
        current = waypoints[0]

    return current, waypoints


# ============================================================
# 2) Lookahead point 계산
# (원래: L=10 고정 → 변경: 속도 기반 Dynamic Lookahead)
# ============================================================
def compute_lookahead_point(player_x, player_z, waypoints, speed):

    if not waypoints:
        return None

    # 원래: L = 10.0
    # L = LOOKAHEAD_DIST

    # 변경: 동적 lookahead = base + k * speed
    L = LOOKAHEAD_BASE + LOOKAHEAD_K * speed
    L = max(5.0, min(L, 25.0))  # 안정성 제한

    wp0 = waypoints[0]
    dx = wp0["x"] - player_x
    dz = wp0["z"] - player_z
    dist = math.sqrt(dx*dx + dz*dz)

    if dist < L and len(waypoints) >= 2:
        wp1 = waypoints[1]
    else:
        wp1 = wp0

    vx = wp1["x"] - player_x
    vz = wp1["z"] - player_z
    v_len = math.sqrt(vx*vx + vz*vz)

    if v_len < 1e-6:
        return wp1

    scale = L / v_len
    lx = player_x + vx * scale
    lz = player_z + vz * scale

    return {"x": lx, "z": lz}


# ============================================================
# 3) Steering PD Control 적용
#    (원래: 10° 넘으면 갑자기 "확" 꺾는 Step Function 회전)
#    → 변경: 연속적인 PD 기반 회전 (Integral steady-state error 제거 용도로 존재하는데
#           조향(Steering)은 position 제어가 아니라 heading 제어라서
#           시간이 지나면 반드시 0°로 수렴하게 되어 있음.)
# ============================================================
def steering_pd(angle_error):

    global prev_angle_error

    # P 항: 각도 오차 비례 조향
    P = KP_STEER * angle_error

    # D 항: 변화율 기반 조향 감쇠 (스무딩)
    D = KD_STEER * (angle_error - prev_angle_error)

    steer_cmd = P + D

    prev_angle_error = angle_error

    # 기존: turn_weight = abs(angle_diff)/60, step식
    # 변경: PD 출력 자체를 [-1, 1] 범위로 제한해 스무스하게
    steer_cmd = max(-1.0, min(1.0, steer_cmd))

    return steer_cmd


# ============================================================
# 4) Smooth Speed Control
#    (원래: abs(angle)/80 → 완전 선형, 계단 발생)
#    → 변경: steering_cmd 기반의 smooth 감속
# ============================================================
def smooth_speed_control(steer_cmd):

    # 기존: factor = 1 - |angle| / 80
    # 변경: steering_cmd 기반 smooth 감속
    curvature = abs(steer_cmd)

    # curvature 0~1 → 속도 weight 1/(1+k*curve)
    k = 1.8     # 감속 민감도
    weight = 1 / (1 + k * curvature)

    weight = max(weight, MIN_SPEED_WEIGHT)
    weight = min(weight, MAX_SPEED_WEIGHT)

    return weight


# ============================================================
# 5) ADCS 메인 제어 (전체 구조 동일)
# ============================================================
def path_tracking(px, py, pz, yaw_deg, waypoints, speed):

    # waypoint pop
    head_wp, waypoints = select_waypoint(px, pz, waypoints)

    if head_wp is None:
        return ("STOP", 1.0, "", 0.0, None)

    # 🔧 Dynamic Lookahead 적용
    lookahead = compute_lookahead_point(px, pz, waypoints, speed)

    dx = lookahead["x"] - px
    dz = lookahead["z"] - pz
    target_angle = math.degrees(math.atan2(dx, dz)) % 360

    angle_error = (target_angle - yaw_deg + 540) % 360 - 180

    # PD Steering 적용
    steer_cmd = steering_pd(angle_error)

    # A/D 조향 결정
    if steer_cmd > 0:
        AD_cmd = "D"
    elif steer_cmd < 0:
        AD_cmd = "A"
    else:
        AD_cmd = ""

    AD_weight = abs(steer_cmd)

    # Smooth Speed Control 적용
    WS_cmd = "W"
    WS_weight = smooth_speed_control(steer_cmd)

    return WS_cmd, WS_weight, AD_cmd, AD_weight, head_wp



# ============================================================
# Flask Endpoint (IBSM 출력 형식 변경 없음)
# ============================================================
@app.route('/get_adcs', methods=['POST'])
def get_adcs():

    data = request.get_json(force=True)
    print("\n@@@@@ IBSM → ADCS 입력\n", data)

    pos = data.get("ally_body_pos", {})
    ang = data.get("ally_body_angle", {})
    wps = data.get("waypoints", [])
    speed = data.get("ally_speed", 0.0)

    px = pos.get("x", 0.0)
    py = pos.get("y", 0.0)
    pz = pos.get("z", 0.0)
    yaw = ang.get("y", 0.0)

    WS_cmd, WS_w, AD_cmd, AD_w, head_wp = path_tracking(
        px, py, pz, yaw, wps, speed
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

    print("\n@@@@@ ADCS → IBSM 응답\n", response)

    return jsonify(response)



if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
