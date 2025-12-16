# VDRS(Visual Detection Ranging System)
from flask import Flask, request, jsonify
import base64
import cv2
import numpy as np
import math

app = Flask(__name__)

# ----------------------------------------------------
# Base64 → OpenCV 이미지 변환
# ----------------------------------------------------
def decode_base64_to_image(base64_str):
    try:
        img_data = base64.b64decode(base64_str)
        np_arr = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        print("디코딩성공@@@@@@@@@@@@@@")
        return img
    except Exception as e:
        # print("Base64 디코딩 실패:", e)
        return None


# ----------------------------------------------------
# 객체 탐지 (더미 버전 - 실제 YOLO로 교체 가능)
# ----------------------------------------------------
from ultralytics import YOLO

# 모델 로딩 (최초 1회만)
yolo_model = YOLO(r"C:\Users\user\Desktop\HDRT-Final-Project\research\VDRS\archive\testchoong\yolo11x_scratch_trained.pt")

def detect_object(image):
    """
    실제 YOLO 모델을 이용한 객체 탐지.
    이미지 내 모든 객체의 class, bbox, center_pixel을 리스트로 반환.
    """
    results = yolo_model(image)
    boxes = results[0].boxes
    class_counter = {}
    class_names = []
    center_pixels = []
    if len(boxes) == 0:
        return class_names, 0, center_pixels

    for box in boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        class_id = int(box.cls[0])
        class_name = yolo_model.model.names[class_id] if hasattr(yolo_model.model, "names") else str(class_id)
        class_counter[class_name] = class_counter.get(class_name, 0) + 1
        numbered_class = f"{class_name}{class_counter[class_name]}"
        class_names.append(numbered_class)
        center_pixels.append((cx, cy))
    print("11111111111111111111111111111111111","detected:", class_names, len(class_names), "center_pixels:", center_pixels)
    return class_names, len(class_names), center_pixels


# ----------------------------------------------------
# 스테레오 거리 계산 (더미 버전)
# ----------------------------------------------------
def estimate_distance(image_left, image_right, tank_x, tank_y, tank_z, y_tolerance=2):
    """
    스테레오 이미지에서 객체 중심점의 disparity를 이용해 거리(z) 계산.
    - 왼쪽/오른쪽 이미지 모두에서 객체 탐지
    - y좌표가 거의 같은 객체끼리만 disparity 계산
    - 매칭된 쌍에 대해서만 거리 반환
    """
    baseline = 1.115  # meters
    focal_length = 920  # pixels

    # 1. 왼쪽/오른쪽 이미지에서 객체 탐지 및 중심점 좌표
    results_left = yolo_model(image_left)
    boxes_left = results_left[0].boxes
    left_centers = []
    if len(boxes_left) == 0:
        return []

    for box in boxes_left:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        left_centers.append((cx, cy))

    results_right = yolo_model(image_right)
    boxes_right = results_right[0].boxes
    right_centers = []
    if len(boxes_right) == 0:
        return []

    for box in boxes_right:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        right_centers.append((cx, cy))

    distances = []
    # 4. 왼쪽 객체 중심점마다 오른쪽 객체 중심점과 y좌표가 비슷한 것만 disparity 계산
    for cx_left, cy_left in left_centers:
        # 오른쪽 객체 중 y좌표가 비슷한 것 찾기
        matched = [(cx_right, cy_right) for cx_right, cy_right in right_centers if abs(cy_left - cy_right) <= y_tolerance]
        if not matched:
            continue  # 매칭되는 객체가 없으면 건너뜀

        # 가장 가까운 x좌표(SSD가 아니라 단순 x좌표 차이 최소)로 매칭
        cx_right, cy_right = min(matched, key=lambda rc: abs(cx_left - rc[0]))
        disparity = abs(cx_left - cx_right)
        if disparity == 0:
            continue  # 무한대(거리 계산 불가)

        z = (focal_length * baseline) / disparity
        distances.append(z)

    # (tank_x, tank_z)와 (150, 150) 사이의 유클리드 거리 계산
    real_distance = ((tank_x - 150) ** 2 + (tank_z - 150) ** 2) ** 0.5
    print("222222222222222222222222222222222222222222222222222distances:", distances)
    print("tank_x:", tank_x, "tank_y:", tank_y, "tank_z:", tank_z, "real_distance:", real_distance)
    return distances


# ----------------------------------------------------
# 픽셀 → 상대 각도 변환
# ----------------------------------------------------
def calc_relative_angle(x_pixel, y_pixel, screen_w, screen_h, fov_h, fov_v):
        """
        여러 픽셀 좌표(x_pixel, y_pixel) 쌍을 받아 각도 리스트 반환
        x_pixel, y_pixel: 각각 리스트 또는 튜플(동일 길이)
        """
        cx = screen_w / 2
        cy = screen_h / 2
        if isinstance(x_pixel, (list, tuple)) and isinstance(y_pixel, (list, tuple)):
            rel_h_list = []
            rel_v_list = []
            for x, y in zip(x_pixel, y_pixel):
                rel_h = ((x - cx) / cx) * (fov_h / 2)
                rel_v = ((cy - y) / cy) * (fov_v / 2)
                rel_h_list.append(rel_h)
                rel_v_list.append(rel_v)
            return rel_h_list, rel_v_list
        else:
            rel_h = ((x_pixel - cx) / cx) * (fov_h / 2)
            rel_v = ((cy - y_pixel) / cy) * (fov_v / 2)
            return rel_h, rel_v


# ----------------------------------------------------
# 적 좌표 계산 (월드 좌표)
# ----------------------------------------------------
MAP_SCALE = 10.7143   # 시뮬레이터 기준 1m = 10.7143px

def calc_world_position(friendly_pos, distance_m, turret_angle_deg, rel_angle_h):
    """
    여러 거리/각도 입력을 받아 월드 좌표 리스트 반환
    distance_m, rel_angle_h: 리스트 또는 단일값
    friendly_pos: [x, y] (단일)
    turret_angle_deg: 단일값
    """
    if isinstance(distance_m, (list, tuple)) and isinstance(rel_angle_h, (list, tuple)):
        x_list, y_list, abs_angle_list = [], [], []
        for d, rel_h in zip(distance_m, rel_angle_h):
            distance = (d * MAP_SCALE) / 10
            abs_angle = (turret_angle_deg + rel_h) % 360
            rad = math.radians(abs_angle)
            x_enemy = friendly_pos[0] + distance * math.sin(rad)
            y_enemy = friendly_pos[1] + distance * math.cos(rad)
            x_list.append(x_enemy)
            y_list.append(y_enemy)
            abs_angle_list.append(abs_angle)
        return x_list, y_list, abs_angle_list
    else:
        distance = (distance_m * MAP_SCALE) / 10
        abs_angle = (turret_angle_deg + rel_angle_h) % 360
        rad = math.radians(abs_angle)
        x_enemy = friendly_pos[0] + distance * math.sin(rad)
        y_enemy = friendly_pos[1] + distance * math.cos(rad)
        return x_enemy, y_enemy, abs_angle


# ====================================================
#                   /get_vdrs 엔드포인트
# ====================================================
@app.route('/get_vdrs', methods=['POST'])
def get_vdrs():
    request_data = request.get_json()
    # print("request_data:", request_data)

    # --------------------------
    # 1. 입력 데이터 수신
    # --------------------------

    left_image_b64 = request_data.get("stereo_image_left_b64", "")
    right_image_b64 = request_data.get("stereo_image_right_b64", "")
    main_image_b64 = request_data.get("image_b64", "")
    turret_angle = request_data.get("turret_angle", 0.0)
    friendly_pos = request_data.get("friendly_pos", [0, 0])

    fov_h = request_data.get("fov_h", 47.8)
    fov_v = request_data.get("fov_v", 28.0)

    # ally_body_pos에서 x, y, z 추출
    ally_body_pos = request_data.get("ally_body_pos", {})
    
    tank_x = ally_body_pos.get("x", 0)
    tank_y = ally_body_pos.get("y", 0)
    tank_z = ally_body_pos.get("z", 0)

    # --------------------------
    # 2. base64 → OpenCV 이미지 변환 (입력값 체크 포함)


    import time
    while True:
        try:
            img_left = decode_base64_to_image(left_image_b64)
            img_right = decode_base64_to_image(right_image_b64)
            main_img = decode_base64_to_image(main_image_b64)
            if img_left is not None and img_right is not None and main_img is not None:
                break
            else:
                time.sleep(0.5)
        except Exception as e:
            print(f"[대기] 이미지 디코딩 중 예외 발생: {e}")
            time.sleep(0.5)

    # 여기서부터는 while 밖에서 순차적으로 처리
    h, w = img_left.shape[:2]

    class_names, count, center_pixels = detect_object(main_img)
    if count == 0:
        return jsonify({"error": "객체 탐지 결과 없음"}), 400

    x_pixel, y_pixel = center_pixels[0]
    distance_m = estimate_distance(img_left, img_right,tank_x, tank_y, tank_z)
    if not distance_m or len(distance_m) == 0:
        return jsonify({"error": "거리 계산 결과 없음"}), 400

    rel_h, rel_v = calc_relative_angle(x_pixel, y_pixel, w, h, fov_h, fov_v)
    x_enemy, y_enemy, abs_angle = calc_world_position(
        friendly_pos, distance_m[0], turret_angle, rel_h if isinstance(rel_h, float) else rel_h[0]
    )
    sample_response_data = {
        "object_pos": [x_enemy, y_enemy, 0.0],
        "abs_angle": 0,
        "distance_m": distance_m[0],
        "pixel_pos": [x_pixel, y_pixel]
    }
    return jsonify(sample_response_data)


# ====================================================
# 서버 시작
# ====================================================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
