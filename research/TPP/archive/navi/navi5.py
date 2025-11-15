import numpy as np
import heapq, math
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

# ========================= 설정 =========================
MAP_SIZE = 3000          # 300m x 300m
CELL_SIZE = 0.1          # 1셀 = 0.1m
OBSTACLE_SIZE = 20       # 장애물 한 변의 셀 수 (2m)
OBSTACLE_RADIUS = OBSTACLE_SIZE // 2

# ========================= 맵 초기화 =========================
occupancy_map = np.zeros((MAP_SIZE, MAP_SIZE), dtype=np.int8)
cost_map = np.ones((MAP_SIZE, MAP_SIZE), dtype=np.float16)

def world_to_grid(x, z):
    gx = int(x / CELL_SIZE)
    gz = int(z / CELL_SIZE)
    return gx, gz

def grid_to_world(gx, gz):
    return gx * CELL_SIZE, gz * CELL_SIZE

def in_bounds(x, z):
    return 0 <= x < MAP_SIZE and 0 <= z < MAP_SIZE

# ========================= 장애물 처리 =========================
def add_obstacle(x, z):
    gx, gz = world_to_grid(x, z)
    for dx in range(-OBSTACLE_RADIUS, OBSTACLE_RADIUS + 1):
        for dz in range(-OBSTACLE_RADIUS, OBSTACLE_RADIUS + 1):
            nx, nz = gx + dx, gz + dz
            if in_bounds(nx, nz):
                occupancy_map[nz, nx] = 1  # 1 = 장애물

def add_multiple_obstacles(obstacle_positions):
    for (x, z) in obstacle_positions:
        add_obstacle(x, z)

# ========================= A* 알고리즘 =========================
def heuristic(a, b):
    (x1, y1), (x2, y2) = a, b
    return math.hypot(x1 - x2, y1 - y2)

def neighbors(x, y):
    for dx in [-1, 0, 1]:
        for dy in [-1, 0, 1]:
            if dx == 0 and dy == 0:
                continue
            nx, ny = x + dx, y + dy
            if in_bounds(nx, ny) and occupancy_map[ny, nx] == 0:
                yield nx, ny

def a_star(start, goal):
    open_list = []
    heapq.heappush(open_list, (0, start))
    came_from = {}
    g_score = {start: 0}

    while open_list:
        _, current = heapq.heappop(open_list)
        if current == goal:
            path = []
            while current in came_from:
                path.append(current)
                current = came_from[current]
            path.append(start)
            path.reverse()
            return path

        for neighbor in neighbors(*current):
            tentative_g = g_score[current] + cost_map[neighbor[1], neighbor[0]]
            if tentative_g < g_score.get(neighbor, 1e9):
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f_score = tentative_g + heuristic(neighbor, goal)
                heapq.heappush(open_list, (f_score, neighbor))

    return []

# ========================= 시각화 및 시뮬레이션 =========================
def simulate_tank_path(start_world, goal_world, obstacles_world):
    # 장애물 등록
    add_multiple_obstacles(obstacles_world)

    # 좌표 변환
    start = world_to_grid(*start_world)
    goal = world_to_grid(*goal_world)

    # 경로 탐색
    print("🧭 경로 탐색 중...")
    path = a_star(start, goal)
    if not path:
        print("❌ 경로를 찾을 수 없습니다.")
        return

    print(f"✅ 경로 탐색 완료! (길이: {len(path)} 셀)")
    print("🎥 전차 시뮬레이션 시작...")

    # ---------------- 시각화 ----------------
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.set_title("Tank Path Simulation (A* Pathfinding)")
    ax.set_xlim(0, MAP_SIZE)
    ax.set_ylim(0, MAP_SIZE)
    ax.set_xlabel("X")
    ax.set_ylabel("Z")
    ax.invert_yaxis()

    # 장애물 표시
    obs_y, obs_x = np.where(occupancy_map == 1)
    ax.scatter(obs_x, obs_y, s=1, c="red", alpha=0.5, label="Obstacle")

    # 경로 표시
    px, py = zip(*path)
    path_line, = ax.plot(px, py, color="yellow", linewidth=1.5, label="Path")

    # 시작 & 목표 표시
    ax.scatter(start[0], start[1], color="green", s=50, label="Start")
    ax.scatter(goal[0], goal[1], color="blue", s=50, label="Goal")

    # 전차 표시 (움직이는 점)
    tank_dot, = ax.plot([], [], 'go', markersize=8)

    # 애니메이션 프레임 함수
    def update(frame):
        if frame < len(path):
            x, y = path[frame]
            tank_dot.set_data(x, y)
        return tank_dot,

    ani = FuncAnimation(fig, update, frames=len(path), interval=5, repeat=False)
    ax.legend()
    plt.show()

# ========================= 실행 예시 =========================
if __name__ == "__main__":
    print("=== A* Pathfinding + Tank Simulation ===")

    # 장애물 여러 개 배치
    obstacles = [
        (100, 100),
        (150, 180),
        (120, 250),
        (200, 200),
        (250, 150),
        (220, 260)
    ]

    start_pos = (50, 50)
    goal_pos = (280, 280)

    simulate_tank_path(start_pos, goal_pos, obstacles)
