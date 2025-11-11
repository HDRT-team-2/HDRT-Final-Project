# benchmark_astar_8dir_barh.py
import math
import random
import time
import numpy as np
import matplotlib.pyplot as plt

# ---------------------------
# 8-방향 A* (대각선 비용 = sqrt(2))
# ---------------------------
def neighbors_8dir(r, c):
    return [
        (r-1, c), (r+1, c), (r, c-1), (r, c+1),     # 상하좌우
        (r-1, c-1), (r-1, c+1), (r+1, c-1), (r+1, c+1)  # 대각선
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
            if not walkable(nr, nc):
                continue
            nxt = (nr, nc)

            # 대각선 이동 비용 = sqrt(2), 직선 = 1
            dr = abs(nr - cr)
            dc = abs(nc - cc)
            step_cost = math.sqrt(2) if (dr == 1 and dc == 1) else 1.0
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
# 유틸: 격자/장애물 생성
# ---------------------------
def make_grid(n, obstacle_ratio=0.05, seed=None):
    """
    n x n Grid 생성. 0=빈칸, 1=장애물
    obstacle_ratio: 장애물 비율 (기본 5%)
    start=(n-1,n-1), goal=(0,0)은 항상 비워둠
    """
    if seed is not None:
        rng = random.Random(seed)
        np_rng = np.random.default_rng(seed)
    else:
        rng = random
        np_rng = np.random.default_rng()

    grid = np.zeros((n, n), dtype=np.uint8)

    total_cells = n * n
    num_obstacles = int(total_cells * obstacle_ratio)

    # 장애물 위치 무작위 선정
    # 시작/도착 제외
    free_cells = [(r, c) for r in range(n) for c in range(n) if not (r == 0 and c == 0) and not (r == n-1 and c == n-1)]
    chosen = set()
    while len(chosen) < num_obstacles and free_cells:
        r, c = free_cells[rng.randrange(len(free_cells))]
        chosen.add((r, c))
    for (r, c) in chosen:
        grid[r, c] = 1

    # start/goal은 반드시 0
    grid[0, 0] = 0
    grid[n-1, n-1] = 0
    return grid

# ---------------------------
# 메인: 여러 n에 대해 실행 & 시각화
# ---------------------------
if __name__ == "__main__":
    n_values = [300, 200, 150, 100, 60, 50, 30, 20, 15, 10, 5, 4, 3, 2, 1]
    obstacle_ratio = 0.05
    base_seed = 12345  # 재현성

    timings_ms = []
    results = []  # (n, found, path_len or False)

    # --- 각 n에 대해 경로 탐색 & 시간 측정 ---
    for n in n_values:
        start = (n-1, n-1)
        goal = (0, 0)

        grid = make_grid(n, obstacle_ratio=obstacle_ratio, seed=base_seed + n)

        t0 = time.perf_counter()
        path = a_star_8dir(grid, start, goal)
        t1 = time.perf_counter()

        elapsed_ms = (t1 - t0) * 1000.0
        timings_ms.append(elapsed_ms)

        if path is None:
            results.append((n, False, False, grid, start, goal))
        else:
            results.append((n, True, len(path), grid, start, goal, path))

    # --- 격자 시각화 (옵션: 큰 n은 크게, 작은 n은 서브플롯) ---
    # 큰 격자(>=100)는 개별 그림, 작은 격자는 서브플롯 모아보기
    big_ns = [n for n in n_values if n >= 100]
    small_ns = [n for n in n_values if n < 100]

    # 개별(큰 n)
    for n in big_ns:
        rec = next(r for r in results if r[0] == n)
        found = rec[1]
        path_len = rec[2]
        grid = rec[3]
        start = rec[4]
        goal = rec[5]
        path = rec[6] if found else None
        time_ms = timings_ms[n_values.index(n)]

        plt.figure(figsize=(6, 6))
        plt.title(f"Grid {n}x{n} | obstacles={int(n*n*obstacle_ratio)} | "
                  f"path_len={path_len if found else 'False'} | time={time_ms:.2f} ms")
        # 0=흰색, 1=검정색
        plt.imshow(grid, cmap="gray_r", origin="upper", interpolation="nearest")
        # 시작(파랑), 도착(빨강)
        plt.scatter([start[1]], [start[0]], s=40, c="blue", marker="s", label="Start")
        plt.scatter([goal[1]], [goal[0]], s=40, c="red", marker="s", label="Goal")

        # 경로(초록)
        if found and path:
            ys = [r for r, c in path]
            xs = [c for r, c in path]
            plt.plot(xs, ys, linewidth=1.5, c="green")

        plt.legend(loc="upper right")
        plt.tight_layout()

    # 서브플롯(작은 n)
    if small_ns:
        cols = 4
        rows = int(math.ceil(len(small_ns) / cols))
        plt.figure(figsize=(4*cols, 4*rows))
        for idx, n in enumerate(small_ns, 1):
            rec = next(r for r in results if r[0] == n)
            found = rec[1]
            path_len = rec[2]
            grid = rec[3]
            start = rec[4]
            goal = rec[5]
            path = rec[6] if found else None
            time_ms = timings_ms[n_values.index(n)]

            ax = plt.subplot(rows, cols, idx)
            ax.set_title(f"n={n} | len={path_len if found else 'False'}\n{time_ms:.2f} ms", fontsize=10)
            ax.imshow(grid, cmap="gray_r", origin="upper", interpolation="nearest")
            # 시작/도착
            ax.scatter([start[1]], [start[0]], s=30, c="blue", marker="s")
            ax.scatter([goal[1]], [goal[0]], s=30, c="red", marker="s")
            # 경로
            if found and path:
                ys = [r for r, c in path]
                xs = [c for r, c in path]
                ax.plot(xs, ys, linewidth=1.2, c="green")
            ax.set_xticks([])
            ax.set_yticks([])
        plt.tight_layout()

    # --- 처리시간 막대그래프 (축 교환: x = 시간(ms), y = n) ---
    plt.figure(figsize=(8, max(6, len(n_values)*0.35)))
    # y축에 n을 위에서 큰 값이 위로 오게 정렬
    y_labels = [str(n) for n in n_values]
    y_pos = np.arange(len(n_values))
    plt.barh(y_pos, timings_ms)
    plt.yticks(y_pos, y_labels)
    plt.xlabel("A* time (ms)")          # x축 = 시간
    plt.ylabel("Grid size n")            # y축 = n
    plt.title("A* 8-dir Runtime by Grid Size (Horizontal Bar)")
    # 값 라벨
    for i, v in enumerate(timings_ms):
        plt.text(v + max(timings_ms)*0.01, i, f"{v:.2f} ms", va="center", fontsize=8)
    plt.tight_layout()

    plt.show()
