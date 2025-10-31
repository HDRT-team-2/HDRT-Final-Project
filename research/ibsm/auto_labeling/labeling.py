# =========================================================================
# auto_label_obstacles.py
# =========================================================================
# 설명:
#   - 'input' 폴더 안의 맵(map)별, 장애물(obstacle)별 이미지들을 자동으로 라벨링
#   - 라벨링된 텍스트(.txt)와 시각화 이미지를 'output' 폴더에 저장
#   - 탐지 객체가 정확히 1개일 때만 라벨링 수행
#   - 탐지 0개 또는 2개 이상인 이미지는 삭제
#   - map/obstacle 구조를 그대로 유지
# =========================================================================

import os
import cv2
from ultralytics import YOLO
import shutil

# =========================
# 사용자 설정
# =========================
INPUT_DIR = r"c:\PYSOU\final_project\labeling\input"  # 원본 이미지 폴더
OUTPUT_DIR = r"c:\PYSOU\final_project\labeling\output"  # 라벨링 결과 저장 폴더
CONF_THRES = 0.5  # YOLO 탐지 신뢰도 threshold

# YOLO 모델: 기본 YOLOv8n 모델 사용
MODEL_PATH = "yolov8n.pt"

# obstacle별 클래스 번호 통일 (라벨링 시 사용)
CLASS_MAPPING = {
    "Car 2": 1,
    "Car 3": 2,
    "Car 4": 3, 
    "Human 1": 4,
    "Tank 1": 5,
    "Rock 1": 6,
    "Rock 2": 7, 
    "Mine 1": 8, 
    "Wall 2": 9,
    "Wall 2 X 10": 10,
    "Other": 0  # 매핑되지 않은 기타 클래스
}

# =========================
# YOLO 모델 로드
# =========================
print("🔹 YOLO 모델 로드 중...")
model = YOLO(MODEL_PATH)  # 모델 불러오기
print("✅ 모델 로드 완료\n")

# =========================
# 기존 output 폴더 삭제 후 새로 생성
# =========================
if os.path.exists(OUTPUT_DIR):
    shutil.rmtree(OUTPUT_DIR)  # 이전 결과 삭제
os.makedirs(OUTPUT_DIR, exist_ok=True)  # output 폴더 생성

# =========================
# map 폴더 순회 (map별 처리)
# =========================
for map_name in os.listdir(INPUT_DIR):
    map_path = os.path.join(INPUT_DIR, map_name)
    if not os.path.isdir(map_path):
        continue  # 폴더가 아니면 건너뜀

    print(f"\n🗺️ [{map_name}] 맵 처리 중...")

    # =========================
    # obstacle 폴더 순회 (장애물별 처리)
    # =========================
    for obs_name in os.listdir(map_path):
        obs_path = os.path.join(map_path, obs_name)
        if not os.path.isdir(obs_path):
            continue  # 폴더가 아니면 건너뜀
        print(f"  🚗 [{obs_name}] 클래스 처리 중...")

        # output 구조 생성: map/obstacle/labels
        output_obs_path = os.path.join(OUTPUT_DIR, map_name, obs_name)
        output_labels_path = os.path.join(output_obs_path, "labels")
        os.makedirs(output_labels_path, exist_ok=True)

        # 현재 obstacle의 통일 클래스 번호
        unified_class_id = CLASS_MAPPING.get(obs_name, 9)

        # =========================
        # 이미지 파일 순회
        # =========================
        for img_name in os.listdir(obs_path):
            img_path = os.path.join(obs_path, img_name)
            if not img_name.lower().endswith((".jpg", ".png", ".jpeg")):
                continue  # 이미지 파일이 아니면 건너뜀

            print(f"    ▶ {img_name} 라벨링 중...")

            # =========================
            # YOLO 예측
            # =========================
            results = model.predict(source=img_path, conf=CONF_THRES, verbose=False)
            result = results[0]

            # =========================
            # 탐지된 객체 수 확인
            # =========================
            num_boxes = len(result.boxes)
            if num_boxes != 1:
                # 탐지 실패 (0개 또는 2개 이상) → 이미지 삭제
                print(f"       ⚠️ {img_name} — 탐지 {num_boxes}개, 삭제됨")
                os.remove(img_path)
                continue

            # =========================
            # 탐지 1개인 경우 라벨링 수행
            # =========================
            box = result.boxes[0]
            x1, y1, x2, y2 = map(int, box.xyxy[0])  # 좌표 int로 변환
            h, w = result.orig_shape  # 원본 이미지 높이, 너비
            x_center = ((x1 + x2) / 2) / w
            y_center = ((y1 + y2) / 2) / h
            box_w = (x2 - x1) / w
            box_h = (y2 - y1) / h

            # =========================
            # 라벨 텍스트 저장 (YOLO 포맷)
            # =========================
            base_name = os.path.splitext(img_name)[0]
            label_txt_path = os.path.join(output_labels_path, f"{base_name}.txt")
            with open(label_txt_path, "w") as f:
                f.write(f"{unified_class_id} {x_center:.6f} {y_center:.6f} {box_w:.6f} {box_h:.6f}\n")

            # =========================
            # 시각화 이미지 저장 (녹색 박스 + 클래스명)
            # =========================
            img = cv2.imread(img_path)
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(img, f"{obs_name}", (x1, y1-5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)

            output_img_path = os.path.join(output_obs_path, f"{base_name}_labeled.jpg")
            cv2.imwrite(output_img_path, img)

            # =========================
            # 진행 로그 출력
            # =========================
            print(f"       ✅ 라벨 저장 → {label_txt_path}")
            print(f"       🖼️ 시각화 저장 → {output_img_path}")

# =========================
# 전체 완료 메시지
# =========================
print("\n🎉 모든 맵 및 이미지 라벨링 완료!")
print(f"📁 결과 폴더: '{OUTPUT_DIR}'")
