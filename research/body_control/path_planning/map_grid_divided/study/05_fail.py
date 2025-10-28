# benchmark_astar_8dir_bar_obstacles.py
import math
import random
import time
import numpy as np
import matplotlib.pyplot as plt

# =========================
# 8-방향 A* (코너 끼기 방지)
# =========================
def neighbors_8dir(r, c):
    return [
        (r-1, c), (r+1, c), (r, c-1), (r, c+1),           # 상하좌우
        (r-1, c-1), (r-1, c+1), (r+1, c-1), (r+1, c+1)    # 대각선
    ]

def diagonal_heuristic(a, b):
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
    대각선 이동 시 양 옆 직교 칸이 비어 있어야 함(코너 끼기 방지).
    """
    n_rows, n_cols = grid.shape
    def in_bounds(r, c): return 0 <= r < n_rows and 0 <= c < n_cols
    def walkable(r, c):  return in_bounds(r, c) and grid[r, c] == 0

    if not walkable(*start) or not walkable(*goal):
        return None

    g_score = {start: 0.0}
    f_start = diagonal_heuristic(start, goal)
    open_heap = [(f_start, 0.0, start)]
    came_from, closed = {}, set()

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

            dr, dc = nr - cr, nc - cc
            # 코너 끼기 방지
            if abs(dr) == 1 and abs(dc) == 1:
                if grid[cr + dr, cc] == 1 or grid[cr, cc + dc] == 1:
                    continue
                step_cost = math.sqrt(2)
            else:
                step_cost = 1.0

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

# =========================================
# 무작위 "막대(바) 형태" 장애물 생성 유틸
# =========================================
def make_bar_obstacles_grid(
    n,
    obstacle_ratio=0.20,
    seed=None,
    min_bar_len_ratio=0.05,  # n의 비율 기준 최소 길이 (예: 0.05*n)
    max_bar_len_ratio=0.25,  # 최대 길이
    min_thickness=1,         # 최소 두께(격자 폭)
    max_thickness=3,         # 최대 두께
    p_horizontal=0.5,        # 가로 막대 확률(세로는 1 - p_horizontal)
    clear_margin=1           # 시작/목표 주변 여유(맨해튼 거리<=clear_margin은 비움)
):
    """
    n x n, 0=빈칸, 1=장애물.
    - 목표 개수: round(n*n*obstacle_ratio)
    - 막대 길이/두께/방향/위치를 무작위로 샘플링해 채움(겹침 허용).
    - start(0,0) / goal(n-1,n-1)과 그 주변 clear_margin은 항상 비워둠.
    """
    rng = random.Random(seed)
    grid = np.zeros((n, n), dtype=np.uint8)

    target = int(round(n * n * obstacle_ratio))
    placed = 0

    def protect_zone(r, c):
        # 시작/목표 및 주변 여유
        if abs(r - 0) + abs(c - 0) <= clear_margin:           # goal (0,0)
            return True
        if abs(r - (n - 1)) + abs(c - (n - 1)) <= clear_margin:  # start (n-1,n-1)
            return True
        return False

    def paint_cell(r, c):
        nonlocal placed
        if 0 <= r < n and 0 <= c < n and grid[r, c] == 0 and not protect_zone(r, c):
            grid[r, c] = 1
            placed += 1

    # 막대를 계속 추가하면서 목표 개수에 도달시 중단
    while placed < target:
        # 막대 파라미터 샘플링
        horizontal = rng.random() < p_horizontal
        bar_len = rng.randint(max(1, int(n * min_bar_len_ratio)),
                              max(1, int(n * max_bar_len_ratio)))
        bar_th = rng.randint(min_thickness, max_thickness)

        if horizontal:
            r0 = rng.randrange(n)                      # 시작 행
            c0 = rng.randrange(n)                      # 시작 열
            # 오른쪽/왼쪽 방향 랜덤 (둘 중 하나)
            dir_c = 1 if rng.random() < 0.5 else -1
            # 두께 방향(세로로 확장): 위로/아래로 편향 랜덤
            th_sign = 1 if rng.random() < 0.5 else -1

            for t in range(bar_len):
                c = c0 + dir_c * t
                if not (0 <= c < n):
                    break
                # 두께 적용
                for w in range(bar_th):
                    r = r0 + th_sign * w
                    if 0 <= r < n:
                        if placed >= target: break
                        paint_cell(r, c)
                if placed >= target: break
        else:
            r0 = rng.randrange(n)
            c0 = rng.randrange(n)
            dir_r = 1 if rng.random() < 0.5 else -1
            th_sign = 1 if rng.random() < 0.5 else -1

            for t in range(bar_len):
                r = r0 + dir_r * t
                if not (0 <= r < n):
                    break
                for w in range(bar_th):
                    c = c0 + th_sign * w
                    if 0 <= c < n:
                        if placed >= target: break
                        paint_cell(r, c)
                if placed >= target: break

        # 안전장치: 무한루프 방지 (희박한 확률로 채우기 어려울 수 있으니 랜덤 픽셀로 보충)
        if placed < target and rng.random() < 0.02:
            # 랜덤 보충
            free = [(rr, cc) for rr in range(n) for cc in range(n)
                    if grid[rr, cc] == 0 and not protect_zone(rr, cc)]
            rng.shuffle(free)
            for rr, cc in free:
                if placed >= target: break
                paint_cell(rr, cc)

    # 보호 구역 보장
    grid[0, 0] = 0
    grid[n-1, n-1] = 0
    for r in range(n):
        for c in range(n):
            if protect_zone(r, c):
                grid[r, c] = 0
    return grid

# =========================
# 메인: 벤치마크 & 시각화
# =========================
if __name__ == "__main__":
    n_values = [300, 200, 150, 100, 60, 50, 30, 20, 15, 10, 5, 4, 3, 2, 1]
    obstacle_ratio = 0.20
    base_seed = 12345

    timings_ms = []
    results = []  # (n, found, path_len or False, grid, start, goal, [path])

    for n in n_values:
        start = (n-1, n-1)
        goal = (0, 0)

        grid = make_bar_obstacles_grid(
            n,
            obstacle_ratio=obstacle_ratio,
            seed=base_seed + n,
            min_bar_len_ratio=0.05,
            max_bar_len_ratio=0.25,
            min_thickness=1,
            max_thickness=3,
            p_horizontal=0.5,
            clear_margin=1
        )

        t0 = time.perf_counter()
        path = a_star_8dir(grid, start, goal)
        t1 = time.perf_counter()
        elapsed_ms = (t1 - t0) * 1000.0
        timings_ms.append(elapsed_ms)

        if path is None:
            results.append((n, False, False, grid, start, goal))
        else:
            results.append((n, True, len(path), grid, start, goal, path))

    # 큰 격자(>=100) 크게 출력
    big_ns = [n for n in n_values if n >= 100]
    small_ns = [n for n in n_values if n < 100]

    for n in big_ns:
        rec = next(r for r in results if r[0] == n)
        found, path_len, grid, start, goal = rec[1], rec[2], rec[3], rec[4], rec[5]
        path = rec[6] if found else None
        time_ms = timings_ms[n_values.index(n)]

        plt.figure(figsize=(6.8, 6.8))
        plt.title(f"Grid {n}x{n} | obstacles≈{int(n*n*obstacle_ratio)} | "
                  f"path_len={path_len if found else 'False'} | time={time_ms:.2f} ms")
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
            ax.set_xticks([]); ax.set_yticks([])
        plt.tight_layout()

    # 처리시간 막대그래프 (가로)
    plt.figure(figsize=(8, max(6, len(n_values)*0.35)))
    y_pos = np.arange(len(n_values))
    plt.barh(y_pos, timings_ms)
    plt.yticks(y_pos, [str(n) for n in n_values])
    plt.xlabel("A* time (ms)")
    plt.ylabel("Grid size n")
    plt.title("A* 8-dir (no corner cutting) Runtime by Grid Size (random bar obstacles)")
    for i, v in enumerate(timings_ms):
        plt.text(v + (max(timings_ms)*0.01 if max(timings_ms) > 0 else 0.02), i, f"{v:.2f} ms",
                 va="center", fontsize=8)
    plt.tight_layout()

    plt.show()
