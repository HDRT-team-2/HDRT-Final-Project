import os
from flask import Flask, request, jsonify
import math
import pandas as pd
import numpy as np
import time

"""
[Turret Yaw Stabilizer]
전차 포탑의 수평 회전(Yaw)을 제어하는 클래스입니다.

[제어 방식: P + D(Gyro Damping) + FF(Feed-Forward)]
1. P (Proportional): 목표물과의 각도 차이에 비례하여 회전 (스프링 역할)
2. Gyro Damping (D): 현재 회전 속도에 저항하여 오버슈트 및 진동 억제 (댐퍼 역할)
3. FF (Feed-Forward): 차체 선회 입력(A/D) 감지 시, 반대 방향으로 즉시 보상 입력 (예측 제어)
   - I(적분) 제거: 반응성 향상 및 타깃 변경 시 헌팅(Hunting) 방지
"""

##################### IBSM에 보낼 데이터의 기본값 (스태빌라이저 출력용) ##########################
qe_command = ""  # 최종 명령 (Q: 좌회전, E: 우회전)
qe_weight = 0    # 회전 강도 (0.0 ~ 1.0)

######################## 스태빌라이져용 전역변수 ###########################
# 물체(장애물/적) 조준용 타깃 좌표 (마지막 수신 값 유지용)
aim_target_x = None
aim_target_y = None
aim_target_z = None

# dt(델타타임) 및 "자이로(각속도)" 계산용 이전 프레임 상태 저장
prev_time       = None
prev_turret_x   = None   # 이전 프레임 포탑 yaw
prev_turret_y   = None   # 이전 프레임 포탑 pitch (현재 로직엔 미사용)

# 웨이포인트 전환 완충용 (추후 확장용 변수)
wp_switch_cooldown = 0

# ======================================================

def normalize_angle_deg(angle: float) -> float:
    """
    [각도 정규화 함수]
    입력된 각도를 -180 ~ +180도 사이로 변환합니다.
    예: 270도 -> -90도 / -190도 -> +170도
    목적: 포탑이 360도를 돌아가는 것이 아니라, 가장 가까운 방향(최단 경로)으로 회전하게 함.
    """
    return (angle + 180.0) % 360.0 - 180.0

# ======================================================

class TurretYawStabilizer:
    """
    [핵심 제어 클래스]
    P + Gyro Damping + Feed-Forward 알고리즘 구현체
    """
    def __init__(self):
        # ----------------------------------------
        # 1. 상태 변수 초기화 (미분 계산용)
        # ----------------------------------------
        self.prev_time     = None
        self.prev_turret_x = None
        self.prev_turret_y = None

        # ----------------------------------------
        # 2. 제어 게인 (Tuning Points) - 감도 조절
        # ----------------------------------------
        self.Kp_yaw       = 0.045   # P게인: 목표 추적 반응성 (높을수록 빠름)
        self.Kd_yaw_gyro  = 0.015   # D게인: 회전 저항력 (높을수록 묵직하고 부드러움)

        # ----------------------------------------
        # 3. 임계값 및 제한 (Thresholds & Limits)
        # ----------------------------------------
        self.YAW_DEADBAND   = 0.5   # 목표 오차가 0.5도 미만이면 제어 중지 (떨림 방지)
        self.GYRO_DEADBAND  = 1.0   # 회전 속도가 매우 느리면 정지한 것으로 간주
        self.AD_DEADBAND    = 0.05  # 조향 입력 데드밴드
        self.MAX_QE         = 1.0   # 출력 최대값 (100%)
        self.MIN_QE_OUTPUT  = 0.02  # 출력 최소값 (모터 구동 최소 전압 유사 개념)

    # ------------------------------------------------------------------
    # [내부 함수] 시간 간격(dt) 및 각속도(Gyro) 계산
    # ------------------------------------------------------------------
    def _compute_dt_and_gyro(self, time_val, turret_x, turret_y):
        # 기본 dt: 60FPS 기준 약 0.016초 (예외 상황 대비용)
        dt = 0.016  

        # dt 계산 (현재 시간 - 이전 시간)
        if self.prev_time is None:
            self.prev_time = time_val
        else:
            dt_raw = time_val - self.prev_time
            if dt_raw > 0:
                dt = dt_raw
            self.prev_time = time_val

        # 자이로(각속도) 계산: (각도 변화량) / dt
        if self.prev_turret_x is None or self.prev_turret_y is None:
            gyro_yaw_rate = 0.0
        else:
            # 정규화를 통해 359도 -> 1도 넘어가는 경계선 문제 해결
            dyaw = normalize_angle_deg(turret_x - self.prev_turret_x)
            
            if dt > 0.0:
                gyro_yaw_rate = dyaw / dt # 도/초 (deg/s)
            else:
                gyro_yaw_rate = 0.0

        # 다음 프레임 비교를 위해 현재 값 저장
        self.prev_turret_x = turret_x
        self.prev_turret_y = turret_y

        return dt, gyro_yaw_rate

    # ------------------------------------------------------------------
    # [메인 함수] 입력 데이터를 받아 최종 제어 명령(Q/E, Weight) 반환
    # ------------------------------------------------------------------
    def update(
        self,
        *,
        time_val: float,
        player_x: float,
        player_y: float,
        player_z: float,
        player_turret_x: float,     # 현재 포탑 Yaw
        target_x: float,
        target_y: float,
        target_z: float,
        body_yaw: float,            # 차체 Yaw
        body_AD_cmd: str,           # 차체 조향 명령 (A/D) - FF 제어용
        body_AD_weight: float,      # 차체 조향 강도
        player_speed: float,
        body_WS_weight: float = 0.0 # 전진 가중치
    ):
        # 1. dt 및 현재 포탑 회전 속도(자이로) 계산
        dt, gyro_yaw_rate = self._compute_dt_and_gyro(time_val, player_turret_x, 0.0)

        # 2. 목표 각도(Target Yaw) 계산
        dx = target_x - player_x
        dz = target_z - player_z
        
        # atan2(dx, dz): Unity/Unreal 등 Z축이 전방인 좌표계 기준 각도 산출
        target_yaw = math.degrees(math.atan2(dx, dz))
        if target_yaw < 0:
            target_yaw += 360.0

        # 3. 현재 오차(Error) 계산 (목표 각도 - 현재 각도)
        # normalize_angle_deg 사용: -180 ~ 180도로 변환하여 최단 회전 방향 도출
        yaw_err_now = normalize_angle_deg(target_yaw - player_turret_x)
        
        # 4. 데드밴드(Deadband) 체크
        # 오차가 매우 작고(0.5도 미만), 포탑이 거의 정지 상태라면 제어를 멈춤
        if abs(yaw_err_now) < self.YAW_DEADBAND and abs(gyro_yaw_rate) < self.GYRO_DEADBAND:
            return "", 0.0

        # =================================================================
        # [Feed-Forward Control] 선회 보상 로직
        # 차체가 회전하려는 순간(키 입력), 포탑을 미리 반대 방향으로 돌려 조준선 유지
        # =================================================================
        u_ff = 0.0
        K_FF_AD = 0.4  # FF 게인: 차체 회전 속도 대비 포탑 반대 회전 비율 조절
        
        if body_AD_cmd == "D":      # 차체 우회전 시
            u_ff = -K_FF_AD * float(body_AD_weight) # 포탑 좌회전(-) 힘 추가
        elif body_AD_cmd == "A":    # 차체 좌회전 시
            u_ff = +K_FF_AD * float(body_AD_weight) # 포탑 우회전(+) 힘 추가

        # =================================================================
        # [Feedback Control] P + Gyro Damping
        # =================================================================
        
        # P 제어 (Proportional): "목표를 봐라"
        # 오차(yaw_err_now)에 비례하여 회전
        P = self.Kp_yaw * yaw_err_now
        
        # Gyro Damping (Derivative 성격): "너무 빨리 돌지 마라 / 흔들리지 마라"
        # 현재 회전 속도(gyro_yaw_rate)의 반대 방향으로 저항을 줌
        # 순수 미분제어(오차의 변화율)보다 노이즈에 강하고, 물리적 댐퍼와 유사하게 작동
        D = -self.Kd_yaw_gyro * gyro_yaw_rate 

        # 5. 최종 제어 입력 합산 ($u = P + D + FF$)
        u = P + D + u_ff

        # 6. 출력 제한 (Clamping)
        # 시뮬레이터가 허용하는 최대 입력값(1.0)을 넘지 않도록 자름
        if u > self.MAX_QE:
            u = self.MAX_QE
        elif u < -self.MAX_QE:
            u = -self.MAX_QE

        # 7. 최소 출력 처리 (너무 작은 입력은 무시)
        if abs(u) < self.MIN_QE_OUTPUT:
            return "", 0.0

        # 8. 최종 명령 결정 (방향 및 크기 분리)
        # u > 0: 우회전(E), u < 0: 좌회전(Q)
        if u > 0:
            return "E", u
        else:
            return "Q", -u # 크기는 항상 양수로 전달
        
# ======================================================

# 전역 스태빌라이저 인스턴스 (서버 시작 시 1회 생성)
yaw_stabilizer = TurretYawStabilizer()

def turret_control(request_data: dict):
    """
    [IBSM -> FCS Wrapper]
    외부 데이터(JSON)를 파싱하여 스태빌라이저 알고리즘을 수행하고,
    결과값(QE Command, Weight)을 전역 변수에 갱신하는 함수
    """
    global qe_command, qe_weight, aim_target_x, aim_target_y, aim_target_z
    
    # 1. JSON 데이터 파싱 (안전한 처리를 위해 .get() 및 기본값 사용)
    time_val = float(request_data.get("time", 0.0))

    ally_pos   = request_data.get("ally_body_pos", {}) or {}     # 내 위치
    ally_ang   = request_data.get("ally_body_angle", {}) or {}   # 내 회전값
    turret_ang = request_data.get("ally_turret_angle", {}) or {} # 포탑 회전값
    target_pos = request_data.get("ibsm_target", {}) or {}       # 타깃 위치

    player_x = float(ally_pos.get("x", 0.0))
    player_y = float(ally_pos.get("y", 0.0))
    player_z = float(ally_pos.get("z", 0.0))

    player_turret_x = float(turret_ang.get("x", 0.0))   # 포탑 Yaw (현재 각도)
    body_yaw = float(ally_ang.get("y", 0.0))            # 차체 Yaw
    player_speed = float(request_data.get("ally_speed", 0.0))

    # 차체 조작 명령 수신 (FF 제어에 사용됨)
    body_AD_cmd    = request_data.get("AD_command", "")     # "A" or "D"
    body_AD_weight = float(request_data.get("AD_weight", 0.0)) 
    body_WS_weight = float(request_data.get("WS_weight", 0.0)) 

    # 2. 타깃 설정 로직
    # 새 타깃 데이터가 있으면 갱신, 없으면 기존 타깃(aim_target_*) 유지
    if "x" in target_pos and "y" in target_pos and "z" in target_pos:
        target_x = float(target_pos.get("x", 0.0))
        target_y = float(target_pos.get("y", 0.0))
        target_z = float(target_pos.get("z", 0.0))
        aim_target_x, aim_target_y, aim_target_z = target_x, target_y, target_z

    elif aim_target_x is not None:
        target_x, target_y, target_z = aim_target_x, aim_target_y, aim_target_z
    else:
        # 타깃이 아예 없으면 제어하지 않음 (기존 명령 유지 또는 정지)
        return qe_command, qe_weight

    # 3. 스태빌라이저 업데이트 (핵심 연산 수행)
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
        body_AD_cmd=body_AD_cmd,        # [중요] 피드포워드를 위한 차체 조향 명령 전달
        body_AD_weight=body_AD_weight,  # [중요] 차체 조향 강도 전달
        player_speed=player_speed,
        body_WS_weight=body_WS_weight
    )

    # 4. 계산된 결과를 전역 변수에 업데이트 (IBSM 응답용)
    qe_command = QE_cmd
    qe_weight  = QE_w