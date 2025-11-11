# astar_barh_8dir_maze_batch_2x2.py                           파일명: 8방향 A* + 미로형 장애물 + 배치 시각화 + 통계 저장
# ------------------------------------------------------------ 
# 주요 특징:
# - 대각선 이동 비용 = sqrt(2)
# - "코너 끼기" 방지: 대각선 이동 시 양 옆 직교 칸이 모두 비어있을 때만 허용
# - 미로장애물: 작은 격자(Prim 변형) → 블록 확장(kron) → 목표 벽 비율로 보정
# 8방향(대각 포함) A* 경로탐색을 "미로형" 장애물에서 수행하고   
# - n 값별로 2×2 subplot 묶음 이미지 저장/표시
# - n 값별 평균 처리시간 가로 막대 그래프 저장/표시
# - n 값별 통계를 CSV 로 저장
# ------------------------------------------------------------ 

import math                                                   # 수학 함수(특히 sqrt) 사용
import random                                                 # 파이썬 표준 난수 모듈(시드 고정용)
import time                                                   # 성능 측정(경과 시간)용
import csv                                                    # CSV 파일 저장용
from collections import defaultdict                           # (현재 사용하지 않지만) 기본 dict 확장 시 유용
import numpy as np                                            # 수치 연산 및 배열 처리
import matplotlib.pyplot as plt                               # 시각화(격자/경로/막대그래프)

# ---------------------------                                  # A* 관련 유틸 섹션 구분선
# 8-방향 A* (대각선 비용 = sqrt(2), 코너 끼기 방지)
# ---------------------------

def neighbors_8dir(r, c):                                     # 격자 좌표 (r,c)의 8방향 이웃을 반환하는 함수
    """
    (r, c)에서 이동 가능한 8방향 이웃 좌표를 반환.
    상하좌우 + 4개의 대각선.
    """
    return [                                                  # 8개의 방향 튜플을 리스트로 반환
        (r-1, c), (r+1, c), (r, c-1), (r, c+1),              # 상, 하, 좌, 우
        (r-1, c-1), (r-1, c+1), (r+1, c-1), (r+1, c+1)       # 좌상, 우상, 좌하, 우하(대각)
    ]

def diagonal_heuristic(a, b):                                 # 8방향 격자에 적합한 휴리스틱(Octile distance)
    """
    Octile distance(8방향 격자에 적절한 휴리스틱).
    - admissible(낙관적)하여 A*의 최단경로 보장에 적합.
    """
    dx = abs(a[0] - b[0])                                     # 행 차이 절댓값
    dy = abs(a[1] - b[1])                                     # 열 차이 절댓값
    return (dx + dy) + (math.sqrt(2) - 2) * min(dx, dy)       # Octile 공식을 그대로 적용

def reconstruct_path(came_from, current):                     # 부모 포인터로부터 경로 복원
    """
    A* 탐색에서 도착 노드(current)부터 부모 포인터(came_from)를 따라
    시작까지 되짚어가며 경로를 복원.
    """
    path = [current]                                          # 현재 노드로 시작
    while current in came_from:                               # current의 부모가 존재하는 동안
        current = came_from[current]                          # 부모로 올라가고
        path.append(current)                                  # 경로에 추가
    return path[::-1]                                         # 시작 → 도착 순서로 뒤집어서 반환

def a_star_8dir_no_corner_cut(grid, start, goal):             # 8방향 A* (코너 끼기 방지) 본체
    """
    8방향 A* 탐색 (코너 끼기 방지):
    - grid: 0=통과가능, 1=장애물
    - start/goal: (row, col)
    - 대각선 이동 시 '코너 끼기' 금지:
      예) (r,c) → (r+1,c+1) 이동하려면 (r+1,c)와 (r,c+1)이 모두 0이어야 함.
    """
    n_rows, n_cols = grid.shape                               # 격자 높이/너비

    def in_bounds(r, c): return 0 <= r < n_rows and 0 <= c < n_cols  # 경계 체크 람다
    def walkable(r, c):  return in_bounds(r, c) and grid[r, c] == 0  # 통행 가능 여부 람다

    if not walkable(*start) or not walkable(*goal):           # 시작이나 도착이 막혀있으면
        return None                                           # 경로 없음

    import heapq                                              # 우선순위 큐(힙) 사용
    g_score = {start: 0.0}                                    # 시작점의 g(실제 비용) = 0
    f_start = diagonal_heuristic(start, goal)                 # 시작점의 f = g + h
    open_heap = [(f_start, 0.0, start)]                       # (f,g,node) 튜플로 큐 초기화
    came_from = {}                                            # 부모 포인터 저장 dict
    closed = set()                                            # 확정(이미 처리) 노드 집합

    while open_heap:                                          # 오픈 리스트가 빌 때까지 반복
        f, g, cur = heapq.heappop(open_heap)                  # f가 가장 작은 노드 pop
        if cur in closed:                                     # 이미 처리된 노드면
            continue                                          
        closed.add(cur)                                       # 현 노드를 처리 집합에 넣음

        if cur == goal:                                       # 목표 도달 시
            return reconstruct_path(came_from, cur)           # 경로 복원 후 반환

        cr, cc = cur                                          # 현재 좌표 분해
        for nr, nc in neighbors_8dir(cr, cc):                 # 8방향 이웃 순회
            if not in_bounds(nr, nc) or grid[nr, nc] == 1:    # 경계 밖/벽이면
                continue                                      # 스킵

            dr = nr - cr                                      # 행 이동량
            dc = nc - cc                                      # 열 이동량
            if abs(dr) == 1 and abs(dc) == 1:                 # 대각선 이동인 경우
                if grid[cr + dr, cc] == 1 or grid[cr, cc + dc] == 1:  # 양 옆 직교칸 중 하나라도 벽이면
                    continue                                  # 대각선 이동 금지(코너 끼기 방지)
                step_cost = math.sqrt(2)                      # 대각선 비용 = √2
            else:                                             # 직교 이동인 경우
                step_cost = 1.0                               # 비용 = 1

            nxt = (nr, nc)                                    # 다음 노드 좌표
            tentative_g = g + step_cost                       # g 후보값 = 현재 g + 이동 비용

            if nxt in closed and tentative_g >= g_score.get(nxt, float("inf")):  # 이미 더 좋은 g가 있으면
                continue                                      

            if tentative_g < g_score.get(nxt, float("inf")):  # 더 좋은 경로면 갱신
                came_from[nxt] = cur                          # 부모 포인터 갱신
                g_score[nxt] = tentative_g                    # g 갱신
                f_new = tentative_g + diagonal_heuristic(nxt, goal)  # f = g+h
                heapq.heappush(open_heap, (f_new, tentative_g, nxt))  # 오픈 큐에 push

    return None                                               # 큐가 비도록 못 찾으면 경로 없음

# ---------------------------                                  # 미로 생성 섹션 구분선
# 미로 느낌 장애물 생성
# - 작은(coarse) 격자에서 Prim 변형으로 미로(0=길, 1=벽) 생성
# - block_size 배수로 크기 확장(kron)
# - 최종 벽 비율을 obstacle_ratio에 맞추도록 랜덤 보정
# ---------------------------

def generate_coarse_maze(H, W, rng):                          # 작은 격자에서 미로(Prim 변형) 생성
    """
    H×W(홀수 권장)에서 1=벽, 0=길 형태 미로를 생성.
    - (1,1)에서 시작하여, 벽 목록에서 무작위 팝 → 벽을 허물며 길 확장
    - 이웃은 2칸 간격(벽을 사이에 둔 셀)을 기준으로 연결
    """
    H = max(3, H | 1)                                         # H를 홀수로 보정(최소 3)
    W = max(3, W | 1)                                         # W를 홀수로 보정(최소 3)
    maze = np.ones((H, W), dtype=np.uint8)                    # 초기: 전부 벽(1)
    sr, sc = 1, 1                                             # 시작 좌표(홀수 격자 기준 내부)
    maze[sr, sc] = 0                                          # 시작 셀을 길(0)로 지정

    walls = []                                                # 인접 벽 후보 리스트
    def add_walls(r, c):                                      # (r,c)의 2칸 떨어진 이웃을 벽 후보로 추가
        for dr, dc in [(-2,0),(2,0),(0,-2),(0,2)]:            # 상하좌우로 2칸
            nr, nc = r+dr, c+dc                               # 후보 좌표
            if 0 <= nr < H and 0 <= nc < W and maze[nr, nc] == 1:  # 내부 & 아직 벽이면
                walls.append((nr, nc, r, c))                  # (벽 좌표, 부모 길 좌표) 추가
    add_walls(sr, sc)                                         # 시작점 주변 벽 후보 초기화

    while walls:                                              # 벽 후보가 남는 동안
        idx = rng.randrange(len(walls))                       # 무작위 인덱스 선택
        wr, wc, pr, pc = walls.pop(idx)                       # 해당 벽 후보 pop
        mr, mc = (wr+pr)//2, (wc+pc)//2                       # 벽과 길 사이의 중간(실제 벽 위치)
        if maze[wr, wc] == 1:                                 # 해당 후보가 아직 벽이면
            maze[wr, wc] = 0                                  # 벽을 허물어 길로 만든다
            maze[mr, mc] = 0                                  # 중간 벽도 허물어 연결
            add_walls(wr, wc)                                 # 새로 열린 길 주변의 벽 후보 추가

    return maze                                               # 0=길, 1=벽 미로 반환

def make_maze_obstacles_grid(n, obstacle_ratio=0.4, seed=123, block_size=6, clear_margin=1):
    """
    n×n 최종 grid 생성(0=빈칸, 1=장애물).
    1) 작은 미로(coarse)를 만든 뒤 block_size로 크기 확장
    2) 중앙 기준으로 n×n으로 크롭/패딩
    3) 테두리 여백(clear_margin) 및 start/goal 확보
    4) 최종 벽 비율이 obstacle_ratio가 되도록 랜덤 보정
    """
    rng = random.Random(seed)                                  # 파이썬 random 시드 고정

    Hc = max(3, (n // block_size) | 1)                         # coarse 높이(홀수), n과 block_size로 결정
    Wc = max(3, (n // block_size) | 1)                         # coarse 너비(홀수)
    coarse = generate_coarse_maze(Hc, Wc, rng)                 # coarse 미로 생성(0=길,1=벽)

    fine = np.kron(coarse, np.ones((block_size, block_size), dtype=np.uint8))  # block_size 배로 확장

    Hf, Wf = fine.shape                                        # 확장된 배열 크기
    if Hf < n or Wf < n:                                       # 목표 크기보다 작으면
        pad_r = max(0, n - Hf)                                 # 필요한 행 패딩 양
        pad_c = max(0, n - Wf)                                 # 필요한 열 패딩 양
        fine = np.pad(fine, ((pad_r//2, pad_r - pad_r//2),     # 위/아래 대칭 패딩
                             (pad_c//2, pad_c - pad_c//2)),    # 좌/우 대칭 패딩
                      mode="edge")                             # 가장자리 값 복제 방식으로 패딩

    Hf, Wf = fine.shape                                        # 패딩 후 크기 갱신
    sr = (Hf - n)//2                                           # 중앙 크롭 시작 행
    sc = (Wf - n)//2                                           # 중앙 크롭 시작 열
    grid = fine[sr:sr+n, sc:sc+n].copy()                       # n×n으로 잘라 복사(0=길,1=벽)

    grid[:clear_margin, :] = 0                                 # 위쪽 테두리 여백을 길로
    grid[:, :clear_margin] = 0                                 # 왼쪽 테두리 여백을 길로
    grid[-clear_margin:, :] = 0                                # 아래쪽 테두리 여백을 길로
    grid[:, -clear_margin:] = 0                                # 오른쪽 테두리 여백을 길로
    grid[0, 0] = 0                                             # 시작 셀 보장(비움)
    grid[n-1, n-1] = 0                                         # 도착 셀 보장(비움)

    cur_ratio = grid.mean()                                    # 현재 벽 비율(1의 평균)
    target = obstacle_ratio                                    # 목표 벽 비율
    rng_np = np.random.default_rng(seed + 999)                 # NumPy RNG(샘플링용)

    if cur_ratio > target:                                     # 벽이 너무 많으면
        wall_pos = np.argwhere(grid == 1)                      # 벽 좌표 목록
        need = int((cur_ratio - target) * n * n)               # 제거해야 할 벽 수(대략)
        if need > 0 and len(wall_pos) > 0:                     # 필요한 양이 있고 벽이 존재하면
            idx = rng_np.choice(len(wall_pos), size=min(need, len(wall_pos)), replace=False)  # 무작위 추출
            for r, c in wall_pos[idx]:                         # 선택된 벽 좌표들을
                grid[r, c] = 0                                 # 길로 바꿔 비율 낮춤
    elif cur_ratio < target:                                   # 벽이 너무 적으면
        free_pos = np.argwhere(grid == 0)                      # 빈칸 좌표 목록
        need = int((target - cur_ratio) * n * n)               # 추가해야 할 벽 수(대략)
        if need > 0 and len(free_pos) > 0:                     # 필요한 양이 있고 빈칸이 존재하면
            idx = rng_np.choice(len(free_pos), size=min(need, len(free_pos)), replace=False)  # 무작위 추출
            for r, c in free_pos[idx]:                         # 선택된 빈칸 좌표들을
                grid[r, c] = 1                                 # 벽으로 바꿔 비율 올림
        grid[0, 0] = 0                                         # 시작/도착은 다시 비워서 통로 보장
        grid[n-1, n-1] = 0

    return grid                                                # 최종 n×n 그리드 반환

# ---------------------------                                  # 실행/벤치마크 섹션 구분선
# 벤치마크 & 시각화 (항상 2×2 묶음 저장→print→표시→닫기)
# ---------------------------
if __name__ == "__main__":                                     # 스크립트 직접 실행 시에만 아래 수행
    n_values = [300, 200, 150, 100, 60, 50, 30, 20, 15, 10, 5, 4, 3, 2, 1]  # 테스트할 n 목록(큰→작은)
    obstacle_ratio = 0.20                                      # 미로형 벽 비율(요청한 0.2)
    base_seed = 12345                                          # 시드 기반(재현성)
    trials_per_n = 10                                          # 각 n 별 반복 횟수(평균 시간 계산)
    block_size = 4                                             # 미로 스케일(클수록 벽이 더 굵게 보임)
    clear_margin = 1                                           # 테두리 여백(시작/종료 막힘 방지)

    avg_time_ms = []                                           # n별 평균 처리시간(ms) 저장
    avg_path_len_success = []                                  # n별(성공만) 평균 경로 길이
    success_counts = []                                         # n별 성공 횟수
    sample_records = {}                                        # 시각화용 샘플: {n: (grid, path, found, time_ms)}

    csv_rows = [("n", "trials", "success", "avg_time_ms", "avg_path_len_success")]  # CSV 헤더

    for n in n_values:                                         # 각 n에 대해
        start = (n-1, n-1)                                     # 시작: 우하단 모서리
        goal = (0, 0)                                          # 목표: 좌상단 모서리

        times = []                                             # trial별 처리시간(ms)
        path_lens = []                                         # 성공 trial의 경로 길이
        success = 0                                            # 성공 카운트
        sample_saved = False                                   # 첫 trial을 샘플로 저장했는지 여부

        for t in range(trials_per_n):                          # 동일 n에서 여러 번 실행
            seed = base_seed + n*1000 + t                      # n과 trial t에 따라 달라지는 시드
            grid = make_maze_obstacles_grid(                   # 미로형 장애물 그리드 생성
                n,
                obstacle_ratio=obstacle_ratio,
                seed=seed,
                block_size=block_size,
                clear_margin=clear_margin
            )

            t0 = time.perf_counter()                           # 시간 측정 시작
            path = a_star_8dir_no_corner_cut(grid, start, goal)  # A* 실행
            t1 = time.perf_counter()                           # 시간 측정 끝
            dt_ms = (t1 - t0) * 1000.0                         # 경과(ms) 계산
            times.append(dt_ms)                                # 시간 기록

            if path is not None:                               # 성공 시
                success += 1                                   # 성공 카운트 증가
                path_lens.append(len(path))                    # 경로 길이 기록

            if not sample_saved:                               # 첫 trial이면
                sample_records[n] = (grid, path, path is not None, dt_ms)  # 샘플 저장
                sample_saved = True                            # 플래그 세팅

        mean_time = float(np.mean(times)) if times else 0.0    # 평균 처리시간(ms)
        mean_path_len = float(np.mean(path_lens)) if path_lens else 0.0  # 성공 평균 경로 길이

        avg_time_ms.append(mean_time)                          # 리스트에 누적
        avg_path_len_success.append(mean_path_len)             # 리스트에 누적
        success_counts.append(success)                         # 리스트에 누적

        print(                                                 # 콘솔 요약 출력
            f"n={n:>3} | trials={trials_per_n} | success={success:<2} | "
            f"avg_time={mean_time:.2f} ms | avg_path_len_success={mean_path_len:.1f}"
        )

        csv_rows.append((n, trials_per_n, success,             # CSV 한 행 추가
                         round(mean_time, 4), round(mean_path_len, 2)))

    csv_path = "benchmark_results.csv"                         # CSV 파일 경로
    with open(csv_path, "w", newline="", encoding="utf-8") as f:  # 쓰기 모드 오픈
        writer = csv.writer(f)                                 # csv writer 생성
        writer.writerows(csv_rows)                             # 모든 행 쓰기
    print(f"[saved] {csv_path}")                               # 저장 완료 로그

    def draw_one(ax, n, record):                               # 한 서브플롯(ax)에 한 개의 n×n 결과를 그림
        """
        한 축(ax)에 하나의 n×n grid와 경로를 그려준다.
        - 시작(파랑), 도착(빨강), 경로(초록)
        - 제목: n, 경로 길이(실패 시 False), 샘플 처리시간
        """
        grid, path, found, time_ms = record                    # 레코드 언팩
        ax.imshow(grid, cmap="gray_r", origin="upper", interpolation="nearest")  # 격자 영상
        start = (n-1, n-1)                                     # 시작 좌표
        goal = (0, 0)                                          # 목표 좌표
        ax.scatter([start[1]], [start[0]], s=35, c="blue", marker="s")  # 시작(파랑)
        ax.scatter([goal[1]], [goal[0]], s=35, c="red", marker="s")     # 목표(빨강)
        if found and path is not None:                         # 경로가 있으면
            ys = [r for r, c in path]                          # 경로 y(행) 목록
            xs = [c for r, c in path]                          # 경로 x(열) 목록
            ax.plot(xs, ys, linewidth=1.4, c="green")          # 경로(초록) 그리기
            title_len = len(path)                              # 제목에 표시할 경로 길이
        else:                                                  # 경로가 없으면
            title_len = "False"                                # False로 표시
        ax.set_title(f"n={n} | len={title_len}\nsample={time_ms:.2f} ms", fontsize=10)  # 제목
        ax.set_xticks([])                                      # 축 눈금 제거(가독성)
        ax.set_yticks([])                                      # 축 눈금 제거(가독성)

    batch_size = 4                                             # 한 그림에 4개(2×2)씩
    batches = [n_values[i:i+batch_size] for i in range(0, len(n_values), batch_size)]  # n을 4개씩 나눔
    for bidx, batch in enumerate(batches, 1):                  # 각 배치에 대해
        fig, axes = plt.subplots(2, 2, figsize=(8, 8))         # 2×2 서브플롯 생성
        axes = axes.ravel()                                    # 1차원 배열로 평탄화
        for i in range(4):                                     # 4칸 순회
            ax = axes[i]                                       # 현재 축
            if i < len(batch):                                 # 배치 내 실제 n이 있으면
                n = batch[i]                                   # 해당 n
                rec = sample_records[n]                        # 샘플 레코드
                draw_one(ax, n, rec)                           # 그리기
            else:                                              # 배치가 4보다 작아 빈칸이면
                ax.axis("off")                                 # 축 비활성화(빈 칸)
        plt.tight_layout()                                     # 레이아웃 정리
        out_path = f"grids_batch_{bidx:02d}.jpg"               # 저장 파일명
        plt.savefig(out_path, dpi=180)                         # JPG로 저장(quality 인자 없이)
        print(f"[saved] {out_path}")                           # 저장 완료 로그
        plt.show()                                             # 화면에 표시
        plt.close(fig)                                         # 그림 닫기(메모리/창 정리)

    fig = plt.figure(figsize=(8, max(6, len(n_values)*0.35)))  # 처리시간 가로 막대그래프용 figure
    y_pos = np.arange(len(n_values))                           # y축 위치(카테고리 인덱스)
    plt.barh(y_pos, avg_time_ms)                               # 가로 막대 그래프(길이=평균 시간)
    plt.yticks(y_pos, [str(n) for n in n_values])              # y축 라벨을 n 값으로 표시
    plt.xlabel("Average A* time (ms)")                         # x축 라벨
    plt.ylabel("Grid size n")                                  # y축 라벨
    plt.title("A* 8-dir (no corner cutting) - Avg Runtime by Grid Size")  # 그래프 제목

    mmax = max(avg_time_ms) if avg_time_ms else 0.0            # 막대 끝 라벨 위치 계산용 최대값
    for i, v in enumerate(avg_time_ms):                        # 각 막대 위에 값 표시
        plt.text(v + (mmax * 0.01 if mmax > 0 else 0.02),      # 막대 끝 조금 오른쪽
                 i, f"{v:.2f} ms", va="center", fontsize=8)    # "xx.xx ms" 텍스트

    plt.tight_layout()                                         # 레이아웃 정리
    bar_path = "runtime_barh.jpg"                              # 저장 파일명
    plt.savefig(bar_path, dpi=180)                             # JPG로 저장
    print(f"[saved] {bar_path}")                               # 저장 완료 로그
    plt.show()                                                 # 화면 표시
    plt.close(fig)                                             # 창 닫기
