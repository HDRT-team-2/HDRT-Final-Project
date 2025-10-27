# astar_barh_8dir_maze_batch_2x2.py
import math
import random
import time
import csv
from collections import defaultdict

import numpy as np
import matplotlib.pyplot as plt

# ---------------------------
# 8-방향 A* (대각선 비용 = sqrt(2), 코너 끼기 방지)
# ---------------------------
def neighbors_8dir(r, c):
    return [
        (r-1, c), (r+1, c), (r, c-1), (r, c+1),           # 상하좌우
        (r-1, c-1), (r-1, c+1), (r+1, c-1), (r+1, c+1)    # 대각선
    ]

def diagonal_heuristic(a, b):
    # Octile distance (8-방향에서 admissible)
    dx = abs(a[0] - b[0])
    dy = abs(a[1] - b[1])
    return (dx + dy) + (math.sqrt(2) - 2) * min(dx, dy)

def reconstruct_path(came_from, current):
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    return path[::-1]

def a_star_8dir_no_corner_cut(grid, start, goal):
    """
    grid: 0=통과가능, 1=장애물
    start/goal: (row, col)
    규칙: 대각선 이동 시 양 옆 직교 칸이 모두 비어 있어야 함(코너 끼기 금지).
    """
    n_rows, n_cols = grid.shape

    def in_bounds(r, c): return 0 <= r < n_rows and 0 <= c < n_cols
    def walkable(r, c):  return in_bounds(r, c) and grid[r, c] == 0

    if not walkable(*start) or not walkable(*goal):
        return None

    import heapq
    g_score = {start: 0.0}
    f_start = diagonal_heuristic(start, goal)
    open_heap = [(f_start, 0.0, start)]
    came_from = {}
    closed = set()

    while open_heap:
        f, g, cur = heapq.heappop(open_heap)
        if cur in closed:
            continue
        closed.add(cur)

        if cur == goal:
            return reconstruct_path(came_from, cur)

        cr, cc = cur
        for nr, nc in neighbors_8dir(cr, cc):
            if not in_bounds(nr, nc) or grid[nr, nc] == 1:
                continue

            dr = nr - cr
            dc = nc - cc
            # ---- 코너 끼기 방지 ----
            if abs(dr) == 1 and abs(dc) == 1:  # 대각선
                if grid[cr + dr, cc] == 1 or grid[cr, cc + dc] == 1:
                    continue
                step_cost = math.sqrt(2)
            else:
                step_cost = 1.0
            # ------------------------

            nxt = (nr, nc)
            tentative_g = g + step_cost
            if nxt in closed and tentative_g >= g_score.get(nxt, float("inf")):
                continue
            if tentative_g < g_score.get(nxt, float("inf")):
                came_from[nxt] = cur
                g_score[nxt] = tentative_g
                f_new = tentative_g + diagonal_heuristic(nxt, goal)
                heapq.heappush(open_heap, (f_new, tentative_g, nxt))

    return None

# ---------------------------
# 미로 느낌 장애물 생성
#  - coarse(작은) 격자에서 랜덤 Prim으로 미로 생성 후
#  - block_size로 키워서 실제 n×n에 매핑
#  - obstacle_ratio로 벽 밀도 조정
# ---------------------------
def generate_coarse_maze(H, W, rng):
    """
    H×W (둘 다 홀수 권장)에서 1=벽, 0=길 형태 미로 생성(랜덤 Prim 변형)
    """
    H = max(3, H | 1)  # 홀수 보정
    W = max(3, W | 1)
    maze = np.ones((H, W), dtype=np.uint8)
    sr, sc = 1, 1
    maze[sr, sc] = 0

    walls = []
    def add_walls(r, c):
        for dr, dc in [(-2,0),(2,0),(0,-2),(0,2)]:
            nr, nc = r+dr, c+dc
            if 0 <= nr < H and 0 <= nc < W and maze[nr, nc] == 1:
                walls.append((nr, nc, r, c))
    add_walls(sr, sc)

    while walls:
        idx = rng.randrange(len(walls))
        wr, wc, pr, pc = walls.pop(idx)
        mr, mc = (wr+pr)//2, (wc+pc)//2
        if maze[wr, wc] == 1:
            maze[wr, wc] = 0
            maze[mr, mc] = 0
            add_walls(wr, wc)

    return maze  # 0=길, 1=벽

def make_maze_obstacles_grid(n, obstacle_ratio=0.2, seed=123, block_size=6, clear_margin=1):
    """
    n×n 최종 grid 생성(0=빈칸, 1=장애물)
    - obstacle_ratio: 최종 벽 비율(대략)
    - block_size: coarse -> fine 스케일 업 배수 (클수록 벽이 두꺼워짐)
    - clear_margin: 테두리 여백(시작/종료 통로 확보용)
    """
    rng = random.Random(seed)

    # 1) coarse 미로 생성
    Hc = max(3, (n // block_size) | 1)
    Wc = max(3, (n // block_size) | 1)
    coarse = generate_coarse_maze(Hc, Wc, rng)  # 0=길, 1=벽

    # 2) 스케일 업
    fine = np.kron(coarse, np.ones((block_size, block_size), dtype=np.uint8))

    # 3) n×n으로 중앙 자르기/패딩
    Hf, Wf = fine.shape
    if Hf < n or Wf < n:
        pad_r = max(0, n - Hf)
        pad_c = max(0, n - Wf)
        fine = np.pad(fine, ((pad_r//2, pad_r - pad_r//2),
                             (pad_c//2, pad_c - pad_c//2)),
                      mode="edge")
    Hf, Wf = fine.shape
    sr = (Hf - n)//2
    sc = (Wf - n)//2
    grid = fine[sr:sr+n, sc:sc+n].copy()  # 0=길, 1=벽

    # 4) 가장자리 여백 정리 + 시작/도착 보장
    grid[:clear_margin, :] = 0
    grid[:, :clear_margin] = 0
    grid[-clear_margin:, :] = 0
    grid[:, -clear_margin:] = 0
    grid[0, 0] = 0
    grid[n-1, n-1] = 0

    # 5) 벽 비율 보정(너무 많으면 희석, 너무 적으면 추가)
    cur_ratio = grid.mean()
    target = obstacle_ratio
    rng_np = np.random.default_rng(seed + 999)

    if cur_ratio > target:
        # 벽 줄이기: 랜덤으로 일부 벽을 길(0)로
        wall_pos = np.argwhere(grid == 1)
        need = int((cur_ratio - target) * n * n)
        if need > 0 and len(wall_pos) > 0:
            idx = rng_np.choice(len(wall_pos), size=min(need, len(wall_pos)), replace=False)
            for r, c in wall_pos[idx]:
                grid[r, c] = 0
    elif cur_ratio < target:
        # 벽 늘리기: 랜덤으로 일부 길을 벽(1)으로
        free_pos = np.argwhere(grid == 0)
        need = int((target - cur_ratio) * n * n)
        if need > 0 and len(free_pos) > 0:
            idx = rng_np.choice(len(free_pos), size=min(need, len(free_pos)), replace=False)
            for r, c in free_pos[idx]:
                grid[r, c] = 1

        # 시작/종료는 다시 비우기
        grid[0, 0] = 0
        grid[n-1, n-1] = 0

    return grid

# ---------------------------
# 벤치마크 & 시각화(항상 2×2 묶음, 저장완료 print, 즉시 표시)
# ---------------------------
if __name__ == "__main__":
    # 실험 파라미터
    n_values = [300, 200, 150, 100, 60, 50, 30, 20, 15, 10, 5, 4, 3, 2, 1]
    obstacle_ratio = 0.20       # 미로형태 벽 비율(원하는 느낌 맞았다던 0.2)
    base_seed = 12345
    trials_per_n = 10
    block_size = 4              # 미로 스케일(크면 벽 두꺼움)
    clear_margin = 1

    # 결과 누적
    avg_time_ms = []
    avg_path_len_success = []
    success_counts = []
    sample_records = {}  # n -> (grid, path, found, time_ms) 시각화용 샘플

    # CSV 저장용
    csv_rows = [("n", "trials", "success", "avg_time_ms", "avg_path_len_success")]

    for n in n_values:
        start = (n-1, n-1)
        goal = (0, 0)

        times = []
        path_lens = []
        success = 0
        # 시각화는 첫 trial을 샘플로 저장
        sample_saved = False

        for t in range(trials_per_n):
            seed = base_seed + n*1000 + t
            grid = make_maze_obstacles_grid(
                n,
                obstacle_ratio=obstacle_ratio,
                seed=seed,
                block_size=block_size,
                clear_margin=clear_margin
            )

            t0 = time.perf_counter()
            path = a_star_8dir_no_corner_cut(grid, start, goal)
            t1 = time.perf_counter()
            dt_ms = (t1 - t0) * 1000.0
            times.append(dt_ms)

            if path is not None:
                success += 1
                path_lens.append(len(path))
            # 시각화 샘플 저장(첫 번째 trial)
            if not sample_saved:
                sample_records[n] = (grid, path, path is not None, dt_ms)
                sample_saved = True

        mean_time = float(np.mean(times)) if times else 0.0
        mean_path_len = float(np.mean(path_lens)) if path_lens else 0.0

        avg_time_ms.append(mean_time)
        avg_path_len_success.append(mean_path_len)
        success_counts.append(success)

        # 콘솔 출력(정렬 맞춤)
        print(f"n={n:>3} | trials={trials_per_n} | success={success:<2} | "
              f"avg_time={mean_time:.2f} ms | avg_path_len_success={mean_path_len:.1f}")

        # CSV 행 추가
        csv_rows.append((n, trials_per_n, success, round(mean_time, 4), round(mean_path_len, 2)))

    # CSV 저장 + 저장로그
    csv_path = "benchmark_results.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(csv_rows)
    print(f"[saved] {csv_path}")

    # ---------------------------
    # 시각화: n 상관없이 항상 2×2로 묶어서 저장하고 즉시 표시(B 방식)
    # ---------------------------
    def draw_one(ax, n, record):
        grid, path, found, time_ms = record
        ax.imshow(grid, cmap="gray_r", origin="upper", interpolation="nearest")
        start = (n-1, n-1)
        goal = (0, 0)
        ax.scatter([start[1]], [start[0]], s=35, c="blue", marker="s")
        ax.scatter([goal[1]], [goal[0]], s=35, c="red", marker="s")
        if found and path is not None:
            ys = [r for r, c in path]
            xs = [c for r, c in path]
            ax.plot(xs, ys, linewidth=1.4, c="green")
            title_len = len(path)
        else:
            title_len = "False"
        ax.set_title(f"n={n} | len={title_len}\nsample={time_ms:.2f} ms", fontsize=10)
        ax.set_xticks([])
        ax.set_yticks([])

    # 4개씩(2×2) 묶기
    batch_size = 4
    batches = [n_values[i:i+batch_size] for i in range(0, len(n_values), batch_size)]
    for bidx, batch in enumerate(batches, 1):
        fig, axes = plt.subplots(2, 2, figsize=(8, 8))
        axes = axes.ravel()
        for i in range(4):
            ax = axes[i]
            if i < len(batch):
                n = batch[i]
                rec = sample_records[n]
                draw_one(ax, n, rec)
            else:
                ax.axis("off")
        plt.tight_layout()
        out_path = f"grids_batch_{bidx:02d}.jpg"
        plt.savefig(out_path, dpi=180)   # JPG, quality 인자 없이 저장
        print(f"[saved] {out_path}")     # ✅ 저장 완료 로그
        plt.show()                       # ✅ 즉시 화면 표시
        plt.close(fig)                   # ✅ 다음 묶음을 위해 닫기

    # ---------------------------
    # 처리시간 가로 막대그래프 (x=시간, y=n) - 평균시간 사용
    # ---------------------------
    fig = plt.figure(figsize=(8, max(6, len(n_values)*0.35)))
    y_pos = np.arange(len(n_values))
    plt.barh(y_pos, avg_time_ms)
    plt.yticks(y_pos, [str(n) for n in n_values])
    plt.xlabel("Average A* time (ms)")
    plt.ylabel("Grid size n")
    plt.title("A* 8-dir (no corner cutting) - Avg Runtime by Grid Size")
    # 값 표시
    mmax = max(avg_time_ms) if avg_time_ms else 0.0
    for i, v in enumerate(avg_time_ms):
        plt.text(v + (mmax * 0.01 if mmax > 0 else 0.02), i, f"{v:.2f} ms",
                 va="center", fontsize=8)
    plt.tight_layout()
    bar_path = "runtime_barh.jpg"
    plt.savefig(bar_path, dpi=180)
    print(f"[saved] {bar_path}")  # ✅ 저장 완료 로그
    plt.show()                    # ✅ 화면 표시
    plt.close(fig)

