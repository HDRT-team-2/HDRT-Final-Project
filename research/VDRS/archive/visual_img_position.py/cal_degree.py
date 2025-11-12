# 1인칭 화면에서 적 전차 픽셀 값과 아군 전차 위치, 터렛 각도 입력값 넣으면 포신과의 적과의 각도 알려줄 수 있도록 

import csv

def calculate_relative_angles(x_pixel, y_pixel, screen_w, screen_h, fov_h, fov_v):
    """
    1인칭 화면 픽셀 좌표 -> 포신 기준 수평/수직 상대각도
    """
    # 화면 중심
    cx = screen_w / 2
    cy = screen_h / 2

    # 수평 각도 계산 (왼쪽 음수, 오른쪽 양수)
    rel_angle_h = ((x_pixel - cx) / cx) * (fov_h / 2)

    # 수직 각도 계산 (위쪽 양수, 아래쪽 음수)
    rel_angle_v = ((cy - y_pixel) / cy) * (fov_v / 2)

    # 방향 판별 (수평 기준)
    if rel_angle_h > 0:
        direction = "오른쪽"
    elif rel_angle_h < 0:
        direction = "왼쪽"
    else:
        direction = "정면"

    return rel_angle_h, rel_angle_v, direction

def save_angles_to_csv(results, output_csv):
    fieldnames = ['frame','x_pixel','y_pixel','rel_angle_h','rel_angle_v','direction']
    with open(output_csv, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow(row)
    print(f"✅ CSV 저장 완료: {output_csv}")

# 🔹 사용자 입력 영역
if __name__ == "__main__":
    # -------------------------------
    # 화면 정보 입력
    screen_w = 1920         # 화면 가로 해상도(픽셀)
    screen_h = 1080         # 화면 세로 해상도(픽셀)
    fov_h = 47.81061        # 화면 수평 시야각(FOV, degrees)
    fov_v = 28.0            # 화면 수직 시야각(FOV, degrees)
    # -------------------------------

    # -------------------------------
    # 프레임별 적 전차 픽셀 좌표 입력
    # x_pixel, y_pixel = 1인칭 화면에서 적 전차 중심 픽셀 좌표
    # frame = 각 프레임 이름/번호 (임의로 지정)
    frames = [
        {'frame':'frame001','x_pixel':1606,'y_pixel':540}
    ]
    # -------------------------------

    results = []
    for f in frames:
        rel_h, rel_v, direction = calculate_relative_angles(
            f['x_pixel'], f['y_pixel'], screen_w, screen_h, fov_h, fov_v
        )
        results.append({
            'frame': f['frame'],
            'x_pixel': f['x_pixel'],
            'y_pixel': f['y_pixel'],
            'rel_angle_h': rel_h,
            'rel_angle_v': rel_v,
            'direction': direction
        })

    # -------------------------------
    # CSV 저장 경로 입력
    output_csv = r"C:\PYSOU\final_project\relative_angles.csv"
    # -------------------------------
    save_angles_to_csv(results, output_csv)

    # 확인용 출력
    for r in results:
        print(r)
