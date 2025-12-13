import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# =========================
# 사용자 설정 파라미터
# =========================
CSV_PATH = "pid/log_data/drive_log.csv"
SETTLING_BAND_DEG = 5.0     # ±band deg 안에 들어오면 안정으로 판단
LOOKAHEAD = 5               # 타깃 yaw가 없을 때 진행방향 근사용
MIN_VALID_LEN = 10          # 최소 길이

# =========================
# 유틸 함수
# =========================
def wrap_deg(a):
    """각도를 -180 ~ +180 범위로 래핑"""
    return (a + 180.0) % 360.0 - 180.0

def compute_step_metrics(t, ref, cur, band_deg=5.0):
    """
    step-like 응답 지표:
    - rise time (10%->90%)
    - overshoot (% of step amplitude)
    - settling time (±band_deg)
    - steady-state error (deg)
    """
    t = np.asarray(t, dtype=float)
    ref = wrap_deg(np.asarray(ref, dtype=float))
    cur = wrap_deg(np.asarray(cur, dtype=float))

    out = dict(rise_time=np.nan, overshoot_pct=np.nan, settling_time=np.nan, ss_error=np.nan)
    n = len(t)
    if n < 5:
        return out

    # step 크기(참조 변화) 정의: ref[0] -> ref[-1]
    ref0, ref1 = ref[0], ref[-1]
    amp = wrap_deg(ref1 - ref0)  # -180~180
    if abs(amp) < 1e-6:
        # step이 거의 없으면 SS error만 계산
        tail = max(5, n // 10)
        out["ss_error"] = np.nanmedian(wrap_deg(cur - ref1)[-tail:])
        return out

    # 정규화 응답: cur를 ref0 기준으로 0→1로 기대
    y_norm = wrap_deg(cur - ref0) / amp
    if amp > 0:
        idx10 = np.where(y_norm >= 0.1)[0]
        idx90 = np.where(y_norm >= 0.9)[0]
    else:
        idx10 = np.where(y_norm <= -0.1)[0]
        idx90 = np.where(y_norm <= -0.9)[0]
    if len(idx10) > 0 and len(idx90) > 0:
        out["rise_time"] = t[idx90[0]] - t[idx10[0]]

    # 오버슈트: 최종 ref1 기준 초과량 / |amp|
    over = wrap_deg(cur - ref1)
    peak = np.max(over) if amp > 0 else np.min(over)
    out["overshoot_pct"] = (peak / max(1e-6, abs(amp))) * 100.0

    # Settling time: |cur - ref1| <= band가 이후 계속 유지되는 최초 시각
    within = np.abs(wrap_deg(cur - ref1)) <= band_deg
    st = np.nan
    for i in range(n):
        if np.all(within[i:]):
            st = t[i] - t[0]
            break
    out["settling_time"] = st

    # Steady-state error: 끝부분 중앙값
    tail = max(5, n // 10)
    out["ss_error"] = np.nanmedian(wrap_deg(cur - ref1)[-tail:])
    return out

# =========================
# 데이터 로드 & 준비
# =========================
df = pd.read_csv(CSV_PATH)

if "Time" not in df.columns:
    raise ValueError("CSV에 'Time' 컬럼이 필요합니다.")

time = df["Time"].to_numpy(dtype=float)

# --- 현재 yaw (우선순위: Player_Body_X → 위치 변화로 추정) ---
if "Player_Body_X" in df.columns:
    yaw_cur = df["Player_Body_X"].to_numpy(dtype=float)
else:
    need = {"Player_Pos_X", "Player_Pos_Z"}
    if not need.issubset(df.columns):
        raise ValueError("Player_Body_X가 없으면 Player_Pos_X, Player_Pos_Z가 필요합니다.")
    dx = df["Player_Pos_X"].to_numpy(dtype=float)
    dz = df["Player_Pos_Z"].to_numpy(dtype=float)
    vx = np.diff(dx, prepend=dx[0])
    vz = np.diff(dz, prepend=dz[0])
    yaw_cur = np.degrees(np.arctan2(vz, vx))
yaw_cur = wrap_deg(yaw_cur)

# --- 목표 yaw (우선순위: target_angle/Target_Yaw/Desired_Yaw → Player_Turret_X → 진행방향 근사) ---
if "target_angle" in df.columns:
    yaw_ref = df["target_angle"].to_numpy(dtype=float)
elif "Target_Yaw" in df.columns:
    yaw_ref = df["Target_Yaw"].to_numpy(dtype=float)
elif "Desired_Yaw" in df.columns:
    yaw_ref = df["Desired_Yaw"].to_numpy(dtype=float)
elif "Player_Turret_X" in df.columns:
    yaw_ref = df["Player_Turret_X"].to_numpy(dtype=float)
else:
    need = {"Player_Pos_X", "Player_Pos_Z"}
    if not need.issubset(df.columns):
        raise ValueError("목표 yaw가 없으면 Player_Pos_X, Player_Pos_Z로 진행방향을 근사합니다. 해당 컬럼이 필요합니다.")
    x = df["Player_Pos_X"].to_numpy(dtype=float)
    z = df["Player_Pos_Z"].to_numpy(dtype=float)
    x2 = np.roll(x, -LOOKAHEAD); x2[-LOOKAHEAD:] = x[-LOOKAHEAD:]
    z2 = np.roll(z, -LOOKAHEAD); z2[-LOOKAHEAD:] = z[-LOOKAHEAD:]
    yaw_ref = np.degrees(np.arctan2(z2 - z, x2 - x))
yaw_ref = wrap_deg(yaw_ref)

# --- 유효성/정렬/결측치 제거 ---
valid = np.isfinite(time) & np.isfinite(yaw_ref) & np.isfinite(yaw_cur)
time, yaw_ref, yaw_cur = time[valid], yaw_ref[valid], yaw_cur[valid]
order = np.argsort(time)
time, yaw_ref, yaw_cur = time[order], yaw_ref[order], yaw_cur[order]

if len(time) < MIN_VALID_LEN:
    raise ValueError("유효 샘플이 너무 적습니다.")

# =========================
# 메트릭 계산
# =========================
metrics = compute_step_metrics(time, yaw_ref, yaw_cur, band_deg=SETTLING_BAND_DEG)

# =========================
# 시각화
# =========================
plt.figure(figsize=(14, 8))

# 타깃/실제
plt.plot(time, yaw_ref, label="Target Yaw (Ref)", linewidth=2)
plt.plot(time, yaw_cur, label="Current Yaw (Body)", linewidth=2)

# 정착 밴드(타깃 기준 ±band)
upper = wrap_deg(yaw_ref) + SETTLING_BAND_DEG
lower = wrap_deg(yaw_ref) - SETTLING_BAND_DEG
plt.fill_between(time, lower, upper, color='gray', alpha=0.15,
                 label=f"±{SETTLING_BAND_DEG}° Settling Band")

# 오버슈트 표시
ref_end = yaw_ref[-1]
cur_over = wrap_deg(yaw_cur - ref_end)
amp = wrap_deg(yaw_ref[-1] - yaw_ref[0])
if abs(amp) >= 1e-6:
    peak_idx = np.argmax(cur_over) if amp > 0 else np.argmin(cur_over)
    plt.scatter(time[peak_idx], yaw_cur[peak_idx], color='red', s=80, marker='o',
                label=f"Overshoot ({metrics['overshoot_pct']:.1f}%)")

# 세틀링 타임 표시
if not np.isnan(metrics["settling_time"]):
    st_abs = time[0] + metrics["settling_time"]
    plt.axvline(st_abs, color='orange', linestyle='--', linewidth=2,
                label=f"Settling Time = {metrics['settling_time']:.2f}s")

# Steady-state error 주석
plt.text(0.02, 0.95,
         f"Steady-State Error: {metrics['ss_error']:.2f}°",
         transform=plt.gca().transAxes,
         fontsize=12, bbox=dict(facecolor='white', alpha=0.7))

plt.title("Step Response (Yaw Tracking)", fontsize=16)
plt.xlabel("Time (s)", fontsize=14)
plt.ylabel("Yaw (deg)", fontsize=14)
plt.grid(True, alpha=0.3)
plt.legend(fontsize=11)
plt.tight_layout()
plt.show()

# =========================
# Extract step-like window & draw CONTROL-ENGINEERING STYLE FIGURE
# =========================

STEP_THRESH_DEG = 10.0       # ref 변화량 threshold
WINDOW_AFTER_STEP = 200      # step 이후 몇개를 보여줄지

# --- Step event detection ---
ref_diff = np.abs(np.diff(yaw_ref, prepend=yaw_ref[0]))
step_indices = np.where(ref_diff > STEP_THRESH_DEG)[0]

if len(step_indices) == 0:
    print("⚠ step-like 구간을 찾지 못했습니다. threshold를 낮춰보세요.")
else:
    step_idx = step_indices[0]    # 첫 스텝 구간만 사용
    print(f"✅ Step-like event detected at index = {step_idx}")

    # --- segment slice ---
    end_idx = min(len(time), step_idx + WINDOW_AFTER_STEP)
    t_seg = time[step_idx:end_idx] - time[step_idx]
    ref_seg = wrap_deg(yaw_ref[step_idx:end_idx])
    cur_seg = wrap_deg(yaw_cur[step_idx:end_idx])

    # --- Step amplitude ---
    ref0 = ref_seg[0]
    ref1 = ref_seg[-1]
    amp = wrap_deg(ref1 - ref0)

    if abs(amp) < 1e-6:
        print("⚠ step amplitude가 너무 작아 실제적인 step response 분석 불가.")
    else:
        # =========================
        # Normalization (control style)
        # =========================
        y_norm = wrap_deg(cur_seg - ref0) / amp           # 0 → 1 expected
        ref_norm = np.ones_like(y_norm)                   # reference fixed at 1

        # metric 계산
        step_metrics = compute_step_metrics(t_seg, ref_seg, cur_seg, band_deg=SETTLING_BAND_DEG)

        # =========================
        # Plot 제어공학 스타일
        # =========================
        plt.figure(figsize=(12,6))
        plt.plot(t_seg, ref_norm, 'k--', linewidth=2, label="Reference (Normalized)")
        plt.plot(t_seg, y_norm, 'b-', linewidth=2, label="Response (Normalized)")

        plt.title("Normalized Step Response (Control Engineering Style)", fontsize=16)
        plt.xlabel("Time (s)")
        plt.ylabel("Normalized Amplitude")
        plt.grid(True)

        # ---- overshoot ----
        if not np.isnan(step_metrics["overshoot_pct"]):
            if amp > 0:
                peak_idx = np.argmax(y_norm)
            else:
                peak_idx = np.argmin(y_norm)

            plt.scatter(t_seg[peak_idx], y_norm[peak_idx],
                        color='red', s=80, label=f"Overshoot: {step_metrics['overshoot_pct']:.1f}%")

        # ---- settling time ----
        st = step_metrics["settling_time"]
        if not np.isnan(st):
            plt.axvline(st, color='orange', linestyle='--', linewidth=2,
                        label=f"Settling Time: {st:.2f}s")

        # ---- steady-state error ----
        plt.text(
            0.02, 0.9,
            f"SS Error = {step_metrics['ss_error']:.2f}°",
            transform=plt.gca().transAxes,
            fontsize=12,
            bbox=dict(facecolor='white', alpha=0.7)
        )

        plt.legend()
        plt.tight_layout()
        plt.show()
