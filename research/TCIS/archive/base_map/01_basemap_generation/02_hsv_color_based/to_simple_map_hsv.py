import cv2
import numpy as np
import matplotlib.pyplot as plt
import os

# 현재 파일 기준 상대 경로로 map_images 폴더 접근
script_dir = os.path.dirname(os.path.abspath(__file__))
base_map_dir = os.path.join(script_dir, '..', '..')
map_images_path = os.path.join(base_map_dir, 'map_images', '01_forest_and_river.PNG')

img = cv2.imread(map_images_path)
img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
img_hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

# HSV 색공간에서 더 정확한 색상 구분
# H(색조): 0-180, S(채도): 0-255, V(명도): 0-255

# 물: 어두운 청록색 계열
mask_water = cv2.inRange(img_hsv, (85, 30, 20), (110, 255, 100))

# 모폴로지 연산으로 노이즈 제거
kernel = np.ones((3,3), np.uint8)
mask_water = cv2.morphologyEx(mask_water, cv2.MORPH_CLOSE, kernel)  # 작은 구멍 메우기
mask_water = cv2.morphologyEx(mask_water, cv2.MORPH_OPEN, kernel)   # 작은 노이즈 제거

# 작은 영역 제거 (면적 필터링)
contours, _ = cv2.findContours(mask_water, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
for cnt in contours:
    if cv2.contourArea(cnt) < 50:  # 50픽셀 이하는 제거
        cv2.drawContours(mask_water, [cnt], -1, 0, -1)

# 숲: 녹색 계열
mask_forest = cv2.inRange(img_hsv, (30, 40, 20), (80, 255, 160))

# 도로: 회색 계열 (채도가 낮고 명도가 중간)
mask_road = cv2.inRange(img_hsv, (0, 0, 100), (180, 30, 180))

# 기본 회색 배경
base = np.ones_like(img_rgb) * 230

# 각 구역 색 입히기 (우선순위: 도로 > 물 > 숲)
base[mask_forest > 0] = (160, 200, 160)   # 숲: 연한 녹색
base[mask_water > 0] = (180, 210, 240)    # 물: 연한 파란색
base[mask_road > 0] = (180, 180, 180)     # 도로: 회색

# 결과 표시
fig, axes = plt.subplots(2, 3, figsize=(15, 10))

axes[0, 0].imshow(img_rgb)
axes[0, 0].set_title('Original')
axes[0, 0].axis('off')

axes[0, 1].imshow(mask_water, cmap='gray')
axes[0, 1].set_title('Water Mask')
axes[0, 1].axis('off')

axes[0, 2].imshow(mask_forest, cmap='gray')
axes[0, 2].set_title('Forest Mask')
axes[0, 2].axis('off')

axes[1, 0].imshow(mask_road, cmap='gray')
axes[1, 0].set_title('Road Mask')
axes[1, 0].axis('off')

axes[1, 1].imshow(base)pip install ultralytics
axes[1, 1].set_title('Result')
axes[1, 1].axis('off')

axes[1, 2].axis('off')

plt.tight_layout()
plt.show()
