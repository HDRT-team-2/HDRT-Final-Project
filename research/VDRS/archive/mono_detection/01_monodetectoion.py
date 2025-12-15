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
CONFIDENCE_THRESHOLD = 0.5  # 80% 이상만 탐지 결과로 저장

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
        
        write_log(f"✅ 객체 탐지 완료: {len(detections)}개 탐지")
        return detections
    
    except Exception as e:
        write_log(f"❌ 객체 탐지 실패: {e}")
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
    write_log(f"📷 탐지 결과 저장: {filepath}")
    
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
        # TODO: 실험 데이터로 수식 보정 필요
        # 임시 공식 (예시)
        if height > 0:
            distance = 1.0 / height  # 간단한 역비례 관계 (실험 후 보정)
        else:
            distance = 999.0  # 측정 불가
        return distance
    
    def calculate_distance_infantry(height):
        """
        Infantry 클래스의 상하 길이 기반 거리 계산
        height: 정규화된 높이 값 (0~1)
        """
        # TODO: 실험 데이터로 수식 보정 필요
        if height > 0:
            distance = 0.8 / height  # Car보다 작은 객체 (실험 후 보정)
        else:
            distance = 999.0
        return distance
    
    def calculate_distance_tank(height):
        """
        Tank 클래스의 상하 길이 기반 거리 계산
        height: 정규화된 높이 값 (0~1)
        """
        # TODO: 실험 데이터로 수식 보정 필요
        if height > 0:
            distance = 1.2 / height  # Car보다 큰 객체 (실험 후 보정)
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
    write_log(f"📏 거리 측정 결과 저장: {filepath}")
    
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
        write_log("❌ 이미지 디코딩 실패")
        return jsonify({"error": "Image decoding failed"}), 400
    
    write_log(f"✅ 이미지 디코딩 완료 - 크기: {img_front.shape[1]}x{img_front.shape[0]}")
    
    # 이미지 저장 (디버깅용)
    if obstacle_pos:  # obstacle_pos가 있을 때만 저장
        save_img(img_front, ally_body_pos, obstacle_pos, label="front")
        write_log("✅ 전면 이미지 저장 완료")

    # 02_object_detection 함수
    write_log("02_object_detection")
    detections_front = object_detection(img_front)
    write_log(f"Front: {len(detections_front)}개 탐지")

    # # 03_range_finder 함수
    # write_log("03_range_finder")
    # range_results = range_finder(detections_front)
    # write_log(f"Range: {len(range_results)}개 거리 측정 완료")

    # 탐지 결과 시각화 (디버깅용)
    if obstacle_pos:
        visualize_detections(img_front, detections_front, label="front")
        write_log("✅ 탐지 결과 시각화 완료")
        
    #     # 거리 측정 결과 시각화 (디버깅용)
    #     visualize_range_results(img_front, range_results, label="front")
    #     write_log("✅ 거리 측정 결과 시각화 완료")

    # Response 데이터 생성 (임시 더미 데이터)
    response_data = [
        {
            "class": 0, # car
            "object": {"x": 0.0, "y": 0.0, "z": 0.0}, # x, z: 평면좌표, y: 고도
            "object_angle": {"x": 0.0, "y": 0.0} # 차후 고도화 염두에 둔 필드
        },
        {
            "class": 1, # infantry
            "object": {"x": 0.0, "y": 0.0, "z": 0.0}, # x, z: 평면좌표, y: 고도
            "object_angle": {"x": 0.0, "y": 0.0} # 차후 고도화 염두에 둔 필드
        },
        {
            "class": 2, # tank
            "object": {"x": 0.0, "y": 0.0, "z": 0.0}, # x, z: 평면좌표, y: 고도
            "object_angle": {"x": 0.0, "y": 0.0} # 차후 고도화 염두에 둔 필드
        }
    ]

    return jsonify(response_data)

# ====================================================
# 서버 시작
# ====================================================
if __name__ == '__main__':    
    app.run(host='0.0.0.0', port=5000, debug=False)
