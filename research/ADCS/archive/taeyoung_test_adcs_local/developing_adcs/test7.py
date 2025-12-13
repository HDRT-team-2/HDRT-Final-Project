from flask import Flask, request, jsonify
import math

app = Flask(__name__)

# ===============================
# 전역 저장값 (IBSM ↔ ADCS)
# ===============================
global_WS_command = ""
global_WS_weight = 0.0
global_AD_command = ""
global_AD_weight = 0.0

# ============================================================
# Waypoint Selection 적용 (A 스타일 + 목적지 도달 처리)
# ============================================================

def select_waypoint(player_x, player_z, waypoints):
    """
    A 스타일 도달 판정:
    - waypoints[0]까지의 거리가 8m 이하 → pop(0)
    - pop 후 리스트가 비면 목적지 도달 → None 반환
    """
    if not waypoints:
        return None, waypoints

    current = waypoints[0]
    dx = current["x"] - player_x
    dz = current["z"] - player_z
    distance = math.sqrt(dx*dx + dz*dz)

    THRESHOLD = 8.0

    # ---- 도달 판정 ----
    if distance <= THRESHOLD:
        waypoints.pop(0)

        # 목적지 도달
        if not waypoints:
            return None, waypoints

        current = waypoints[0]

    return current, waypoints


# ============================================================
# ADCS 메인 제어 로직
# ============================================================

def path_tracking(player_x, player_y, player_z, body_yaw_deg, waypoints):

    head_wp, waypoints = select_waypoint(player_x, player_z, waypoints)

    # ---- 목적지 도달 ----
    if head_wp is None:
        return ("STOP", 1.0, "", 0.0, None)

    # ------------------------------
    # 2. 좌표 차 계산
    # ------------------------------
    dx = head_wp["x"] - player_x
    dz = head_wp["z"] - player_z
    target_angle = math.degrees(math.atan2(dx, dz)) % 360

    # ------------------------------
    # 3. 차량 yaw 기준 각도차 계산
    # ------------------------------
    angle_diff = (target_angle - body_yaw_deg + 540.0) % 360.0 - 180.0
    abs_angle_diff = abs(angle_diff)

    # ------------------------------
    # 4. 전진 속도 조절
    # ------------------------------
    angle_norm = min(abs_angle_diff / 90.0, 1.0)
    forward_weight = 0.6 * (1.0 - angle_norm)

    max_forward_weight = 1.0  # 65/65
    forward_weight = min(forward_weight, max_forward_weight)

    # ------------------------------
    # 5. 회전 명령
    # ------------------------------
    AD_command = ""
    AD_weight = 0.0

    if abs_angle_diff > 10:
        turn_weight = min(abs_angle_diff / 60.0, 1.0)
        if angle_diff > 0:
            AD_command = "D"
            AD_weight = turn_weight
        else:
            AD_command = "A"
            AD_weight = turn_weight

    # ------------------------------
    # 6. 전진 명령
    # ------------------------------
    WS_command = ""
    WS_weight = 0.0

    if forward_weight > 0.05:
        WS_command = "W"
        WS_weight = forward_weight

    return WS_command, WS_weight, AD_command, AD_weight, head_wp


# ============================================================
# /get_adcs API
# ============================================================

@app.route('/get_adcs', methods=['POST'])
def get_adcs():
    data = request.get_json(force=True)

    ally_pos = data.get("ally_body_pos", {})
    ally_angle = data.get("ally_body_angle", {})
    waypoints = data.get("waypoints", [])

    player_x = ally_pos.get("x", 0.0)
    player_y = ally_pos.get("y", 0.0)
    player_z = ally_pos.get("z", 0.0)

    # yaw = y축
    body_yaw_deg = ally_angle.get("y", 0.0)

    WS_command, WS_weight, AD_command, AD_weight, head_wp = path_tracking(
        player_x, player_y, player_z, body_yaw_deg, waypoints
    )

    # Head_waypoint dict 구성
    if head_wp is not None:
        head_waypoint_dict = {
            "x": head_wp.get("x", 0.0),
            "y": head_wp.get("y", 0.0),
            "z": head_wp.get("z", 0.0)
        }
    else:
        head_waypoint_dict = {
            "x": player_x,
            "y": player_y,
            "z": player_z
        }

    response = {
        "WS_command": WS_command,
        "WS_weight": WS_weight,
        "AD_command": AD_command,
        "AD_weight": AD_weight,
        "Head_waypoint": head_waypoint_dict
    }

    print('@@@ibsm에 주는 데이터 : \n', response)

    return jsonify(response)


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
