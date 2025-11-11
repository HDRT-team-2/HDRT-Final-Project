# =========================================================================
# auto_detect_all_obstacles_filter.py
# =========================================================================
# 설명:
#   - YOLOv9e 모델을 사용하여 폴더 내 모든 이미지의 객체 탐지 수행
#   - 탐지된 객체가 정확히 1개일 경우만 라벨링과 시각화 저장
#   - 탐지 0개 또는 2개 이상인 경우 원본 이미지 삭제
#   - 라벨 파일(.txt)은 YOLO 포맷(x_center, y_center, width, height)으로 저장
# =========================================================================

import os
import cv2
from ultralytics import YOLO
import shutil

# =========================
# 사용자 설정
# =========================
INPUT_DIR = r"c:\PYSOU\final_project\labeling\input"        # 원본 이미지 폴더
OUTPUT_DIR = r"c:\PYSOU\final_project\labeling\output_filtered"  # 시각화 이미지 저장 폴더
LABELS_DIR = os.path.join(OUTPUT_DIR, "labels")              # 라벨 텍스트(.txt) 저장 폴더
CONF_THRES = 0.5  # YOLO 탐지 신뢰도 threshold

# =========================
# YOLOv9e 모델 로드 (pretrained)
# =========================
model = YOLO("yolov9e.pt")

# =========================
# 출력 폴더 초기화
# =========================
if os.path.exists(OUTPUT_DIR):
    shutil.rmtree(OUTPUT_DIR)  # 이전 결과 삭제
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(LABELS_DIR, exist_ok=True)  # 라벨 폴더 생성

# =========================
# 입력 이미지 리스트 생성
# =========================
image_files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith((".png", ".jpg", ".jpeg"))]
print(f"[INFO] 총 {len(image_files)}개의 이미지 탐지 시작...")

# =========================
# 이미지별 탐지 및 라벨링
# =========================
for img_name in image_files:
    img_path = os.path.join(INPUT_DIR, img_name)
    img = cv2.imread(img_path)
    h, w, _ = img.shape

    # YOLOv9e 예측 수행
    results = model.predict(source=img_path, conf=CONF_THRES, verbose=False)

    # =========================
    # 모든 탐지 객체 수집
    # =========================
    detected_boxes = []
    for r in results:
        for box in r.boxes:
            cls_id = int(box.cls[0])
            cls_name = model.names[cls_id]
            conf = float(box.conf[0])
            detected_boxes.append((cls_id, cls_name, box, conf))

    # =========================
    # 탐지된 객체가 1개일 때만 라벨링 및 시각화
    # =========================
    if len(detected_boxes) == 1:
        cls_id, cls_name, box, conf = detected_boxes[0]
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        x_center = ((x1 + x2)/2)/w
        y_center = ((y1 + y2)/2)/h
        box_w = (x2 - x1)/w
        box_h = (y2 - y1)/h

        # -------------------------
        # 라벨 파일 저장 (YOLO 포맷)
        # -------------------------
        label_file = os.path.join(LABELS_DIR, img_name.rsplit('.', 1)[0] + ".txt")
        with open(label_file, "w") as f:
            f.write(f"{cls_id} {x_center:.6f} {y_center:.6f} {box_w:.6f} {box_h:.6f}\n")

        # -------------------------
        # 시각화 이미지 저장
        # -------------------------
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)  # 박스 그리기
        cv2.putText(img, f"{cls_name} {conf:.2f}", (x1, y1-5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        save_path = os.path.join_
