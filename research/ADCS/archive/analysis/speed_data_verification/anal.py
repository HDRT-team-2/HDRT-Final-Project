import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import sys

# ==========================================================
# 1. 파일 설정
# ==========================================================
LOG_FILE_PATH = 'research/ADCS/archive/analysis/speed_data_verification/log.txt' 

# ==========================================================
# 2. 데이터 로드
# ==========================================================
try:
    df = pd.read_csv(LOG_FILE_PATH)
    print(f"✅ 로그 파일 로드 완료: {len(df)} 라인")
except FileNotFoundError:
    print(f"❌ 파일을 찾을 수 없습니다: {LOG_FILE_PATH}")
    sys.exit()

req_cols = ['Time', 'Player_Pos_X', 'Player_Pos_Y', 'Player_Pos_Z', 'Player_Speed']
for col in req_cols:
    if col not in df.columns:
        print(f"❌ 에러: CSV 안에 '{col}' 컬럼이 없습니다.")
        sys.exit()

df = df.sort_values(by='Time').reset_index(drop=True)

# ==========================================================
# 3. Ground Truth 속도 계산
# ==========================================================
# 전체 데이터에 대해 먼저 계산 (미분 연속성을 위해 자르기 전에 계산)
df['dt'] = df['Time'].diff()
df['dx'] = df['Player_Pos_X'].diff()
df['dy'] = df['Player_Pos_Y'].diff()
df['dz'] = df['Player_Pos_Z'].diff()
df['dist_3d'] = np.sqrt(df['dx']**2 + df['dy']**2 + df['dz']**2)

def get_real_speed(row):
    if pd.isna(row['dt']) or row['dt'] <= 0.0001:
        return np.nan
    return row['dist_3d'] / row['dt']

df['Calc_Speed'] = df.apply(get_real_speed, axis=1)

# ==========================================================
# [중요] 4. 데이터 필터링 (10초 이후만 남기기)
# ==========================================================
# NaN 제거
valid_df = df.dropna(subset=['Calc_Speed', 'Player_Speed'])

# 시작 시간 찾기
start_time = valid_df['Time'].min()
cutoff_time = start_time + 10.0  # 10초 뒤

print(f"⏱️ 데이터 필터링 기준: {start_time:.2f}초(시작) + 10초 = {cutoff_time:.2f}초 이후 데이터만 분석합니다.")

# 10초 이후 데이터만 잘라냄 (target_df)
target_df = valid_df[valid_df['Time'] >= cutoff_time].copy()

# 데이터가 너무 짧아서 10초 이후가 없는 경우 예외처리
if len(target_df) == 0:
    print("❌ [오류] 로그 데이터의 길이가 10초 미만입니다. 분석할 데이터가 없습니다.")
    sys.exit()

# ==========================================================
# 5. 통계 분석 (10초 이후 데이터 대상)
# ==========================================================
target_df['Diff'] = target_df['Calc_Speed'] - target_df['Player_Speed']
mae = target_df['Diff'].abs().mean()
corr = target_df['Calc_Speed'].corr(target_df['Player_Speed'])

print("\n" + "="*60)
print("📊 [속도 데이터 정밀 검증 (10초 이후 구간)]")
print("="*60)
print(f"1. 분석 구간        : {cutoff_time:.2f}초 ~ {target_df['Time'].max():.2f}초")
print(f"2. 분석 프레임 수   : {len(target_df)} frames")
print(f"3. 상관계수 (R)     : {corr:.4f}")
print(f"4. 평균 오차 (MAE)  : {mae:.4f} m/s")
print("-" * 60)

# 샘플 데이터 출력
print("\n[🔍 구간별 데이터 샘플 (상위 5개)]")
print(target_df[['Time', 'Player_Speed', 'Calc_Speed', 'Diff']].head(5).to_string(index=False))

print("\n" + "-" * 60)
print("📢 [최종 결론]")

if corr > 0.9 and mae < 0.5:
    print("✅ 신뢰 가능: 10초 이후 안정화된 상태에서도 두 데이터가 일치합니다.")
elif corr > 0.8:
    print("⚠️ 오차 발생: 경향성은 비슷하나 값의 차이가 있습니다.")
else:
    print("❌ 신뢰 불가: 데이터가 완전히 다릅니다.")

# ==========================================================
# 6. 시각화 (10초 이후만 그림)
# ==========================================================
plt.figure(figsize=(12, 6))

plt.plot(target_df['Time'], target_df['Calc_Speed'], label='Ground Truth (Calculated)', color='red', linewidth=2, alpha=0.7)
plt.plot(target_df['Time'], target_df['Player_Speed'], label='Log Data (Player_Speed)', color='blue', linestyle='--', linewidth=2)

plt.title(f'Speed Verification (After 10s) | Corr: {corr:.2f}')
plt.xlabel('Time (s)')
plt.ylabel('Speed (m/s)')
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.savefig('research/ADCS/archive/analysis/speed_data_verification/cons.png')

plt.show()
plt.close()