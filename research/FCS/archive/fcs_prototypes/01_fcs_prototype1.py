"""
FCS 모듈 Prototype1

credit by : oixxta

FCS의 단순 알고리즘 구현

IBSM으로부터 json으로 받아와야 하는 값들은 임시로 더미값.
맵은 Forest and River(maptype = 0) 맵으로 테스트용.
"""
import os
import math
import pandas as pd

##### IBSM으로부터 현재 맵 종류를 수신받음.(최초 1회) #####
maptype = 0

##### 맵 종류에 맞는 Altatude Map csv 파일을 읽어와서 판다스 데이터프레임에 저장.(최초 1회) #####
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
altitude_map_csv_path = os.path.join(BASE_DIR, "map_csvs")
if maptype == 0:
    csv_path = os.path.join(altitude_map_csv_path, "00_forest_and_river_300x300.csv")
elif maptype == 1:
    csv_path = os.path.join(altitude_map_csv_path, "01_country_road_300x300.csv")
elif maptype == 2:
    csv_path = os.path.join(altitude_map_csv_path, "02_wildness_dry_300x300.csv")
elif maptype == 3:
    csv_path = os.path.join(altitude_map_csv_path, "03_simple_flat_300x300.csv")
else:
    raise ValueError('fail to read map type!')

altitude_df = pd.read_csv(csv_path)

##### IBSM으로부터 플레이어 x, y, z좌표, 차체 회전각 수신, 격멸 대상의 x, y, z좌표 수신. #####
def altatude_calculator(x, y):  # x와 y값을 입력받아 csv를 참고해 z값(고도)을 반환하는 매서드
    filtered = altitude_df[(altitude_df["x"] == x) & (altitude_df["y"] == y)]
    if not filtered.empty:
        return filtered["z"].iloc[0]
    else:
        return 0

enemy_pos_x = 135
enemy_pos_y = 276
enemy_alt = altatude_calculator(enemy_pos_x, enemy_pos_y)   #위 읽어온 csv altatude map을 기반으로 현재 고도를 판단
my_pos_x = 118.82
my_pos_y = 230.48
my_alt = altatude_calculator(my_pos_x, my_pos_y)  #위 읽어온 csv altatude map을 기반으로 현재 고도를 판단
my_body_y = 7.62      #차체(포탑)의 기울기

simulator_time = 0
my_speed = 0


##### IBSM으로부터 수신받은 정보들 + 위에서 계산한 차체의 기울기로 즉시 사격 가능 여부 계산 및 판단 #####
G = 9.81 # 중력가속도
muzzle_velocity = 61 # 포탄의 초기속도(61m/s)

# 1. 수평거리 및 고저차 계산
dx = enemy_pos_x - my_pos_x
dy = enemy_pos_y - my_pos_y
horizontal_distance = math.sqrt(dx**2 + dy**2)
height_diff = enemy_alt - my_alt

# 2. 발사 각도(고각) 계산 (수치해석)
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

elevation_angle = find_elevation_angle(horizontal_distance, height_diff, muzzle_velocity, G)

# 3. 수평 방위각(아지무스) 계산 (12시 방향 기준, 시계방향 증가)
azimuth_rad = math.atan2(dy, dx)
azimuth_deg_math = math.degrees(azimuth_rad)
azimuth_deg_12oclock = (90 - azimuth_deg_math) % 360

print(f"적 전차를 맞추기 위한 발사 고각: {elevation_angle:.2f}도")
print(f"적 전차를 향한 수평 방위각(12시 기준, 시계방향): {azimuth_deg_12oclock:.2f}도")

# 4. 포탑 수직 각도 제한 체크 (기준: 차체 수직각 +15도 ~ -5도, 최대 10도까지 허용)
turret_min_angle = my_body_y - 5
turret_max_angle = my_body_y + 10  # 최대 10도까지만 허용

if elevation_angle is not None:
    if turret_min_angle <= elevation_angle <= turret_max_angle:
        print(f"발사 고각({elevation_angle:.2f}도)는 포탑 수직 각도 제한 내에 있습니다. (최대 10도 기준)")
    else:
        print(f"발사 고각({elevation_angle:.2f}도)는 포탑 수직 각도 제한({turret_min_angle:.2f}도 ~ {turret_max_angle:.2f}도, 최대 10도 기준)를 벗어납니다.")
else:
    print("적 전차를 맞출 수 있는 발사 고각을 찾지 못했습니다.")

# 5. 발사각 10도 기준 사정거리 계산
theta_deg = 10
theta_rad = math.radians(theta_deg)
range_10deg = (muzzle_velocity ** 2) * math.sin(2 * theta_rad) / G
print(f"전차 사정거리(발사각 10도 기준): {range_10deg:.2f} m")

# 6. 현재 전차와 적 전차 위치의 실제 사거리(직선 거리) 계산
distance_3d = math.sqrt(
    (enemy_pos_x - my_pos_x) ** 2 +
    (enemy_pos_y - my_pos_y) ** 2 +
    (enemy_alt - my_alt) ** 2
)
print(f"현재 전차와 적 전차 위치의 실제 사거리(직선 거리): {distance_3d:.2f} m")

# 이동해야 할 위치 계산 (적 전차 방향으로 사정거리만큼 접근)
def get_move_position(my_x, my_y, enemy_x, enemy_y, move_distance):
    dx = enemy_x - my_x
    dy = enemy_y - my_y
    total_distance = math.sqrt(dx**2 + dy**2)
    ratio = (total_distance - move_distance) / total_distance
    new_x = my_x + dx * ratio
    new_y = my_y + dy * ratio
    return new_x, new_y

# 사정거리(발사각 10도 기준)
required_distance = range_10deg

##### 만약 사격이 불가능할 경우, 사격 가능 지점(x, z좌표)을 산출해서 IBMS에게 전달 #####
if distance_3d > required_distance:
    move_x, move_y = get_move_position(my_pos_x, my_pos_y, enemy_pos_x, enemy_pos_y, required_distance)
    print(f"적 전차를 맞추려면 다음 위치까지 접근하세요:")
    print(f"이동 좌표: x={move_x:.2f}, y={move_y:.2f}")

    # 이동 후 수평거리 및 고저차 재계산
    dx_new = enemy_pos_x - move_x
    dy_new = enemy_pos_y - move_y
    horizontal_distance_new = math.sqrt(dx_new**2 + dy_new**2)
    height_diff_new = enemy_alt - my_alt  # 고도는 그대로라고 가정

    # 이동 후 발사 고각(수직 각도) 재계산
    elevation_angle_new = find_elevation_angle(horizontal_distance_new, height_diff_new, muzzle_velocity, G)

    # 이동 후 수평 방위각(아지무스) 재계산
    azimuth_rad_new = math.atan2(dy_new, dx_new)
    azimuth_deg_math_new = math.degrees(azimuth_rad_new)
    azimuth_deg_12oclock_new = (90 - azimuth_deg_math_new) % 360

    print(f"이동 후 맞추기 위한 발사 고각(수직 각도): {elevation_angle_new:.2f}도")
    print(f"이동 후 맞추기 위한 수평 방위각(12시 기준, 시계방향): {azimuth_deg_12oclock_new:.2f}도")


##### 만약 즉시 사격이 가능할 경우, IBMS에게 사격 명령 전달 #####
else:
    print("현재 위치에서 사격이 가능합니다.")
    print(f"맞추기 위한 발사 고각(수직 각도): {(elevation_angle + my_body_y):.2f}도")
    print(f"맞추기 위한 수평 방위각(12시 기준, 시계방향): {azimuth_deg_12oclock:.2f}도")
