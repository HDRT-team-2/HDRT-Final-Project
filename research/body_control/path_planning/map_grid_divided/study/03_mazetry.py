# easy_sparse_maze_demo.py
import random
import math
import numpy as np
import matplotlib.pyplot as plt

# ---- 8방향 A*를 쓰고 싶으면: grid를 이 함수에 넣어 경로도 구할 수 있음(옵션) ----
# 여기선 미로만 시각화하므로 A* 코드는 생략. 필요하면 알려줘!

def perfect_maze_dfs(h, w, rng):
    """
    h, w: coarse-cell 크기(미로 셀 개수). 각각 홀수 권장.
    반환: passages[r][c] = True/False (통로여부), 그리고 인접 연결 정보
    """
    h = h if h % 2 == 1 else h - 1
    w = w if w % 2 == 1 else w - 1
    passages = [[False]*w for _ in range(h)]
    # 4방향 인접
    dirs = [(-2,0),(2,0),(0,-2),(0,2)]
    stack = []
    # 시작은 (1,1) 근처
    sr, sc = 1, 1
    passages[sr][sc] = True
    stack.append((sr,sc))
    while stack:
        r,c = stack[-1]
        # 아직 뚫지 않은 이웃 후보
        candidates = []
        for dr,dc in dirs:
            nr, nc = r+dr, c+dc
            if 1 <= nr < h-1 and 1 <= nc < w-1 and not passages[nr][nc]:
                candidates.append((nr,nc, dr//2, dc//2))  # 중간 벽 위치용
        if not candidates:
            stack.pop()
            continue
        nr, nc, mr, mc = rng.choice(candidates)
        # 중간벽과 목표셀을 통로로
        passages[r+mr][c+mc] = True
        passages[nr][nc] = True
        stack.append((nr,nc))
    return passages  # True인 칸이 통로(통로가 아닌 칸은 잠정적 '벽'로 볼 수 있음)

def draw_sparse_walls_from_maze(passages, n, target_ratio, rng):
    """
    조밀 미로(passages)를 n×n로 스케일링해서 '선형 벽'만 일부 추출.
    목표 비율(2~3%) 근처가 되도록 벽을 솎아낸다.
    """
    Hc, Wc = len(passages), len(passages[0])
    # 대략적인 벽 비율 ~ 1/cell_size 가 되도록 셀 크기 선택
    # 목표 비율이 0.025면 cell_size ~ 40가 적절하지만, n이 작으면 클램프.
    # 너무 굵게 그리지 않으려고 최소 2 유지
    cell = max(2, min(n//3, int(round(1.0/target_ratio)) if target_ratio > 0 else n//3))
    if cell < 2: cell = 2

    grid = np.zeros((n, n), dtype=np.uint8)

    # passages는 True=통로, False=벽(조밀). 우리는 "통로 사이 경계선"만 선으로 그린다.
    # coarse -> fine 매핑: 각 coarse 칸을 cell×cell 블록으로 본다.
    # 이웃 셀 사이에 연결이 없으면 경계선을 1로 그려 '벽 느낌'만 유지(면이 아니라 선).
    def block_top_left(r, c):
        return r*cell, c*cell

    # 연결 판정용: 인접한 두 통로가 둘 다 True이면 경계선은 열어둠(벽X).
    # 둘 중 하나라도 False면 경계선을 '얇은 벽 선'으로 긋는다.
    for r in range(Hc):
        for c in range(Wc):
            # 경계선 후보: 우/하
            br, bc = block_top_left(r, c)

            # 오른쪽 경계선
            if c+1 < Wc:
                a = passages[r][c]
                b = passages[r][c+1]
                if not (a and b):
                    # 세로선 그리기 (두 블록 사이)
                    x = bc + cell - 1  # 한 칸 두께의 세로 벽
                    y0 = br
                    y1 = min(n, br + cell)
                    grid[y0:y1, min(n-1, x)] = 1

            # 아래쪽 경계선
            if r+1 < Hc:
                a = passages[r][c]
                b = passages[r+1][c]
                if not (a and b):
                    # 가로선 그리기
                    y = br + cell - 1
                    x0 = bc
                    x1 = min(n, bc + cell)
                    grid[min(n-1, y), x0:x1] = 1

    # 시작/도착은 열어두기
    grid[0,0] = 0
    grid[n-1,n-1] = 0

    # 목표 비율에 맞게 '벽 픽셀'을 일부 제거(솎아내기)해서 2~3% 근처로 조정
    wall_coords = np.argwhere(grid == 1)
    want = int(round(target_ratio * n * n))
    if len(wall_coords) > want:
        # 남길 개수 = want
        keep_idx = rng.sample(range(len(wall_coords)), want)
        keep_mask = np.zeros(len(wall_coords), dtype=bool)
        keep_mask[keep_idx] = True
        to_zero = wall_coords[~keep_mask]
        grid[to_zero[:,0], to_zero[:,1]] = 0

    # 최종 비율
    ratio = grid.sum() / float(n*n)
    return grid, ratio

def generate_sparse_maze(n=30, target_ratio=0.025, seed=0):
    """
    n×n에서 '아주 성긴' 미로풍 벽(2~3%)을 생성.
    """
    rng = random.Random(seed)
    # coarse 미로 크기는 너무 작지 않게(최소 9×9), n에 비례
    coarse = max(9, (n // 3) | 1)  # 홀수 유지
    passages = perfect_maze_dfs(coarse, coarse, rng)
    grid, ratio = draw_sparse_walls_from_maze(passages, n, target_ratio, rng)
    return grid, ratio

def show_three_examples(n=30, target_ratio=0.025, base_seed=1234):
    fig, axes = plt.subplots(1, 3, figsize=(9, 3), constrained_layout=True)
    for i, ax in enumerate(axes):
        grid, ratio = generate_sparse_maze(n=n, target_ratio=target_ratio, seed=base_seed+i)
        ax.imshow(1-grid, cmap="gray", interpolation="nearest", origin="upper")
        # 시작(파랑), 도착(빨강)
        ax.plot([n-1],[n-1],"s", ms=6, color="blue")
        ax.plot([0],[0],"s", ms=6, color="red")
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(f"n={n}  walls≈{ratio*100:.1f}%")
    plt.suptitle(f"Sparse Maze-like Walls (target ~{target_ratio*100:.1f}%)")
    plt.show()

if __name__ == "__main__":
    # n=30에서 3가지 예시 출력 (장애물 2~3%대)
    show_three_examples(n=30, target_ratio=0.2, base_seed=777)
