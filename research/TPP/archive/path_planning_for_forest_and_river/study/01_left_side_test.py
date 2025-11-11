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

def create_nodes(z, z_move, buffer_distance, waypoints):
    """
    z0: 시작 z (위에서 아래로 진행)
    z_move: 줄 간격(세로 이동)
    buffer_distance: 좌/우 안전 버퍼 (좌측 시작 x로 사용)
    waypoints: WaypointList 인스턴스 (append(x, z))

    강 경계는 z-구간별 최대 안전 x로 단순화해 선택합니다.
    """
    # 1) z 상한 (버퍼만큼 아래 여유 두기)
    z_limit = 300 - buffer_distance
    if z >= z_limit:
        return waypoints

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
        waypoints.append(sx, cz)
        waypoints.append(ex, cz)

        # 다음 줄로 내려가는 세로 이동 (마지막 줄은 생략)
        if i < n_lines - 1:
            waypoints.append(ex, cz + z_move)

    return waypoints


create_nodes(300, z_move=10, buffer_distance=5, waypoints=waypoints)

print(waypoints.to_list())


### 시각화
river_cells_down_scaled = [
        (0, 5), (0, 6),
                (1, 6), (1, 7),
                (2, 6), (2, 7), (2, 8),
                (3, 6), (3, 7), (3, 8),
                        (4, 7), (4, 8),
                        (5, 7), (5, 8),
                        (6, 7), (6, 8), (6, 9),
                        (7, 7), (7, 8), (7, 9),
                        (8, 7), (8, 8), (8, 9),
                        (9, 7), (9, 8), (9, 9),
]

### 해당 좌표들을 그대로 300 * 300으로 바꿈.
river_cells = [
    (col * 30 + 30 / 2,
    row * 30 + 30 / 2)
    for row, col in river_cells_down_scaled
]

def visualize_waypoints(waypoints, river_cells=None, grid_size=30):
    """
    waypoints: WaypointList 객체
    river_cells: [(x, z), ...] 강 구역 좌표 (optional)
    grid_size: 격자 단위 (기본 30)
    """

    fig, ax = plt.subplots(figsize=(6,6))
    ax.set_xlim(0, 300)
    ax.set_ylim(0, 300)
    ax.set_aspect('equal')
    ax.invert_yaxis()  # 위쪽이 0이 되도록 (맵 좌표계 맞춤)

    # === 격자선 ===
    for i in range(0, 301, grid_size):
        ax.axhline(i, color='lightgray', linewidth=0.5)
        ax.axvline(i, color='lightgray', linewidth=0.5)

    # === 강 구역 표시 ===
    if river_cells:
        for (x, z) in river_cells:
            rect = plt.Rectangle(
                (x - grid_size/2, z - grid_size/2),
                grid_size, grid_size,
                facecolor='red', alpha=0.4, edgecolor='black'
            )
            ax.add_patch(rect)

    # === 웨이포인트 표시 ===
    wps = waypoints.to_list()
    if not wps:
        print("No waypoints to visualize.")
        return

    xs = [wp['x'] for wp in wps]
    zs = [wp['z'] for wp in wps]

    # 선 연결 (파란색 경로)
    ax.plot(xs, zs, '-o', color='blue', markersize=4, linewidth=1.5)

    # 순서 번호 (디버그용)
    for i, (x, z) in enumerate(zip(xs, zs)):
        ax.text(x, z - 3, str(i), fontsize=7, color='black', ha='center')

    ax.set_title("Waypoint Path Visualization")
    plt.xlabel("X")
    plt.ylabel("Z")
    plt.tight_layout()
    plt.show()
visualize_waypoints(waypoints, river_cells=river_cells)