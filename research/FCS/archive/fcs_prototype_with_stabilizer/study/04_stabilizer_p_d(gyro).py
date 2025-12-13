import os
from flask import Flask, request, jsonify
import math
import pandas as pd
import numpy as np
import time
"""
[Turret Yaw Stabilizer]
전차 포탑의 수평 회전(Yaw)을 제어하는 클래스입니다.

[제어 방식: P + D(Gyro Damping)]
1. P (Proportional): 목표 각도와의 오차만큼 회전 명령을 줌 (목표 추적)
2. Gyro Damping: 현재 회전 속도에 저항을 줌 (오버슈트 방지 및 부드러운 정지)
* I(적분) 제어는 반응성을 위해 제거되었습니다.
"""
##################### IBSM에 보낼 데이터의 기본값 (스태빌라이저 출력용) ##########################
qe_command = ""  # 포탑 회전 명령 (Q: 왼쪽, E: 오른쪽)
qe_weight = 0    # 회전 속도 가중치 (0.0 ~ 1.0)

######################## 스태빌라이져용 전역변수 ###########################
# 물체(장애물/적) 조준용 타깃 좌표 (마지막으로 수신된 타깃 위치 저장)
aim_target_x = None
aim_target_y = None
aim_target_z = None

# dt(델타 타임) 및 "자이로(각속도)" 계산용 이전 프레임 상태 저장 변수
prev_time       = None   # 이전 프레임의 시간값
prev_turret_x   = None   # 이전 프레임의 포탑 Yaw 각도
prev_turret_y   = None   # 이전 프레임의 포탑 Pitch 각도 (현재 로직에서는 미사용)

# ======================================================

def normalize_angle_deg(angle: float) -> float:
    """
    각도를 -180 ~ 180도로 정규화하는 함수
    예: 370도 -> 10도, -190도 -> 170도
    목적: 최단 거리 회전 방향을 계산하기 위함
    """
    return (angle + 180.0) % 360.0 - 180.0

# ======================================================

class TurretYawStabilizer:
    """
    [Turret Yaw Stabilizer]
    전차 포탑의 수평 회전(Yaw)을 제어하는 클래스입니다.
    
    [제어 방식: P + Gyro Damping]
    1. P (Proportional): 목표 각도와의 오차만큼 회전 명령을 줌 (목표 추적)
    2. Gyro Damping: 현재 회전 속도에 저항을 줌 (오버슈트 방지 및 부드러운 정지)
    * I(적분) 제어는 반응성을 위해 제거되었습니다.
    """
    def __init__(self):
        # ----------------------------------------
        # 상태 변수 초기화
        # ----------------------------------------
        self.prev_time     = None
        self.prev_turret_x = None
        self.prev_turret_y = None

        # ----------------------------------------
        # PID 제어 파라미터 (튜닝 포인트)
        # ----------------------------------------
        self.Kp_yaw       = 0.045   # P게인: 값이 클수록 목표를 향해 더 빠르게 회전하지만 오버슈트 위험 증가
        self.Kd_yaw_gyro  = 0.015   # D게인(자이로): 값이 클수록 회전 저항이 커져서 움직임이 묵직해짐

        # ----------------------------------------
        # 임계값 설정 (Deadband & Limit)
        # ----------------------------------------
        self.YAW_DEADBAND   = 0.5   # 목표와의 오차가 0.5도 이내면 제어 중지 (떨림 방지)
        self.GYRO_DEADBAND  = 1.0   # 회전 속도가 이 값 이하면 정지한 것으로 간주
        self.AD_DEADBAND    = 0.05  # (참고용) 차체 선회 관련 데드밴드
        self.MAX_QE         = 1.0   # 제어 출력의 최댓값 (1.0 = 100% 출력)
        self.MIN_QE_OUTPUT  = 0.02  # 제어 출력의 최솟값 (이보다 작으면 0으로 처리)

    # ------------------------------------------------------------------
    # 시간 간격(dt) 및 각속도(Gyro) 계산 함수
    # ------------------------------------------------------------------
    def _compute_dt_and_gyro(self, time_val, turret_x, turret_y):
        # 1. dt (Delta Time) 계산
        # 기본값: 60 FPS 기준 약 0.016초
        dt = 0.016  

        if self.prev_time is None:
            self.prev_time = time_val
        else:
            dt_raw = time_val - self.prev_time
            # 시간이 정상적으로 흘렀을 때만 dt 업데이트
            if dt_raw > 0:
                dt = dt_raw
            self.prev_time = time_val

        # 2. 자이로(각속도) 계산: (현재각도 - 이전각도) / 시간
        if self.prev_turret_x is None or self.prev_turret_y is None:
            gyro_yaw_rate = 0.0
        else:
            # 각도 차이 계산 (정규화 포함)
            dyaw = normalize_angle_deg(turret_x - self.prev_turret_x)
            
            if dt > 0.0:
                gyro_yaw_rate = dyaw / dt  # 각속도 = 거리 / 시간
            else:
                gyro_yaw_rate = 0.0

        # 현재 상태를 다음 프레임 비교를 위해 저장
        self.prev_turret_x = turret_x
        self.prev_turret_y = turret_y

        return dt, gyro_yaw_rate

    # ------------------------------------------------------------------
    # 메인 제어 루프 (입력 데이터를 받아 Q/E 명령 및 강도 계산)
    # ------------------------------------------------------------------
    def update(
        self,
        *,
        time_val: float,        # 현재 시뮬레이션 시간
        player_x: float,        # 내 탱크 X 좌표
        player_y: float,        # 내 탱크 Y 좌표
        player_z: float,        # 내 탱크 Z 좌표
        player_turret_x: float, # 내 포탑의 현재 Yaw 각도
        target_x: float,        # 목표물 X 좌표
        target_y: float,        # 목표물 Y 좌표 (높이)
        target_z: float,        # 목표물 Z 좌표
        body_yaw: float,        # 차체의 Yaw 각도
        body_AD_cmd: str,       # 차체 회전 명령 (참고용)
        body_AD_weight: float,  # 차체 회전 가중치
        player_speed: float,    # 현재 속도
        body_WS_weight: float = 0.0 # 전진/후진 가중치
    ):
        # 1. dt 및 현재 포탑의 회전 속도(자이로) 계산
        dt, gyro_yaw_rate = self._compute_dt_and_gyro(time_val, player_turret_x, 0.0)

        # 2. 목표 지점까지의 각도(Target Yaw) 계산
        dx = target_x - player_x
        dz = target_z - player_z
        
        # atan2를 사용하여 좌표(x, z)를 각도(라디안 -> 디그리)로 변환
        # IBSM 좌표계 특성에 맞춰 계산 (일반적으로수학에선 atan2(y, x)지만 여기선 x, z 사용)
        target_yaw = math.degrees(math.atan2(dx, dz))
        if target_yaw < 0:
            target_yaw += 360.0 # 0~360도 범위로 변환

        # 3. 현재 오차 계산 (목표 각도 - 내 포탑 각도)
        # normalize_angle_deg를 통해 -180 ~ 180도로 변환 (최단 회전 방향 찾기)
        yaw_err_now = normalize_angle_deg(target_yaw - player_turret_x)
        
        # 4. Deadband 체크 (오차가 너무 작고, 움직임도 거의 없으면 제어 안 함)
        if abs(yaw_err_now) < self.YAW_DEADBAND and abs(gyro_yaw_rate) < self.GYRO_DEADBAND:
            return "", 0.0

        # 5. P-Gyro 제어량 계산
        # P항: 목표를 향해 가려는 힘 (오차 * P게인)
        P = self.Kp_yaw * yaw_err_now
        
        # D항(Gyro Damping): 현재 회전 속도를 줄이려는 힘 (속도 * -D게인)
        # 움직이는 반대 방향으로 힘을 주어 관성을 제어함
        D = -self.Kd_yaw_gyro * gyro_yaw_rate 

        # 최종 제어 입력값 합산 ($u = P + D$)
        u = P + D

        # 6. 출력 제한 (Clamping)
        # 모터/게임 입력이 받아들일 수 있는 최대치(1.0)를 넘지 않도록 제한
        if u > self.MAX_QE:
            u = self.MAX_QE
        elif u < -self.MAX_QE:
            u = -self.MAX_QE

        # 최소 출력 확인 (너무 작은 값은 무시)
        if abs(u) < self.MIN_QE_OUTPUT:
            return "", 0.0

        # 7. 방향 결정 및 명령 반환
        # u가 양수면 오른쪽(E), 음수면 왼쪽(Q)
        # (시뮬레이션 좌표계에 따라 Q/E 방향이 반대일 경우 여기서 "Q", "E"를 서로 바꾸면 됨)
        if u > 0:
            return "E", u
        else:
            return "Q", -u # 크기는 양수로 반환
        
# ======================================================

# 전역 스태빌라이저 인스턴스 생성 (서버 실행 시 1회 생성)
yaw_stabilizer = TurretYawStabilizer()

def turret_control(request_data: dict):
    """
    [Wrapper Function]
    IBSM(통합 시스템)에서 들어온 JSON 요청을 파싱하여 스태빌라이저를 실행하고,
    결과값(QE 명령, 가중치)을 전역 변수에 업데이트하는 함수
    """
    global qe_command, qe_weight, aim_target_x, aim_target_y, aim_target_z
    
    # 1. 데이터 파싱 (JSON -> 변수)
    # 딕셔너리 get 메소드를 사용하여 키가 없을 경우 기본값(0.0)을 사용해 에러 방지
    time_val = float(request_data.get("time", 0.0))

    ally_pos   = request_data.get("ally_body_pos", {}) or {}     # 내 차체 위치
    ally_ang   = request_data.get("ally_body_angle", {}) or {}   # 내 차체 각도
    turret_ang = request_data.get("ally_turret_angle", {}) or {} # 내 포탑 각도
    target_pos = request_data.get("ibsm_target", {}) or {}       # 목표물 위치

    player_x = float(ally_pos.get("x", 0.0))
    player_y = float(ally_pos.get("y", 0.0))
    player_z = float(ally_pos.get("z", 0.0))

    player_turret_x = float(turret_ang.get("x", 0.0))   # 포탑 Yaw (수평 회전)
    
    body_yaw = float(ally_ang.get("y", 0.0))            # 차체 Yaw

    player_speed = float(request_data.get("ally_speed", 0.0))

    # 차체 주행 명령 상태 (참고용 데이터)
    body_AD_cmd    = request_data.get("AD_command", "")
    body_AD_weight = float(request_data.get("AD_weight", 0.0))
    body_WS_weight = float(request_data.get("WS_weight", 0.0)) 

    # 2. 타깃 설정 로직
    # 요청 데이터에 새로운 타깃 정보가 있으면 업데이트, 없으면 기존 타깃 유지
    if "x" in target_pos and "y" in target_pos and "z" in target_pos:
        target_x = float(target_pos.get("x", 0.0))
        target_y = float(target_pos.get("y", 0.0))
        target_z = float(target_pos.get("z", 0.0))
        # 전역 변수에 타깃 저장 (다음 프레임에 타깃 정보가 안 올 경우를 대비)
        aim_target_x, aim_target_y, aim_target_z = target_x, target_y, target_z

    elif aim_target_x is not None:
        # 새로운 타깃 정보가 없으면 이전에 저장된 타깃 사용
        target_x, target_y, target_z = aim_target_x, aim_target_y, aim_target_z
    else:
        # 타깃 정보가 아예 없으면 아무것도 하지 않음 (기존 명령 유지)
        return qe_command, qe_weight

    # 3. 스태빌라이저 업데이트 (계산 수행)
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
        body_WS_weight=body_WS_weight
    )

    # 4. 결과값 전역 변수 업데이트
    qe_command = QE_cmd
    qe_weight  = QE_w