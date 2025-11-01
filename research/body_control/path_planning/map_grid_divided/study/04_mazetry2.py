# benchmark_astar_8dir_maze_like.py
import math
import random
import time
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

def a_star_8dir(grid, start, goal):
    """
    grid: 0=통과가능, 1=장애물
    start/goal: (row, col)
    규칙: 대각선 이동 시 양 옆 직교 칸이 모두 비어 있어야 한다(코너 끼기 금지).
    """
    n_rows, n_cols = grid.shape

    def in_bounds(r, c): return 0 <= r < n_rows and 0 <= c < n_cols
    def walkable(r, c):  return in_bounds(r, c) and grid[r, c] == 0

    if not walkable(*start) or not walkable(*goal):
        return None

    g_score = {start: 0.0}
    f_start = diagonal_heuristic(start, goal)
    open_heap = [(f_start, 0.0, start)]
    came_from = {}
    closed = set()

    import heapq
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
            # ---- 코너 끼기 방지 조건 ----
            if abs(dr) == 1 and abs(dc) == 1:  # 대각선 이동
                # 예: (r,c)->(r+1,c+1) 이면 (r+1,c)와 (r,c+1) 둘 다 비어 있어야 함
                if grid[cr + dr, cc] == 1 or grid[cr, cc + dc] == 1:
                    continue
                step_cost = math.sqrt(2)
            else:
                step_cost = 1.0
            # ----------------------------

            nxt = (nr, nc)
            tentative_g = g_score[cur] + step_cost

            if nxt in closed and tentative_g >= g_score.get(nxt, float("inf")):
                continue

            if tentative_g < g_score.get(nxt, float("inf")):
                came_from[nxt] = cur
                g_score[nxt] = tentative_g
                f_new = tentative_g + diagonal_heuristic(nxt, goal)
                heapq.heappush(open_heap, (f_new, tentative_g, nxt))

    return None

# ---------------------------
# 유틸: "미로 느낌" 장애물 생성
#  - 세로/가로 스트라이프 벽을 균일 간격으로 깔고, 각 벽에 다수의 통로(gap)를 낸다.
#  - target 장애물 수(=n*n*obstacle_ratio)에 맞추어 채운다.
#  - 시작/목표는 항상 비움.
# ---------------------------
def make_maze_like_grid(n, obstacle_ratio=0.2, seed=None):
    """
    n x n Grid 생성. 0=빈칸, 1=장애물
    obstacle_ratio: 장애물 비율 (예: 0.2 → 20%)
    start=(n-1,n-1), goal=(0,0)은 항상 비워둠
    """
    rng = random.Random(seed)
    grid = np.zeros((n, n), dtype=np.uint8)

    target = int(n * n * obstacle_ratio)
    placed = 0

    def can_fill(r, c):
        return not (r == 0 and c == 0) and not (r == n-1 and c == n-1) and grid[r, c] == 0

    # 1) 세로 스트라이프 벽
    v_step = max(4, n // 10)             # 벽 간격
    v_gap_count = max(2, n // 6)         # 각 벽에 뚫을 통로 수
    for c in range(v_step, n, v_step):
        # 통로 위치 선택
        gaps = set(rng.sample(range(n), k=min(v_gap_count, n)))
        for r in range(n):
            if placed >= target:
                break
            if r in gaps:
                continue
            if can_fill(r, c):
                grid[r, c] = 1
                placed += 1
        if placed >= target:
            break

    # 2) 가로 스트라이프 벽 (아직 목표에 못 미치면 보강)
    if placed < target:
        h_step = max(4, n // 10)
        h_gap_count = max(2, n // 6)
        # 세로벽과 교차되도록 약간의 오프셋
        start_r = (h_step // 2)
        for r in range(start_r, n, h_step):
            gaps = set(rng.sample(range(n), k=min(h_gap_count, n)))
            for c in range(n):
                if placed >= target:
                    break
                if c in gaps:
                    continue
                if can_fill(r, c):
                    grid[r, c] = 1
                    placed += 1
            if placed >= target:
                break

    # 3) 부족하면 랜덤 벽으로 채움(비율 정확히 맞추기)
    if placed < target:
        free = [(r, c) for r in range(n) for c in range(n) if can_fill(r, c)]
        rng.shuffle(free)
        for (r, c) in free:
            if placed >= target:
                break
            grid[r, c] = 1
            placed += 1

    # 시작/목표 보장 (혹시라도)
    grid[0, 0] = 0
    grid[n-1, n-1] = 0
    return grid

# ---------------------------
# 메인: 여러 n에 대해 실행 & 시각화
# ---------------------------
if __name__ == "__main__":
    # 벤치마크할 n 목록
    n_values = [300, 200, 150, 100, 60, 50, 30, 20, 15, 10, 5, 4, 3, 2, 1]
    obstacle_ratio = 0.20     # 요청하신 비율(미로 느낌으로 잘 나오는 값)
    base_seed = 12345         # 재현성

    timings_ms = []
    results = []  # (n, found, path_len or False, grid, start, goal, [path?])

    # --- 각 n에 대해 경로 탐색 & 시간 측정 ---
    for n in n_values:
        start = (n-1, n-1)
        goal = (0, 0)

        grid = make_maze_like_grid(n, obstacle_ratio=obstacle_ratio, seed=base_seed + n)

        t0 = time.perf_counter()
        path = a_star_8dir(grid, start, goal)
        t1 = time.perf_counter()

        elapsed_ms = (t1 - t0) * 1000.0
        timings_ms.append(elapsed_ms)

        if path is None:
            results.append((n, False, False, grid, start, goal))
        else:
            results.append((n, True, len(path), grid, start, goal, path))

    # --- 격자 시각화: 큰 n 개별, 작은 n 서브플롯 ---
    big_ns = [n for n in n_values if n >= 100]
    small_ns = [n for n in n_values if n < 100]

    # 큰 격자(>=100)
    for n in big_ns:
        rec = next(r for r in results if r[0] == n)
        found, path_len, grid, start, goal = rec[1], rec[2], rec[3], rec[4], rec[5]
        path = rec[6] if found else None
        time_ms = timings_ms[n_values.index(n)]

        plt.figure(figsize=(6.5, 6.5))
        plt.title(
            f"Grid {n}x{n} | obstacles≈{int(n*n*obstacle_ratio)} | "
            f"path_len={path_len if found else 'False'} | time={time_ms:.2f} ms"
        )
        plt.imshow(grid, cmap="gray_r", origin="upper", interpolation="nearest")
        plt.scatter([start[1]], [start[0]], s=40, c="blue", marker="s", label="Start")
        plt.scatter([goal[1]], [goal[0]], s=40, c="red", marker="s", label="Goal")
        if found and path:
            ys = [r for r, c in path]
            xs = [c for r, c in path]
            plt.plot(xs, ys, linewidth=1.5, c="green")
        plt.legend(loc="upper right")
        plt.tight_layout()

    # 작은 격자(<100): 서브플롯
    if small_ns:
        cols = 4
        rows = int(math.ceil(len(small_ns) / cols))
        plt.figure(figsize=(4.2*cols, 4.2*rows))
        for idx, n in enumerate(small_ns, 1):
            rec = next(r for r in results if r[0] == n)
            found, path_len, grid, start, goal = rec[1], rec[2], rec[3], rec[4], rec[5]
            path = rec[6] if found else None
            time_ms = timings_ms[n_values.index(n)]

            ax = plt.subplot(rows, cols, idx)
            ax.set_title(f"n={n} | len={path_len if found else 'False'}\n{time_ms:.2f} ms", fontsize=10)
            ax.imshow(grid, cmap="gray_r", origin="upper", interpolation="nearest")
            ax.scatter([start[1]], [start[0]], s=30, c="blue", marker="s")
            ax.scatter([goal[1]], [goal[0]], s=30, c="red", marker="s")
            if found and path:
                ys = [r for r, c in path]
                xs = [c for r, c in path]
                ax.plot(xs, ys, linewidth=1.2, c="green")
            ax.set_xticks([])
            ax.set_yticks([])
        plt.tight_layout()

    # --- 처리시간 가로 막대그래프 (x=시간, y=n) ---
    plt.figure(figsize=(8, max(6, len(n_values)*0.35)))
    y_pos = np.arange(len(n_values))
    plt.barh(y_pos, timings_ms)
    plt.yticks(y_pos, [str(n) for n in n_values])
    plt.xlabel("A* time (ms)")
    plt.ylabel("Grid size n")
    plt.title("A* 8-dir (no corner cutting) Runtime by Grid Size (maze-like obstacles)")
    for i, v in enumerate(timings_ms):
        plt.text(v + (max(timings_ms) * 0.01 if max(timings_ms) > 0 else 0.02), i, f"{v:.2f} ms",
                 va="center", fontsize=8)
    plt.tight_layout()

    plt.show()
