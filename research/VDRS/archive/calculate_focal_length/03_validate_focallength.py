# diaparity 계산하는 코드

import cv2 # OpenCV 라이브러리
import numpy as np # NumPy 라이브러리
from PIL import Image # PIL 라이브러리

# 파일 경로 (새로운 이미지로 변경)
left_path = r'C:\Users\htw02\OneDrive\문서\Tank Challenge\capture_images\L\012_39.png'
right_path = r'C:\Users\htw02\OneDrive\문서\Tank Challenge\capture_images\R\012_39.png'

# 한글 경로 지원: PIL로 읽고 OpenCV로 변환
def load_image(path):
    pil_img = Image.open(path).convert('RGB')
    img = np.array(pil_img)
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)


def find_enemy_tank_feature_point(img):
    """적 탱크를 검출하는 함수: 이미지 중앙 상단 영역에서 특징점 선택"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    sift = cv2.SIFT_create()
    keypoints, descriptors = sift.detectAndCompute(gray, None)
    h, w = img.shape[:2]
    # 적 탱크가 있을 것으로 예상되는 영역 (이미지 중앙 상단)
    region = {
        'x_min': int(w * 0.35), 'x_max': int(w * 0.65),
        'y_min': int(h * 0.15), 'y_max': int(h * 0.45)
    }
    enemy_keypoints = []
    for kp in keypoints:
        x, y = int(kp.pt[0]), int(kp.pt[1])
        if (region['x_min'] <= x <= region['x_max'] and
            region['y_min'] <= y <= region['y_max']):
            enemy_keypoints.append(kp)
    if enemy_keypoints:
        best_kp = max(enemy_keypoints, key=lambda kp: kp.response)
        feature_x = int(best_kp.pt[0])
        feature_y = int(best_kp.pt[1])
        return feature_x, feature_y
    else:
        # 특징점이 없으면 중앙 상단 반환
        return w // 2, int(h * 0.3)

def find_enemy_tank_feature_point(img):
    """적 탱크를 검출하는 함수: 이미지 중앙 상단 영역에서 특징점 선택"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    sift = cv2.SIFT_create()
    keypoints, descriptors = sift.detectAndCompute(gray, None)
    h, w = img.shape[:2]
    # 적 탱크가 있을 것으로 예상되는 영역 (이미지 중앙 상단)
    region = {
        'x_min': int(w * 0.35), 'x_max': int(w * 0.65),
        'y_min': int(h * 0.15), 'y_max': int(h * 0.45)
    }
    enemy_keypoints = []
    for kp in keypoints:
        x, y = int(kp.pt[0]), int(kp.pt[1])
        if (region['x_min'] <= x <= region['x_max'] and
            region['y_min'] <= y <= region['y_max']):
            enemy_keypoints.append(kp)
    if enemy_keypoints:
        best_kp = max(enemy_keypoints, key=lambda kp: kp.response)
        feature_x = int(best_kp.pt[0])
        feature_y = int(best_kp.pt[1])
        return feature_x, feature_y
    else:
        # 특징점이 없으면 중앙 상단 반환
        return w // 2, int(h * 0.3)


imgL = load_image(left_path) # 왼쪽 이미지 로드
imgR = load_image(right_path) # 오른쪽 이미지 로드

# 실제 이미지 크기 확인
print(f"실제 이미지 크기: {imgL.shape}") # (높이, 너비, 채널)
print(f"높이: {imgL.shape[0]}, 너비: {imgL.shape[1]}") # 높이와 너비 출력

# 왼쪽 이미지에서 적 탱크 특징점 자동 검출
feature_x, feature_y = find_enemy_tank_feature_point(imgL)
print(f"적 탱크에서 검출된 특징점: ({feature_x}, {feature_y})")


# 이미지 크기 확인
hL, wL = imgL.shape[:2]
hR, wR = imgR.shape[:2]

# 패치 크기와 경계 보정
patch_size = 21
half = patch_size // 2

# y, x 경계 체크
fy = max(half, min(feature_y, hL - half - 1))
fx = max(half, min(feature_x, wL - half - 1))

# 패치 추출 (경계 보정)
patch = imgL[fy-half:fy+half+1, fx-half:fx+half+1]

# 오른쪽 이미지에서 같은 y라인만 슬라이딩 매칭 (경계 보정)
if fy-half < 0 or fy+half+1 > hR:
    raise ValueError(f"feature_y={feature_y}에서 라인 추출이 이미지 경계를 벗어납니다.")
line = imgR[fy-half:fy+half+1, :, :]

# 템플릿 매칭 (cv2.TM_SQDIFF_NORMED: 값이 작을수록 유사)
if patch.shape[0] > line.shape[0] or patch.shape[1] > line.shape[1]:
    raise ValueError(f"패치 크기 {patch.shape}가 라인 크기 {line.shape}보다 큽니다. patch_size, feature_x/y를 조정하세요.")
res = cv2.matchTemplate(line, patch, cv2.TM_SQDIFF_NORMED)
min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
matched_x = min_loc[0] + half  # 패치 중심 보정



# 결과 시각화 및 저장
import os


# 저장 경로를 작업 폴더로 고정
save_dir = r'C:\Users\htw02\OneDrive\문서\Tank Challenge\tw\camera_data\saved_cameradata\L_camera'
left_save_path = os.path.join(save_dir, 'check_point3_left.png')
right_save_path = os.path.join(save_dir, 'check_point3_right.png')


# 왼쪽 이미지에 초록색 점과 좌표 표시
imgL_dot = imgL.copy()
cv2.circle(imgL_dot, (fx, fy), radius=8, color=(0,255,0), thickness=-1)
cv2.putText(imgL_dot, f'({fx},{fy})', (fx+15, fy-15), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,0), 2)
cv2.putText(imgL_dot, 'Left Feature Point', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)

# 오른쪽 이미지에 파란색 점과 좌표 표시
imgR_dot = imgR.copy()
cv2.circle(imgR_dot, (matched_x, fy), radius=8, color=(255,0,0), thickness=-1)
cv2.putText(imgR_dot, f'({matched_x},{fy})', (matched_x+15, fy-15), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255,0,0), 2)
cv2.putText(imgR_dot, 'Right Matched Point', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,0,0), 2)

# 화면에 이미지 띄우기
cv2.imshow('Left Image with Green Dot', imgL_dot)
cv2.imshow('Right Image with Blue Dot', imgR_dot)
print("이미지가 화면에 표시되었습니다. 아무 키나 누르면 저장 후 종료됩니다.")
cv2.waitKey(0)
cv2.destroyAllWindows()

# PIL로 저장 (한글 경로 지원)
pil_imgL = Image.fromarray(cv2.cvtColor(imgL_dot, cv2.COLOR_BGR2RGB))
try:
    pil_imgL.save(left_save_path)
    success_L = True
except Exception as e:
    success_L = False
    print(f'[오류] 왼쪽 이미지 저장 실패: {e}')
print(f'왼쪽 이미지 특징점: ({fx}, {fy}) → 저장: {left_save_path} (성공: {success_L})')

pil_imgR = Image.fromarray(cv2.cvtColor(imgR_dot, cv2.COLOR_BGR2RGB))
try:
    pil_imgR.save(right_save_path)
    success_R = True
except Exception as e:
    success_R = False
    print(f'[오류] 오른쪽 이미지 저장 실패: {e}')
print(f'오른쪽 이미지에서 매칭된 x좌표: {matched_x}, y좌표: {fy} → 저장: {right_save_path} (성공: {success_R})')

print(f'\n🎯 결과 요약:')
print(f'왼쪽 특징점: ({fx}, {fy})')
print(f'오른쪽 매칭점: ({matched_x}, {fy})')
print(f'Disparity: {fx - matched_x} px')
