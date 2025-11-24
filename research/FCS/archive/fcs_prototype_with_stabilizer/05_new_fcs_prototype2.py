"""

스테빌라이저 + FCS 코드의 기본 뼈대

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
qe_weight = 0
rf_command = ""
rf_weight = 0
fire_command = False
fire_target_pos = None
new_fire_point_pos = None

######################## 스태빌라이져용 전역변수 ###########################
# 물체(장애물/적) 조준용 타깃 좌표 (IBSM에서 내려주는 좌표)
aim_target_x = None
aim_target_y = None
aim_target_z = None

# dt 및 "자이로(각속도)" 계산용 상태
prev_time       = None
prev_turret_x   = None   # 이전 프레임 포탑 yaw
prev_turret_y   = None   # 이전 프레임 포탑 pitch (pitch는 지금 안 쓰지만 각속도 계산 위해 보관)

# Yaw PI 제어기 상태 (적분항 저장)
yaw_int   = 0.0
YAW_INT_LIMIT   = 30.0  # deg·s (적분항 클램프)

# 웨이포인트 전환 완충용 (지금은 0부터 시작, 필요시 외부에서 세팅)
wp_switch_cooldown = 0

# 차체 회전(AD) → 포탑 QE 역보상 게인 (feed-forward)
AD_YAW_COMP_DEG = 8.0   # 개념용 (지금은 weight로 직접 사용)

# W 기반 기하학 미래예측용 상수
PREDICT_NOMINAL_MAX_SPEED = 25.0   # [게임 단위/s] 가정 최대 속도 (튜닝용)
PREDICT_BASE_HORIZON      = 0.30   # [s] 최소로 보는 미래 시간
PREDICT_MAX_HORIZON       = 0.80   # [s] 최대로 보는 미래 시간
PREDICT_ALPHA_YAW         = 0.60   # 현재 yaw_err vs 미래 yaw_err 블렌딩 비율 (0~1)

########################### FCS용 전역변수 ###############################
altitude_df = None              # csv 파일을 데이터프레임화 시킨 것을 저장할 전역 변수
altitude_grid = None            # altitude_df를 numpy 2d grid화 시킨 것을 저장할 전역변수
altitude_grid_shape = None      # (y크기, x크기) 형태로 그리드 크기 저장할 전역변수

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
# FCS 기능에 사용할 함수들
# 맵 종류에 맞는 Altatude Map csv 파일을 읽어와서 판다스 데이터프레임에 저장, 그리고 넘파이 2D그리드화(최초 1회)
def check_maptype(maptype: int):
    global altitude_df, altitude_grid, altitude_grid_shape

    if getattr(check_maptype, "_loaded_mt", None) == maptype and altitude_df is not None:
        return  # 이전과 같은 맵이라면, 맵 정보 재로딩을 하지 않음.

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    altitude_map_csv_path = os.path.join(BASE_DIR, "map_csvs")

    csv_file_names = {
        0: "00_forest_and_river_300x300.csv",
        1: "01_country_road_300x300.csv",
        2: "02_wildness_dry_300x300.csv",
        3: "03_simple_flat_300x300.csv",
    }

    if maptype not in csv_file_names:
        raise ValueError(f"Invalid map type: {maptype}")
    
    csv_path = os.path.join(altitude_map_csv_path, csv_file_names[maptype])

    altitude_df = pd.read_csv(csv_path)
    
    x_arr = altitude_df["x"].to_numpy(dtype=int)     # 데이터프레임의 x값들을 numpy 배열로 변환
    y_arr = altitude_df["y"].to_numpy(dtype=int)     # 데이터프레임의 y값들을 numpy 배열로 변환
    z_arr = altitude_df["z"].to_numpy(dtype=float)   # 데이터프레임의 z값들을 numpy 배열로 변환
    max_x = x_arr.max()                     # x 그리드 최대값
    max_y = y_arr.max()                     # y 그리드 최대값
    grid = np.zeros((max_y + 1, max_x + 1), dtype=float)        # 고도값들을 저장할 0으로만 가득 찬 2차원 배열 준비
    grid[y_arr, x_arr] = z_arr              # 각 (y, x)에 고도값(z)들을 넣기
    altitude_grid = grid                    # 위 2차원 넘파이 배열을 전역변수화
    altitude_grid_shape = grid.shape        # 위 2차원 넘파이 배열의 크기의 전역변수화
    check_maptype._loaded_mt = maptype      # 로딩한 맵 타입을 저장, 다음 로딩에는 생략할 수 있게 

# x와 y값을 입력받아 csv로 만든 넘파이 그리드를 참고해 z값(고도)을 반환하는 매서드
def altitude_calculator(x, y):
    global altitude_grid, altitude_grid_shape

    if altitude_grid is None:
        return 0                    # 맵 고도값 그리드가 없을 경우, 0을 반환하는 예외처리
    
    xi = int(round(x))              # 매서드로 들어온 x값의 소숫점 단위 이하를 제거
    yi = int(round(y))              # 매서드로 들어온 y값의 소숫점 단위 이하를 제거
    max_y, max_x = altitude_grid_shape              # 그리드 배열의 크기 불러오기
    if 0 <= yi < max_y and 0 <= xi < max_x:         # 매서드로 들어온 x, y값이 그리드 안에 해당할 경우,
        return float(altitude_grid[yi, xi])         # 해당하는 고도값 반환
    else:
        return 0                    # 들어온 x, y값이 그리드 범위를 넘어가는 숫자일 경우 0을 반환하는 예외처리
    
# 고각 계산기 매서드
# 수평거리 x, 높이차 y, 포구속도 v0이 주어졌을때, 어떤 발사각 θ에서 명중하는지 찾는 함수
def find_elevation_angle(x, y, v0, g=9.81):
    low = 0.01
    high = math.radians(89)
    for _ in range(1000):
        mid = (low + high) / 2
        cos2 = math.cos(mid) ** 2
        tan = math.tan(mid)
        y_calc = x * tan - (g * x**2) / (2 * v0**2 * cos2)
        if abs(y_calc - y) < 1e-6:
            return math.degrees(mid)
        if y_calc < y:
            low = mid
        else:
            high = mid
    return None

# 0~1 사이의 최적의 weight 값을 계산해 반환하는 매서드 (rf_weight 계산용)
def angle_to_weight(angle_diff_deg, max_angle=30.0, min_weight=0.0, max_weight=1.0, dead_zone=0.5):
    # angle_diff_deg: 목표 각도와의 차이
    # max_angle: 이 각도 이상 차이 나면 항상 max_weight
    # dead_zone: 이 각도보다 차이가 작으면 weight=0 (멈춤)
    diff = abs(angle_diff_deg)  # 목표 각도와의 차이를 절댓값만 남기는 가공

    if diff < dead_zone:    # 목표 각도와의 차이가 dead_zone보다 작을 경우, 0을 반환, 회전 멈춤. 미세한 각도차이는 보정 안하기
        return 0
    
    if diff >= max_angle:   # 목표 각도외의 차이가 최대 max_angle보다 클 경우, 무조건 최대 파워로 회전
        return max_weight   # 기본값 기준 1.0 반환
    
    # 위 두가지 경우에서 걸러지지 않은 나머지 상황
    t = (diff - dead_zone) / (max_angle - dead_zone)
    return min_weight + (max_weight - min_weight) * t   # dead_zone ~ max_angle 사이를 0~1로 선형 매핑해 반환  

# FCS 기능 메인
def fcs_function(request_data : dict):
    global rf_command, rf_weight, fire_command, fire_target_pos, new_fire_point_pos

    # 매 프레임 초기화 (stale 값 방지)
    rf_command = ""
    rf_weight  = 0.0
    fire_command = False
    new_fire_point_pos = None
    fire_target_pos = None
    
    # IBSM으로 부터 읽어온 값들을 계산에 쓰기 위한 변수로 저장(payload 누락에 대한 예외처리, 0 추가.)
    data =  request_data

    maptype = int(data.get("map_type", 0))      # 맵 타입
    check_maptype(maptype)
    enemy_pos_x = float(data.get("ibsm_target_pos", {}).get("x", 0))    # 적 x좌표 (topview 기준)
    enemy_pos_y = float(data.get("ibsm_target_pos", {}).get("y", 0))    # 적 y좌표 (topview 기준)
    my_pos_x = float(data.get("ally_body_pos", {}).get("x", 0))     # 내 x좌표 (topview 기준)
    my_pos_y = float(data.get("ally_body_pos", {}).get("y", 0))     # 내 y좌표 (topview 기준)
    my_turret_x = float(data.get("ally_turret_angle", {}).get("x", 0))    # 내 포탑 수평 기울기
    my_turret_y = float(data.get("ally_turret_angle", {}).get("y", 0))    # 내 포탑 수직 기울기
    my_chassis_x = float(data.get("ally_body_angle", {}).get("x", 0))    # 내 차체 x 기울기
    my_chassis_y = float(data.get("ally_body_angle", {}).get("y", 0))    # 내 차체 y 기울기
    my_chassis_z = float(data.get("ally_body_angle", {}).get("z", 0))    # 내 차체 z 기울기
    simulator_time = float(data.get("time", 0))                     # IDMS 기준 시간
    my_speed = float(data.get("ally_speed", 0))                     # 내 차체의 속도
    enemy_alt = altitude_calculator(enemy_pos_x, enemy_pos_y)   #위 읽어온 csv altatude map을 기반으로 현재 고도를 판단
    my_alt = altitude_calculator(my_pos_x, my_pos_y)  #위 읽어온 csv altatude map을 기반으로 현재 고도를 판단
    G = 9.81 # 중력가속도
    muzzle_velocity = 61 # 포탄의 초기속도(61m/s)
    fire_target_pos = {"x": enemy_pos_x, "y": enemy_pos_y, "z": enemy_alt}  #사격해야 할 적의 좌표
    
    print(data)  # IBSM에서 수신받은 값들 출력

    print(f'내 높이 : {my_alt}')
    print(f'적 높이 : {enemy_alt}')

    # 계산 1. 수평거리 및 고저차 계산
    dx = enemy_pos_x - my_pos_x
    dy = enemy_pos_y - my_pos_y
    horizontal_distance = math.sqrt(dx**2 + dy**2)      # topview 기준 나와 격멸대상 사이의 평면거리
    height_diff = enemy_alt - my_alt                    # 나와 격멸대상 사이의 고저차

    # 계산 2. 발사 각도(고각) 계산 (수치해석)
    elevation_angle = find_elevation_angle(horizontal_distance, height_diff, muzzle_velocity, G)

    if elevation_angle is None:         # 만약, find_elevation_angle로 탄도상 명중 가능한 각도를 못찾을 경우
        print("적 전차를 맞출 수 있는 발사 고각을 찾지 못했습니다.")
        fire_command = False
    else :                              # find_elevation_angle로 탄도상 명중 가능한 각도를 찾는데 성공했을 경우
        print(f"적 전차를 맞추기 위한 발사 고각: {elevation_angle:.2f}도")
        if elevation_angle > my_turret_y:
            rf_command = "R"                # 포신을 위로 올림
            delta_pitch = elevation_angle - my_turret_y
            rf_weight = angle_to_weight(delta_pitch, max_angle=20.0, dead_zone=0.5)
        elif elevation_angle < my_turret_y:
            rf_command = "F"                # 포신을 아래로 내림
            delta_pitch = elevation_angle - my_turret_y
            rf_weight = angle_to_weight(delta_pitch, max_angle=20.0, dead_zone=0.5)
        else:   # elevation_angle == my_body_y, rf_command 디폴트값 사용
            pass

    # 계산 3. 수평 방위각(아지무스) 계산 (12시 방향 기준, 시계방향 증가)
    azimuth_rad = math.atan2(dy, dx)                                    # 기본 atan2 각도
    azimuth_deg_math = math.degrees(azimuth_rad)                        # 일반적인 수학 좌표계 기준
    azimuth_deg_12oclock = (90 - azimuth_deg_math) % 360                # 시계방향 12시를 0도로 가정하고 시계방향으로 증가

    print(f"적 전차를 향한 수평 방위각(12시 기준, 시계방향): {azimuth_deg_12oclock:.2f}도")
    #if azimuth_deg_12oclock > my_turret_x:            # 내 포탑 수평각과 비교해서 Q와 E 결정하기
    #    qe_command = "Q"
    #    pass
    #elif azimuth_deg_12oclock < my_turret_x:
    #    qe_command = "E"
    #    pass
    #else:   # azimuth_deg_12oclock == my_turret_x, qe_command 디폴트값 사용
    #    pass

    # 계산 4. 포탑 수직 각도 제한 체크 (기준: 차체 수직각 +15도 ~ -5도, 최대 10도까지 허용)
    turret_min_angle = my_chassis_x - 5   # 최저 -5도까지만 허용
    turret_max_angle = my_chassis_x + 10  # 최대 10도까지만 허용

    if elevation_angle is not None:
        if turret_min_angle <= elevation_angle <= turret_max_angle:
            print(f"발사 고각({elevation_angle:.2f}도)는 포탑 수직 각도 제한 내에 있습니다. (최대 10도 기준)")
        else:
            print(f"발사 고각({elevation_angle:.2f}도)는 포탑 수직 각도 제한({turret_min_angle:.2f}도 ~ {turret_max_angle:.2f}도, 최대 10도 기준)를 벗어납니다.")
    else:
        print("적 전차를 맞출 수 있는 발사 고각을 찾지 못했습니다.")

    # 계산 5. 발사각 10도 기준 사정거리 계산
    theta_deg = 10
    theta_rad = math.radians(theta_deg)
    range_10deg = (muzzle_velocity ** 2) * math.sin(2 * theta_rad) / G  # 포물선 최대 사거리 공식: R = v² * sin(2θ) / g 사용
    print(f"전차 사정거리(발사각 10도 기준): {range_10deg:.2f} m")

    # 계산 6. 현재 전차와 적 전차 위치의 실제 사거리(직선 거리) 계산
    distance_3d = math.sqrt((enemy_pos_x - my_pos_x) ** 2 + (enemy_pos_y - my_pos_y) ** 2 + (enemy_alt - my_alt) ** 2)
    print(f"현재 전차와 적 전차 위치의 실제 사거리(직선 거리): {distance_3d:.2f} m")

    # 이동해야 할 위치 계산 후, x,y 좌표를 반환하는 계산기 매서드 (적 전차 방향으로 사정거리만큼 접근)
    def get_move_position(my_x, my_y, enemy_x, enemy_y, move_distance):
        dx = enemy_x - my_x
        dy = enemy_y - my_y
        total_distance = math.sqrt(dx**2 + dy**2)
        if total_distance == 0:         # 내가 적 좌표와 같은 x,y에 있을 경우, 0으로 나누는것 방지용
            return my_x, my_y
        ratio = (total_distance - move_distance) / total_distance  # 전체 거리 중 필요한 거리 만큼만 적 방향으로 이동
        new_x = my_x + dx * ratio
        new_y = my_y + dy * ratio
        return new_x, new_y             # 새로 가야할 x좌표, y좌표를 반환

    # 사정거리(발사각 10도 기준)
    required_distance = range_10deg

    # 만약 사격이 불가능할 경우, 사격 가능 지점(x, z좌표)을 산출해서 IBMS에게 전달
    in_elev_limit = (elevation_angle is not None and turret_min_angle <= elevation_angle)

    if (horizontal_distance > required_distance) or not(in_elev_limit):
        fire_command = False
        move_x, move_y = get_move_position(my_pos_x, my_pos_y, enemy_pos_x, enemy_pos_y, required_distance) # 새로 가야할 x좌표, y좌표를 반환하는 계산기에 넣음
        print(f"적 전차를 맞추려면 다음 위치까지 접근하세요:")
        print(f"이동 좌표: x={move_x:.2f}, y={move_y:.2f}")
        new_fire_point_pos = {"x": move_x, "y": move_y, "z": altitude_calculator(move_x, move_y)} # 새로 가야할 곳의 x, y, z 좌표

        # 이동 후 수평거리 및 고저차 재계산
        dx_new = enemy_pos_x - move_x
        dy_new = enemy_pos_y - move_y
        horizontal_distance_new = math.sqrt(dx_new**2 + dy_new**2)
        my_alt_new = altitude_calculator(move_x, move_y)
        height_diff_new = enemy_alt - my_alt_new

        # 이동 후 발사 고각(수직 각도) 재계산
        elevation_angle_new = find_elevation_angle(horizontal_distance_new, height_diff_new, muzzle_velocity, G)
        if elevation_angle_new is not None:
            print(f"이동 후 맞추기 위한 발사 고각(수직 각도): {elevation_angle_new:.2f}도")
        else:
            print("이동에도 불구하고, 적 전차를 맞출 수 있는 발사 고각을 찾지 못했습니다.")

        # 이동 후 수평 방위각(아지무스) 재계산
        azimuth_rad_new = math.atan2(dy_new, dx_new)
        azimuth_deg_math_new = math.degrees(azimuth_rad_new)
        azimuth_deg_12oclock_new = (90 - azimuth_deg_math_new) % 360
        print(f"이동 후 맞추기 위한 수평 방위각(12시 기준, 시계방향): {azimuth_deg_12oclock_new:.2f}도")


    # 만약 즉시 사격이 가능할 경우, IBMS에게 사격 명령 전달
    else:
        fire_command = True
        print("현재 위치에서 사격이 가능합니다.")
        print(f"맞추기 위한 발사 고각(수직 각도): {(elevation_angle + my_turret_y):.2f}도")
        print(f"맞추기 위한 수평 방위각(12시 기준, 시계방향): {azimuth_deg_12oclock:.2f}도")


##################### IBSM이 호출할 FCS의 엔드포인트 #######################
@app.post("/get_fcs")
def get_fcs():
    # IBSM에서 받아온 데이터를 저장
    request_data = request.get_json(force=True, silent=True) or {}
    print("IBSM으로 부터 받은 데이터 : ", request_data)

    turret_control(request_data)
    fcs_function(request_data)

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