# VDRS 통합 시스템 (Visual Detection Ranging System)
from flask import Flask, request, jsonify
from datetime import datetime
import base64
import cv2
import numpy as np
from ultralytics import YOLO
from typing import List, Dict, Tuple, Optional
import os

# ====================================================
# 전역 변수
# ====================================================
IMAGE_WIDTH = 800

# 전면 이미지 필터링 범위
FRONT_EXCLUDE_LEFT = 175   # 왼쪽 제외 영역 (픽셀)
FRONT_EXCLUDE_RIGHT = 175  # 오른쪽 제외 영역 (픽셀)

# YOLO 신뢰도 임계값
CONFIDENCE_THRESHOLD = 0.8  # 80% 이상만 탐지 결과로 저장

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
    save_dir = "saved_images"
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
# 02_convert_to_16_9 함수
# ====================================================
def convert_to_16_9(img: np.ndarray, target_width: int = 800, target_height: int = 450) -> np.ndarray:
    """
    512x512 이미지를 800x450 (16:9) 비율로 변환 (좌우 패딩 추가)
    """
    h, w = img.shape[:2]
    
    # 세로 크기를 목표 높이에 맞춤
    scale = target_height / h
    new_width = int(w * scale)
    new_height = target_height
    
    # 이미지 리사이즈
    resized = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_LINEAR)
    
    # 좌우 패딩 계산
    padding_total = target_width - new_width
    padding_left = padding_total // 2
    padding_right = padding_total - padding_left
    
    # 패딩 추가 (검은색)
    converted = cv2.copyMakeBorder(
        resized,
        top=0,
        bottom=0,
        left=padding_left,
        right=padding_right,
        borderType=cv2.BORDER_CONSTANT,
        value=[0, 0, 0]
    )
    
    return converted

# ====================================================
# 03_object_detection 함수
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
        
        # 바운딩 박스 그리기
        cv2.rectangle(vis_img, (x1, y1), (x2, y2), color, 1)
        
        # 텍스트 (클래스명 + 신뢰도)
        text = f"{class_name}: {det['confidence']:.2f}"
        text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)[0]
        
        # 텍스트 배경
        cv2.rectangle(vis_img, (x1, y1 - text_size[1] - 4), 
                     (x1 + text_size[0], y1), color, -1)
        
        # 텍스트 그리기
        cv2.putText(vis_img, text, (x1, y1 - 2), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
    
    # 저장 디렉토리 생성
    save_dir = "detection_results"
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
# 04_filter_front_center_region 함수
# ====================================================
def filter_center_region(detections: List[Dict], 
                         image_width: int = IMAGE_WIDTH,
                         exclude_left: int = FRONT_EXCLUDE_LEFT,
                         exclude_right: int = FRONT_EXCLUDE_RIGHT) -> List[Dict]:
    """이미지에서 좌우 영역에 걸치지 않은 객체만 필터링 (조금이라도 걸치면 제외)"""
    left_boundary = exclude_left / image_width
    right_boundary = (image_width - exclude_right) / image_width
    
    filtered = []
    for det in detections:
        x_center = det['x_center']
        half_width = det['width'] / 2
        x_min = x_center - half_width
        x_max = x_center + half_width
        
        # 바운딩 박스가 완전히 중앙 영역 안에 있어야 함 (조금이라도 걸치면 제외)
        if x_min >= left_boundary and x_max <= right_boundary:
            filtered.append(det)
    
    return filtered

# ====================================================
# 05_match_objects 함수
# ====================================================
def match_stereo_objects(left_detections: List[Dict],
                         right_detections: List[Dict],
                         y_threshold: float = 0.05) -> List[Tuple[Dict, Dict]]:
    """좌우 스테레오 이미지에서 동일 객체 매칭"""
    matched_pairs = []
    used_right_indices = set()
    
    for left_det in left_detections:
        best_match = None
        best_score = 0
        best_idx = -1
        
        for idx, right_det in enumerate(right_detections):
            if idx in used_right_indices:
                continue
            
            # 조건: 같은 클래스 + Y 좌표 유사
            if left_det['class_id'] != right_det['class_id']:
                continue
            
            y_diff = abs(left_det['y_center'] - right_det['y_center'])
            if y_diff > y_threshold:
                continue
            
            # 매칭 점수
            y_score = 1 - (y_diff / y_threshold)
            
            if y_score > best_score:
                best_score = y_score
                best_match = right_det
                best_idx = idx
        
        if best_match:
            matched_pairs.append((left_det, best_match))
            used_right_indices.add(best_idx)
    
    return matched_pairs


def match_with_front_image(stereo_pairs: List[Tuple[Dict, Dict]],
                           front_detections: List[Dict],
                           y_threshold: float = 0.08) -> List[Dict]:
    """스테레오 쌍과 전면 이미지 객체를 매칭"""
    matched_objects = []
    used_front_indices = set()
    
    for left_det, right_det in stereo_pairs:
        best_match = None
        best_score = 0
        best_idx = -1
        
        stereo_y_avg = (left_det['y_center'] + right_det['y_center']) / 2
        
        for idx, front_det in enumerate(front_detections):
            if idx in used_front_indices:
                continue
            
            # 조건: 같은 클래스 + Y 좌표 유사
            if left_det['class_id'] != front_det['class_id']:
                continue
            
            y_diff = abs(stereo_y_avg - front_det['y_center'])
            if y_diff > y_threshold:
                continue
            
            # 매칭 점수
            y_score = 1 - (y_diff / y_threshold)
            
            if y_score > best_score:
                best_score = y_score
                best_match = front_det
                best_idx = idx
        
        if best_match:
            matched_objects.append({
                'left': left_det,
                'right': right_det,
                'front': best_match,
                'class_id': left_det['class_id']
            })
            used_front_indices.add(best_idx)
    
    return matched_objects


def visualize_matched_objects(img_left, img_right, img_front, 
                              matched_objects: List[Dict],
                              label="matched"):
    """
    매칭된 객체를 3개 이미지에 시각화
    
    Args:
        img_left: 왼쪽 스테레오 이미지
        img_right: 오른쪽 스테레오 이미지
        img_front: 전면 이미지
        matched_objects: match_with_front_image()의 반환값
        label: 저장 파일명 레이블
    
    Returns:
        결합된 시각화 이미지
    """
    # 이미지 복사
    vis_left = img_left.copy()
    vis_right = img_right.copy()
    vis_front = img_front.copy()
    
    # 클래스별 색상 (BGR)
    colors = {
        0: (0, 255, 0),    # Green - car
        1: (255, 255, 0),  # Yellow - infantry
        2: (0, 0, 255),    # Red - tank
    }
    
    class_names = {
        0: "car",
        1: "infantry",
        2: "tank"
    }
    
    # 각 매칭된 객체에 대해 시각화
    for idx, matched in enumerate(matched_objects, 1):
        class_id = matched['class_id']
        color = colors.get(class_id, (255, 255, 255))
        class_name = class_names.get(class_id, "unknown")
        
        # 왼쪽 이미지 시각화
        left_det = matched['left']
        h_left, w_left = vis_left.shape[:2]
        x_center = left_det['x_center'] * w_left
        y_center = left_det['y_center'] * h_left
        width = left_det['width'] * w_left
        height = left_det['height'] * h_left
        x1 = int(x_center - width / 2)
        y1 = int(y_center - height / 2)
        x2 = int(x_center + width / 2)
        y2 = int(y_center + height / 2)
        
        cv2.rectangle(vis_left, (x1, y1), (x2, y2), color, 1)
        
        # 중심점 표시 (작은 원)
        center_x = int(x_center)
        center_y = int(y_center)
        cv2.circle(vis_left, (center_x, center_y), 3, color, -1)
        
        # 텍스트 (클래스명)
        text = f"#{idx} {class_name}"
        cv2.putText(vis_left, text, (x1, y1 - 5), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        
        # 중심 좌표 텍스트
        coord_text = f"({center_x},{center_y})"
        cv2.putText(vis_left, coord_text, (center_x + 5, center_y - 5), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
        
        # 오른쪽 이미지 시각화
        right_det = matched['right']
        h_right, w_right = vis_right.shape[:2]
        x_center = right_det['x_center'] * w_right
        y_center = right_det['y_center'] * h_right
        width = right_det['width'] * w_right
        height = right_det['height'] * h_right
        x1 = int(x_center - width / 2)
        y1 = int(y_center - height / 2)
        x2 = int(x_center + width / 2)
        y2 = int(y_center + height / 2)
        
        cv2.rectangle(vis_right, (x1, y1), (x2, y2), color, 1)
        
        # 중심점 표시 (작은 원)
        center_x = int(x_center)
        center_y = int(y_center)
        cv2.circle(vis_right, (center_x, center_y), 3, color, -1)
        
        # 텍스트 (클래스명)
        text = f"#{idx} {class_name}"
        cv2.putText(vis_right, text, (x1, y1 - 5), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        
        # 중심 좌표 텍스트
        coord_text = f"({center_x},{center_y})"
        cv2.putText(vis_right, coord_text, (center_x + 5, center_y - 5), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
        
        # 전면 이미지 시각화
        front_det = matched['front']
        h_front, w_front = vis_front.shape[:2]
        x_center = front_det['x_center'] * w_front
        y_center = front_det['y_center'] * h_front
        width = front_det['width'] * w_front
        height = front_det['height'] * h_front
        x1 = int(x_center - width / 2)
        y1 = int(y_center - height / 2)
        x2 = int(x_center + width / 2)
        y2 = int(y_center + height / 2)
        
        cv2.rectangle(vis_front, (x1, y1), (x2, y2), color, 1)
        
        # 중심점 표시 (작은 원)
        center_x = int(x_center)
        center_y = int(y_center)
        cv2.circle(vis_front, (center_x, center_y), 3, color, -1)
        
        # 텍스트 (클래스명)
        text = f"#{idx} {class_name}"
        cv2.putText(vis_front, text, (x1, y1 - 5), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        
        # 중심 좌표 텍스트
        coord_text = f"({center_x},{center_y})"
        cv2.putText(vis_front, coord_text, (center_x + 5, center_y - 5), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

    # 필터링 영역 표시 (전면 이미지)
    h_front, w_front = vis_front.shape[:2]
    left_boundary = FRONT_EXCLUDE_LEFT
    right_boundary = w_front - FRONT_EXCLUDE_RIGHT
    
    # 반투명 빨간색 영역 표시
    overlay = vis_front.copy()
    cv2.rectangle(overlay, (0, 0), (left_boundary, h_front), (0, 0, 255), -1)
    cv2.rectangle(overlay, (right_boundary, 0), (w_front, h_front), (0, 0, 255), -1)
    cv2.addWeighted(overlay, 0.2, vis_front, 0.8, 0, vis_front)
    
    # 경계선 표시
    cv2.line(vis_front, (left_boundary, 0), (left_boundary, h_front), (0, 0, 255), 1)
    cv2.line(vis_front, (right_boundary, 0), (right_boundary, h_front), (0, 0, 255), 1)
    
    # 3개 이미지를 가로로 결합
    # 전면 이미지 크기에 맞춰 스테레오 이미지 리사이즈
    h_target = h_front
    w_left_resized = int(w_left * (h_target / h_left))
    w_right_resized = int(w_right * (h_target / h_right))
    
    vis_left_resized = cv2.resize(vis_left, (w_left_resized, h_target))
    vis_right_resized = cv2.resize(vis_right, (w_right_resized, h_target))
    
    # 이미지 결합
    combined = np.hstack([vis_left_resized, vis_front, vis_right_resized])
    
    # 텍스트 레이블 추가
    cv2.putText(combined, "LEFT", (10, 30), 
               cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 1)
    cv2.putText(combined, "FRONT", (w_left_resized + 10, 30), 
               cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 1)
    cv2.putText(combined, "RIGHT", (w_left_resized + w_front + 10, 30), 
               cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 1)

    # 매칭 개수 표시
    info_text = f"Matched Objects: {len(matched_objects)}"
    cv2.putText(combined, info_text, (10, h_target - 20), 
               cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 1)

    # 저장 디렉토리 생성
    save_dir = "match_results"
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    
    # 파일명 생성
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    filename = f"{timestamp_str}_{label}_matched.png"
    filepath = os.path.join(save_dir, filename)
    
    # 이미지 저장
    cv2.imwrite(filepath, combined)
    write_log(f"🎯 매칭 결과 저장: {filepath}")
    
    return combined

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
    image_b64 = request_data.get("image_b64")
    stereo_image_left_b64 = request_data.get("stereo_image_left_b64")
    stereo_image_right_b64 = request_data.get("stereo_image_right_b64")
    obstacle_pos = request_data.get("obstacle_pos") # 디버그용 추가 필드, 1개 옵스타클만 배치해서 pos x, y, z 받음

    """
    < request data 예시 >
    "time": (simulation time)
    "ally_body_pos":{"x": , "y": , "z": }
    "ally_body_angle":{"x": , "y": , "z": }
    "ally_speed":(m/s)
    "image_b64": (base64 string)
    "stereo_image_left_b64": (base64 string)
    "stereo_image_right_b64": (base64 string)
    "obstacle_pos":{"x": , "y": , "z": }  # 디버그용 추가 필드
    """

    # 01_decode_base64_to_image 함수
    write_log("01_decode_base64_to_image")
    img_front = decode_base64_to_image(image_b64)
    img_left = decode_base64_to_image(stereo_image_left_b64)
    img_right = decode_base64_to_image(stereo_image_right_b64)
    
    # 디코딩 실패 체크
    if img_front is None or img_left is None or img_right is None:
        write_log("❌ 이미지 디코딩 실패")
        return jsonify({"error": "Image decoding failed"}), 400
    
    # 이미지 저장 (디버깅용)
    if obstacle_pos:  # obstacle_pos가 있을 때만 저장
        save_img(img_front, ally_body_pos, obstacle_pos, label="front")
        save_img(img_left, ally_body_pos, obstacle_pos, label="left")
        save_img(img_right, ally_body_pos, obstacle_pos, label="right")
        write_log("✅ 3개 이미지 저장 완료")

    # 02_convert_to_16_9 함수
    write_log("02_convert_to_16_9")
    converted_img_left = convert_to_16_9(img_left)
    converted_img_right = convert_to_16_9(img_right)

    # 이미지 저장 (디버깅용)
    if obstacle_pos:  # obstacle_pos가 있을 때만 저장
        save_img(converted_img_left, ally_body_pos, obstacle_pos, label="left_16_9")
        save_img(converted_img_right, ally_body_pos, obstacle_pos, label="right_16_9")
        write_log("✅ 스테레오 이미지 16:9 변환 후 저장 완료")

    # 03_object_detection 함수
    write_log("03_object_detection")
    
    detections_front = object_detection(img_front)
    detections_left = object_detection(converted_img_left)
    detections_right = object_detection(converted_img_right)
    
    write_log(f"Front: {len(detections_front)}개 탐지")
    write_log(f"Left:  {len(detections_left)}개 탐지")
    write_log(f"Right: {len(detections_right)}개 탐지")

    # 탐지 결과 시각화 (디버깅용)
    if obstacle_pos:
        visualize_detections(img_front, detections_front, label="front")
        visualize_detections(converted_img_left, detections_left, label="left")
        visualize_detections(converted_img_right, detections_right, label="right")
        write_log("✅ 탐지 결과 시각화 완료")

    # 04_filter_center_region 함수 (좌우 175px 제외 영역 필터링)
    write_log("\n04_filter_center_region")
    
    # 3개 이미지 모두 중앙 영역만 필터링
    detections_front_filtered = filter_center_region(detections_front)
    detections_left_filtered = filter_center_region(detections_left)
    detections_right_filtered = filter_center_region(detections_right)
    
    write_log(f"  📷 Front - 필터링 전: {len(detections_front)}개, 필터링 후: {len(detections_front_filtered)}개")
    write_log(f"  📷 Left  - 필터링 전: {len(detections_left)}개, 필터링 후: {len(detections_left_filtered)}개")
    write_log(f"  📷 Right - 필터링 전: {len(detections_right)}개, 필터링 후: {len(detections_right_filtered)}개")

    # 05_match_objects 함수
    write_log("\n05_match_objects")
    
    # Step 1: 좌우 스테레오 매칭 (필터링된 이미지 사용)
    stereo_pairs = match_stereo_objects(detections_left_filtered, detections_right_filtered)
    write_log(f"  ✅ 좌우 매칭: {len(stereo_pairs)}쌍")
    
    # Step 2: 전면 이미지와 매칭 (필터링된 이미지 사용)
    matched_objects = match_with_front_image(stereo_pairs, detections_front_filtered)
    write_log(f"  ✅ 전면 매칭: {len(matched_objects)}개")
    
    # 매칭 결과 시각화 (디버깅용)
    if obstacle_pos and len(matched_objects) > 0:
        visualize_matched_objects(converted_img_left, converted_img_right, img_front,
                                 matched_objects, label="match")
        write_log("✅ 매칭 결과 시각화 완료")

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
