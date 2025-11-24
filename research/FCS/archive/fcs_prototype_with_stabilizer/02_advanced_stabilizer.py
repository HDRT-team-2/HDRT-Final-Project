"""
스테빌라이저 + FCS 코드 (문제점 제거 / 동작 버전)
"""
############################ 필요 라이브러리 선언 ###########################
import os
from flask import Flask, request, jsonify
import math
import pandas as pd
import numpy as np
import time

############################## Flask 추가 ################################
app = Flask(__name__)

##################### IBSM에 보낼 데이터의 기본값 ##########################
qe_command = ""
qe_weight = 0.0
rf_command = ""
rf_weight = 0.0
fire_command = False
fire_target_pos = None
new_fire_point_pos = None

######################## 스태빌라이져용 전역변수 ###########################
# 물체(장애물/적) 조준용 타깃 좌표 (IBSM에서 내려주는 좌표)
aim_target_x = None
aim_target_y = None
aim_target_z = None

# 🔁 dt 및 "자이로(각속도)" 계산용 상태
prev_time       = None
prev_turret_x   = None   # 이전 프레임 포탑 yaw
prev_turret_y   = None   # 이전 프레임 포탑 pitch (pitch는 지금 안 쓰지만 각속도 계산 위해 보관)

# 🔁 Yaw PI 제어기 상태 (적분항 저장)
yaw_int   = 0.0
YAW_INT_LIMIT   = 30.0  # deg·s (적분항 클램프)

# 웨이포인트 전환 완충용 (지금은 0부터 시작, 필요시 외부에서 세팅)
wp_switch_cooldown = 0

# 🔁 차체 회전(AD) → 포탑 QE 역보상 게인 (feed-forward)
AD_YAW_COMP_DEG = 8.0   # 개념용 (지금은 weight로 직접 사용)

# ==========================
# 🔮 W 기반 기하학 미래예측용 상수
# ==========================
PREDICT_NOMINAL_MAX_SPEED = 25.0   # [게임 단위/s] 가정 최대 속도 (튜닝용)
PREDICT_BASE_HORIZON      = 0.30   # [s] 최소로 보는 미래 시간
PREDICT_MAX_HORIZON       = 0.80   # [s] 최대로 보는 미래 시간
PREDICT_ALPHA_YAW         = 0.60   # 현재 yaw_err vs 미래 yaw_err 블렌딩 비율 (0~1)

########################### 스태빌라이저 기능 #############################
def normalize_angle_deg(angle: float) -> float:
    """각도를 -180 ~ 180도로 정규화"""
    return (angle + 180.0) % 360.0 - 180.0

class TurretYawStabilizer:
    """
    - 시뮬레이터 시간 + 포탑 각도 변화로 dt / 자이로(각속도) 계산
    - yaw PID + gyro D + AD feed-forward로 QE_command / QE_weight 산출
    """
    def __init__(self):
        # dt & gyro 계산용 상태
        self.prev_time     = None
        self.prev_turret_x = None
        self.prev_turret_y = None

        # Yaw 적분항
        self.yaw_int       = 0.0
        self.YAW_INT_LIMIT = 30.0  # 적분항 클램프

        # 파라미터 (튜닝포인트)
        self.Kp_yaw      = 0.035
        self.Ki_yaw      = 0.010
        self.Kd_yaw_gyro = 0.010

        self.YAW_DEADBAND   = 0.5
        self.GYRO_DEADBAND  = 1.0
        self.AD_DEADBAND    = 0.05
        self.MAX_QE         = 1.0
        self.MIN_QE_OUTPUT  = 0.02

        # 적분 억제 / 감쇠
        self.YAW_INT_ERR_THRESH = 2.0
        self.YAW_INT_DECAY      = 0.90

    # ------------------------------------------------------------------
    # 시간 / 자이로 계산
    # ------------------------------------------------------------------
    def _compute_dt_and_gyro(self, time_val, turret_x, turret_y):
        """
        시뮬레이터 시간(time_val)과 포탑 각도 변화로
        - dt (프레임 간 시간)
        - gyro_yaw_rate (deg/s)
        를 계산
        """
        # 기본 dt (fallback)
        dt = 0.016

        # dt 계산
        if self.prev_time is None:
            self.prev_time = time_val
        else:
            dt_raw = time_val - self.prev_time
            if dt_raw > 0:
                dt = dt_raw
            self.prev_time = time_val

        # 각속도 계산
        if self.prev_turret_x is None or self.prev_turret_y is None:
            gyro_yaw_rate = 0.0
        else:
            dyaw = normalize_angle_deg(turret_x - self.prev_turret_x)
            if dt > 0.0:
                gyro_yaw_rate = dyaw / dt
            else:
                gyro_yaw_rate = 0.0

        self.prev_turret_x = turret_x
        self.prev_turret_y = turret_y

        return dt, gyro_yaw_rate

    # ------------------------------------------------------------------
    # 메인 Yaw 제어 (QE_command / QE_weight 계산)
    # ------------------------------------------------------------------
    def update(
        self,
        *,
        time_val: float,
        player_x: float,
        player_y: float,
        player_z: float,
        player_turret_x: float,     # 포탑 yaw
        target_x: float,
        target_y: float,
        target_z: float,
        body_yaw: float,            # 차체 yaw (ally_body_angle["y"])
        body_AD_cmd: str,
        body_AD_weight: float,
        player_speed: float
    ):
        """
        한 프레임마다 호출:
        QE_command, QE_weight를 반환
        """
        # dt / 자이로 계산
        dt, gyro_yaw_rate = self._compute_dt_and_gyro(time_val, player_turret_x, 0.0)

        # 1) 타겟까지의 yaw 오차 계산
        dx = target_x - player_x
        dz = target_z - player_z
        dist_xz = math.hypot(dx, dz)
        if dist_xz < 1e-6:
            dist_xz = 1e-6

        # Unity 기준: z+ 앞, x+ 오른쪽이라면 atan2(dx, dz) 사용
        target_yaw = math.degrees(math.atan2(dx, dz))
        if target_yaw < 0:
            target_yaw += 360.0

        yaw_err = normalize_angle_deg(target_yaw - player_turret_x)

        # 2) Deadband 안이면 거의 고정
        if abs(yaw_err) < self.YAW_DEADBAND and abs(gyro_yaw_rate) < self.GYRO_DEADBAND:
            # 작은 오차 영역에서는 적분항 서서히 감쇠
            self.yaw_int *= self.YAW_INT_DECAY
            return "", 0.0

        # 3) 적분항 업데이트 (현재 오차 기준)
        if dt > 0.0:
            if abs(yaw_err) > self.YAW_INT_ERR_THRESH:
                self.yaw_int += yaw_err * dt
            else:
                self.yaw_int *= self.YAW_INT_DECAY

        # 적분항 클램프
        self.yaw_int = max(-self.YAW_INT_LIMIT, min(self.YAW_INT_LIMIT, self.yaw_int))

        # 4) AD feed-forward (몸통 회전 보상)
        #    몸통이 오른쪽(D)으로 돌면 포탑은 왼쪽(Q)로 살짝 밀어줌
        u_ff = 0.0
        K_FF_AD = 0.4
        if body_AD_cmd == "D":
            u_ff = -K_FF_AD * float(body_AD_weight)
        elif body_AD_cmd == "A":
            u_ff = +K_FF_AD * float(body_AD_weight)

        # 5) PID 계산
        P = self.Kp_yaw * yaw_err
        I = self.Ki_yaw * self.yaw_int
        D = -self.Kd_yaw_gyro * gyro_yaw_rate  # 자이로 D: 회전 속도가 빠르면 브레이크

        u = P + I + D + u_ff

        # 6) 출력 클램프
        if u > self.MAX_QE:
            u = self.MAX_QE
        elif u < -self.MAX_QE:
            u = -self.MAX_QE

        # 너무 작으면 멈춘 것으로 처리
        if abs(u) < self.MIN_QE_OUTPUT:
            return "", 0.0

        # 7) 부호에 따라 Q / E 결정
        if u > 0:
            return "E", u
        else:
            return "Q", -u

# 전역 스태빌라이저 인스턴스
yaw_stabilizer = TurretYawStabilizer()

def turret_control(request_data: dict):
    """
    IBSM → FCS로 들어온 request_data(dict)를 그대로 받아서
    QE_command / QE_weight만 계산하는 래퍼 함수.

    get_fcs()에서:
        turret_control(request_data)
    만 호출해주면 됨.
    """
    global qe_command, qe_weight, aim_target_x, aim_target_y, aim_target_z

    # 1) 공통 데이터 파싱
    time_val = float(request_data.get("time", 0.0))

    ally_pos   = request_data.get("ally_body_pos", {}) or {}
    ally_ang   = request_data.get("ally_body_angle", {}) or {}
    turret_ang = request_data.get("ally_turret_angle", {}) or {}
    target_pos = request_data.get("ibsm_target_pos", {}) or {}

    player_x = float(ally_pos.get("x", 0.0))
    player_y = float(ally_pos.get("y", 0.0))
    player_z = float(ally_pos.get("z", 0.0))

    player_turret_x = float(turret_ang.get("x", 0.0))   # yaw
    player_turret_y = float(turret_ang.get("y", 0.0))   # pitch (지금은 안 씀)

    body_yaw = float(ally_ang.get("y", 0.0))            # 차체 yaw

    player_speed = float(request_data.get("ally_speed", 0.0))

    # AD 명령 (몸통 회전) – IBSM에서 내려준 값 사용
    body_AD_cmd    = request_data.get("AD_command", "")
    body_AD_weight = float(request_data.get("AD_weight", 0.0))

    # 2) 타깃 선택 (기본은 ibsm_target_pos → 없으면 aim_target_* 사용)
    if "x" in target_pos and "y" in target_pos and "z" in target_pos:
        target_x = float(target_pos.get("x", 0.0))
        target_y = float(target_pos.get("y", 0.0))
        target_z = float(target_pos.get("z", 0.0))

        # 최신 타깃을 aim_target에도 반영 (옵션)
        aim_target_x, aim_target_y, aim_target_z = target_x, target_y, target_z

    elif aim_target_x is not None:
        # IBSM 타깃이 없으면 이전에 저장된 aim_target 사용
        target_x, target_y, target_z = aim_target_x, aim_target_y, aim_target_z
    else:
        # 타깃 자체가 없으면 그대로 유지
        return qe_command, qe_weight

    # 3) 스태빌라이저 업데이트 (QE_command / QE_weight 계산)
    QE_cmd, QE_w = yaw_stabilizer.update(
        time_val=time_val,
        player_x=player_x,
        player_y=player_y,
        player_z=player_z,
        player_turret_x=player_turret_x,
        target_x=target_x,
        target_y=target_y,
        target_z=target_z,
        body_yaw=body_yaw,
        body_AD_cmd=body_AD_cmd,
        body_AD_weight=body_AD_weight,
        player_speed=player_speed,
    )

    # 전역으로 저장해서 get_fcs 응답에서 바로 사용할 수 있게
    qe_command = QE_cmd
    qe_weight  = QE_w

############################### FCS 기능 ################################
# fcs 기능에 사용할 함수들


# fcs 기능 메인
def fcs_function(request_data : dict):
    data =  request_data


##################### IBSM이 호출할 FCS의 엔드포인트 #######################
@app.post("/get_fcs")
def get_fcs():
    # IBSM에서 받아온 데이터를 저장
    request_data = request.get_json(force=True, silent=True) or {}
    print("IBSM으로 부터 받은 데이터 : ", request_data)

    turret_control(request_data)

    # IBSM으로 보낼 데이터 : 
    response_data = {
        "QE_command" : qe_command,          # 포탑 좌 / 우 회전 방향 제어, string형, 'Q' 혹은 'E'
        "QE_weight" : qe_weight,            # 포탑 좌 / 우 회전 세기, float형
        "RF_command" : rf_command,          # 포신 상 / 하 방향 제어, string형, 'R' 혹은 'F'
        "RF_weight" : rf_weight,            # 포신 상 / 하 세기, float형
        "fire_command" : fire_command,      # 사격 여부, bool형, True or False
        "fire_target_pos" : fire_target_pos,        # 사격 대상, dict형, {"x": 15.0, "y": 25.0, "z": 0.0}
        "new_fire_point_pos" : new_fire_point_pos   # 현 위치 즉시 사격 불가 시 사격 가능 지점, dict형, {"x": 15.0, "y": 25.0, "z": 0.0}
    }
    print("IBSM으로 보낼 데이터 : ", response_data)

    # 호출자(IBSM)에게 결과 반환
    return jsonify(response_data)


################################ 메인매서드 ################################
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001, debug=True)