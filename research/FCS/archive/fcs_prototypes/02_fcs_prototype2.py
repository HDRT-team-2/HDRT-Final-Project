"""
FCS 모듈 Prototype2

credit by : oixxta

FCS와 IBSM과의 실시간 서버통신 구현 포함.

지형 고도 + 포탄 탄도식을 이용해서, 지금 자세에서 적을 쏠 수 있는지 판단하고
못 쏘면 ‘어디까지 접근해야 쏠 수 있는지’ 좌표를 IBSM에 돌려주는 FCS 서버.
"""
import os
from flask import Flask, request, jsonify
import math
import pandas as pd
import numpy as np

##### Flask 추가 #####
app = Flask(__name__)

##### csv 파일 사용 관련 전역변수 선언 #####
altitude_df = None              # csv 파일을 데이터프레임화 시킨 것을 저장할 전역 변수
altitude_grid = None            # altitude_df를 numpy 2d grid화 시킨 것을 저장할 전역변수
altitude_grid_shape = None      # (y크기, x크기) 형태로 그리드 크기 저장할 전역변수

##### 맵 종류에 맞는 Altatude Map csv 파일을 읽어와서 판다스 데이터프레임에 저장, 그리고 넘파이 2D그리드화(최초 1회) #####
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


##### x와 y값을 입력받아 csv로 만든 넘파이 그리드를 참고해 z값(고도)을 반환하는 매서드 #####
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

##### 고각 계산기 매서드 #####
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

##### 0~1 사이의 최적의 weight 값을 계산해 반환하는 매서드 #####
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
    
##### FCS 주요 로직 #####
def fcs_function(payload: dict):
    ### IBSM으로 부터 읽어온 값들을 계산에 쓰기 위한 변수로 저장(payload 누락에 대한 예외처리, 0 추가.)
    maptype = int(payload.get("Map_type", 0))                   # 맵 타입
    check_maptype(maptype)
    enemy_pos_x = float(payload.get("ibsm_target", {}).get("x", 0))    # 적 x좌표 (topview 기준)
    enemy_pos_y = float(payload.get("ibsm_target", {}).get("y", 0))    # 적 y좌표 (topview 기준)
    my_pos_x = float(payload.get("ally_body_pos", {}).get("x", 0))     # 내 x좌표 (topview 기준)
    my_pos_y = float(payload.get("ally_body_pos", {}).get("y", 0))     # 내 y좌표 (topview 기준)
    my_body_x = float(payload.get("ally_turret_angle", {}).get("X", 0))    # 내 포탑 수평 기울기
    my_body_y = float(payload.get("ally_turret_angle", {}).get("Y", 0))    # 내 차체(+포탑) 수직 기울기
    simulator_time = float(payload.get("time", 0))                     # IDMS 기준 시간
    my_speed = float(payload.get("ally_speed", 0))                     # 내 차체의 속도
    enemy_alt = altitude_calculator(enemy_pos_x, enemy_pos_y)   #위 읽어온 csv altatude map을 기반으로 현재 고도를 판단
    my_alt = altitude_calculator(my_pos_x, my_pos_y)  #위 읽어온 csv altatude map을 기반으로 현재 고도를 판단
    G = 9.81 # 중력가속도
    muzzle_velocity = 61 # 포탄의 초기속도(61m/s)

    ### IBSM에게 보낼 값들을 담을 변수들 선언 및 기본값 지정
    qe_command = ""
    qe_weight = 0
    rf_command = ""
    rf_weight = 0
    fire_command = False
    fire_target = [enemy_pos_x, enemy_pos_y, enemy_alt]
    new_fire_point = None

    ### 계산 1. 수평거리 및 고저차 계산
    dx = enemy_pos_x - my_pos_x
    dy = enemy_pos_y - my_pos_y
    horizontal_distance = math.sqrt(dx**2 + dy**2)      # topview 기준 나와 격멸대상 사이의 평면거리
    height_diff = enemy_alt - my_alt                    # 나와 격멸대상 사이의 고저차

    ### 계산 2. 발사 각도(고각) 계산 (수치해석)
    elevation_angle = find_elevation_angle(horizontal_distance, height_diff, muzzle_velocity, G)

    if elevation_angle is None:         # 만약, find_elevation_angle로 탄도상 명중 가능한 각도를 못찾을 경우
        print("적 전차를 맞출 수 있는 발사 고각을 찾지 못했습니다.")
        fire_command = False
    else :                              # find_elevation_angle로 탄도상 명중 가능한 각도를 찾는데 성공했을 경우
        print(f"적 전차를 맞추기 위한 발사 고각: {elevation_angle:.2f}도")
        if elevation_angle > my_body_y:
            rf_command = "R"                # 포신을 위로 올림
        elif elevation_angle < my_body_y:
            rf_command = "F"                # 포신을 아래로 내림
        else:   # elevation_angle == my_body_y, rf_command 디폴트값 사용
            pass

    ### 계산 3. 수평 방위각(아지무스) 계산 (12시 방향 기준, 시계방향 증가)
    azimuth_rad = math.atan2(dy, dx)                                    # 기본 atan2 각도
    azimuth_deg_math = math.degrees(azimuth_rad)                        # 일반적인 수학 좌표계 기준
    azimuth_deg_12oclock = (90 - azimuth_deg_math) % 360                # 시계방향 12시를 0도로 가정하고 시계방향으로 증가

    print(f"적 전차를 향한 수평 방위각(12시 기준, 시계방향): {azimuth_deg_12oclock:.2f}도")
    if azimuth_deg_12oclock > my_body_x:            # 내 포탑 수평각과 비교해서 Q와 E 결정하기
        qe_command = "Q"
    elif azimuth_deg_12oclock < my_body_x:
        qe_command = "E"
    else:   # azimuth_deg_12oclock == my_body_x, qe_command 디폴트값 사용
        pass

    ### 계산 4. 포탑 수직 각도 제한 체크 (기준: 차체 수직각 +15도 ~ -5도, 최대 10도까지 허용)
    turret_min_angle = my_body_y - 5   # 최저 -5도까지만 허용
    turret_max_angle = my_body_y + 10  # 최대 10도까지만 허용

    if elevation_angle is not None:
        if turret_min_angle <= elevation_angle <= turret_max_angle:
            print(f"발사 고각({elevation_angle:.2f}도)는 포탑 수직 각도 제한 내에 있습니다. (최대 10도 기준)")
        else:
            print(f"발사 고각({elevation_angle:.2f}도)는 포탑 수직 각도 제한({turret_min_angle:.2f}도 ~ {turret_max_angle:.2f}도, 최대 10도 기준)를 벗어납니다.")
    else:
        print("적 전차를 맞출 수 있는 발사 고각을 찾지 못했습니다.")

    ### 계산 5. 발사각 10도 기준 사정거리 계산
    theta_deg = 10
    theta_rad = math.radians(theta_deg)
    range_10deg = (muzzle_velocity ** 2) * math.sin(2 * theta_rad) / G  # 포물선 최대 사거리 공식: R = v² * sin(2θ) / g 사용
    print(f"전차 사정거리(발사각 10도 기준): {range_10deg:.2f} m")

    ### 계산 6. 현재 전차와 적 전차 위치의 실제 사거리(직선 거리) 계산
    distance_3d = math.sqrt((enemy_pos_x - my_pos_x) ** 2 + (enemy_pos_y - my_pos_y) ** 2 + (enemy_alt - my_alt) ** 2)
    print(f"현재 전차와 적 전차 위치의 실제 사거리(직선 거리): {distance_3d:.2f} m")

    ### 이동해야 할 위치 계산 후, x,y 좌표를 반환하는 계산기 매서드 (적 전차 방향으로 사정거리만큼 접근)
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

    ### 사정거리(발사각 10도 기준)
    required_distance = range_10deg

    ### 최적의 QE, RF weight 계산 : 추후에 더 적절한 위치로 옮길것. ###
    delta_yaw = azimuth_deg_12oclock - my_body_x
    delta_pitch = elevation_angle - my_body_y
    qe_weight = angle_to_weight(delta_yaw, max_angle=60.0, dead_zone=1.0)
    rf_weight = angle_to_weight(delta_pitch, max_angle=20.0, dead_zone=0.5)


    ### 만약 사격이 불가능할 경우, 사격 가능 지점(x, z좌표)을 산출해서 IBMS에게 전달 #####
    if distance_3d > required_distance:
        fire_command = False
        move_x, move_y = get_move_position(my_pos_x, my_pos_y, enemy_pos_x, enemy_pos_y, required_distance) # 새로 가야할 x좌표, y좌표를 반환하는 계산기에 넣음
        print(f"적 전차를 맞추려면 다음 위치까지 접근하세요:")
        print(f"이동 좌표: x={move_x:.2f}, y={move_y:.2f}")
        new_fire_point = [move_x, move_y, altitude_calculator(move_x, move_y)]  # 새로 가야할 곳의 x, y, z 좌표

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


    ##### 만약 즉시 사격이 가능할 경우, IBMS에게 사격 명령 전달 #####
    else:
        fire_command = True
        print("현재 위치에서 사격이 가능합니다.")
        print(f"맞추기 위한 발사 고각(수직 각도): {(elevation_angle + my_body_y):.2f}도")
        print(f"맞추기 위한 수평 방위각(12시 기준, 시계방향): {azimuth_deg_12oclock:.2f}도")

    ##### IBSM에게 보낼 값들 #####
    result = {
        "QE_command" : qe_command,          # 포탑 좌 / 우 회전 방향 제어, string형, 'Q' 혹은 'E'
        "QE_weight" : qe_weight,            # 포탑 좌 / 우 회전 세기, float형
        "RF_command" : rf_command,          # 포신 상 / 하 방향 제어, string형, 'R' 혹은 'F'
        "RF_weight" : rf_weight,            # 포신 상 / 하 세기, float형
        "Fire_command" : fire_command,      # 사격 여부, bool형, True or False
        "Fire_target" : fire_target,        # 사격 대상, list형, [x, y, z]
        "new_fire_point" : new_fire_point   # 현 위치 즉시 사격 불가 시 사격 가능 지점, list형, [x, y, z]
    }

    return result


##### IBSM이 호출할 FCS의 엔드포인트 #####
@app.post("/get_fcs")
def get_fcs():
    payload = request.get_json(force=True, silent=True) or {}

    # 핵심 계산
    result = fcs_function(payload)

    # 호출자(IBSM)에게 결과 반환
    return jsonify(result)

##### 메인 메서드 #####
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)