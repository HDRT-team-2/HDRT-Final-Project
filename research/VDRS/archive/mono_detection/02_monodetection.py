# VDRS 통합 시스템 (Visual Detection Ranging System)
from flask import Flask, request, jsonify
from datetime import datetime
import base64
import cv2
import numpy as np
from ultralytics import YOLO
import os

# ====================================================
# 전역 변수
# ====================================================
# YOLO 신뢰도 임계값
CONFIDENCE_THRESHOLD = 0.8  # 80% 이상만 탐지 결과로 저장

# 시뮬레이터 카메라 스펙
FOV_HORIZONTAL = 47.81061  # 수평 FOV (degrees)
FOV_VERTICAL = 28.0        # 수직 FOV (degrees)

# ====================================================
# YOLO 모델 로드
# ====================================================
model = YOLO('best.pt')

# ====================================================
# 로그 기록용 함수
# ====================================================
# 현재 시간 기반 로그 파일 생성
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = f"{timestamp}_log.txt"

def write_log(message):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # 밀리초 3자리까지
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"{now} - {message}\n")

write_log("로그 파일 생성 완료")

# ====================================================
# 01_decode_base64_to_image 함수
# ====================================================
def decode_base64_to_image(base64_str):
    try:
        img_data = base64.b64decode(base64_str)
        np_arr = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        write_log("디코딩성공")
        return img
    except Exception as e:
        # write_log(f"Base64 디코딩 실패: {e}")
        return None
    
def save_img(img, ally_body_pos, obstacle_pos, label="image"):
    """
    이미지를 파일로 저장 (아군 및 장애물 위치 정보를 파일명에 포함)
    
    Args:
        img: OpenCV 이미지 (numpy array)
        ally_body_pos: {"x": float, "y": float, "z": float}
        obstacle_pos: {"x": float, "y": float, "z": float}
        label: 이미지 구분 레이블 (front, left, right 등)
    
    Returns:
        저장된 파일 경로
    """
    import os
    
    # 저장 디렉토리 생성
    save_dir = "result/saved_images"
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    
    # 타임스탬프 생성
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    
    # 아군 위치 문자열
    ally_body_pos_x = ally_body_pos.get("x", 0.0)
    ally_body_pos_y = ally_body_pos.get("y", 0.0)
    ally_body_pos_z = ally_body_pos.get("z", 0.0)
    ally_str = f"ally_{ally_body_pos_x:.2f}_{ally_body_pos_y:.2f}_{ally_body_pos_z:.2f}"

    # 장애물 위치 문자열
    obstacle_pos_x = obstacle_pos.get("x", 0.0)
    obstacle_pos_y = obstacle_pos.get("y", 0.0)
    obstacle_pos_z = obstacle_pos.get("z", 0.0)
    obstacle_str = f"obs_{obstacle_pos_x:.2f}_{obstacle_pos_y:.2f}_{obstacle_pos_z:.2f}"
    
    # 파일명 조합: timestamp_label_ally_위치_obs_위치.png
    filename = f"{timestamp_str}_{label}_{ally_str}_{obstacle_str}.png"
    filepath = os.path.join(save_dir, filename)
    
    # 이미지 저장
    try:
        cv2.imwrite(filepath, img)
        write_log(f"이미지 저장 성공: {filepath}")
        return filepath
    except Exception as e:
        write_log(f"이미지 저장 실패: {e}")
        return None

# ====================================================
# 02_object_detection 함수
# ====================================================
def object_detection(img):
    """
    YOLO 모델을 이용한 객체 탐지
    
    Args:
        img: OpenCV 이미지 (numpy array)
    
    Returns:
        List[Dict]: 탐지된 객체 리스트
        [{
            'class_id': int,
            'x_center': float (0~1 정규화),
            'y_center': float (0~1 정규화),
            'width': float (0~1 정규화),
            'height': float (0~1 정규화),
            'confidence': float
        }, ...]
    """
    try:
        # YOLO 추론 실행
        results = model(img, verbose=False)
        result = results[0]
        
        # 이미지 크기
        img_height, img_width = img.shape[:2]
        
        # 탐지 결과 리스트
        detections = []
        
        # 각 탐지 객체 처리
        for box in result.boxes:
            # 바운딩 박스 좌표 (x1, y1, x2, y2)
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            
            # 클래스 ID와 신뢰도
            class_id = int(box.cls[0])
            confidence = float(box.conf[0])
            
            # 신뢰도 필터링
            if confidence < CONFIDENCE_THRESHOLD:
                continue
            
            # 정규화된 중심점 좌표 + 너비/높이 계산
            x_center = float(((x1 + x2) / 2) / img_width)
            y_center = float(((y1 + y2) / 2) / img_height)
            width = float((x2 - x1) / img_width)
            height = float((y2 - y1) / img_height)
            
            # 결과 추가
            detections.append({
                'class_id': class_id,
                'x_center': x_center,
                'y_center': y_center,
                'width': width,
                'height': height,
                'confidence': confidence
            })
        
        write_log(f" 객체 탐지 완료: {len(detections)}개 탐지")
        return detections
    
    except Exception as e:
        write_log(f" 객체 탐지 실패: {e}")
        return []


def visualize_detections(img, detections, label="detection"):
    """
    탐지 결과를 이미지에 시각화
    
    Args:
        img: OpenCV 이미지
        detections: object_detection()의 반환값
        label: 저장 파일명 레이블
    
    Returns:
        시각화된 이미지
    """
    
    # 이미지 복사
    vis_img = img.copy()
    img_height, img_width = img.shape[:2]
    
    # 클래스별 색상 (BGR)
    colors = {
        0: (0, 255, 0),    # Green - car
        1: (255, 0, 0),    # Blue - infantry
        2: (0, 0, 255),    # Red - tank
    }
    
    class_names = {
        0: "car",
        1: "infantry",
        2: "tank"
    }
    
    # 각 객체에 바운딩 박스 그리기
    for det in detections:
        # 정규화된 좌표 → 픽셀 좌표 변환
        x_center = det['x_center'] * img_width
        y_center = det['y_center'] * img_height
        width = det['width'] * img_width
        height = det['height'] * img_height
        
        # 바운딩 박스 좌표 계산
        x1 = int(x_center - width / 2)
        y1 = int(y_center - height / 2)
        x2 = int(x_center + width / 2)
        y2 = int(y_center + height / 2)
        
        # 색상 선택
        class_id = det['class_id']
        color = colors.get(class_id, (255, 255, 255))
        class_name = class_names.get(class_id, "unknown")
        
        # 바운딩 박스 그리기 (굵기 2 → 1)
        cv2.rectangle(vis_img, (x1, y1), (x2, y2), color, 1)
        
        # 상하 픽셀 수 계산
        height_pixels = int(height)
        
        # 텍스트 (클래스명 + 신뢰도 + 높이)
        text = f"{class_name}: {det['confidence']:.2f} h:{height_pixels}px"
        text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)[0]
        
        # 텍스트 배경
        cv2.rectangle(vis_img, (x1, y1 - text_size[1] - 4), 
                     (x1 + text_size[0], y1), color, -1)
        
        # 텍스트 그리기 (굵기 2 → 1)
        cv2.putText(vis_img, text, (x1, y1 - 2), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
    
    # 저장 디렉토리 생성
    save_dir = "result/detection_results"
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    
    # 파일명 생성
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    filename = f"{timestamp_str}_{label}_detected.png"
    filepath = os.path.join(save_dir, filename)
    
    # 이미지 저장
    cv2.imwrite(filepath, vis_img)
    write_log(f" 탐지 결과 저장: {filepath}")
    
    return vis_img


def visualize_manual_measurements(img, detections, actual_distance, label="manual"):
    """
    수동 측정 거리를 이미지에 시각화 (캘리브레이션용)
    
    Args:
        img: OpenCV 이미지
        detections: object_detection()의 반환값
        actual_distance: 실제 측정한 거리 (m)
        label: 저장 파일명 레이블
    
    Returns:
        시각화된 이미지
    """
    
    # 이미지 복사
    vis_img = img.copy()
    img_height, img_width = img.shape[:2]
    
    # 클래스별 색상 (BGR)
    colors = {
        0: (0, 255, 0),    # Green - car
        1: (255, 0, 0),    # Blue - infantry
        2: (0, 0, 255),    # Red - tank
    }
    
    class_names = {
        0: "car",
        1: "infantry",
        2: "tank"
    }
    
    # 각 객체에 바운딩 박스 그리기
    for det in detections:
        # 정규화된 좌표 → 픽셀 좌표 변환
        x_center = det['x_center'] * img_width
        y_center = det['y_center'] * img_height
        width = det['width'] * img_width
        height = det['height'] * img_height
        
        # 바운딩 박스 좌표 계산
        x1 = int(x_center - width / 2)
        y1 = int(y_center - height / 2)
        x2 = int(x_center + width / 2)
        y2 = int(y_center + height / 2)
        
        # 색상 선택
        class_id = det['class_id']
        color = colors.get(class_id, (255, 255, 255))
        class_name = class_names.get(class_id, "unknown")
        
        # 바운딩 박스 그리기
        cv2.rectangle(vis_img, (x1, y1), (x2, y2), color, 2)
        
        # 상하 픽셀 수 계산
        height_pixels = int(height)
        
        # 정규화된 높이 계산
        normalized_height = det['height']
        
        # 텍스트 (클래스명 + 픽셀 높이 + 정규화 높이 + 실제 거리)
        text = f"{class_name} h:{height_pixels}px norm:{normalized_height:.4f} DIST:{actual_distance:.2f}m"
        text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
        
        # 텍스트 위치 조정 (���미지 경계 체크)
        text_x = x1
        text_y = y1 - 5
        
        # 왼쪽 경계 체크
        if text_x < 0:
            text_x = 0
        # 오른쪽 경계 체크
        if text_x + text_size[0] > img_width:
            text_x = img_width - text_size[0]
        # 위쪽 경계 체크 (텍스트가 이미지 위로 나가면 박스 아래로 이동)
        if text_y - text_size[1] < 0:
            text_y = y2 + text_size[1] + 5
        
        # 텍스트 배경 (더 큰 배경)
        cv2.rectangle(vis_img, (text_x, text_y - text_size[1] - 6), 
                     (text_x + text_size[0] + 4, text_y + 2), color, -1)
        
        # 텍스트 그리기 (굵은 글씨)
        cv2.putText(vis_img, text, (text_x + 2, text_y - 2), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
    
    # 저장 디렉토리 생성
    save_dir = "result/manual_measurements"
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    
    # 파일명 생성 (실제 거리 포함)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    filename = f"{timestamp_str}_{label}_dist{actual_distance:.2f}m.png"
    filepath = os.path.join(save_dir, filename)
    
    # 이미지 저장
    cv2.imwrite(filepath, vis_img)
    write_log(f" 수동 측정 결과 저장: {filepath}")
    
    return vis_img

# ====================================================
# 03_range_finder 함수
# ====================================================
def range_finder(detections):
    """
    기계식 육안 거리 측정기 방식으로 거리 계산
    객체의 상하 길이(height)를 기반으로 거리 추정
    
    Args:
        detections: object_detection()의 반환값 (정규화된 탐지 결과)
    
    Returns:
        List[Dict]: 거리 정보가 추가된 탐지 결과
        [{
            'class_id': int,
            'class_name': str,
            'distance': float (meters),
            'x_center': float,
            'y_center': float,
            'width': float,
            'height': float,
            'confidence': float
        }, ...]
    """
    
    # 클래스별 거리 계산 함수
    def calculate_distance_car(height):
        """
        Car 클래스의 상하 길이 기반 거리 계산
        height: 정규화된 높이 값 (0~1)
        """
        # ========== 캘리브레이션 데이터 (수동 측정) ==========
        # 형식: (정규화된 높이, 실제 거리(m))
        # 이미지 해상도: 450px (높이 기준으로 정규화)
        calibration_data = [
            (18/450, 138.24), (23/450, 132.96), (23/450, 132.52), (17/450, 132.21),
            (23/450, 130.68), (20/450, 129.73), (21/450, 128.09), (25/450, 126.97),
            (19/450, 126.95), (23/450, 126.88), (25/450, 125.05), (20/450, 123.62),
            (19/450, 119.63), (19/450, 119.42), (27/450, 117.32), (30/450, 112.72),
            (23/450, 111.04), (23/450, 110.99), (24/450, 109.81), (33/450, 108.55),
            (33/450, 108.09), (30/450, 107.99), (22/450, 107.88), (26/450, 106.66),
            (31/450, 103.32), (42/450, 102.77), (31/450, 102.33), (23/450, 102.11),
            (29/450, 101.79), (37/450, 101.01), (29/450, 98.53), (35/450, 97.41),
            (35/450, 97.39), (28/450, 94.62), (31/450, 93.67), (36/450, 92.62),
            (37/450, 92.15), (35/450, 91.19), (31/450, 89.31), (28/450, 87.99),
            (44/450, 85.92), (37/450, 82.52), (31/450, 82.11), (37/450, 81.89),
            (36/450, 81.8), (31/450, 81.59), (40/450, 80.72), (37/450, 77.12),
            (45/450, 74.39), (43/450, 74.35), (51/450, 72.47), (35/450, 71.71),
            (38/450, 67.31), (38/450, 65.68), (54/450, 65.14), (41/450, 61.34),
            (43/450, 59.8), (57/450, 53.47), (52/450, 53.05), (54/450, 52.99),
            (59/450, 52.63), (52/450, 50.26), (63/450, 47.93), (66/450, 46.29),
            (59/450, 44.67), (57/450, 44.27), (69/450, 38.19), (84/450, 37.19),
            (64/450, 36.89), (93/450, 34.18), (83/450, 33.13), (92/450, 31.12),
            (137/450, 22.23), (131/450, 22.2), (125/450, 21.41), (149/450, 17.03),
        ]
        
        # 데이터가 있으면 다항식 회귀, 없으면 기본 역비례 공식
        if len(calibration_data) >= 3:  # 최소 3개 데이터 필요
            # 데이터 분리
            heights = np.array([h for h, d in calibration_data])
            distances = np.array([d for h, d in calibration_data])
            
            # 2차 다항식 피팅: distance = a*height^2 + b*height + c
            # 또는 역수 관계 피팅: distance = a/height + b
            # 역수 관계가 더 물리적으로 타당하므로 1/height를 x로 사용
            inv_heights = 1.0 / heights
            
            # 1차 다항식 피팅: distance = a*(1/height) + b
            coeffs = np.polyfit(inv_heights, distances, 1)
            a, b = coeffs[0], coeffs[1]
            
            if height > 0:
                distance = a / height + b
            else:
                distance = 999.0
        else:
            # 데이터 부족 시 기본 역비례 공식
            coefficient = 1.0  # 기본값
            if height > 0:
                distance = coefficient / height
            else:
                distance = 999.0
        
        return distance
    
    def calculate_distance_infantry(height):
        """
        Infantry 클래스의 상하 길이 기반 거리 계산
        height: 정규화된 높이 값 (0~1)
        """
        # ========== 캘리브레이션 데이터 (수동 측정) ==========
        # 형식: (정규화된 높이, 실제 거리(m))
        # 이미지 해상도: 450px (높이 기준으로 정규화)
        calibration_data = [
            (48/450, 44.68), (97/450, 24.36), (31/450, 84.13), (39/450, 66.52),
            (25/450, 90.61), (34/450, 68.59), (47/450, 44.72), (94/450, 22.34),
            (60/450, 32.74), (23/450, 90.78), (53/450, 47.52), (22/450, 91.84),
            (53/450, 46.82),
        ]
        
        # 데이터가 있으면 다항식 회귀, 없으면 기본 역비례 공식
        if len(calibration_data) >= 3:  # 최소 3개 데이터 필요
            heights = np.array([h for h, d in calibration_data])
            distances = np.array([d for h, d in calibration_data])
            
            # 역수 관계 피팅: distance = a/height + b
            inv_heights = 1.0 / heights
            coeffs = np.polyfit(inv_heights, distances, 1)
            a, b = coeffs[0], coeffs[1]
            
            if height > 0:
                distance = a / height + b
            else:
                distance = 999.0
        else:
            coefficient = 0.8  # 기본값
            if height > 0:
                distance = coefficient / height
            else:
                distance = 999.0
        
        return distance
    
    def calculate_distance_tank(height):
        """
        Tank 클래스의 상하 길이 기반 거리 계산
        height: 정규화된 높이 값 (0~1)
        """
        # ========== 캘리브레이션 데이터 (수동 측정) ==========
        # 형식: (정규화된 높이, 실제 거리(m))
        # 이미지 해상도: 450px (높이 기준으로 정규화)
        calibration_data = [
            (30/450, 122.44), (20/450, 123.72), (26/450, 106.7), (31/450, 85.01),
            (40/450, 61.62), (61/450, 40.7), (22/450, 111.21), (26/450, 89.65),
            (27/450, 85.97), (35/450, 63.8), (26/450, 89.56), (33/450, 66.78),
            (49/450, 44.41), (28/450, 82.46), (37/450, 60.91), (59/450, 37.52),
            (27/450, 82.85), (36/450, 61.48), (56/450, 40.03), (27/450, 90.58),
            (33/450, 69.36), (103/450, 26.14), (31/450, 73.06), (51/450, 49.6),
            (18/450, 133.93), (19/450, 115.44), (25/450, 92.33), (34/450, 71.8),
            (52/450, 48.16), (102/450, 27.09), (15/450, 147.45), (16/450, 134.81),
            (17/450, 118.48), (21/450, 96.3), (30/450, 72.45), (47/450, 49.7),
            (87/450, 28.0), (23/450, 95.54), (81/450, 28.53), (25/450, 92.56),
            (33/450, 69.64), (48/450, 45.81),
        ]
        
        # 데이터가 있으면 다항식 회귀, 없으면 기본 역비례 공식
        if len(calibration_data) >= 3:  # 최소 3개 데이터 필요
            heights = np.array([h for h, d in calibration_data])
            distances = np.array([d for h, d in calibration_data])
            
            # 역수 관계 피팅: distance = a/height + b
            inv_heights = 1.0 / heights
            coeffs = np.polyfit(inv_heights, distances, 1)
            a, b = coeffs[0], coeffs[1]
            
            if height > 0:
                distance = a / height + b
            else:
                distance = 999.0
        else:
            coefficient = 1.2  # 기본값
            if height > 0:
                distance = coefficient / height
            else:
                distance = 999.0
        
        return distance
    
    # 클래스별 거리 계산 함수 매핑
    distance_calculators = {
        0: calculate_distance_car,
        1: calculate_distance_infantry,
        2: calculate_distance_tank
    }
    
    # 클래스 이름 매핑
    class_names = {
        0: "car",
        1: "infantry",
        2: "tank"
    }
    
    # 결과 리스트
    results = []
    
    # 각 탐지 객체에 대해 거리 계산
    for det in detections:
        class_id = det['class_id']
        height = det['height']  # 정규화된 상하 길이
        
        # 클래스별 거리 계산 함수 선택
        calculator = distance_calculators.get(class_id, calculate_distance_car)
        distance = calculator(height)
        
        # 결과 추가
        results.append({
            'class_id': class_id,
            'class_name': class_names.get(class_id, "unknown"),
            'distance': round(distance, 2),
            'x_center': det['x_center'],
            'y_center': det['y_center'],
            'width': det['width'],
            'height': det['height'],
            'confidence': det['confidence']
        })
        
        write_log(f"📏 {class_names.get(class_id, 'unknown')} - 높이: {height:.4f}, 거리: {distance:.2f}m")
    
    return results


def visualize_range_results(img, range_results, label="range"):
    """
    거리 측정 결과를 이미지에 시각화
    
    Args:
        img: OpenCV 이미지
        range_results: range_finder()의 반환값
        label: 저장 파일명 레이블
    
    Returns:
        시각화된 이미지
    """
    
    # 이미지 복사
    vis_img = img.copy()
    img_height, img_width = img.shape[:2]
    
    # 클래스별 색상 (BGR)
    colors = {
        0: (0, 255, 0),    # Green - car
        1: (255, 0, 0),    # Blue - infantry
        2: (0, 0, 255),    # Red - tank
    }
    
    # 각 객체에 바운딩 박스 + 거리 정보 그리기
    for result in range_results:
        # 정규화된 좌표 → 픽셀 좌표 변환
        x_center = result['x_center'] * img_width
        y_center = result['y_center'] * img_height
        width = result['width'] * img_width
        height = result['height'] * img_height
        
        # 바운딩 박스 좌표 계산
        x1 = int(x_center - width / 2)
        y1 = int(y_center - height / 2)
        x2 = int(x_center + width / 2)
        y2 = int(y_center + height / 2)
        
        # 색상 선택
        class_id = result['class_id']
        color = colors.get(class_id, (255, 255, 255))
        class_name = result['class_name']
        distance = result['distance']
        
        # 바운딩 박스 그리기 (굵기 2 → 1)
        cv2.rectangle(vis_img, (x1, y1), (x2, y2), color, 1)
        
        # 상하 픽셀 수 계산
        height_pixels = int(height)
        
        # 텍스트 (클래스명 + 거리 + 높이)
        text = f"{class_name}: {distance:.2f}m h:{height_pixels}px"
        text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0]
        
        # 텍스트 배경
        cv2.rectangle(vis_img, (x1, y1 - text_size[1] - 4), 
                     (x1 + text_size[0], y1), color, -1)
        
        # 텍스트 그리기 (굵기 2 → 1)
        cv2.putText(vis_img, text, (x1, y1 - 2), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    
    # 저장 디렉토리 생성
    save_dir = "result/range_results"
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    
    # 파일명 생성
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    filename = f"{timestamp_str}_{label}_range.png"
    filepath = os.path.join(save_dir, filename)
    
    # 이미지 저장
    cv2.imwrite(filepath, vis_img)
    write_log(f" 거리 측정 결과 저장: {filepath}")
    
    return vis_img


# ====================================================
# 04_calculate_world_coordinates 함수
# ====================================================
def calculate_world_coordinates(distance_m, pixel_x, pixel_y, 
                                 camera_x, camera_z, turret_angle_deg,
                                 img_width=800, img_height=450,
                                 fov_h_deg=47.81061, fov_v_deg=28.0):
    """
    거리 측정 결과를 기반으로 월드 좌표 계산
    
    Args:
        distance_m: 측정된 거리 (meters)
        pixel_x: 객체 중심의 X 픽셀 좌표 (0~img_width)
        pixel_y: 객체 중심의 Y 픽셀 좌표 (0~img_height)
        camera_x, camera_z: 카메라(탱크) 월드 좌표 (meters)
        turret_angle_deg: 포탑 절대 각도 (degrees, 0° = 북쪽)
        img_width, img_height: 이미지 해상도 (pixels)
        fov_h_deg: 수평 시야각 (degrees)
        fov_v_deg: 수직 시야각 (degrees)
    
    Returns:
        {
            'world_x': float (meters),
            'world_z': float (meters),
            'rel_angle_h': float (degrees) - 화면 중심 기준 수평 상대 각도,
            'rel_angle_v': float (degrees) - 화면 중심 기준 수직 상대 각도,
            'abs_angle': float (degrees) - 월드 기준 절대 각도
        }
    """
    
    # 1. 화면 중심으로부터의 픽셀 오프셋 계산
    center_x = img_width / 2
    center_y = img_height / 2
    
    offset_x = pixel_x - center_x  # 오른쪽 +, 왼쪽 -
    offset_y = pixel_y - center_y  # 아래쪽 +, 위쪽 -
    
    # 2. 픽셀 오프셋 → 각도 변환
    # 수평 각도: 화면 중심(0°) 기준 좌우 각도
    rel_angle_h = (offset_x / center_x) * (fov_h_deg / 2)
    
    # 수직 각도: 화면 중심(0°) 기준 상하 각도
    rel_angle_v = (offset_y / center_y) * (fov_v_deg / 2)
    
    # 3. 절대 각도 계산 (월드 좌표계 기준)
    # 포탑 각도 + 상대 수평 각도
    abs_angle = turret_angle_deg + rel_angle_h
    
    # 4. 극좌표 → 직교좌표 변환
    # 거리와 각도로부터 상대 위치 계산
    abs_angle_rad = np.deg2rad(abs_angle)
    
    # 상대 좌표 (카메라 기준)
    rel_x = distance_m * np.sin(abs_angle_rad)
    rel_z = distance_m * np.cos(abs_angle_rad)
    
    # 5. 월드 좌표 계산 (카메라 위치 + 상대 위치)
    world_x = camera_x + rel_x
    world_z = camera_z + rel_z
    
    write_log(f" 좌표 계산: 거리={distance_m:.2f}m, "
              f"픽셀=({pixel_x:.0f},{pixel_y:.0f}), "
              f"상대각도=({rel_angle_h:.1f}°,{rel_angle_v:.1f}°), "
              f"절대각도={abs_angle:.1f}°, "
              f"월드좌표=({world_x:.2f},{world_z:.2f})")
    
    return {
        'world_x': round(world_x, 2),
        'world_z': round(world_z, 2),
        'rel_angle_h': round(rel_angle_h, 2),
        'rel_angle_v': round(rel_angle_v, 2),
        'abs_angle': round(abs_angle, 2)
    }


def visualize_world_coordinates(img, position_results, detections, label="world"):
    """
    월드 좌표 계산 결과를 이미지에 시각화
    
    Args:
        img: OpenCV 이미지
        position_results: calculate_world_coordinates()의 결과 리스트
        detections: object_detection()의 반환값 (바운딩 박스 정보용)
        label: 저장 파일명 레이블
    
    Returns:
        시각화된 이미지
    """
    
    # 이미지 복사
    vis_img = img.copy()
    img_height, img_width = img.shape[:2]
    
    # 클래스별 색상 (BGR)
    colors = {
        0: (0, 255, 0),    # Green - car
        1: (255, 0, 0),    # Blue - infantry
        2: (0, 0, 255),    # Red - tank
    }
    
    class_names = {
        0: "car",
        1: "infantry",
        2: "tank"
    }
    
    # 각 객체에 바운딩 박스 + 월드 좌표 정보 그리기
    for i, result in enumerate(position_results):
        if i >= len(detections):
            break
        
        det = detections[i]
        
        # 정규화된 좌표 → 픽셀 좌표 변환
        x_center = det['x_center'] * img_width
        y_center = det['y_center'] * img_height
        width = det['width'] * img_width
        height = det['height'] * img_height
        
        # 바운딩 박스 좌표 계산
        x1 = int(x_center - width / 2)
        y1 = int(y_center - height / 2)
        x2 = int(x_center + width / 2)
        y2 = int(y_center + height / 2)
        
        # 색상 선택
        class_id = result['class_id']
        color = colors.get(class_id, (255, 255, 255))
        class_name = class_names.get(class_id, "unknown")
        
        # 바운딩 박스 그리기
        cv2.rectangle(vis_img, (x1, y1), (x2, y2), color, 1)
        
        # 월드 좌표 정보
        world_x = result['world_x']
        world_z = result['world_z']
        abs_angle = result['abs_angle']
        distance = result['distance']
        
        # 텍스트 (클래스명 + 월드 좌표 + 각도)
        text1 = f"{class_name} D:{distance:.1f}m"
        text2 = f"W:({world_x:.1f}, {world_z:.1f})"
        text3 = f"Ang:{abs_angle:.1f}deg"
        
        # 텍스트 크기 계산
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.4
        thickness = 1
        
        text1_size = cv2.getTextSize(text1, font, font_scale, thickness)[0]
        text2_size = cv2.getTextSize(text2, font, font_scale, thickness)[0]
        text3_size = cv2.getTextSize(text3, font, font_scale, thickness)[0]
        
        max_width = max(text1_size[0], text2_size[0], text3_size[0])
        
        # 텍스트 배경 (3줄)
        text_y_start = y1 - 40
        if text_y_start < 0:
            text_y_start = y2 + 5
        
        # 배경 그리기
        cv2.rectangle(vis_img, 
                     (x1, text_y_start), 
                     (x1 + max_width + 4, text_y_start + 36), 
                     color, -1)
        
        # 텍스트 그리기 (3줄)
        cv2.putText(vis_img, text1, (x1 + 2, text_y_start + 10), 
                   font, font_scale, (255, 255, 255), thickness)
        cv2.putText(vis_img, text2, (x1 + 2, text_y_start + 22), 
                   font, font_scale, (255, 255, 255), thickness)
        cv2.putText(vis_img, text3, (x1 + 2, text_y_start + 34), 
                   font, font_scale, (255, 255, 255), thickness)
    
    # 저장 디렉토리 생성
    save_dir = "result/world_coordinates"
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    
    # 파일명 생성
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    filename = f"{timestamp_str}_{label}_world.png"
    filepath = os.path.join(save_dir, filename)
    
    # 이미지 저장
    cv2.imwrite(filepath, vis_img)
    write_log(f" 월드 좌표 결과 저장: {filepath}")
    
    return vis_img


# ====================================================
# Flask 앱 초기화
# ====================================================
app = Flask(__name__)

# ====================================================
# 메인 파이프라인
# ====================================================
@app.route('/get_vdrs', methods=['POST'])
def get_vdrs():
    request_data = request.get_json()

    # Request 데이터 추출
    time = request_data.get("time")
    ally_body_pos = request_data.get("ally_body_pos")
    ally_body_angle = request_data.get("ally_body_angle")
    ally_speed = request_data.get("ally_speed")
    image_b64 = request_data.get("image_b64")  # 전면 이미지만 사용 (1920x1080)
    obstacle_pos = request_data.get("obstacle_pos") # 디버그용 추가 필드

    """
    < request data 예시 >
    "time": (simulation time)
    "ally_body_pos":{"x": , "y": , "z": }
    "ally_body_angle":{"x": , "y": , "z": }
    "ally_speed":(m/s)
    "image_b64": (base64 string) - 1920x1080 전면 이미지
    "obstacle_pos":{"x": , "y": , "z": }  # 디버그용 추가 필드
    """

    # 01_decode_base64_to_image 함수
    write_log("01_decode_base64_to_image")
    img_front = decode_base64_to_image(image_b64)
    
    # 디코딩 실패 체크
    if img_front is None:
        write_log(" 이미지 디코딩 실패")
        return jsonify({"error": "Image decoding failed"}), 400
    
    write_log(f" 이미지 디코딩 완료 - 크기: {img_front.shape[1]}x{img_front.shape[0]}")
    
    # 이미지 저장 (디버깅용)
    if obstacle_pos:  # obstacle_pos가 있을 때만 저장
        save_img(img_front, ally_body_pos, obstacle_pos, label="front")
        write_log(" 전면 이미지 저장 완료")

    # 02_object_detection 함수
    write_log("02_object_detection")
    detections_front = object_detection(img_front)
    write_log(f"Front: {len(detections_front)}개 탐지")

    # 03_range_finder: 거리 측정
    write_log("03_range_finder: 거리 측정 시작")
    
    # obstacle_pos가 있으면 수동 거리 계산 모드
    if obstacle_pos:
        # 실제 거리 계산 (아군 → 장애물)
        dx = obstacle_pos['x'] - ally_body_pos['x']
        dz = obstacle_pos['z'] - ally_body_pos['z']
        actual_distance = (dx**2 + dz**2) ** 0.5
        
        write_log(f"📏 수동 거리 모드: {actual_distance:.2f}m")
        
        # 탐지된 객체들에 실제 거리 적용
        range_results = []
        for det in detections_front:
            range_results.append({
                'class_id': det['class_id'],
                'class_name': {0: "car", 1: "infantry", 2: "tank"}.get(det['class_id'], "unknown"),
                'distance': round(actual_distance, 2),  # 실제 거리 사용
                'x_center': det['x_center'],
                'y_center': det['y_center'],
                'width': det['width'],
                'height': det['height'],
                'confidence': det['confidence']
            })
        write_log(f"✅ 수동 거리 적용 완료: {len(range_results)}개 객체에 {actual_distance:.2f}m 적용")
    #     # 자동 거리 측정 모드 (기존 range_finder 사용)
    # range_results = range_finder(detections_front)
    # write_log(f"✅ 자동 거리 측정 완료: {len(range_results)}개")
    
    # 04_calculate_world_coordinates: 월드 좌표 계산
    position_results = []
    
    if range_results:
        write_log("04_calculate_world_coordinates: 월드 좌표 계산 시작")
        
        # 이미지 크기 추출
        img_height, img_width = img_front.shape[:2]
        
        # 포탑 각도 추출 (y축 회전)
        turret_angle_deg = ally_body_angle.get("y", 0.0)
        camera_x = ally_body_pos.get("x", 0.0)
        camera_z = ally_body_pos.get("z", 0.0)
        
        # 각 객체에 대해 월드 좌표 계산
        for result in range_results:
            # 픽셀 좌표 계산
            pixel_x = result['x_center'] * img_width
            pixel_y = result['y_center'] * img_height
            distance_m = result['distance']
            
            # 월드 좌표 계산
            world_coords = calculate_world_coordinates(
                distance_m=distance_m,
                pixel_x=pixel_x,
                pixel_y=pixel_y,
                camera_x=camera_x,
                camera_z=camera_z,
                turret_angle_deg=turret_angle_deg,
                img_width=img_width,
                img_height=img_height
            )
            
            # 결과 통합
            position_results.append({
                'class_id': result['class_id'],
                'class_name': result['class_name'],
                'distance': distance_m,
                'world_x': world_coords['world_x'],
                'world_z': world_coords['world_z'],
                'rel_angle_h': world_coords['rel_angle_h'],
                'rel_angle_v': world_coords['rel_angle_v'],
                'abs_angle': world_coords['abs_angle'],
                'confidence': result['confidence']
            })
            
            write_log(f"   {result['class_name']}: "
                      f"거리={distance_m:.2f}m, "
                      f"월드=({world_coords['world_x']:.2f}, {world_coords['world_z']:.2f}), "
                      f"각도={world_coords['abs_angle']:.1f}°")
        
        write_log(f" 월드 좌표 계산 완료: {len(position_results)}개")
    else:
        write_log(" 거리 측정 결과 없음 - 월드 좌표 계산 스킵")

    # 탐지 결과 시각화 (디버깅용)
    if obstacle_pos and detections_front:
        # 실제 거리 계산 (플레이어 → 장애물)
        dx = obstacle_pos['x'] - ally_body_pos['x']
        dz = obstacle_pos['z'] - ally_body_pos['z']
        actual_distance = (dx**2 + dz**2) ** 0.5
        
        # 1단계: 일반 탐지 결과 시각화 (detection_results 폴더)
        visualize_detections(img_front, detections_front, label="front")
        write_log(" [1단계] 탐지 결과 시각화 완료")
        
        # 2단계: 수동 측정용 시각화 - 캘리브레이션 데이터 수집용 (manual_measurements 폴더)
        visualize_manual_measurements(img_front, detections_front, actual_distance, label="manual")
        write_log(f" [2단계] 수동 측정 시각화 완료 (실제 거리: {actual_distance:.2f}m)")
        
        # 3단계: 거리 예측 결과 시각화 (range_results 폴더)
        if position_results:
            # position_results를 range_results 형식으로 변환
            range_results_for_viz = [
                {
                    'class_id': r['class_id'],
                    'class_name': r['class_name'],
                    'distance': r['distance'],
                    'x_center': detections_front[i]['x_center'],
                    'y_center': detections_front[i]['y_center'],
                    'width': detections_front[i]['width'],
                    'height': detections_front[i]['height'],
                    'confidence': r['confidence']
                }
                for i, r in enumerate(position_results)
            ]
            visualize_range_results(img_front, range_results_for_viz, label="front")
            write_log(" [3단계] 거리 예측 결과 시각화 완료")
            
            # 4단계: 월드 좌표 시각화 (world_coordinates 폴더)
            visualize_world_coordinates(img_front, position_results, detections_front, label="front")
            write_log(" [4단계] 월드 좌표 시각화 완료")

    # Response 데이터 생성 (실제 탐지 결과)
    response_data = []
    
    if position_results:
        for result in position_results:
            response_data.append({
                "class": result['class_id'],
                "object": {
                    "x": result['world_x'],
                    "y": 0.0,
                    "z": result['world_z']
                },
                "object_angle": {
                    "x": 0.0,
                    "y": 0.0
                }
            })
        
        write_log(f"📤 Response 생성 완료: {len(response_data)}개 객체")
    else:
        write_log("⚠️ 탐지된 객체 없음 - 빈 Response 반환")
    
    return jsonify(response_data)

# ====================================================
# 서버 시작
# ====================================================
if __name__ == '__main__':    
    app.run(host='0.0.0.0', port=5000, debug=False)
