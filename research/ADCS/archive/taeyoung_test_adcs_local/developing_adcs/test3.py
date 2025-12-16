# ----------------------------
# ADCS - Automatic Driving Control Server
# PID_mid_light_complete 기반 제어 적용
# ----------------------------

from flask import Flask, request, jsonify
import time
import math

app = Flask(__name__)

# ===============================
# 전역 저장값 (IBSM ↔ ADCS)
# ===============================
global_WS_command = ""
global_WS_weight = 0.0
global_AD_command = ""
global_AD_weight = 0.0

prev_time = None   # dt 계산용 (필요시 사용)

# ============================================================
# path_tracking() — mid_light 방식 그대로 적용
# ============================================================
def path_tracking(player_x, player_z, player_body_yaw, waypoints):

    if not waypoints or len(waypoints) == 0:
        return ("", 0.0, "", 0.0)

    # 현재 목표 웨이포인트
    target_wp = waypoints[0]
    wp_x = target_wp["x"]
    wp_z = target_wp["z"]

    dx = wp_x - player_x
    dz = wp_z - player_z

    distance = math.sqrt(dx*dx + dz*dz)

    # ----- 도달 판단 -----
    if distance <= 8.0:
        # 웨이포인트 소비 (제거)
        if len(waypoints) > 1:
            waypoints.pop(0)
            return path_tracking(player_x, player_z, player_body_yaw, waypoints)
        else:
            return ("STOP", 1.0, "", 0.0)

    # ----- 타겟 각도 계산 -----
    target_angle = math.degrees(math.atan2(dx, dz)) % 360
    angle_diff = (target_angle - player_body_yaw + 540) % 360 - 180
    abs_diff = abs(angle_diff)

    # ----- 회전 AD 제어 -----
    if abs_diff > 10:
        steer_weight = min(abs_diff / 60.0, 1.0)
        if angle_diff > 0:
            AD_command = "D"
        else:
            AD_command = "A"
    else:
        AD_command = ""
        steer_weight = 0.0

    # ----- 전진 WS 제어 (각도 기반 자동 감속) -----
    angle_norm = min(abs_diff / 90.0, 1.0)
    forward_weight = 0.6 * (1.0 - angle_norm)
    max_forward = 40.0 / 65.0  # 40km/h 모델
    forward_weight = min(forward_weight, max_forward)

    if forward_weight > 0.05:
        WS_command = "W"
        WS_weight = forward_weight
    else:
        WS_command = ""
        WS_weight = 0.0

    return WS_command, WS_weight, AD_command, steer_weight


# ============================================================
# body_control() — mid_light 방식 완전 동일
# ============================================================
def body_control(player_x, player_z, player_body_yaw, waypoints):

    WS_cmd, WS_w, AD_cmd, AD_w = \
        path_tracking(player_x, player_z, player_body_yaw, waypoints)

    return WS_cmd, WS_w, AD_cmd, AD_w


# ============================================================
# /get_adcs — IBSM → ADCS → weight 계산 후 반환
# ============================================================
@app.route("/get_adcs", methods=["POST"])
def get_adcs():
    global global_WS_command, global_WS_weight
    global global_AD_command, global_AD_weight

    data = request.get_json(force=True)
    print(data)

    # ===== 입력 파싱 =====
    player_x = data["ally_body_pos"]["x"]
    player_y = data["ally_body_pos"]["y"]
    player_z = data["ally_body_pos"]["z"]

    player_body_yaw = data["ally_body_angle"]["y"]   # yaw(차체 회전)

    waypoints = data["waypoints"]  # [[x,y,z], ...]

    # ===== 제어 계산 =====
    WS_cmd, WS_w, AD_cmd, AD_w = \
        body_control(player_x, player_z, player_body_yaw, waypoints)

    global_WS_command = WS_cmd
    global_WS_weight = WS_w
    global_AD_command = AD_cmd
    global_AD_weight = AD_w
    request_data = {
        "WS_command": WS_cmd,
        "WS_weight": round(WS_w, 3),
        "AD_command": AD_cmd,
        "AD_weight": round(AD_w, 3)
    }
    print(request_data)

    # ===== IBSM으로 반환 =====
    return jsonify(request_data)
    

# ============================================================
# 실행
# ============================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
