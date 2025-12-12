from flask import Flask, request, jsonify
import math

app = Flask(__name__)

# ------------------------------------------------------
# 전역 상태값 (속도 추정용)
# ------------------------------------------------------
prev_time = None
prev_x = None
prev_z = None
prev_speed = 0.0


# ------------------------------------------------------
# 1. A-Style Waypoint Pop
# ------------------------------------------------------
def select_waypoint(player_x, player_z, waypoints):
    """
    A-Style 도달 판정:
    - head waypoint까지의 거리가 8m 이하 → pop(0)
    - pop 후 리스트가 비면 → 목적지 도달
    """
    if not waypoints:
        return None, waypoints

    head = waypoints[0]
    dx = head["x"] - player_x
    dz = head["z"] - player_z
    distance = math.sqrt(dx*dx + dz*dz)

    THRESHOLD = 8.0
    if distance <= THRESHOLD:
        waypoints.pop(0)
        if not waypoints:
            return None, waypoints
        head = waypoints[0]

    return head, waypoints


# ------------------------------------------------------
# 2. 속도 추정기 (Distance / Time)
# ------------------------------------------------------
def estimate_speed(time_now, x_now, z_now):
    global prev_time, prev_x, prev_z, prev_speed

    # 첫 프레임 초기화
    if prev_time is None:
        prev_time = time_now
        prev_x = x_now
        prev_z = z_now
        return 0.0

    dt = max(time_now - prev_time, 1e-6)

    dx = x_now - prev_x
    dz = z_now - prev_z
    dist = math.sqrt(dx*dx + dz*dz)

    speed = dist / dt

    # 상태 업데이트
    prev_time = time_now
    prev_x = x_now
    prev_z = z_now
    prev_speed = speed

    return speed


# ------------------------------------------------------
# 3. Lookahead 기반 목표 방향 계산
# ------------------------------------------------------
def compute_lookahead_target(player_x, player_z, waypoints, lookahead=12.0):
    """
    head, head+1, head+2 를 순차적으로 사용하여
    lookahead 거리 내에서 가장 적절한 target point 설정
    """

    if not waypoints:
        return None

    # 후보 노드 최대 3개
    candidates = waypoints[:3]

    best_wp = candidates[0]
    best_dist = 9999

    for wp in candidates:
        dx = wp["x"] - player_x
        dz = wp["z"] - player_z
        dist = math.sqrt(dx*dx + dz*dz)

        # lookahead 거리 안에서 가장 먼 놈을 채택 → 코너 부드러워짐
        if dist <= lookahead and dist > best_dist:
            best_wp = wp
            best_dist = dist

    return best_wp


# ------------------------------------------------------
# 4. ADCS 메인 제어
# ------------------------------------------------------
def path_tracking(player_x, player_y, player_z, body_yaw_deg, time_now, waypoints):

    # (1) waypoint 도달 판정
    head_wp, waypoints = select_waypoint(player_x, player_z, waypoints)

    if head_wp is None:
        # 목적지 도달
        return ("STOP", 1.0, "", 0.0, None)

    # (2) lookahead target 계산
    target_wp = compute_lookahead_target(player_x, player_z, waypoints)

    # fallback
    if target_wp is None:
        target_wp = head_wp

    # (3) heading 계산
    dx = target_wp["x"] - player_x
    dz = target_wp["z"] - player_z
    target_angle = math.degrees(math.atan2(dx, dz)) % 360

    angle_diff = (target_angle - body_yaw_deg + 540) % 360 - 180
    abs_angle_diff = abs(angle_diff)

    # (4) 현재 속도 추정
    current_speed = estimate_speed(time_now, player_x, player_z)

    # (5) 곡률 기반 커브 감속 → 목표 속도 설정
    #    큰 각도 = 커브 = 감속 필요
    curvature_factor = min(abs_angle_diff / 90.0, 1.0)

    # 최고속도 65 → 직선에서는 full speed
    MAX_SPEED = 65.0
    MIN_SPEED_CURVE = 15.0  # 급커브 최소 속도

    target_speed = MAX_SPEED * (1.0 - curvature_factor)
    target_speed = max(target_speed, MIN_SPEED_CURVE)

    # (6) 속도 오차 기반 W weight 계산
    speed_error = target_speed - current_speed

    # 아주 간단한 P-control
    Kp = 0.03
    ws_weight = max(0.0, min(Kp * speed_error, 1.0))

    WS_command = "W" if ws_weight > 0.05 else ""

    # (7) 회전 명령
    AD_command = ""
    AD_weight = 0.0

    if abs_angle_diff > 5:
        AD_weight = min(abs_angle_diff / 60.0, 1.0)
        AD_command = "D" if angle_diff > 0 else "A"

    return WS_command, ws_weight, AD_command, AD_weight, target_wp


# ------------------------------------------------------
# REST API
# ------------------------------------------------------
@app.route('/get_adcs', methods=['POST'])
def get_adcs():
    data = request.get_json(force=True)
    print('@@@@@@ IBSM 에서 제공받은 데이터 : ', data)

    ally_pos = data.get("ally_body_pos", {})
    ally_angle = data.get("ally_body_angle", {})
    time_now = data.get("time", 0.0)

    player_x = ally_pos.get("x", 0.0)
    player_y = ally_pos.get("y", 0.0)
    player_z = ally_pos.get("z", 0.0)

    body_yaw_deg = ally_angle.get("y", 0.0)

    waypoints = data.get("waypoints", [])

    WS_command, WS_weight, AD_command, AD_weight, head_wp = path_tracking(
        player_x, player_y, player_z, body_yaw_deg, time_now, waypoints
    )

    if head_wp is None:
        head_wp = {"x": player_x, "y": player_y, "z": player_z}

    response = {
        "WS_command": WS_command,
        "WS_weight": WS_weight,
        "AD_command": AD_command,
        "AD_weight": AD_weight,
        "head_waypoint": head_wp
    }

    print("\n@@@@ ADCS Response → IBSM\n", response)

    return jsonify(response)


# ------------------------------------------------------
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
