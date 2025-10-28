import numpy as np
from scipy.stats import qmc
from fractions import Fraction
import matplotlib.pyplot as plt

# 샘플링 설정
n_samples = 20   # 실험 점 20개
d_vars = 2       # w, d 두 변수

# Latin Hypercube 샘플러 생성
sampler = qmc.LatinHypercube(d=d_vars)
X_lhs = sampler.random(n=n_samples)  # 0~1 범위 샘플링

# 변수 범위 변환: 1 ~ 65
min_val, max_val = 1, 65
w_weight = min_val + X_lhs[:, 0] * (max_val - min_val)
d_weight = min_val + X_lhs[:, 1] * (max_val - min_val)

# 분수 형태로 변환 (분모 65로 통일)
w_frac = [Fraction(int(round(w)), 65) for w in w_weight]
d_frac = [Fraction(int(round(d)), 65) for d in d_weight]

# 시각화 (2D)
plt.figure(figsize=(6,6))
plt.scatter(w_weight, d_weight, c='crimson', s=50)
plt.xlabel('w_weight')
plt.ylabel('d_weight')
plt.title('2D Projection of OLHS Design')
plt.grid(True)
plt.savefig('surrogate_w_d/sampling/sampling_lhs.png')
plt.show()

# 샘플링 결과 출력 (분수로 보기 좋게)
print("OLHS 20점 샘플링 결과 (w_weight, d_weight) - 분모 65 기준:")
for i, (w, d) in enumerate(zip(w_frac, d_frac), start=1):
    print(f"{i:2d}: w = {w}, d = {d}")

# OLHS 20점 샘플링 결과 (w_weight, d_weight) - 분모 65 기준:
#  1: w = 46/65, d = 43/65
#  2: w = 63/65, d = 59/65
#  3: w = 42/65, d = 34/65
#  4: w = 51/65, d = 49/65
#  5: w = 59/65, d = 62/65
#  6: w = 3/5, d = 14/65
#  7: w = 23/65, d = 29/65
#  8: w = 43/65, d = 6/65
#  9: w = 1/65, d = 9/65
# 10: w = 4/65, d = 2/65
# 11: w = 27/65, d = 5/13
# 12: w = 23/65, d = 48/65
# 13: w = 7/13, d = 31/65
# 14: w = 31/65, d = 17/65
# 15: w = 58/65, d = 58/65
# 16: w = 19/65, d = 38/65
# 17: w = 1/5, d = 53/65
# 18: w = 16/65, d = 11/65
# 19: w = 2/13, d = 42/65
# 20: w = 54/65, d = 21/65
