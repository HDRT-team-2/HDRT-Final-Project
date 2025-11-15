import numpy as np
from PIL import Image

img = Image.open("map_images/01_forest_and_river.PNG")
img_rgb = np.array(img)

print("이미지 크기:", img_rgb.shape)
print("\n=== 색상 분석 ===")

# 파란색 계열 (물) 찾기 - B값이 높고 R값이 낮은 픽셀
water_mask = (img_rgb[:,:,2] > 100) & (img_rgb[:,:,0] < 100)
water_pixels = img_rgb[water_mask]

if len(water_pixels) > 0:
    print(f"\n물 영역 픽셀 수: {len(water_pixels)}")
    print("물 영역 색상 샘플 (처음 10개):")
    print(water_pixels[:10])
    print(f"\n물 색상 범위:")
    print(f"  R: {water_pixels[:, 0].min()} ~ {water_pixels[:, 0].max()}")
    print(f"  G: {water_pixels[:, 1].min()} ~ {water_pixels[:, 1].max()}")
    print(f"  B: {water_pixels[:, 2].min()} ~ {water_pixels[:, 2].max()}")
else:
    print("물 영역을 찾을 수 없습니다.")

# 전체 이미지의 고유 색상 확인 (RGBA를 RGB로 변환)
img_rgb_only = img_rgb[:,:,:3]  # 알파 채널 제거
unique_colors = np.unique(img_rgb_only.reshape(-1, 3), axis=0)
print(f"\n이미지 내 고유 색상 개수: {len(unique_colors)}")
print("\n모든 고유 색상 (RGB):")
for i, color in enumerate(unique_colors[:20]):
    print(f"{i+1}. R:{color[0]:3d}, G:{color[1]:3d}, B:{color[2]:3d} (HEX: #{color[0]:02x}{color[1]:02x}{color[2]:02x})")
if len(unique_colors) > 20:
    print(f"... 외 {len(unique_colors) - 20}개")
