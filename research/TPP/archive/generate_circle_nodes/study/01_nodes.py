"""
입력받은 좌표를 바탕으로 좌표 주위에 원형을 이루는 노드 좌표들을 생성.

credit by : oixxta

목적 : 주행 모듈과 결합해 맵 상의 obstacle 주위를 빙글빙글 돌며 데이터를 수집하는데 사용할 경로들을 생성하는데
필요한 노드들을 만들기 위함.

설명 : x, y, z 좌표, 생성할 노드의 갯수, 반지름 길이 이상 총 5개의 파라미터를 입력받고, 좌표를 중심으로
생성할 노드의 갯수만큼의 노드를 최대한 균등한 거리로 생성하는 함수.

또한, 코드로 생성된 좌표들을 시계방향 기준 오후 1시에 가까운 지점부터 차례대로 만들며, 
마지막에 다시 첫 번째 좌표로 돌아오게 함. (결과적으로, 만들고자 하는 노드의 갯수 + 1개의 좌표가 Linked-list에 주입됨.)

추가로, 해당 매서드로 생성된 좌표들을 WaypointList에 넣고 확인해 볼 수 있는 예시코드도 함께 동봉됨.

위의 class WaypointNode와 WaypointList는 techgyu가 제작한 웨이포인트 관리 단방향 Linked-list,
generate_circle_nodes 매서드가 개발물.
import math 필요함.
"""


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

# x, y, z 값을 입력받아 원형 노드 좌표를 생성하는 매서드.
import math                         # 필수
import matplotlib.pyplot as plt     # 시각화 테스트용, 실제 구동 시엔 필요없음

def generate_circle_nodes(x, y, z, num_nodes, radius):  #y는 좌표입력 혼동방지를 위한 더미데이터(top view 기준의 2차원 좌표이기에, y값은 안쓰임.)
    nodes = []                                  # 출력할 좌표들을 저장할 리스트

    # 노드들을 생성함.
    for i in range(num_nodes):
        angle = 2 * math.pi * i / num_nodes     # 원을 라디안 단위 각도로 노드 갯수 만큼 나눔
        px = x + radius * math.cos(angle)       # x좌표 생성
        pz = z + radius * math.sin(angle)       # z좌표 생성
        nodes.append((px, pz))                  # 생성한 x,z좌표를 리스트에 저장

    # 생성된 노드들의 중앙점과의 각도를 계산해봄.
    def calculate_angle(node):
        dx = node[0] - x
        dz = node[1] - z
        angle_degree = math.degrees(math.atan2(dz, dx))
        if angle_degree < 0:                # 음수 각도들을 양수화
            angle_degree = angle_degree + 360
        else:
            pass
        return angle_degree
    
    # 계산된 중심점-노드 각도들을 새 리스트에 저장
    angles = [calculate_angle(n) for n in nodes]

    # 생성된 노드들을 시계방향으로 정렬함(각도를 기준으로 리스트 안의 좌표들을 내림차순 순으로 정렬)
    nodes_with_angles = sorted(zip(nodes, angles), key=lambda t: -t[1])  #nodes 리스트와 angles 리스트를 합쳐서 튜플로 된 리스트를 만듬, 그리고 각도 기준 내림차순(시계방향) 정렬


    # 각 좌표들 중 시계뱡향 기준 한시(30°)와 가장 가까운 점을 첫 점으로 회전(rotate)
    def circ_dist(a, b):
        d = abs(a - b) % 360
        return min(d, 360 - d)

    start_idx = min(range(len(nodes_with_angles)),
                    key=lambda i: circ_dist(nodes_with_angles[i][1], 30))

    ordered_nodes = [na[0] for na in (nodes_with_angles[start_idx:] + nodes_with_angles[:start_idx])]
    nodes = ordered_nodes

    # 생성된 노드들이 담긴 리스트에 마지막으로 0번째 노드를 추가 (다시 원점으로 돌아오게 하기 위해)
    nodes.append(nodes[0])                      

    return nodes
    

nodes = generate_circle_nodes(100, 10, 200, num_nodes = 8, radius = 10) # x, y, z 좌표, 노드 갯수(짝수로 입력할것!), 반지름 넓이
#print(nodes)               # generate_circle_nodes로 생성된 노드 전체 출력
#print(len(nodes))          # generate_circle_nodes로 생성된 노드 갯수 출력
#print(nodes[0])            # generate_circle_nodes로 생성된 0번째 노드 확인


# generate_circle_nodes로 생성한 노드들을 waypoints에 넣는 예시코드
for i in range(len(nodes)):
    waypoints.append(nodes[i][0], nodes[i][1])      # 웨이포인트에 생성된 좌표들 주입

print(waypoints.to_list())                          # 웨이포인트에 generate_circle_nodes가 만든 좌표들이 정상적으로 주입되었는지 확인용



# 이하 시각화 (코드 테스트용, 실제 구동 시엔 필요 없음.)
x_vals = [n[0] for n in nodes]
z_vals = [n[1] for n in nodes]

plt.figure(figsize=(6,6))
plt.plot(x_vals, z_vals, 'o-', color='royalblue', label='Order Path')

# 점 번호 표시
for i, (px, pz) in enumerate(nodes[:-1]):       #마지막 노드는 0번째 노드와 같은 노드(순환)이기에 번호 부여 생략
    plt.text(px, pz, str(i), fontsize=9, ha='center', va='center', color='darkred')

# 중심점 표시
plt.scatter(100, 200, color='red', marker='x', s=100, label='Center')

plt.title("Waypoint Order")
plt.xlabel("X coordinate")
plt.ylabel("Z coordinate")
plt.legend()
plt.grid(True)
plt.gca().set_aspect('equal', adjustable='box')
plt.show()

