# -*- coding: utf-8 -*-
import cv2
import numpy as np

def imread_unicode(path):
	stream = np.fromfile(path, np.uint8)
	img = cv2.imdecode(stream, cv2.IMREAD_COLOR)
	return img

base_img_path = r"C:\Users\htw02\OneDrive\문서\Tank Challenge\capture_images\capture_0009.png"
img_r_path = r"C:\Users\htw02\OneDrive\문서\Tank Challenge\capture_images\R\055_82.png"
img_l_path = r"C:\Users\htw02\OneDrive\문서\Tank Challenge\capture_images\L\055_82.png"

base_img = imread_unicode(base_img_path)
img_r = imread_unicode(img_r_path)
img_l = imread_unicode(img_l_path)

print(f"base_img size: {base_img.shape if base_img is not None else '읽기 실패'}")
print(f"img_r size: {img_r.shape if img_r is not None else '읽기 실패'}")
print(f"img_l size: {img_l.shape if img_l is not None else '읽기 실패'}")
