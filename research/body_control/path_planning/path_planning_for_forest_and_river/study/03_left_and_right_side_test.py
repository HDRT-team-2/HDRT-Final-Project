"""
포레스트 앤 리버 맵에서 강만 피하는 주행경로 만들기.

credit by : oixxta

"""
import matplotlib.pyplot as plt
import math

# --- 연결 리스트 형태의 웨이포인트(목표) 관리 ---
class WaypointNode:
    def __init__(self, x, z, arrived=False):
        self.x = float(x)
        self.z = float(z)
        self.arrived = bool(arrived)
        self.next = None

class WaypointList:
    def __init__(self):
        self.head = None
        self.tail = None
        self._len = 0

    def append(self, x, z, arrived=False):
        node = WaypointNode(x, z, arrived)
        if not self.head:
            self.head = self.tail = node
        else:
            self.tail.next = node
            self.tail = node
        self._len += 1
        return node

    def peek(self):
        return self.head

    def pop(self):
        if not self.head:
            return None
        node = self.head
        self.head = node.next
        if not self.head:
            self.tail = None
        node.next = None
        self._len -= 1
        return node

    def mark_head_arrived(self):
        if self.head:
            self.head.arrived = True
            return True
        return False

    def is_empty(self):
        return self.head is None

    def to_list(self):
        out = []
        cur = self.head
        while cur:
            out.append({'x': cur.x, 'z': cur.z, 'arrived': cur.arrived})
            cur = cur.next
        return out

# 전역 웨이포인트 리스트 인스턴스 (기본값: 빈 리스트)
waypoints = WaypointList()

def create_nodes_for_leftside(z, z_move, buffer_distance, waypoints):
    # 1) z 상한 (버퍼만큼 아래 여유 두기)
    z_limit = 300 - buffer_distance

    # 2) z-구간별 최대 안전 x 정의(필요시 값만 바꾸면 됨)
    zones = [
        (30, 145),
        (120, 175),
        (300, 205),
    ]

    def max_safe_x_for(z):
        # z가 속한 첫 구간의 x를 반환
        for z_top, mx in zones:
            if z < z_top:
                return mx
        return zones[-1][1]  # 안전망

    # 3) 줄 개수 미리 산출 (마지막 줄 포함, 세로 이동 노드는 마지막에 추가하지 않음)
    n_lines = int(math.floor((z_limit - z) / z_move)) + 1

    for i in range(n_lines):
        cz = z + i * z_move
        mx = max_safe_x_for(cz)

        if i % 2 == 0:
            sx, ex = buffer_distance, mx
        else:
            sx, ex = mx, buffer_distance

        # 가로 주행
        waypoints.append(sx, abs(cz - 300))     # z좌표가 좌 상단이 0이 아니라 300이기 때문에 재 계산 후 웨이포인트에 추가
        waypoints.append(ex, abs(cz - 300))     # z좌표가 좌 상단이 0이 아니라 300이기 때문에 재 계산 후 웨이포인트에 추가

        # 다음 줄로 내려가는 세로 이동 (마지막 줄은 생략)
        if i < n_lines - 1:
            waypoints.append(ex, abs((cz + z_move) - 300))      # z좌표가 좌 상단이 0이 아니라 300이기 때문에 재 계산 후 웨이포인트에 추가

    return waypoints

def create_nodes_for_rightside(z, z_move, buffer_distance, waypoints):
    zones = [
        (270, 210),
        (240, 225),
        (210, 245),
        (120, 270),
        (0,   285),
    ]

    def max_safe_x_for(zpos):
        for thr, lx in zones:
            if zpos > thr + buffer_distance:
                return lx + buffer_distance
        # 마지막 구간(>0+buffer)과 동일
        return zones[-1][1] + buffer_distance

    right_x = 300 - buffer_distance
    z_pos = z
    waypoints.append(right_x, z_pos)

    while z_pos > buffer_distance:
        left_x = max_safe_x_for(z_pos)

        waypoints.append(left_x, z_pos)
        z_pos -= z_move
        waypoints.append(left_x, z_pos)
        waypoints.append(right_x, z_pos)
        z_pos -= z_move
        if z_pos > buffer_distance:
            waypoints.append(right_x, z_pos)

    return waypoints

create_nodes_for_leftside(5, z_move=10, buffer_distance=5, waypoints=waypoints)
create_nodes_for_rightside(295, z_move=10, buffer_distance=5, waypoints=waypoints)

print(waypoints.to_list())

### 시각화
river_cells_down_scaled = [
        (9, 5), (9, 6),
                (8, 6), (8, 7),
                (7, 6), (7, 7), (7, 8),
                (6, 6), (6, 7), (6, 8),
                        (5, 7), (5, 8),
                        (4, 7), (4, 8),
                        (3, 7), (3, 8), (3, 9),
                        (2, 7), (2, 8), (2, 9),
                        (1, 7), (1, 8), (1, 9),
                        (0, 7), (0, 8), (0, 9),
]

### 해당 좌표들을 그대로 300 * 300으로 바꿈.
river_cells = [
    (col * 30 + 30 / 2,
    row * 30 + 30 / 2)
    for row, col in river_cells_down_scaled
]

def visualize_waypoints(waypoints, river_cells=None, grid_size=30):
    fig, ax = plt.subplots(figsize=(6,6))
    ax.set_xlim(0, 300)
    ax.set_ylim(0, 300)
    ax.set_aspect('equal')

    # === 격자선 ===
    for i in range(0, 301, grid_size):
        ax.axhline(i, color='lightgray', linewidth=0.5)
        ax.axvline(i, color='lightgray', linewidth=0.5)

    # === 강 구역 ===
    if river_cells:
        for (x, z) in river_cells:
            rect = plt.Rectangle(
                (x - grid_size/2, z - grid_size/2),
                grid_size, grid_size,
                facecolor='red', alpha=0.4, edgecolor='black'
            )
            ax.add_patch(rect)

    # === 웨이포인트 ===
    wps = waypoints.to_list()
    if not wps:
        print("No waypoints to visualize.")
        return

    xs = [wp['x'] for wp in wps]
    zs = [wp['z'] for wp in wps]

    ax.plot(xs, zs, '-o', color='blue', markersize=4, linewidth=1.5)

    for i, (x, z) in enumerate(zip(xs, zs)):
        ax.text(x, z - 3, str(i), fontsize=7, color='black', ha='center')

    ax.set_title("Waypoint Path Visualization")
    plt.xlabel("X")
    plt.ylabel("Z")
    plt.tight_layout()
    plt.show()

visualize_waypoints(waypoints, river_cells=river_cells, grid_size=30)