# 1인칭 화면에서 적 전차의 픽셀좌표와 아군전차의 위치, 터렛 각도 등 입력 시 적 전차 위치 나올 수 있도록 

import math
import csv

# 1m당 맵 좌표 단위 (300/28)
MAP_SCALE = 10.7143

# -------------------------------
# 1인칭 화면 픽셀 → 포신 기준 상대각 계산
def calculate_relative_angles(x_pixel, y_pixel, screen_w, screen_h, fov_h, fov_v):
    cx = screen_w / 2
    cy = screen_h / 2

    # 수평 상대각
    rel_angle_h = ((x_pixel - cx) / cx) * (fov_h / 2)

    # 수직 상대각 (선택, 높낮이 참고용)
    rel_angle_v = ((cy - y_pixel) / cy) * (fov_v / 2)

    # 수평 방향 판별
    if rel_angle_h > 0:
        direction = "오른쪽"
    elif rel_angle_h < 0:
        direction = "왼쪽"
    else:
        direction = "정면"

    return rel_angle_h, rel_angle_v, direction

# -------------------------------
# 아군 위치, 거리, 포탑 각도, 포신 상대각 → 적 전차 절대 좌표
def calculate_absolute_position(friendly_pos, distance_m, turret_angle_deg, rel_angle_h):
    distance = (distance_m * MAP_SCALE) / 10  # 거리 변환

    abs_angle_deg = (turret_angle_deg + rel_angle_h) % 360
    rad = math.radians(abs_angle_deg)

    x_enemy = friendly_pos[0] + distance * math.sin(rad)
    y_enemy = friendly_pos[1] + distance * math.cos(rad)

    return x_enemy, y_enemy, abs_angle_deg

# -------------------------------
# 프레임별 처리
def process_frames(frames, screen_w, screen_h, fov_h, fov_v, friendly_pos, turret_angle_deg):
    results = []
    for f in frames:
        # 1️⃣ 픽셀 → 상대각
        rel_h, rel_v, direction = calculate_relative_angles(
            f['x_pixel'], f['y_pixel'], screen_w, screen_h, fov_h, fov_v
        )
        # 2️⃣ 절대 좌표 계산
        x_enemy, y_enemy, abs_angle = calculate_absolute_position(
            friendly_pos, f['distance_m'], turret_angle_deg, rel_h
        )
        # 3️⃣ 결과 저장
        results.append({
            'frame': f['frame'],
            'x_pixel': f['x_pixel'],
            'y_pixel': f['y_pixel'],
            'rel_angle_h': rel_h,
            'rel_angle_v': rel_v,
            'direction': direction,
            'distance_m': f['distance_m'],
            'x_enemy': x_enemy,
            'y_enemy': y_enemy,
            'abs_angle': abs_angle
        })
    return results

# -------------------------------
# CSV 저장
def save_results_to_csv(results, output_csv):
    fieldnames = ['frame','x_pixel','y_pixel','rel_angle_h','rel_angle_v','direction','distance_m','x_enemy','y_enemy','abs_angle']
    with open(output_csv, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow(row)
    print(f"✅ CSV 저장 완료: {output_csv}")

# -------------------------------
# 🔹 사용자 입력 영역
if __name__ == "__main__":
    # 1️⃣ 화면 정보
    screen_w = 1919          # 화면 가로 해상도
    screen_h = 1047          # 화면 세로 해상도
    fov_h = 47.81061         # 수평 시야각
    fov_v = 28.0             # 수직 시야각

    # 2️⃣ 아군 전차 위치 (맵 좌표) 및 포탑 각도
    friendly_pos = (0, 0)  # 아군 전차 좌표
    turret_angle_deg = 45.12          # 포탑 절대각, 0 = 북쪽

    # 3️⃣ 프레임별 입력
    # x_pixel, y_pixel: 1인칭 화면에서 적 전차 중심 픽셀
    # distance_m: 아군 전차와 적 전차 사이 거리(m)
    frames = [
        {'frame':'frame001','x_pixel':957,'y_pixel':536,'distance_m':390.0}
    ]

    # 4️⃣ CSV 저장 경로
    output_csv = r"C:\PYSOU\final_project\enemy_positions_map.csv"

    # -------------------------------
    # 처리
    results = process_frames(frames, screen_w, screen_h, fov_h, fov_v, friendly_pos, turret_angle_deg)
    save_results_to_csv(results, output_csv)

    # 확인용 출력
    for r in results:
        print(r)
