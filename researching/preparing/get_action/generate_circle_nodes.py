"""
입력받은 좌표를 바탕으로 좌표 주위에 원형을 이루는 노드 좌표들을 생성.

credit by : oixxta

목적 : 주행 모듈과 결합해 맵 상의 obstacle 주위를 빙글빙글 돌며 데이터를 수집하는데 사용할 경로들을 생성하는데
필요한 노드들을 만들기 위함.

설명 : x, y, z 좌표, 생성할 노드의 갯수, 반지름 길이 이상 총 5개의 파라미터를 입력받고, 좌표를 중심으로
생성할 노드의 갯수만큼의 노드를 최대한 균등한 거리로 생성하는 함수.
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

    for i in range(num_nodes):
        angle = 2 * math.pi * i / num_nodes     # 원을 라디안 단위 각도로 노드 갯수 만큼 나눔
        px = x + radius * math.cos(angle)       # x좌표 생성
        pz = z + radius * math.sin(angle)       # z좌표 생성
        nodes.append((px, pz))                  # 생성한 x,z좌표를 리스트에 저장

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

plt.figure(figsize=(6, 6))
plt.scatter(x_vals, z_vals, color='blue', label='Nodes', s=50)
plt.scatter(100, 200, color='red', label='Center', s=80, marker='x')  # 중심점
plt.gca().set_aspect('equal', adjustable='box')
plt.title("Generated Circle Nodes")
plt.xlabel("X coordinate")
plt.ylabel("Z coordinate")
plt.legend()
plt.grid(True)
plt.show()

