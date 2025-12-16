# 관심영역 설정 후 해당 관심영역에 존재하는 객체와이 거리 계산

import cv2
import numpy as np
from PIL import Image
import os

# 이미지 경로
left_path = r'C:\Users\htw02\OneDrive\문서\Tank Challenge\capture_images\L\030_28.png'
right_path = r'C:\Users\htw02\OneDrive\문서\Tank Challenge\capture_images\R\030_28.png'

# 한글 경로 지원: PIL로 읽고 OpenCV로 변환
def load_image(path):
	pil_img = Image.open(path).convert('RGB')
	img = np.array(pil_img)
	return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

def find_tank_feature_point(img):
	# 이미지를 그레이스케일로 변환
	gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
	# SIFT 알고리즘으로 특징점 검출
	sift = cv2.SIFT_create()
	keypoints, descriptors = sift.detectAndCompute(gray, None)
	h, w = img.shape[:2]
	# 탱크가 이미지 중앙에 위치한다고 가정하여 중앙 영역으로 설정
	tank_region = {
		'x_min': int(w*0.4), 'x_max': int(w*0.6),
		'y_min': int(h*0.4), 'y_max': int(h*0.6)
	}
	tank_keypoints = []
	# 검출된 특징점 중 탱크 영역에 속하는 것만 필터링
	for kp in keypoints:
		x, y = int(kp.pt[0]), int(kp.pt[1])
		if (tank_region['x_min'] <= x <= tank_region['x_max'] and 
			tank_region['y_min'] <= y <= tank_region['y_max']):
			tank_keypoints.append(kp)
	# 탱크 영역 내 특징점 중 가장 강한 특징점 선택
	if tank_keypoints:
		best_kp = max(tank_keypoints, key=lambda kp: kp.response)
		feature_x = int(best_kp.pt[0])
		feature_y = int(best_kp.pt[1])
		return feature_x, feature_y
	else:
		# 특징점이 없으면 탱크 영역의 중심 반환
		return w//2, int(h*0.7)

# 이미지 로드

imgL = load_image(left_path)
imgR = load_image(right_path)

# 왼쪽 이미지에서 탱크 특징점 검출
feature_x, feature_y = find_tank_feature_point(imgL)

# 패치 크기 설정
patch_size = 21
half = patch_size // 2
hL, wL = imgL.shape[:2]
hR, wR = imgR.shape[:2]
fy = max(half, min(feature_y, hL - half - 1))
fx = max(half, min(feature_x, wL - half - 1))
patch = imgL[fy-half:fy+half+1, fx-half:fx+half+1]
line = imgR[fy-half:fy+half+1, :, :]
res = cv2.matchTemplate(line, patch, cv2.TM_SQDIFF_NORMED)
min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
matched_x = min_loc[0] + half

# disparity 계산
disparity = fx - matched_x

# 거리 계산 공식
baseline = 1.115  # m
focal_length = 920  # 픽셀
if disparity != 0:
	distance = (focal_length * baseline) / disparity
else:
	distance = None

print(f"왼쪽 특징점 x좌표: {fx}")
print(f"오른쪽 매칭 x좌표: {matched_x}")
print(f"Disparity: {disparity} px")
print(f"Baseline: {baseline} m")
print(f"Focal Length: {focal_length} px")
if distance:
	print(f"거리: {distance:.2f} m")
else:
	print("Disparity가 0이어서 거리를 계산할 수 없습니다.")

# 특징점 시각화 및 화면 표시

# 특징점 시각화: 왼쪽 이미지에 초록색 원과 좌표 표시
imgL_dot = imgL.copy()
cv2.circle(imgL_dot, (fx, fy), radius=8, color=(0,255,0), thickness=-1)  # 특징점 위치에 원 그리기
cv2.putText(imgL_dot, f'({fx},{fy})', (fx+15, fy-15), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,0), 2)  # 좌표 텍스트 표시
cv2.putText(imgL_dot, 'Left Feature Point', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)  # 설명 텍스트

# 특징점 시각화: 오른쪽 이미지에 파란색 원과 좌표 표시
imgR_dot = imgR.copy()
cv2.circle(imgR_dot, (matched_x, fy), radius=8, color=(255,0,0), thickness=-1)  # 매칭된 위치에 원 그리기
cv2.putText(imgR_dot, f'({matched_x},{fy})', (matched_x+15, fy-15), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255,0,0), 2)  # 좌표 텍스트 표시
cv2.putText(imgR_dot, 'Right Matched Point', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,0,0), 2)  # 설명 텍스트

cv2.imshow('Left Image with Green Dot', imgL_dot)
cv2.imshow('Right Image with Blue Dot', imgR_dot)
print("이미지가 화면에 표시되었습니다. 아무 키나 누르면 종료됩니다.")
cv2.waitKey(0)
cv2.destroyAllWindows()

# 이미지 저장 경로 및 파일명 생성
save_dir = r'C:\Users\htw02\OneDrive\문서\Tank Challenge\tw\camera_data\making_ppt'
os.makedirs(save_dir, exist_ok=True)

# 파일명에 번호 붙이기 (중복 방지)
def get_next_index(prefix, ext, directory):
	idx = 1
	while True:
		left_path = os.path.join(directory, f'{prefix}_distance{idx}_left{ext}')
		right_path = os.path.join(directory, f'{prefix}_distance{idx}_right{ext}')
		if not os.path.exists(left_path) and not os.path.exists(right_path):
			return idx, left_path, right_path
		idx += 1

prefix = '030_28'
ext = '.png'
idx, left_save_path, right_save_path = get_next_index(prefix, ext, save_dir)

# PIL로 저장 (한글 경로 지원)
Image.fromarray(cv2.cvtColor(imgL_dot, cv2.COLOR_BGR2RGB)).save(left_save_path)
Image.fromarray(cv2.cvtColor(imgR_dot, cv2.COLOR_BGR2RGB)).save(right_save_path)
print(f'왼쪽 이미지 저장: {left_save_path}')
print(f'오른쪽 이미지 저장: {right_save_path}')

