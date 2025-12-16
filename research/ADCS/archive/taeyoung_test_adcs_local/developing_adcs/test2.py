from flask import Flask, request, jsonify
import math
import time

app = Flask(__name__)

# ---------------- PID Controller ----------------
class PID:
    def __init__(self, kp, ki, kd):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.prev_error = 0.0
        self.integral = 0.0
        self.prev_time = None

    def reset(self):
        self.prev_error = 0.0
        self.integral = 0.0
        self.prev_time = None

    def compute(self, target, current):
        error = target - current
        now = time.time()

        if self.prev_time is None:
            dt = 0.03
        else:
            dt = now - self.prev_time
            if dt <= 0:
                dt = 0.03

        self.prev_time = now

        # PID
        self.integral += error * dt
        derivative = (error - self.prev_error) / dt
        out = self.kp * error + self.ki * self.integral + self.kd * derivative

        self.prev_error = error
        return out


# ---------------- PID Instances ----------------
yaw_pid = PID(kp=0.04, ki=0.0, kd=0.01)      # 조향 PID
speed_pid = PID(kp=0.10, ki=0.0, kd=0.02)    # 전진 PID

# ------------------------------------------------

@app.route('/get_adcs', methods=['POST'])
def get_adcs():
    data = request.get_json(force=True)

    # ====== 현재 차량 상태 입력 ======
    px = data["ally_body_pos"]["x"]
    pz = data["ally_body_pos"]["z"]

    yaw = data["ally_body_angle"]["x"]   # 시뮬 yaw = x
    speed = data["ally_speed"]

    waypoints = data["waypoints"]
    if len(waypoints) == 0:
        return jsonify({
            "WS_command": "",
            "WS_weight": 0.0,
            "AD_command": "",
            "AD_weight": 0.0
        })

    # ====== 다음 waypoint 선택 ======
    next_wp = waypoints[0]
    wx, _, wz = next_wp

    # ====== 목표 각도 계산 ======
    dx = wx - px
    dz = wz - pz
    target_angle = math.degrees(math.atan2(dx, dz)) % 360

    # ====== 각도 차이(normalized) ======
    angle_error = (target_angle - yaw + 540) % 360 - 180

    # ====== 조향 PID 값 ======
    steer_out = yaw_pid.compute(0.0, -angle_error)    # error → 0이 목표

    steer_weight = min(abs(steer_out), 1.0)

    if steer_out > 0:
        AD_command = "D"
    else:
        AD_command = "A"

    if abs(angle_error) < 5:
        AD_command = ""
        steer_weight = 0.0

    # ====== 속도 PID ======
    dist = math.sqrt(dx*dx + dz*dz)
    target_speed = max(8.0, min(dist, 30.0))      # waypoint까지 거리 기반 목표 속력
    speed_out = speed_pid.compute(target_speed, speed)

    WS_weight = min(max(speed_out / 30.0, 0.0), 1.0)
    WS_command = "W" if WS_weight > 0.05 else ""

    # ====== IBSM으로 반환 ======
    return jsonify({
        "WS_command": WS_command,
        "WS_weight": round(WS_weight, 3),
        "AD_command": AD_command,
        "AD_weight": round(steer_weight, 3)
    })

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
