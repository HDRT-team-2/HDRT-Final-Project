# -*- coding: utf-8 -*-
import cv2
import numpy as np

def imread_unicode(path):
    stream = np.fromfile(path, np.uint8)
    img = cv2.imdecode(stream, cv2.IMREAD_COLOR)
    return img

# 파일 경로
base_img_path = r"C:\Users\htw02\OneDrive\문서\Tank Challenge\capture_images\capture_0009.png"
img_r_path = r"C:\Users\htw02\OneDrive\문서\Tank Challenge\capture_images\R\055_82.png"
img_l_path = r"C:\Users\htw02\OneDrive\문서\Tank Challenge\capture_images\L\055_82.png"

# 이미지 읽기
base_img = imread_unicode(base_img_path)
img_r = imread_unicode(img_r_path)
img_l = imread_unicode(img_l_path)

def find_and_draw(img_query, base_img, color=(0,255,0)):
	sift = cv2.SIFT_create()
	kp1, des1 = sift.detectAndCompute(img_query, None)
	kp2, des2 = sift.detectAndCompute(base_img, None)
	bf = cv2.BFMatcher()
	matches = bf.knnMatch(des1, des2, k=2)
	# ratio test
	good = []
	for m, n in matches:
		if m.distance < 0.75 * n.distance:
			good.append(m)
	if len(good) > 4:
		src_pts = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
		dst_pts = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
		M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
		h, w = img_query.shape[:2]
		pts = np.float32([[0,0],[w,0],[w,h],[0,h]]).reshape(-1,1,2)
		dst = cv2.perspectiveTransform(pts, M)
		base_img = cv2.polylines(base_img, [np.int32(dst)], True, color, 3, cv2.LINE_AA)
	return base_img

# R 이미지 영역 표시 (초록)
base_img = find_and_draw(img_r, base_img, color=(0,255,0))
# L 이미지 영역 표시 (빨강)
base_img = find_and_draw(img_l, base_img, color=(0,0,255))

# 결과 저장 경로
save_path = r"C:\Users\htw02\HDRT_AI\01_final_pj\01_depth_measure\camera_data\result_blindspot.png"
cv2.imwrite(save_path, base_img)

# 결과 출력
cv2.imshow('Result', base_img)
cv2.waitKey(0)
cv2.destroyAllWindows()
