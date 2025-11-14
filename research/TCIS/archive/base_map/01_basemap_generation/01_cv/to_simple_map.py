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

# 색상 범위 지정
# 물: #022326 (RGB: 2,35,38) 포함 + 파란색 계열 (RGB: 70~105, 75~110, 150~255)
mask_water = cv2.inRange(img_rgb, (0, 30, 35), (110, 115, 255))
mask_forest = cv2.inRange(img_rgb, (30, 80, 20), (100, 160, 80))
mask_road = cv2.inRange(img_rgb, (100, 100, 100), (180, 180, 180))

# 기본 회색 배경
base = np.ones_like(img_rgb) * 230

# 각 구역 색 입히기
# base[mask_forest > 0] = (160, 200, 160)   # 숲
base[mask_water > 0] = (180, 210, 240)    # 물
# base[mask_road > 0] = (180, 180, 180)     # 도로

plt.imshow(base)
plt.axis('off')
plt.show()
