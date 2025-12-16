# IBSM(Integrated Battlefield Situation Management)
from flask import Flask, request, jsonify
import requests
from typing import Optional
import math
import time
import os
import glob
import cv2
import base64
import numpy as np
import threading
import mss
import win32gui
from datetime import datetime
from flask_socketio import SocketIO # frontend 연동용
from flask_cors import CORS # frontend 연동용
import json


# 현재 시간 기반 파일 이름 생성
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = f"{timestamp}_log.txt"

def write_log(message):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # 밀리초 3자리까지
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"{now} - {message}\n")

write_log("로그 파일 생성 완료")
# --------------------------------------------------------------------
global_enemy_id = 0
global_ally_id = 31
global_unknown_id = 50

# 시뮬레이터 시간 (초기값은 0.0, /info 엔드포인트에서 업데이트됨)
global_time = 0.0

global_fire_flag = False  # 사격 모드 최초 비활성화 default 값
global_replan_required = True  # TPP 재 계획 플래그, 최초 True로 설정하여, 첫 계획 수립을 유도
new_fire_point = None # 사격 불가 시
global_current_target = None # 현재 사격 목표

global_time, distance, player_x, player_y, player_z, player_speed, player_health, player_turret_x, player_turret_y = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
player_body_x, player_body_y, player_body_z, enemy_x, enemy_y, enemy_z, enemy_speed, enemy_health = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
enemy_turret_x, enemy_turret_y, enemy_body_x, enemy_body_y, enemy_body_z = 0.0, 0.0, 0.0, 0.0, 0.0

# 스레드 락 (동시 요청 처리 방지)
info_lock = threading.Lock()
vdrs_lock = threading.Lock()
scan_lock = threading.Lock()  # 터렛 스캔 방향 토글 시 동기화용 락
get_action_lock = threading.Lock()  # /get_action 동시 실행 방지용 락
vdrs_processing = False

global_mission_priority = 1  # 임무 우선순위 초기값
global_mission_number = 1  # 임무 번호 초기값

# ============================================================================
# 대기 / 방어 / 전투 로직용 전역 변수
# ============================================================================
enemy_in_range = False # 적 사정거리 이내 여부
defense_arrived = False # 방어 지점 도착 여부
scan_to_left = True # 좌측 방향 스캔 여부
# get_action first-call flag: ignore the very first incoming get_action
get_action_first_call = True
# 터렛 각도 기반 토글 허용 오차 (deg)
turret_angle_toggle_threshold = 1.0
# --------------------------------------------------------------------
# Hostile Object Info - Linked List
class EnemyNode:
    """적 객체 노드"""
    def __init__(self, enemy_id, pos_x, pos_y, pos_z, body_angle_x, body_angle_y, body_angle_z,
                 unit_type, identification_time, status="active", speed=0.0, threat_level=0.0):
        self.enemy_id = enemy_id  # 적 식별 번호
        self.pos_x = pos_x  # X 위치
        self.pos_y = pos_y  # Y 위치
        self.pos_z = pos_z  # Z 위치
        self.body_angle_x = body_angle_x  # 차체 X 각도
        self.body_angle_y = body_angle_y  # 차체 Y 각도
        self.body_angle_z = body_angle_z  # 차체 Z 각도
        self.unit_type = unit_type  # "infantry", "tank", "armored", etc.
        self.identification_time = identification_time  # 식별 시각
        self.status = status  # 상태: "destroyed", "active", "missing"
        self.speed = speed  # 속도 (m/s)
        self.threat_level = threat_level  # 적 위협도 (0.0 ~ 1.0)
        self.next: Optional['EnemyNode'] = None
    
    def update_position(self, x, y, z):
        """위치 업데이트"""
        self.pos_x = x
        self.pos_y = y
        self.pos_z = z
    
    def update_status(self, status):
        """상태 업데이트"""
        if status in ["destroyed", "active", "missing"]:
            self.status = status
    
    def update_speed(self, speed):
        """속도 업데이트"""
        self.speed = speed
    
    def to_dict(self):
        """JSON 형태로 변환"""
        return {
            "enemy_id": self.enemy_id,
            "position": {"x": self.pos_x, "y": self.pos_y, "z": self.pos_z},
            "body_angle": {"x": self.body_angle_x, "y": self.body_angle_y, "z": self.body_angle_z},
            "unit_type": self.unit_type,
            "identification_time": self.identification_time,
            "status": self.status,
            "speed": self.speed,
            "threat_level": self.threat_level
        }

class EnemyList:
    """적 객체 Linked List 관리"""
    def __init__(self):
        self.head: Optional[EnemyNode] = None
        self.count = 0
        self.position_threshold = 15.0  # 15m 이내면 같은 객체로 판단 (VDRS 측정 오차 고려)
    
    def find_enemy_by_position(self, pos_x, pos_y, pos_z, unit_type):
        """위치 및 유닛 타입 기반으로 적 검색 (거리 임계값 이내)"""
        current = self.head
        while current:
            distance = math.sqrt(
                (current.pos_x - pos_x)**2 + 
                (current.pos_y - pos_y)**2 + 
                (current.pos_z - pos_z)**2
            )
            write_log(f"  🔍 비교 중 - ID:{current.enemy_id}, 거리:{distance:.2f}m, 타입비교:'{current.unit_type}'=='{unit_type}' -> {current.unit_type == unit_type}")
            if distance <= self.position_threshold and current.unit_type == unit_type:
                write_log(f"기존 적 발견! ID:{current.enemy_id}")
                return current
            current = current.next
        write_log(f"일치하는 적 없음")
        return None
    
    def find_enemy(self, enemy_id):
        """적 ID로 검색"""
        current = self.head
        while current:
            if current.enemy_id == enemy_id:
                return current
            current = current.next
        return None
    
    def get_all_enemies(self):
        """모든 적 정보 반환"""
        enemies = []
        current = self.head
        while current:
            enemies.append(current.to_dict())
            current = current.next
        return enemies
    
    def clear(self):
        """모든 적 제거"""
        self.head = None
        self.count = 0
    
    def write_log_all(self):
        """모든 적 정보 출력 (디버깅용)"""
        current = self.head
        index = 1
        while current:
            write_log(f"[{index}] Enemy ID: {current.enemy_id}, Type: {current.unit_type}, Status: {current.status}, Threat: {current.threat_level}")
            current = current.next
            index += 1

    def add_or_update_enemy(self, enemy_id, pos_x, pos_y, pos_z, body_angle_x, body_angle_y, body_angle_z,
                           unit_type, identification_time, speed=0.0, threat_level=0.0, ):
        """적 업데이트 또는 신규 추가
        - enemy_id가 주어지면: 해당 ID의 적을 찾아서 업데이트, 없으면 그 ID로 신규 생성
        - enemy_id가 None이면: 위치 기반으로 검색 후 업데이트 또는 신규 추가 (자동 ID 부여)
        """
        global global_enemy_id, global_replan_required
        
        # Case 1: ID가 주어진 경우 - 해당 ID의 적 찾아서 업데이트 또는 그 ID로 신규 생성
        if enemy_id is not None:
            existing_enemy = self.find_enemy(enemy_id)
            if existing_enemy:
                write_log("ID 기반 기존 적 정보 업데이트 중...")
                # 기존 적 찾았으면 위치와 정보 업데이트
                existing_enemy.pos_x = pos_x 
                existing_enemy.pos_y = pos_y
                existing_enemy.pos_z = pos_z
                existing_enemy.body_angle_z = body_angle_z
                existing_enemy.unit_type = unit_type
                existing_enemy.identification_time = identification_time
                existing_enemy.update_speed(speed)
                write_log(f"🔄 적 정보 업데이트! ID: {enemy_id}, 위치: ({pos_x:.1f}, {pos_y:.1f}, {pos_z:.1f})")
                return existing_enemy
            else:
                # ID로 못 찾았으면 해당 ID로 신규 생성
                write_log("ID 기반 신규 적 정보 업데이트 중...")
                write_log(f"📝 ID {enemy_id}로 신규 적 생성 중...")
                new_enemy = EnemyNode(
                    enemy_id, pos_x, pos_y, pos_z, 
                    body_angle_x, body_angle_y, body_angle_z,  # 순서 수정!
                    unit_type, identification_time, 
                    "active",  # status
                    speed,  # speed
                    threat_level  # threat_level
                )

                global_replan_required = True  # 적이 새로 추가되었으므로 TPP 재계획 필요

                # Frontend 전송
                """
                Frontend로 전송되는 형식:
                {
                    "type": "detection_update",
                    "object": { tracking_id, class_id, x, y, alive }
                }
                """
                if unit_type == "armored":
                    class_id = 5
                elif unit_type == "infantry":
                    class_id = 12

                request_data ={
                    "tracking_id": enemy_id,
                    "class_id": class_id,
                    "x": pos_x,
                    "y": pos_z, # z 축을 y로 매핑
                    "alive": True
                }
                send_detection(request_data)


                if not self.head:
                    self.head = new_enemy
                else:
                    current = self.head
                    while current.next:
                        current = current.next
                    current.next = new_enemy
                
                self.count += 1
                # global_enemy_id는 증가시키지 않음 (지정된 ID 사용)
                write_log(f"새로운 적 생성! ID: {enemy_id}, 위치: ({pos_x:.1f}, {pos_y:.1f}, {pos_z:.1f})")
                return new_enemy
        
        # Case 2: ID가 None인 경우 - 위치 및 유닛 타입 기반으로 검색
        nearby_enemy = self.find_enemy_by_position(pos_x, pos_y, pos_z, unit_type=unit_type)

        if nearby_enemy:
            write_log("기존 적 정보 업데이트 중...")
            # 기존 적이 있으면 정보만 업데이트 (위치와 unit_type은 이미 일치하므로 제외)
            nearby_enemy.identification_time = identification_time
            return nearby_enemy
        
        # Case 3: 완전히 새로운 적 발견 - 자동으로 ID 부여
        write_log("신규 적 정보 업데이트 중...")
        write_log(f"📝 ID {global_enemy_id}로 신규 적 {pos_x}, {pos_y}, {pos_z} 에생성 중...")
        new_enemy = EnemyNode(
            global_enemy_id, 
            pos_x, 
            pos_y, 
            pos_z, 
            body_angle_x, 
            body_angle_y, 
            body_angle_z,  # 순서 수정!
            unit_type, 
            identification_time,
            "active",  # status
            speed,  # speed
            threat_level  # threat_level
        )

        global_replan_required = True  # 적이 새로 추가되었으므로 TPP 재계획 필요

        
        # Frontend 전송
        if unit_type == "armored":
            class_id = 5
        elif unit_type == "infantry":
            class_id = 12

        request_data ={
            "tracking_id": global_enemy_id,
            "class_id": class_id,
            "x": pos_x,
            "y": pos_z, # z 축을 y로 매핑
            "alive": True
        }
        send_detection(request_data)

        if not self.head:
            self.head = new_enemy
        else:
            current = self.head
            while current.next:
                current = current.next
            current.next = new_enemy
        
        self.count += 1
        global_enemy_id += 1  # 새로운 적 발견 시 ID 증가
        write_log(f"🆕 새로운 적 발견! ID: {new_enemy.enemy_id}, 위치: ({pos_x:.1f}, {pos_y:.1f}, {pos_z:.1f})")
        return new_enemy

# Enemy List 전역 인스턴스
enemy_list = EnemyList()

# --------------------------------------------------------------------
# Ally Object Info - Linked List
class AllyNode:
    """아군 객체 노드"""
    def __init__(self, ally_id, pos_x, pos_y, pos_z, body_angle_x, body_angle_y, body_angle_z,
                 turret_angle_x, turret_angle_y, unit_type, identification_time, speed,
                 mission_number=None, combat_status="normal"):
        self.ally_id = ally_id  # 아군 식별 번호
        self.pos_x = pos_x  # X 위치
        self.pos_y = pos_y  # Y 위치
        self.pos_z = pos_z  # Z 위치
        self.body_angle_x = body_angle_x  # 차체 X 각도
        self.body_angle_y = body_angle_y  # 차체 Y 각도
        self.body_angle_z = body_angle_z  # 차체 Z 각도
        self.turret_angle_x = turret_angle_x  # 포탑 X 각도
        self.turret_angle_y = turret_angle_y  # 포탑 Y 각도
        self.unit_type = unit_type  # "infantry", "tank", etc.
        self.identification_time = identification_time  # 식별 시각
        self.status = "active"  # 상태: "destroyed", "active", "missing"
        self.speed = speed  # 속도 (m/s)
        self.mission_number = mission_number  # 임무 번호
        self.combat_status = combat_status  # 전투 상태
        self.next: Optional['AllyNode'] = None
    
    def update_position(self, x, y, z):
        """위치 업데이트"""
        self.pos_x = x
        self.pos_y = y
        self.pos_z = z
    
    def update_status(self, status):
        """상태 업데이트"""
        if status in ["destroyed", "active", "missing"]:
            self.status = status
    
    def update_speed(self, speed):
        """속도 업데이트"""
        self.speed = speed
    
    def to_dict(self):
        """JSON 형태로 변환"""
        return {
            "ally_id": self.ally_id,
            "position": {"x": self.pos_x, "y": self.pos_y, "z": self.pos_z},
            "body_angle": {"x": self.body_angle_x, "y": self.body_angle_y, "z": self.body_angle_z},
            "turret_angle": {"x": self.turret_angle_x, "y": self.turret_angle_y},
            "unit_type": self.unit_type,
            "identification_time": self.identification_time,
            "status": self.status,
            "speed": self.speed,
            "mission_number": self.mission_number,
            "combat_status": self.combat_status
        }

class AllyList:
    """아군 객체 Linked List 관리"""
    def __init__(self):
        self.head: Optional[AllyNode] = None
        self.count = 0
        self.position_threshold = 5.0  # 5m 이내면 같은 객체로 판단
    
    def find_ally_by_position(self, pos_x, pos_y, pos_z, unit_type=None, threshold=None):
        """위치 및 유닛 타입 기반으로 아군 검색 (거리 임계값 이내)"""
        if threshold is None:
            threshold = self.position_threshold
        
        current = self.head
        while current:
            distance = math.sqrt(
                (current.pos_x - pos_x)**2 + 
                (current.pos_y - pos_y)**2 + 
                (current.pos_z - pos_z)**2
            )
            if distance <= threshold:
                if unit_type is None or current.unit_type == unit_type:
                    return current
            current = current.next
        return None
    
    def find_ally(self, ally_id):
        """아군 ID로 검색"""
        current = self.head
        while current:
            if current.ally_id == ally_id:
                return current
            current = current.next
        return None
    
    def get_all_allies(self):
        """모든 아군 정보 반환"""
        allies = []
        current = self.head
        while current:
            allies.append(current.to_dict())
            current = current.next
        return allies
    
    def get_active_allies(self):
        """활성 상태의 아군만 반환"""
        allies = []
        current = self.head
        while current:
            if current.status == "active":
                allies.append(current.to_dict())
            current = current.next
        return allies
    
    def clear(self):
        """모든 아군 제거"""
        self.head = None
        self.count = 0
    
    def write_log_all(self):
        """모든 아군 정보 출력 (디버깅용)"""
        current = self.head
        index = 1
        while current:
            write_log(f"[{index}] Ally ID: {current.ally_id}, Type: {current.unit_type}, Status: {current.status}")
            current = current.next
            index += 1
    
    def add_or_update_ally(self, pos_x, pos_y, pos_z, unit_type, identification_time, speed,
                          body_angle_x, body_angle_y, body_angle_z, turret_angle_x, turret_angle_y, 
                          ally_id=None, mission_number=0, combat_status="normal"):
        """아군 업데이트 또는 신규 추가 - 모든 정보 포함
        - ally_id가 주어지면: 해당 ID의 아군을 찾아서 업데이트, 없으면 그 ID로 신규 생성
        - ally_id가 None이면: 위치 기반으로 검색 후 업데이트 또는 신규 추가 (자동 ID 부여)
        """
        global global_ally_id
        
        # Case 1: ID가 주어진 경우
        if ally_id is not None:
            existing_ally = self.find_ally(ally_id)
            if existing_ally:
                write_log("ID 기반 기존 아군 정보 업데이트 중...")
                # 기존 아군 찾았으면 모든 정보 업데이트
                existing_ally.update_position(pos_x, pos_y, pos_z)
                existing_ally.body_angle_x = body_angle_x
                existing_ally.body_angle_y = body_angle_y
                existing_ally.body_angle_z = body_angle_z
                existing_ally.unit_type = unit_type
                existing_ally.identification_time = identification_time
                existing_ally.update_speed(speed)
                existing_ally.turret_angle_x = turret_angle_x
                existing_ally.turret_angle_y = turret_angle_y
                existing_ally.mission_number = mission_number
                existing_ally.combat_status = combat_status
                
                # Frontend 전송
                """
                IBSM이 내 탱크 위치 데이터 전송 시
                
                IBSM에서 보내야 하는 형식:
                {
                    "tanks": [
                        {
                            "tank_id": "17TK-101",
                            "x": -50.0,
                            "y": -100.0
                        }
                    ]
                }
                
                Frontend로 전송되는 형식:
                {
                    "type": "position_update",
                    "tanks": [{ tank_id, x, y }, ...]
                }
                """
                request_data = [
                    {
                        "tank_id": ally_id,
                        "x": pos_x,
                        "y": pos_z
                    }
                ]
                send_ally_position(request_data)

                return existing_ally
            else:
                # ID로 못 찾았으면 해당 ID로 신규 생성
                write_log("ID 기반 신규 아군 생성 중...")
                new_ally = AllyNode(
                    ally_id, pos_x, pos_y, pos_z, 
                    body_angle_x, body_angle_y, body_angle_z,
                    turret_angle_x, turret_angle_y,
                    unit_type, identification_time, speed,
                    mission_number, combat_status
                )
                
                if not self.head:
                    self.head = new_ally
                else:
                    current = self.head
                    while current.next:
                        current = current.next
                    current.next = new_ally

                
                # Frontend 전송
                """
                IBSM이 내 탱크 위치 데이터 전송 시
                
                IBSM에서 보내야 하는 형식:
                {
                    "tanks": [
                        {
                            "tank_id": "17TK-101",
                            "x": -50.0,
                            "y": -100.0
                        }
                    ]
                }
                
                Frontend로 전송되는 형식:
                {
                    "type": "position_update",
                    "tanks": [{ tank_id, x, y }, ...]
                }
                """
                request_data = [
                    {
                        "tank_id": ally_id,
                        "x": pos_x,
                        "y": pos_z
                    }
                ]
                send_ally_position(request_data)
                
                self.count += 1
                write_log(f"🆕 새로운 아군 생성! ID: {ally_id}, 위치: ({pos_x:.1f}, {pos_y:.1f}, {pos_z:.1f})")
                return new_ally
        
        # Case 2: ID가 None인 경우 - 위치 및 유닛 타입 기반으로 검색
        nearby_ally = self.find_ally_by_position(pos_x, pos_y, pos_z, unit_type=unit_type)
        
        if nearby_ally:
            # 기존 아군이 있으면 정보만 업데이트
            write_log("기존 아군 정보 업데이트 중...")
            nearby_ally.pos_x
            nearby_ally.pos_y
            nearby_ally.pos_z
            nearby_ally.body_angle_x
            nearby_ally.body_angle_y
            nearby_ally.body_angle_z
            nearby_ally.identification_time = identification_time
            nearby_ally.update_speed(speed)
            nearby_ally.turret_angle_x = turret_angle_x
            nearby_ally.turret_angle_y = turret_angle_y
            nearby_ally.mission_number = mission_number
            nearby_ally.combat_status = combat_status
            return nearby_ally
        
        # Case 3: 완전히 새로운 아군 발견 - 자동으로 ID 부여
        write_log("신규 아군 정보 업데이트 중...")
        new_ally = AllyNode(
            global_ally_id, pos_x, pos_y, pos_z,
            body_angle_x, body_angle_y, body_angle_z,
            turret_angle_x, turret_angle_y,
            unit_type, identification_time, speed,
            mission_number, combat_status
        )



        # Frontend 전송
        """
        IBSM이 내 탱크 위치 데이터 전송 시
        
        IBSM에서 보내야 하는 형식:
        {
            "tanks": [
                {
                    "tank_id": "17TK-101",
                    "x": -50.0,
                    "y": -100.0
                }
            ]
        }
        
        Frontend로 전송되는 형식:
        {
            "type": "position_update",
            "tanks": [{ tank_id, x, y }, ...]
        }
        """
        request_data = [
            {
                "tank_id": global_ally_id,
                "x": pos_x,
                "y": pos_z
            }
        ]
        send_ally_position(request_data)

        
        if not self.head:
            self.head = new_ally
        else:
            current = self.head
            while current.next:
                current = current.next
            current.next = new_ally
        
        self.count += 1
        global_ally_id += 1
        write_log(f"🆕 새로운 아군 발견! ID: {new_ally.ally_id}, 위치: ({pos_x:.1f}, {pos_y:.1f}, {pos_z:.1f})")
        return new_ally
    
    def get_ally_position(self, ally_id):
        """아군 ID로 위치 정보 반환 (x, y, z 튜플)"""
        ally = self.find_ally(ally_id)
        if ally:
            return ally.pos_x, ally.pos_y, ally.pos_z
        return None, None, None
    
    def remove_ally(self, ally_id):
        """아군 제거"""
        if not self.head:
            return False
        
        if self.head.ally_id == ally_id:
            self.head = self.head.next  # type: ignore
            self.count -= 1
            return True
        
        current = self.head
        while current.next:
            next_node = current.next
            if hasattr(next_node, 'ally_id') and next_node.ally_id == ally_id:
                current.next = next_node.next
                self.count -= 1
                return True
            current = next_node
        
        return False

# Ally List 전역 인스턴스
ally_list = AllyList()

# --------------------------------------------------------------------
# Unknown Object Info - Linked List
class UnknownNode:
    """미식별 객체 노드 (장애물, 민간인 등)"""
    def __init__(self, unknown_id, pos_x, pos_y, pos_z, object_angle_x, object_angle_y,
                 unit_type, identification_time, status="active", speed=0.0):
        self.unknown_id = unknown_id  # 미식별 객체 식별 번호
        self.pos_x = pos_x  # X 위치
        self.pos_y = pos_y  # Y 위치
        self.pos_z = pos_z  # Z 위치
        self.object_angle_x = object_angle_x  # 객체 수평 각도
        self.object_angle_y = object_angle_y  # 객체 수직 각도
        self.unit_type = unit_type  # "obstacle", "civilian", "vehicle", "building", etc.
        self.identification_time = identification_time  # 식별 시각
        self.status = status  # 상태: "active", "inactive", "removed"
        self.speed = speed  # 속도 (m/s) - 이동 가능한 객체의 경우
        self.next: Optional['UnknownNode'] = None
    
    def update_position(self, x, y, z):
        """위치 업데이트"""
        self.pos_x = x
        self.pos_y = y
        self.pos_z = z
    
    def update_status(self, status):
        """상태 업데이트"""
        if status in ["active", "inactive", "removed"]:
            self.status = status
    
    def update_speed(self, speed):
        """속도 업데이트"""
        self.speed = speed
    
    def to_dict(self):
        """JSON 형태로 변환"""
        return {
            "unknown_id": self.unknown_id,
            "position": {"x": self.pos_x, "y": self.pos_y, "z": self.pos_z},
            "object_angle": {"x": self.object_angle_x, "y": self.object_angle_y},
            "unit_type": self.unit_type,
            "identification_time": self.identification_time,
            "status": self.status,
            "speed": self.speed
        }

class UnknownList:
    """미식별 객체 Linked List 관리"""
    def __init__(self):
        self.head: Optional[UnknownNode] = None
        self.count = 0
        self.position_threshold = 5.0  # 5m 이내면 같은 객체로 판단
    
    def find_unknown_by_position(self, pos_x, pos_y, pos_z, unit_type):
        """위치 및 유닛 타입 기반으로 미식별 객체 검색 (거리 임계값 이내)"""
        current = self.head
        while current:
            distance = math.sqrt(
                (current.pos_x - pos_x)**2 + 
                (current.pos_y - pos_y)**2 + 
                (current.pos_z - pos_z)**2
            )
            if distance <= self.position_threshold and current.unit_type == unit_type:
                return current
            current = current.next
        return None
    
    def find_unknown(self, unknown_id):
        """미식별 객체 ID로 검색"""
        current = self.head
        while current:
            if current.unknown_id == unknown_id:
                return current
            current = current.next
        return None
    
    def get_all_unknowns(self):
        """모든 미식별 객체 정보 반환"""
        unknowns = []
        current = self.head
        while current:
            unknowns.append(current.to_dict())
            current = current.next
        return unknowns
    
    def clear(self):
        """모든 미식별 객체 제거"""
        self.head = None
        self.count = 0
    
    def write_log_all(self):
        """모든 미식별 객체 정보 출력 (디버깅용)"""
        current = self.head
        index = 1
        while current:
            write_log(f"[{index}] Unknown ID: {current.unknown_id}, Type: {current.unit_type}, Status: {current.status}")
            current = current.next
            index += 1
    
    def add_or_update_unknown(self, unknown_id, pos_x, pos_y, pos_z, object_angle_x, object_angle_y,
                             unit_type, identification_time, speed=0.0):
        """미식별 객체 업데이트 또는 신규 추가
        - unknown_id가 주어지면: 해당 ID의 객체를 찾아서 업데이트, 없으면 그 ID로 신규 생성
        - unknown_id가 None이면: 위치 기반으로 검색 후 업데이트 또는 신규 추가 (자동 ID 부여)
        """
        global global_unknown_id
        global global_replan_required

        enemy= enemy_list.find_enemy_by_position(pos_x, pos_y, pos_z, unit_type="armored")
        if enemy:
            print("적 객체와 겹침, 미식별 객체로 추가하지 않음")
            return None  # 적 객체와 겹치면 미식별 객체로 추가하지 않음
        
        # Case 1: ID가 주어진 경우
        if unknown_id is not None:
            existing_unknown = self.find_unknown(unknown_id)
            if existing_unknown:
                # 기존 객체 찾았으면 위치와 정보 업데이트
                existing_unknown.update_position(pos_x, pos_y, pos_z)
                existing_unknown.object_angle_x = object_angle_x
                existing_unknown.object_angle_y = object_angle_y
                existing_unknown.unit_type = unit_type
                existing_unknown.identification_time = identification_time
                existing_unknown.update_speed(speed)
                write_log(f"기존 식별 객체 정보 업데이트 ID: {unknown_id}, 위치: ({pos_x:.1f}, {pos_y:.1f}, {pos_z:.1f})")
                return existing_unknown
            else:
                # ID로 못 찾았으면 해당 ID로 신규 생성
                new_unknown = UnknownNode(
                    unknown_id, pos_x, pos_y, pos_z, 
                    object_angle_x, object_angle_y,
                    unit_type, identification_time,
                    "active", speed
                )
                
                if not self.head:
                    self.head = new_unknown
                else:
                    current = self.head
                    while current.next:
                        current = current.next
                    current.next = new_unknown
                global_replan_required = True  # 새로운 미식별 객체 발견 시 재계획 필요

                self.count += 1
                write_log(f"🆕 ID 기반 신규 객체 생성 ID: {unknown_id}, 위치: ({pos_x:.1f}, {pos_y:.1f}, {pos_z:.1f})")
                return new_unknown
        
        # Case 2: ID가 None인 경우 - 위치 및 유닛 타입 기반으로 검색
        nearby_unknown = self.find_unknown_by_position(pos_x, pos_y, pos_z, unit_type=unit_type)

        if nearby_unknown:
            write_log("기존 미식별 객체 정보(시간) 업데이트 중...")
            # 기존 객체가 있으면 정보만 업데이트
            nearby_unknown.identification_time = identification_time
            nearby_unknown.update_speed(speed)
            return nearby_unknown
        
        # Case 3: 완전히 새로운 객체 발견 - 자동으로 ID 부여
        new_unknown = UnknownNode(
            global_unknown_id, pos_x, pos_y, pos_z,
            object_angle_x, object_angle_y,
            unit_type, identification_time,
            "active", speed
        )
        global_replan_required = True  # 새로운 미식별 객체 발견 시 재계획 필요

        # Frontend 전송
        """
        Frontend로 전송되는 형식:
        {
            "type": "detection_update",
            "object": { tracking_id, class_id, x, y, alive }
        }
        """
        request_data ={
            "tracking_id": global_unknown_id,
            "class_id": 0,
            "x": pos_x,
            "y": pos_z, # z 축을 y로 매핑
            "alive": True
        }
        send_detection(request_data)

        if not self.head:
            self.head = new_unknown
        else:
            current = self.head
            while current.next:
                current = current.next
            current.next = new_unknown
        
        self.count += 1
        global_unknown_id += 1
        write_log(f"신규 객체 추가 | ID: {new_unknown.unknown_id}, 위치: ({pos_x:.1f}, {pos_y:.1f}, {pos_z:.1f})")
        return new_unknown
    
    def remove_unknown(self, unknown_id):
        """미식별 객체 제거"""
        if not self.head:
            return False
        
        if self.head.unknown_id == unknown_id:
            self.head = self.head.next  # type: ignore
            self.count -= 1
            return True
        
        current = self.head
        while current.next:
            next_node = current.next
            if hasattr(next_node, 'unknown_id') and next_node.unknown_id == unknown_id:
                current.next = next_node.next
                self.count -= 1
                return True
            current = next_node
        
        return False

# Unknown List 전역 인스턴스
unknown_list = UnknownList()

# --------------------------------------------------------------------
# Mission Management - Linked List
class MissionNode:
    """임무 노드"""
    def __init__(self, mission_number, time, mission_type, mission_priority, status="pending", 
                 target_pos=None, enemy_pos=None, additional_info=None):
        self.mission_number = mission_number  # 임무 번호
        self.time = time  # 생성 시각
        self.mission_type = mission_type  # 임무 종류: "combat", "defense"
        self.mission_priority = mission_priority  # 우선 순위 점수
        self.status = status  # 임무 상태: "pending", "in-progress", "completed", "failed", "cancelled"
        self.target_pos = target_pos  # 목표 위치 {"x": float, "y": float, "z": float}
        self.enemy_pos = enemy_pos # 적 위치 {"x": float, "y": float, "z": float}
        self.additional_info = additional_info  # 추가 정보 (dict)
        self.next: Optional['MissionNode'] = None

class MissionList:
    """임무 Linked List 관리"""
    def __init__(self):
        self.head: Optional[MissionNode] = None
        self.count = 0
    
    def add_mission(self, mission_number, time, mission_type, mission_priority, 
                   status="pending", target_pos=None, enemy_pos=None, target_enemy_id=None, additional_info=None):
        """임무 추가 (우선순위 기반 정렬)"""
        new_mission = MissionNode(
            mission_number, time, mission_type, mission_priority, 
            status, target_pos, enemy_pos, additional_info
        )
        
        # 리스트가 비어있으면 head로 설정
        if not self.head:
            self.head = new_mission
            self.count += 1
            write_log(f"✅ 임무 추가: #{mission_number} [{mission_type}] 우선순위:{mission_priority}")
            return new_mission
        
        # 우선순위가 높으면 head 앞에 삽입 (숫자가 작을수록 높은 우선순위)
        if mission_priority < self.head.mission_priority:
            new_mission.next = self.head
            self.head = new_mission
            self.count += 1
            write_log(f"✅ 임무 추가 (최우선): #{mission_number} [{mission_type}] 우선순위:{mission_priority}")
            return new_mission
        
        # 적절한 위치에 삽입 (우선순위 순서 유지)
        current = self.head
        while current.next:
            if mission_priority < current.next.mission_priority:
                new_mission.next = current.next
                current.next = new_mission
                self.count += 1
                write_log(f"✅ 임무 추가: #{mission_number} [{mission_type}] 우선순위:{mission_priority}")
                return new_mission
            current = current.next
        
        # 끝에 추가
        current.next = new_mission
        self.count += 1
        write_log(f"✅ 임무 추가 (마지막): #{mission_number} [{mission_type}] 우선순위:{mission_priority}")
        return new_mission
    
    def find_mission(self, mission_number):
        """임무 번호로 검색"""
        current = self.head
        while current:
            if current.mission_number == mission_number:
                return current
            current = current.next
        return None
    
    def update_mission_status(self, mission_number, new_status):
        """임무 상태 업데이트"""
        mission = self.find_mission(mission_number)
        if mission:
            old_status = mission.status
            mission.status = new_status
            write_log(f"[임무 상태 변경] 임무 #{mission_number}: {old_status} → {new_status}")
            return True
        return False
    
    def get_current_mission(self):
        """현재 진행 중인 임무 가져오기 (in-progress 상태)"""
        current = self.head
        while current:
            if current.status == "in-progress":

                # frontend 송신
                """
                IBSM이 미션 데이터 전송 시
                
                IBSM에서 보내야 하는 형식:
                {
                    "mission_update": "",
                    "x": float,
                    "y": float
                }
                
                Frontend로 전송되는 형식:
                {
                    "type": "mission_update",
                    "mission": [{ "type": current.mission_type, "position": { "x": current.target_pos["x"], "y": current.target_pos["y"], "z": current.target_pos["z"] } }]
                }
                """
                if current.mission_type == "defense":
                    request_data = {
                        "type": current.mission_type,
                        "x": current.target_pos["x"],
                        "y": current.target_pos["z"],
                    }
                elif current.mission_type == "combat":
                    request_data = {
                        "type": current.mission_type,
                        "x": current.enemy_pos["x"],
                        "y": current.enemy_pos["z"],
                    }
                send_mission(request_data)

                return current
            current = current.next
        return None
    
    def get_next_mission(self):
        """다음 실행할 임무 가져오기 (pending 상태 중 최우선)"""
        current = self.head
        while current:
            if current.status == "pending":
                return current
            current = current.next
        return None
    
    def get_highest_priority_mission(self, exclude_status=None):
        """
        가장 우선순위가 높은 임무 가져오기
        
        Args:
            exclude_status: 제외할 상태 리스트 (예: ["completed", "cancelled", "failed"])
        
        Returns:
            MissionNode: 가장 우선순위 높은 임무 (숫자가 작을수록 높음)
            None: 임무가 없을 경우
        """
        if exclude_status is None:
            exclude_status = []
        
        highest_priority_mission = None
        highest_priority_value = float('inf')  # 무한대로 초기화
        
        current = self.head
        while current:
            # 제외 상태가 아니고, 더 높은 우선순위인 경우
            if current.status not in exclude_status:
                if current.mission_priority < highest_priority_value:
                    highest_priority_value = current.mission_priority
                    highest_priority_mission = current
            current = current.next
        
        if highest_priority_mission:
            write_log(f"📌 최우선 임무: #{highest_priority_mission.mission_number} "
                     f"[{highest_priority_mission.mission_type}] "
                     f"우선순위:{highest_priority_mission.mission_priority} "
                     f"상태:{highest_priority_mission.status}")
        
        return highest_priority_mission
    
    def get_pending_highest_priority_mission(self):
        """
        대기 중인 임무 중 가장 우선순위가 높은 임무 가져오기
        (pending 상태만)
        
        Returns:
            MissionNode: 가장 우선순위 높은 대기 임무
        """
        highest_priority_mission = None
        highest_priority_value = float('-inf')
        
        current = self.head
        while current:
            if current.status == "pending":
                if current.mission_priority > highest_priority_value:
                    highest_priority_value = current.mission_priority
                    highest_priority_mission = current
            current = current.next
        
        return highest_priority_mission
    
    def get_all_missions(self):
        """모든 임무 반환"""
        missions = []
        current = self.head
        while current:
            missions.append(current.to_dict())
            current = current.next
        return missions
    
    def get_missions_by_status(self, status):
        """특정 상태의 임무들 반환"""
        missions = []
        current = self.head
        while current:
            if current.status == status:
                missions.append(current.to_dict())
            current = current.next
        return missions
    
    def remove_mission(self, mission_number):
        """임무 제거"""
        if not self.head:
            return False
        
        # head가 제거 대상인 경우
        if self.head.mission_number == mission_number:
            self.head = self.head.next
            self.count -= 1
            write_log(f"🗑️ 임무 #{mission_number} 제거")
            return True
        
        # 중간/끝 노드 제거
        current = self.head
        while current.next:
            if current.next.mission_number == mission_number:
                current.next = current.next.next
                self.count -= 1
                write_log(f"🗑️ 임무 #{mission_number} 제거")
                return True
            current = current.next
        
        return False
    
    def cancel_mission(self, mission_number):
        """임무 취소 (상태만 변경)"""
        return self.update_mission_status(mission_number, "cancelled")
    
    def complete_mission(self, mission_number):
        """임무 완료 처리"""
        return self.update_mission_status(mission_number, "completed")
    
    def start_mission(self, mission_number):
        """임무 시작 (pending → in-progress)"""
        mission = self.find_mission(mission_number)
        if mission and mission.status == "pending":
            # 기존 in-progress 임무는 pending으로 되돌림
            current_mission = self.get_current_mission()
            if current_mission:
                current_mission.status = "pending"
                write_log(f"⏸️ 임무 #{current_mission.mission_number} 일시 중지")
            
            # 새 임무 시작
            mission.status = "in-progress"
            write_log(f"▶️ 임무 #{mission_number} 시작: [{mission.mission_type}]")
            return True
        return False
    
    def clear(self):
        """모든 임무 제거"""
        self.head = None
        self.count = 0
        write_log("🗑️ 모든 임무 제거")
    
    def write_log_all(self):
        """모든 임무 정보 출력 (디버깅용)"""
        current = self.head
        index = 1
        write_log("=" * 50)
        write_log(f"임무 목록 ({self.count}개)")
        write_log("=" * 50)
        while current:
            write_log(f"[{index}] 임무 #{current.mission_number}")
            write_log(f"    종류: {current.mission_type}")
            write_log(f"    우선순위: {current.mission_priority}")
            write_log(f"    상태: {current.status}")
            write_log(f"    생성 시각: {current.time:.2f}s")
            if current.target_pos:
                write_log(f"    목표 위치: ({current.target_pos['x']:.1f}, {current.target_pos['y']:.1f}, {current.target_pos['z']:.1f})")
            if current.target_enemy_id is not None:
                write_log(f"    목표 적 ID: {current.target_enemy_id}")
            current = current.next
            index += 1
        write_log("=" * 50)

# Mission List 전역 인스턴스
mission_list = MissionList()

# --------------------------------------------------------------------


# --------------------------------------------------------------------
# Helper functions for image processing

def get_latest_image(directory):
    write_log("get_latest_image() 호출 받음")
    """디렉토리에서 가장 최신 이미지 파일 경로 반환"""
    images = glob.glob(os.path.join(directory, "*.*"))
    if images:
        latest_image = max(images, key=os.path.getmtime)
        return latest_image
    else:
        write_log(f"{directory}에서 이미지를 찾을 수 없습니다.")
        return None

def encode_image_to_base64(image_path):
    write_log("encode_image_to_base64() 호출 받음")
    """이미지 파일을 읽어서 base64로 인코딩"""
    if image_path is None:
        return None
    
    try:
        image = cv2.imread(image_path)
        if image is None:
            write_log(f"이미지 로드 실패: {image_path}")
            return None
        
        # numpy array를 base64로 인코딩
        _, buffer = cv2.imencode('.jpg', image)
        image_b64 = base64.b64encode(buffer.tobytes()).decode('utf-8')
        return image_b64
    except Exception as e:
        write_log(f"이미지 인코딩 실패 ({image_path}): {e}")
        return None
    
# --- VDRS 관련 파일/이미지 유틸리티 함수 최상위로 이동 ---
def get_latest_png(directory):
    write_log("get_latest_png() 호출 받음")
    images = glob.glob(os.path.join(directory, "*.png"))
    if not images:
        return None
    return max(images, key=os.path.getmtime)

def get_next_image(directory, after_time):
    write_log("get_next_image() 호출 받음")
    images = glob.glob(os.path.join(directory, "*.png"))
    # after_time보다 크면서 가장 작은(가장 가까운) 생성시간
    next_img = None
    min_dt = float('inf')
    for img in images:
        t = os.path.getmtime(img)
        if t > after_time and (t - after_time) < min_dt:
            min_dt = t - after_time
            next_img = img
    return next_img

def delete_all_images(directory):
    write_log("delete_all_images() 호출 받음")
    images = glob.glob(os.path.join(directory, "*.png"))
    for img in images:
        try:
            os.remove(img)
        except Exception as e:
            write_log(f"이미지 삭제 실패: {img} - {e}")

# --------------------------------------------------------------------
# Helper functions for defense function
def angle_diff_deg(a, b):
    """두 각도 a, b의 차이를 -180~+180°로 반환"""
    diff = (a - b + 180) % 360 - 180
    return diff

# --------------------------------------------------------------------

def send_fcs(request_data=None):
    write_log("send_fcs() 호출 받음")
    """FCS에 사격 통제 요청"""
    external_server = "http://192.168.0.21:5000/get_fcs"
    try:
        write_log(f"fcs 발신 데이터 : {request_data}")
        ext_response = requests.post(external_server, json=request_data, timeout=2)
        ext_result = ext_response.json()
        write_log(f"fcs 수신 데이터 : {ext_result}")
        write_log(f"fcs 수신 데이터 타입 : {type(ext_result)}")
    except Exception as e:
        write_log(f"fcs_except 발생 : {str(e)}")
        ext_result = {"error": str(e)}
    return ext_result

def send_adcs(request_data=None):
    write_log("send_adcs() 호출 받음")
    external_server = "http://192.168.0.124:5000/get_adcs"
    try:
        write_log(f"adcs 발신 데이터 : {request_data}")
        ext_response = requests.post(external_server, json=request_data, timeout=2)
        ext_result = ext_response.json()
        write_log(f"adcs 수신 데이터 : {ext_result}")
        write_log(f"adcs 수신 데이터 타입 : {type(ext_result)}")
    except Exception as e:
        write_log(f"adcs_except 발생 : {str(e)}")
        ext_result = {"error": str(e)}
    return ext_result

def send_vdrs(request_data=None):
    write_log("send_vdrs() 호출 받음")
    vdrs_total_start = time.time()
    
    main_image_dir = r"C:\Users\acorn\Documents\Tank Challenge\capture_images"

    # 1. 이미지 경로 탐색
    img_search_start = time.time()
    main_image_path = get_latest_png(main_image_dir)
    img_search_end = time.time()
    write_log(f"  └ 이미지 경로 탐색 소요시간: {(img_search_end - img_search_start)*1000:.2f}ms")

    # 이미지 경로 유효성 검증
    if not main_image_path:
        write_log("⚠️ 메인 이미지 없음")
        return {"error": "No main image found"}

    # 2. 이미지 인코딩
    img_encode_start = time.time()
    main_image_data = encode_image_to_base64(main_image_path)
    img_encode_end = time.time()
    write_log(f"  └ 이미지 인코딩 소요시간: {(img_encode_end - img_encode_start)*1000:.2f}ms")

    # 이미지 인코딩 성공 여부 검증
    if not main_image_data:
        write_log("⚠️ 이미지 인코딩 실패")
        # 인코딩 실패 시에도 이미지 삭제
        delete_all_images(main_image_dir)
        return {"error": "Image encoding failed"}

    # 3. 이미지 삭제
    img_delete_start = time.time()
    delete_all_images(main_image_dir)
    img_delete_end = time.time()
    write_log(f"  └ 이미지 삭제 소요시간: {(img_delete_end - img_delete_start)*1000:.2f}ms")

    # 4. 아군 데이터 준비
    data_prep_start = time.time()
    ally = ally_list.find_ally(31)
    if not ally:
        write_log("ID 31 아군(플레이어 탱크)을 찾을 수 없습니다.")
        return {"error": "No ally with ID 31 found"}

    request_data = {
        "time": global_time,  # 시뮬레이터 시각
        "ally_body_pos": {"x": ally.pos_x, "y": ally.pos_y, "z": ally.pos_z},  # 아군 전차 차체 X, Y, Z 위치
        "ally_body_angle": {"x": ally.body_angle_x, "y": ally.body_angle_y, "z": ally.body_angle_z},  # 아군 전차 차체 X, Y, Z 각도
        "ally_speed": ally.speed,  # 아군 전차 속도(m/s)
        "image_b64": main_image_data,  # base64 인코딩된 메인 이미지 (800x450 or 1920x1080)
        "stereo_image_left_b64": main_image_data,  # base64 인코딩된 왼쪽 스테레오 이미지 (메인과 동일)
        "stereo_image_right_b64": main_image_data,  # base64 인코딩된 오른쪽 스테레오 이미지 (메인과 동일)
    }
    data_prep_end = time.time()
    write_log(f"  └ 요청 데이터 준비 소요시간: {(data_prep_end - data_prep_start)*1000:.2f}ms")
    
    # 5. VDRS 서버 통신
    external_server = "http://192.168.0.15:5000/get_vdrs"
    try:
        vdrs_comm_start = time.time()
        ext_response = requests.post(external_server, json=request_data, timeout=2)
        ext_result = ext_response.json()
        vdrs_comm_end = time.time()
        write_log(f"  └ VDRS 서버 통신 소요시간: {(vdrs_comm_end - vdrs_comm_start)*1000:.2f}ms")
        write_log(f"vdrs 수신 데이터 : {ext_result}")
        write_log(f"vdrs 수신 데이터 타입 : {type(ext_result)}")
    except Exception as e:
        write_log(f"vdrs_except 발생 : {str(e)}")
        ext_result = {"error": str(e)}
    
    vdrs_total_end = time.time()
    write_log(f"  └ VDRS 전체 소요시간: {(vdrs_total_end - vdrs_total_start)*1000:.2f}ms")
    
    return ext_result

def process_vdrs_objects(vdrs_data, global_time):
        write_log("process_vdrs_objects() 호출 받음")
        """VDRS에서 탐지된 객체들을 분류 및 리스트에 추가
        
        VDRS 데이터 형식:
        [
            {
                "class": 0 (car) / 1 (infantry) / 2 (tank),
                "object": {"x": float, "y": float, "z": float},
                "object_angle": {"x": 0.0, "y": 0.0}
            },
            ...
        ]
        """
        
        # 상세 디버깅 로그
        write_log(f"🔍 [DEBUG] vdrs_data 타입: {type(vdrs_data)}")
        write_log(f"🔍 [DEBUG] vdrs_data 존재 여부: {vdrs_data is not None}")
        
        # VDRS 데이터 존재 여부 체크
        if not vdrs_data:
            write_log("⚠️ [ERROR] vdrs_data가 None이거나 비어있음!")
            return
        
        # VDRS 에러 응답 체크 (dict로 에러 메시지 반환)
        if isinstance(vdrs_data, dict):
            if 'error' in vdrs_data:
                write_log(f"⚠️ [VDRS ERROR] VDRS에서 에러 반환: {vdrs_data['error']}")
                return
            else:
                write_log(f"⚠️ [ERROR] vdrs_data가 예상치 못한 dict 형식: {vdrs_data}")
                return
        
        # VDRS 데이터가 리스트인지 확인
        if not isinstance(vdrs_data, list):
            write_log(f"⚠️ [ERROR] vdrs_data가 list가 아님! 실제 타입: {type(vdrs_data)}, 내용: {vdrs_data}")
            return
        
        # 탐지된 객체 처리
        write_log(f"� VDRS에서 {len(vdrs_data)}개 객체 탐지됨")
        
        for idx, obj in enumerate(vdrs_data):
            if not isinstance(obj, dict):
                write_log(f"⚠️ [DEBUG] obj[{idx}]가 dict가 아님: {type(obj)}, 값: {obj}")
                continue
            
            try:
                write_log(f"🔍 [DEBUG] 처리 중인 obj[{idx}] 키 목록: {list(obj.keys())}")
                
                # 데이터 추출 (새로운 형식)
                obj_class = obj.get('class', -1)  # class: 0 (car), 1 (infantry), 2 (tank)
                obj_pos = obj.get('object', {})  # object: {x, y, z}
                obj_angle = obj.get('object_angle', {})  # object_angle: {x, y}
                
                write_log(f"🔍 [DEBUG] obj_class: {obj_class}")
                write_log(f"🔍 [DEBUG] obj_pos: {obj_pos}")
                write_log(f"🔍 [DEBUG] obj_angle: {obj_angle}")
                
                # 유효성 검사
                if not isinstance(obj_pos, dict) or not isinstance(obj_angle, dict):
                    write_log(f"⚠️ [DEBUG] obj[{idx}] 데이터 형식 오류")
                    continue
                
                # 좌표 추출
                pos_x = float(obj_pos.get('x', 0.0))
                pos_y = float(obj_pos.get('y', 0.0))
                pos_z = float(obj_pos.get('z', 0.0))
                angle_x = float(obj_angle.get('x', 0.0))
                angle_y = float(obj_angle.get('y', 0.0))
                
                # 클래스별 처리 (0: car, 1: infantry, 2: tank)
                if obj_class == 0:  # car → 장애물로 처리 (Unknown)
                    write_log(f"장애물(차량) 발견: car at ({pos_x:.1f}, {pos_y:.1f}, {pos_z:.1f})")
                    # unknown_list.add_or_update_unknown(
                    #     unknown_id=None,
                    #     pos_x=pos_x,
                    #     pos_y=pos_y,
                    #     pos_z=pos_z,
                    #     object_angle_x=angle_x,
                    #     object_angle_y=angle_y,
                    #     unit_type="car",
                    #     identification_time=global_time,
                    #     speed=0.0
                    # )
                elif obj_class == 1:  # infantry → 적 보병 (Enemy)
                    write_log(f"적 보병 발견: infantry at ({pos_x:.1f}, {pos_y:.1f}, {pos_z:.1f})")
                    enemy_list.add_or_update_enemy(
                        enemy_id=None,
                        pos_x=pos_x,
                        pos_y=pos_y,
                        pos_z=pos_z,
                        body_angle_x=angle_x,
                        body_angle_y=angle_y,
                        body_angle_z=0.0,
                        unit_type="infantry",
                        identification_time=global_time,
                        speed=0.0,
                        threat_level=0.3
                    )
                elif obj_class == 2:  # tank → 적 전차 (Enemy)
                    write_log(f"적 전차 발견: armored at ({pos_x:.1f}, {pos_y:.1f}, {pos_z:.1f})")
                    # enemy_list.add_or_update_enemy(
                    #     enemy_id=None,
                    #     pos_x=pos_x,
                    #     pos_y=pos_y,
                    #     pos_z=pos_z,
                    #     body_angle_x=angle_x,
                    #     body_angle_y=angle_y,
                    #     body_angle_z=0.0,
                    #     unit_type="armored",
                    #     identification_time=global_time,
                    #     speed=0.0,
                    #     threat_level=0.9
                    # )
                else:
                    write_log(f"⚠️ 알 수 없는 클래스: {obj_class} at ({pos_x:.1f}, {pos_y:.1f}, {pos_z:.1f})")
                    unknown_list.add_or_update_unknown(
                        unknown_id=None,
                        pos_x=pos_x,
                        pos_y=pos_y,
                        pos_z=pos_z,
                        object_angle_x=angle_x,
                        object_angle_y=angle_y,
                        unit_type="unknown",
                        identification_time=global_time,
                        speed=0.0
                    )
                
            except Exception as e:
                write_log(f"⚠️ VDRS 객체[{idx}] 처리 중 오류: {e}")
                import traceback
                write_log(f"⚠️ 오류 상세: {traceback.format_exc()}")
                continue
        
        write_log(f"✅ VDRS 객체 처리 완료: {len(vdrs_data)}개 처리됨")

def send_tpp(request_data=None):
    write_log("send_tpp() 호출 받음")
    """TPP에 경로 계획 요청"""
    external_server = "http://192.168.0.132:5000/get_tpp"
    try:
        write_log(f"tpp 발신 데이터 : {request_data}")
        ext_response = requests.post(external_server, json=request_data, timeout=2)
        ext_result = ext_response.json()
        write_log(f"tpp 수신 데이터 : {ext_result}")
        write_log(f"tpp 수신 데이터 타입 : {type(ext_result)}")
    except Exception as e:
        write_log(f"tpp_except 발생 : {str(e)}")
        ext_result = {"error": str(e)}
    return ext_result

# --------------------------------------------------------------------

# ============================================================================
# Frontend 송수신 데이터 처리 관련
# ============================================================================

def send_detection(request_data=None):# 새로운 객체(적 전차, 보병)가 탐지되었을 때, Frontend로 전송
    """
    IBSM이 개별 탐지 객체 전송 시
    
    IBSM에서 보내야 하는 형식 예시:
    {
        "tracking_id": 1001,
        "class_id": 1,
        "x": 100.5,
        "z": 200.3,
        "alive": true
    }
    
    Frontend로 전송되는 형식:
    {
        "type": "detection_update",
        "object": { tracking_id, class_id, x, z, alive }
    }
    """
    try:
        write_log(f"[DEBUG] emit detection: {{'type': 'detection_update', 'object': {request_data}}}")
        socketio.emit('detection', {
            "type": "detection_update",
            "object": request_data
        })
    except Exception as e:
        ext_result = {"error": str(e)}
        write_log(f"[ERROR] emit detection: {ext_result}")
        return ext_result
    return None

def send_ally_position(request_data=None): # 아군 전차 위치 업데이트 시, Frontend로 전송
    """
    IBSM이 내 탱크 위치 데이터 전송 시
    
    IBSM에서 보내야 하는 형식:
    {
        "tanks": [
            {
                "tank_id": "17TK-101",
                "x": -50.0,
                "y": -100.0
            }
        ]
    }
    
    Frontend로 전송되는 형식:
    {
        "type": "position_update",
        "tanks": [{ tank_id, x, y }, ...]
    }
    """
    try:
        write_log(f"[DEBUG] emit ally_position: {{'type': 'position_update', 'tanks': {request_data}}}")
        socketio.emit('position', {
            "type": "position_update",
            "tanks": request_data
        })
    except Exception as e:
        ext_result = {"error": str(e)}
        write_log(f"[ERROR] emit ally_position: {ext_result}")
        return ext_result
    return None

def send_fire(request_data=None):
    """
    IBSM에서 보내야 하는 형식 (발사):
    {
        "type": "fire_event",
        "fire": {
            "target_tracking_id": 1001,
            "ally_id": "17TK-101",
            "class_id": 5
        }
    }
    """
    try:
        write_log(f"[DEBUG] emit fire: {{'type': 'fire_event', 'fire': {request_data}}}")
        socketio.emit('fire', {
            "type": "fire_event",
            "fire": request_data
        })
    except Exception as e:
        ext_result = {"error": str(e)}
        write_log(f"[ERROR] emit fire: {ext_result}")
        return ext_result
    return None

def send_hit(request_data=None):
    """
    IBSM에서 보내야 하는 형식 (명중 결과):
    {
        "type": "hit_result",
        "data": {
            "target_tracking_id": 1001,
            "result": "hit"  # 'hit' | 'miss'
        }
    }
    """
    try: 
        write_log(f"[DEBUG] emit hit: {{'type': 'hit_result', 'data': {request_data}}}")
        socketio.emit('fire', {
            "type": "hit_result",
            "data": request_data
        })
    except Exception as e:
        ext_result = {"error": str(e)}
        write_log(f"[ERROR] emit hit: {ext_result}")
        return ext_result
    return None

def send_mission(request_data=None): # 현 임무 갱신 시, Frontend로 전송
    """
    IBSM이 미션 데이터 전송 시
    
    IBSM에서 보내야 하는 형식:
    {
        "mission": "attack"  # 'attack' | 'search' | 'defence'
    }
    
    Frontend로 전송되는 형식:
    {
        "type": "mission_update",
        "mission": "attack"  # 'attack' | 'search' | 'defence'
    }
    """
    try:
        write_log(f"[DEBUG] emit mission: {{'type': 'mission_update', 'mission': {request_data}}}")
        socketio.emit('mission', {
            "type": "mission_update",
            "mission": request_data
        })
    except Exception as e:
        ext_result = {"error": str(e)}
        write_log(f"[ERROR] emit mission: {ext_result}")
        return ext_result
    return None

# ============================================================================
# 대기 / 방어 / 전투 로직
# ============================================================================
def hold_logic():
    """대기 임무 로직"""
    pass

def defense_logic(ally, defense_pos, enemy_pos, QE_command, QE_weight, RF_command, RF_weight, 
                WS_command, WS_weight, AD_command, AD_weight, fire_command):
    """방어 임무 로직"""
    global enemy_in_range # 적이 사격 범위 내에 있는지 여부
    global defense_arrived # 방어 지점 도착 여부
    global scan_to_left # 좌측 방향 스캔 여부

    ally_pos = {"x": ally.pos_x, "y": ally.pos_y, "z": ally.pos_z}
    write_log(f"ally.pos: {ally_pos}, defense_pos: {defense_pos}, enemy_pos: {enemy_pos} 호출 받음")
    # 적이 있다면,
    if enemy_pos: 
        # 적이 사격 범위 내에 있다면,
        if enemy_in_range == True and enemy_pos:
            api1_start = time.time()
            write_log("API 1: 적 사정거리 내 진입, 사격 준비 시작")
            request_data_fcs = {
                "time": global_time,
                "ally_body_pos": {"x": ally.pos_x, "y": ally.pos_y, "z": ally.pos_z},
                "ally_body_angle": {"x": ally.body_angle_x, "y": ally.body_angle_y, "z": ally.body_angle_z},
                "ally_speed": ally.speed,
                "ally_turret_angle": {"x": ally.turret_angle_x, "y": ally.turret_angle_y},
                "ibsm_target": enemy_pos,
                "map_type": 0,
                "AD_command": AD_command,
                "AD_weight": AD_weight,
                "WS_command": WS_command,
                "WS_weight": WS_weight
            }
            fcs_data = send_fcs(request_data_fcs)

            QE_command = fcs_data['QE_command']
            QE_weight = fcs_data['QE_weight']
            RF_command = fcs_data['RF_command']
            RF_weight = fcs_data['RF_weight']
            fire_command = fcs_data['fire_command']
            
            api1_end = time.time()
            write_log(f"  └ API 1번 소요시간: {(api1_end - api1_start)*1000:.2f}ms")

            # 사격 결과 처리
            if fire_command == False:
                write_log("  └ 조준 중... 사격 명령 대기")
            elif fire_command == True:
                write_log("  └ 🎯 조준 완료, 사격 개시!")

        # 적이 사격 범위 내에 없다면,
        elif enemy_in_range == False:
            # 방어 지점에 아직 미 도달이라면,
            if defense_arrived == False:
                # [1] TPP: 경로 계획
                tpp_start = time.time()
                request_data_tpp = {
                    "time": global_time,
                    "ally_body_pos": {"x": ally.pos_x, "y": ally.pos_y, "z": ally.pos_z},
                    "target_pos": defense_pos, # 방어 위치를 전달
                    "unknowns": unknown_list.get_all_unknowns(),
                    "enemies": enemy_list.get_all_enemies()
                }
                tpp_data = send_tpp(request_data_tpp)
                tpp_end = time.time()
                write_log(f"  └ [TPP] 소요시간: {(tpp_end - tpp_start)*1000:.2f}ms")

                # [2] ADCS: 주행 제어
                adcs_start = time.time()
                request_data_adcs = {
                    "time": global_time,
                    "ally_body_pos": {"x": ally.pos_x, "y": ally.pos_y, "z": ally.pos_z},
                    "ally_body_angle": {"x": ally.body_angle_x, "y": ally.body_angle_y, "z": ally.body_angle_z},
                    "ally_speed": ally.speed,
                    "waypoints": tpp_data['waypoints'] # TPP에서 받은 경로점들을 전달
                }
                adcs_data = send_adcs(request_data_adcs)
                adcs_end = time.time()
                write_log(f"  └ [ADCS] 소요시간: {(adcs_end - adcs_start)*1000:.2f}ms")
                WS_command = adcs_data['WS_command']
                WS_weight = adcs_data['WS_weight']
                AD_command = adcs_data['AD_command']
                AD_weight = adcs_data['AD_weight']

                # [3] FCS: 스테빌라이저 사용은 안 하고, 사격 판단만 사용
                fcs_start = time.time()
                request_data_fcs = {
                    "time": global_time,
                    "ally_body_pos": {"x": ally.pos_x, "y": ally.pos_y, "z": ally.pos_z},
                    "ally_body_angle": {"x": ally.body_angle_x, "y": ally.body_angle_y, "z": ally.body_angle_z},
                    "ally_speed": ally.speed,
                    "ally_turret_angle": {"x": ally.turret_angle_x, "y": ally.turret_angle_y},
                    "ibsm_target": enemy_pos, # 적 위치를 전달하여, 사격 가능 여부 판단
                    "map_type": 0,
                    "AD_command": AD_command,
                    "AD_weight": AD_weight,
                    "WS_command": WS_command,
                    "WS_weight": WS_weight
                }
                fcs_data = send_fcs(request_data_fcs)

                enemy_in_range = fcs_data['enemy_in_range'] # 적이 사격 범위 내에 있는지 여부 업데이트

                # [4] 방어 위치 도착 확인
                if WS_command == "STOP":
                    defense_arrived = True
                    write_log("✅ 방어 지점 도착 완료")
            # 방어 지점에 도달했다면,
            elif defense_arrived == True:
                # 차체 회전 수행
                write_log("방어 지점 도착 후 차체 회전 수행")
                # 차체를 회전 시키는 로직 필요

                dx = enemy_pos['x'] - ally.pos_x
                dz = enemy_pos['z'] - ally.pos_z
                target_angle = math.degrees(math.atan2(dx, dz)) % 360
                # print("Target Angle:", target_angle)

                # (회전)2. 현재 탱크의 수직각, 수평각을 확인하여 웨이포인트 방향으로 회전 명령 생성
                # - 전속력(weight = 1.0) 회전 수행
                # - 만약, 탱크의 수평각이 목표 수평각보다 5도 이내로 들어오면, 회전 명령 중지
                angle_diff = angle_diff_deg(ally.body_angle_x, target_angle)
                # print("Angle Diff:", angle_diff)
                if abs(angle_diff) > 20:
                    if angle_diff > 0:
                        AD_command, AD_weight = "A", 1.0
                    else:
                        AD_command, AD_weight = "D", 1.0

                # (회전) 3. 회전 명령 중지 후, 만약, 탱크의 수평각이 목표 수평각보다 1도 이상 크거나, 작으면, 반대로 역 조정 명령 생성
                elif abs(angle_diff) > 0.8:
                    AD_command, AD_weight = "", 0.0 # 명령 초기화
                    if angle_diff > 0.5:
                        AD_command, AD_weight = "A", 0.05
                    elif angle_diff < -0.5:
                        AD_command, AD_weight = "D", 0.05
                # (회전) 4. 만약, 탱크의 회전각이 웨이포인트 방향과 일치하면, 터렛 제어 명령 수행
                elif abs(angle_diff) <= 0.8:
                    # 좌측을 봐야 하는 angle을 계산
                    angle_left = (ally.body_angle_x - 60.0) % 360
                    # 우측을 봐야 하는 angle을 계산
                    angle_right = (ally.body_angle_x + 60.0) % 360

                    if scan_to_left == True:
                        write_log("  └ 좌측 스캔 중...")
                        angle_diff = angle_diff_deg(ally.turret_angle_x, angle_left)
                        write_log(f"    └ ally.turret_angle_x: {ally.turret_angle_x:.2f}°, angle_left: {angle_left:.2f}°, angle_diff: {angle_diff:.2f}°")
                        # print("Angle Diff:", angle_diff)
                        QE_command, QE_weight = "Q", 0.2

                        if abs(angle_diff) <= 5:
                            scan_to_left = False
                            write_log("  └ 좌측 스캔 목표 도달, 플래그 우측으로 전환")

                    elif scan_to_left == False:
                        write_log("  └ 우측 스캔 중...")
                        angle_diff = angle_diff_deg(ally.turret_angle_x, angle_right)
                        write_log(f"    └ ally.turret_angle_x: {ally.turret_angle_x:.2f}°, angle_right: {angle_right:.2f}°, angle_diff: {angle_diff:.2f}°")
                        QE_command, QE_weight = "E", 0.2

                        if abs(angle_diff) <= 5:
                            scan_to_left = True
                            write_log("  └ 우측 스캔 목표 도달, 플래그 좌측으로 전환")
    # 적이 없는데
    elif enemy_pos is None:
        # 방어 지점에 아직 미 도달이라면,
        if defense_arrived == False:
            # [1] TPP: 경로 계획
            tpp_start = time.time()
            request_data_tpp = {
                "time": global_time,
                "ally_body_pos": {"x": ally.pos_x, "y": ally.pos_y, "z": ally.pos_z},
                "target_pos": defense_pos, # 방어 위치를 전달
                "unknowns": unknown_list.get_all_unknowns(),
                "enemies": enemy_list.get_all_enemies()
            }
            tpp_data = send_tpp(request_data_tpp)
            tpp_end = time.time()
            write_log(f"  └ [TPP] 소요시간: {(tpp_end - tpp_start)*1000:.2f}ms")

            # [2] ADCS: 주행 제어
            adcs_start = time.time()
            request_data_adcs = {
                "time": global_time,
                "ally_body_pos": {"x": ally.pos_x, "y": ally.pos_y, "z": ally.pos_z},
                "ally_body_angle": {"x": ally.body_angle_x, "y": ally.body_angle_y, "z": ally.body_angle_z},
                "ally_speed": ally.speed,
                "waypoints": tpp_data['waypoints'] # TPP에서 받은 경로점들을 전달
            }
            adcs_data = send_adcs(request_data_adcs)
            adcs_end = time.time()
            write_log(f"  └ [ADCS] 소요시간: {(adcs_end - adcs_start)*1000:.2f}ms")
            WS_command = adcs_data['WS_command']
            WS_weight = adcs_data['WS_weight']
            AD_command = adcs_data['AD_command']
            AD_weight = adcs_data['AD_weight']

            # [3] 방어 위치 도착 확인
            if WS_command == "STOP":
                defense_arrived = True
                write_log("✅ 방어 지점 도착 완료")
        # 방어 지점에 도달했다면,
        elif defense_arrived == True:
            # 차체 회전 수행
            write_log("방어 지점 도착 후 차체 회전 수행")
            # 차체를 회전 시키는 로직 필요

            dx = 150.0 - ally.pos_x # 맵 중앙을 바라보게 함
            dz = 150.0 - ally.pos_z
            target_angle = math.degrees(math.atan2(dx, dz)) % 360
            # print("Target Angle:", target_angle)

            # (회전)2. 현재 탱크의 수직각, 수평각을 확인하여 웨이포인트 방향으로 회전 명령 생성
            # - 전속력(weight = 1.0) 회전 수행
            # - 만약, 탱크의 수평각이 목표 수평각보다 5도 이내로 들어오면, 회전 명령 중지
            angle_diff = angle_diff_deg(ally.body_angle_x, target_angle)
            # print("Angle Diff:", angle_diff)
            if abs(angle_diff) > 20:
                if angle_diff > 0:
                    AD_command, AD_weight = "A", 1.0
                else:
                    AD_command, AD_weight = "D", 1.0

            # (회전) 3. 회전 명령 중지 후, 만약, 탱크의 수평각이 목표 수평각보다 1도 이상 크거나, 작으면, 반대로 역 조정 명령 생성
            elif abs(angle_diff) > 0.8:
                AD_command, AD_weight = "", 0.0 # 명령 초기화
                if angle_diff > 0.5:
                    AD_command, AD_weight = "A", 0.05
                elif angle_diff < -0.5:
                    AD_command, AD_weight = "D", 0.05
            # (회전) 4. 만약, 탱크의 회전각이 웨이포인트 방향과 일치하면, 터렛 제어 명령 수행
            elif abs(angle_diff) <= 0.8:
                # 좌측을 봐야 하는 angle을 계산
                angle_left = (ally.body_angle_x - 60.0) % 360
                # 우측을 봐야 하는 angle을 계산
                angle_right = (ally.body_angle_x + 60.0) % 360

                if scan_to_left == True:
                    write_log("  └ 좌측 스캔 중...")
                    angle_diff = angle_diff_deg(ally.turret_angle_x, angle_left)
                    write_log(f"    └ ally.turret_angle_x: {ally.turret_angle_x:.2f}°, angle_left: {angle_left:.2f}°, angle_diff: {angle_diff:.2f}°")
                    # print("Angle Diff:", angle_diff)
                    QE_command, QE_weight = "Q", 0.2

                    if abs(angle_diff) <= 5:
                        scan_to_left = False
                        write_log("  └ 좌측 스캔 목표 도달, 플래그 우측으로 전환")

                elif scan_to_left == False:
                    write_log("  └ 우측 스캔 중...")
                    angle_diff = angle_diff_deg(ally.turret_angle_x, angle_right)
                    write_log(f"    └ ally.turret_angle_x: {ally.turret_angle_x:.2f}°, angle_right: {angle_right:.2f}°, angle_diff: {angle_diff:.2f}°")
                    QE_command, QE_weight = "E", 0.2

                    if abs(angle_diff) <= 5:
                        scan_to_left = True
                        write_log("  └ 우측 스캔 목표 도달, 플래그 좌측으로 전환")
    return {
        "QE_command": QE_command,
        "QE_weight": QE_weight,
        "RF_command": RF_command,
        "RF_weight": RF_weight,
        "WS_command": WS_command,
        "WS_weight": WS_weight,
        "AD_command": AD_command,
        "AD_weight": AD_weight,
        "fire_command": fire_command
    }

def combat_logic(ally, enemy_pos, QE_command, QE_weight, RF_command, RF_weight, 
                WS_command, WS_weight, AD_command, AD_weight, fire_command):
    """
    전투 로직 함수 (API 1-7)
    
    Args:
        ally: AllyNode 객체
        enemy: EnemyNode 객체
        QE_command, QE_weight, RF_command, RF_weight: 포탑 제어 명령 (초기값)
        WS_command, WS_weight, AD_command, AD_weight: 주행 제어 명령 (초기값)
        fire_command: 사격 명령 (초기값)
    
    Returns:
        dict: 갱신된 명령 값들
    """
    global global_time
    global global_replan_required
    global global_fire_flag
    global new_fire_point
    
    write_log("🎮 combat_logic() 진입")
    
    # ====================================================================
    # [사격 모드] global_fire_flag == True
    # ====================================================================
    if global_fire_flag == True:
        # ================================================================
        # API 1: 사격 모드 - FCS 조준 및 사격
        # ================================================================
        api1_start = time.time()
        write_log("API 1: 사격 모드 - FCS 조준/사격")
        request_data_fcs = {
            "time": global_time,
            "ally_body_pos": {"x": ally.pos_x, "y": ally.pos_y, "z": ally.pos_z},
            "ally_body_angle": {"x": ally.body_angle_x, "y": ally.body_angle_y, "z": ally.body_angle_z},
            "ally_speed": ally.speed,
            "ally_turret_angle": {"x": ally.turret_angle_x, "y": ally.turret_angle_y},
            "ibsm_target": enemy_pos,
            "map_type": 0,
            "AD_command": AD_command,
            "AD_weight": AD_weight,
            "WS_command": WS_command,
            "WS_weight": WS_weight
        }
        fcs_data = send_fcs(request_data_fcs)

        QE_command = fcs_data['QE_command']
        QE_weight = fcs_data['QE_weight']
        RF_command = fcs_data['RF_command']
        RF_weight = fcs_data['RF_weight']
        fire_command = fcs_data['fire_command']
        new_fire_point = fcs_data['new_fire_point']

        api1_end = time.time()
        write_log(f"  └ API 1번 소요시간: {(api1_end - api1_start)*1000:.2f}ms")

        # 사격 결과 처리
        if fire_command == False:
            write_log("  └ 조준 중... 사격 명령 대기")
        elif fire_command == True:
            write_log("  └ 🎯 조준 완료, 사격 개시!")
        
        # ============================================================
        # API 1-1: 사격 불가능 감지 → 기동 모드 전환
        # ============================================================
        if fcs_data['new_fire_point'] is not None:
            write_log("API 1-1: 사격 불가능 위치 감지 - 기동 모드 전환")
            new_fire_point = fcs_data['new_fire_point']
            global_fire_flag = False
            write_log(f"  └ 이동 목표: {new_fire_point}")
            api1_1_end = time.time()
            write_log(f"  └ API 1-1 소요시간: {(api1_1_end - api1_start)*1000:.2f}ms")

    # ====================================================================
    # [기동 모드] global_fire_flag == False
    # ====================================================================
    elif global_fire_flag == False:
        # ================================================================
        # [경로 재계획 필요] global_replan_required == True
        # ================================================================
        if global_replan_required == True:
            
            # ============================================================
            # API 2, 3: 최초 사격 위치 산출
            # ============================================================
            if new_fire_point is None:
                api23_start = time.time()
                write_log("API 2, 3: 최초 사격 위치 판단 - FCS 호출")
                write_log(f"  └ 현재 new_fire_point: {new_fire_point}")
                request_data_fcs = {
                    "time": global_time,
                    "ally_body_pos": {"x": ally.pos_x, "y": ally.pos_y, "z": ally.pos_z},
                    "ally_body_angle": {"x": ally.body_angle_x, "y": ally.body_angle_y, "z": ally.body_angle_z},
                    "ally_speed": ally.speed,
                    "ally_turret_angle": {"x": ally.turret_angle_x, "y": ally.turret_angle_y},
                    "ibsm_target": enemy_pos,
                    "map_type": 0,
                    "AD_command": AD_command,
                    "AD_weight": AD_weight,
                    "WS_command": WS_command,
                    "WS_weight": WS_weight
                }
                fcs_data = send_fcs(request_data_fcs)

                QE_command = fcs_data['QE_command']
                QE_weight = fcs_data['QE_weight']
                RF_command = fcs_data['RF_command']
                RF_weight = fcs_data['RF_weight']
                fire_command = fcs_data['fire_command']
                new_fire_point = fcs_data['new_fire_point']

                write_log(f"  └ fcs에 전달한 아군 전차 좌표 : {ally.pos_x, ally.pos_y, ally.pos_z}")
                write_log(f"  └ fcs에 전달한 목표 좌표 : {enemy_pos['x'], enemy_pos['y'], enemy_pos['z']}")
                write_log(f"  └ fcs에서 산출된 새 사격 지점 : {new_fire_point}")
                        
                # API 2 결과 처리
                if fcs_data['new_fire_point'] is not None:
                    write_log("API 2: 이동 필요 - 사격 위치 할당")
                    new_fire_point = fcs_data['new_fire_point']
                    write_log(f"  └ 사격 위치: {new_fire_point}")
                    api2_end = time.time()
                    write_log(f"  └ API 2 소요시간: {(api2_end - api23_start)*1000:.2f}ms")

                # API 3 결과 처리
                elif fcs_data['new_fire_point'] is None:
                    write_log("API 3: 즉시 사격 가능 - 사격 모드 전환")
                    global_fire_flag = True
                    api3_end = time.time()
                    write_log(f"  └ API 3 소요시간: {(api3_end - api23_start)*1000:.2f}ms")

            # ============================================================
            # API 4, 5: 경로 재계획 → 이동 → 스테빌라이저
            # ============================================================
            elif new_fire_point is not None:
                api45_start = time.time()
                write_log("API 4, 5: 경로 재계획 모드 - TPP → ADCS → FCS")
                
                # [1] TPP: 경로 계획
                tpp_start = time.time()
                request_data_tpp = {
                    "time": global_time,
                    "ally_body_pos": {"x": ally.pos_x, "y": ally.pos_y, "z": ally.pos_z},
                    "target_pos": new_fire_point,
                    "unknowns": unknown_list.get_all_unknowns(),
                    "enemies": enemy_list.get_all_enemies()
                }
                tpp_data = send_tpp(request_data_tpp)
                tpp_end = time.time()
                write_log(f"  └ [TPP] 소요시간: {(tpp_end - tpp_start)*1000:.2f}ms")
                global_replan_required = False
                
                # [2] ADCS: 주행 제어
                adcs_start = time.time()
                request_data_adcs = {
                    "time": global_time,
                    "ally_body_pos": {"x": ally.pos_x, "y": ally.pos_y, "z": ally.pos_z},
                    "ally_body_angle": {"x": ally.body_angle_x, "y": ally.body_angle_y, "z": ally.body_angle_z},
                    "ally_speed": ally.speed,
                    "waypoints": tpp_data['waypoints']
                }
                adcs_data = send_adcs(request_data_adcs)
                adcs_end = time.time()
                write_log(f"  └ [ADCS] 소요시간: {(adcs_end - adcs_start)*1000:.2f}ms")
                WS_command = adcs_data['WS_command']
                WS_weight = adcs_data['WS_weight']
                AD_command = adcs_data['AD_command']
                AD_weight = adcs_data['AD_weight']

                # [3] FCS: 스테빌라이저 (이동 중 조준)
                fcs_start = time.time()
                request_data_fcs = {
                    "time": global_time,
                    "ally_body_pos": {"x": ally.pos_x, "y": ally.pos_y, "z": ally.pos_z},
                    "ally_body_angle": {"x": ally.body_angle_x, "y": ally.body_angle_y, "z": ally.body_angle_z},
                    "ally_speed": ally.speed,
                    "ally_turret_angle": {"x": ally.turret_angle_x, "y": ally.turret_angle_y},
                    "ibsm_target": enemy_pos,
                    "map_type": 0,
                    "AD_command": AD_command,
                    "AD_weight": AD_weight,
                    "WS_command": WS_command,
                    "WS_weight": WS_weight
                }
                fcs_data = send_fcs(request_data_fcs)

                QE_command = fcs_data['QE_command']
                QE_weight = fcs_data['QE_weight']
                RF_command = fcs_data['RF_command']
                RF_weight = fcs_data['RF_weight']
                fire_command = fcs_data['fire_command']
                new_fire_point = fcs_data['new_fire_point']

                fcs_end = time.time()
                write_log(f"  └ FCS 소요시간: {(fcs_end - fcs_start)*1000:.2f}ms")
                
                # API 4번 로직
                if fcs_data['new_fire_point'] is not None:
                    write_log("API 4번 로직 진입: 사격 지점 갱신 및 VDRS로 객체 탐지 진행")
                    new_fire_point = fcs_data['new_fire_point']
                    global_current_target = fcs_data['fire_target']
                    write_log(f"🔄 new_fire_point 갱신됨: {new_fire_point}")

                    api4_end = time.time()
                    write_log(f"  └ API 4 전체 소요시간: {(api4_end - api45_start)*1000:.2f}ms")
                    
                # API 5번 로직
                elif fcs_data['new_fire_point'] is None:
                    write_log("API 5번 로직 진입: 즉시 사격 모드 전환, VDRS 객체 탐지 미 진행")
                    global_fire_flag = True

                    api5_end = time.time()
                    write_log(f"  └ API 5 전체 소요시간: {(api5_end - api45_start)*1000:.2f}ms")
                
        # ================================================================
        # [경로 재계획 불필요] global_replan_required == False
        # ================================================================
        elif global_replan_required == False:
            write_log("API 6번, 7번 로직: 경로 계산 완료 후, 주행 모드 진입, ADCS -> FCS 순차 호출")
            api67_start = time.time()
            
            # ADCS(주행 제어) 호출
            adcs_start = time.time()
            request_data_adcs = {
                "time": global_time,
                "ally_body_pos": {"x": ally.pos_x, "y": ally.pos_y, "z": ally.pos_z},
                "ally_body_angle": {"x": ally.body_angle_x, "y": ally.body_angle_y, "z": ally.body_angle_z},
                "ally_speed": ally.speed,
                "waypoints": []
            }
            adcs_data = send_adcs(request_data_adcs)
            adcs_end = time.time()
            write_log(f"  └ ADCS 소요시간: {(adcs_end - adcs_start)*1000:.2f}ms")
            WS_command = adcs_data['WS_command']
            WS_weight = adcs_data['WS_weight']
            AD_command = adcs_data['AD_command']
            AD_weight = adcs_data['AD_weight']

            # FCS(사격 통제) 호출: 스테빌라이저 수행
            fcs_start = time.time()
            request_data_fcs = {
                "time": global_time,
                "ally_body_pos": {"x": ally.pos_x, "y": ally.pos_y, "z": ally.pos_z},
                "ally_body_angle": {"x": ally.body_angle_x, "y": ally.body_angle_y, "z": ally.body_angle_z},
                "ally_speed": ally.speed,
                "ally_turret_angle": {"x": ally.turret_angle_x, "y": ally.turret_angle_y},
                "ibsm_target": enemy_pos,
                "map_type": 0,
                "AD_command": AD_command,
                "AD_weight": AD_weight,
                "WS_command": WS_command,
                "WS_weight": WS_weight
            }
            fcs_data = send_fcs(request_data_fcs)

            QE_command = fcs_data['QE_command']
            QE_weight = fcs_data['QE_weight']
            RF_command = fcs_data['RF_command']
            RF_weight = fcs_data['RF_weight']
            fire_command = fcs_data['fire_command']
            new_fire_point = fcs_data['new_fire_point']

            fcs_end = time.time()
            write_log(f"  └ fcs 소요시간: {(fcs_end - fcs_start)*1000:.2f}ms")
            
            # API 7번 로직
            if fcs_data['new_fire_point'] is not None:
                write_log("API 7번 로직 진입: 기존에 산출된 TPP를 따라 주행 중, 사격 지점 갱신 및 VDRS로 객체 탐지 진행")
                new_fire_point = fcs_data['new_fire_point']
                global_current_target = fcs_data['fire_target']

                api7_end = time.time()
                write_log(f"  └ API 7 전체 소요시간: {(api7_end - api67_start)*1000:.2f}ms")
            
            # API 6번 로직
            elif fcs_data['new_fire_point'] is None:
                write_log("API 6번 로직 진입: 기존에 산출된 TPP를 따라 주행 중, 즉시 사격 모드 전환, VDRS 객체 탐지 미 진행")
                global_fire_flag = True

                api6_end = time.time()
                write_log(f"  └ API 6 전체 소요시간: {(api6_end - api67_start)*1000:.2f}ms")

    # 갱신된 명령 값 반환
    return {
        "QE_command": QE_command,
        "QE_weight": QE_weight,
        "RF_command": RF_command,
        "RF_weight": RF_weight,
        "WS_command": WS_command,
        "WS_weight": WS_weight,
        "AD_command": AD_command,
        "AD_weight": AD_weight,
        "fire_command": fire_command
    }

# ============================================================================
app = Flask(__name__)
print("Flask 앱 생성 완료")
CORS(app)
print("CORS 설정 완료")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
print("SocketIO 설정 완료")

# ============================================
# WebSocket 이벤트
# ============================================
print("WebSocket 이벤트 핸들러 설정 중...")
connected_clients = set()

@socketio.on('connect')
def handle_connect():
    connected_clients.add(request.sid)
print("connected_clients connect 완료")

@socketio.on('disconnect')
def handle_disconnect():
    connected_clients.discard(request.sid)
print("connected_clients disconnect 완료")
# ============================================
# Simulator API 엔드포인트
# ============================================

@app.route('/info', methods=['POST'])
def info(): # 수신 정보 처리 및 메인 처리 로직
    write_log("info() 호출 받음")
    global global_time, distance, player_x, player_y, player_z, player_speed, player_health, player_turret_x, player_turret_y
    global player_body_x, player_body_y, player_body_z, enemy_x, enemy_y, enemy_z, enemy_speed, enemy_health
    global enemy_turret_x, enemy_turret_y, enemy_body_x, enemy_body_y, enemy_body_z
    global global_mission_number
    global vdrs_processing

    request_data = request.get_json(force=True)
    if not request_data:
        return jsonify({"error": "No JSON received"}), 400
    
    # info로 수신되는 데이터 기본 파싱
    global_time = request_data["time"]
    distance = request_data["distance"]

    player_x = request_data["playerPos"]["x"]
    player_y = request_data["playerPos"]["y"]
    player_z = request_data["playerPos"]["z"]

    player_speed = request_data["playerSpeed"]
    player_health = request_data["playerHealth"]
    player_turret_x = request_data["playerTurretX"]
    player_turret_y = request_data["playerTurretY"]
    player_body_x = request_data["playerBodyX"]
    player_body_y = request_data["playerBodyY"]
    player_body_z = request_data["playerBodyZ"]

    enemy_x = request_data["enemyPos"]["x"]
    enemy_y = request_data["enemyPos"]["y"]
    enemy_z = request_data["enemyPos"]["z"]

    enemy_speed = request_data["enemySpeed"]
    enemy_health = request_data["enemyHealth"]
    enemy_turret_x = request_data["enemyTurretX"]
    enemy_turret_y = request_data["enemyTurretY"]
    enemy_body_x = request_data["enemyBodyX"]
    enemy_body_y = request_data["enemyBodyY"]
    enemy_body_z = request_data["enemyBodyZ"]

    # 이미 처리 중이면 즉시 거부 (누적 방지)
    if not vdrs_lock.acquire(blocking=False):
        write_log("⚠️ VDRS 이미 처리 중 - 요청 버림")

        return jsonify({"status": "success", "control": ""})

    try:
        vdrs_processing = True
        write_log("🚀 VDRS 처리 시작")
        
        vdrs_start = time.time()
        
        # VDRS 호출
        vdrs_data = send_vdrs()
        process_vdrs_objects(vdrs_data, global_time)
        
        vdrs_end = time.time()
        
        write_log(f"  └ VDRS 소요시간: {(vdrs_end - vdrs_start)*1000:.2f}ms")
        
        return jsonify({"status": "success", "control": ""})
        
    except Exception as e:
        write_log(f"❌ VDRS 처리 중 오류 발생: {e}")
        return jsonify({
            "status": "error", 
            "message": str(e)
        }), 500
    finally:
        vdrs_processing = False
        vdrs_lock.release()
        write_log("🔓 VDRS 락 해제")

@app.route('/get_action', methods=['POST'])
def get_action():
    write_log("get_action() 호출 받음")
    # 동시 호출 방지: 다른 get_action 요청이 처리 중이면 즉시 반환
    acquired_get_action_lock = get_action_lock.acquire(blocking=False)
    if not acquired_get_action_lock:
        write_log("⚠️ get_action 이미 실행 중 - 요청 버림")
        return jsonify({"status": "busy", "control": ""})
    # get_action_first_call 시 호출 무시(info 에서 정보 업데이트 이후에 get_acton을 처리하기 위함)
    global get_action_first_call
    if get_action_first_call:
        write_log("get_action 최초 호출 감지 - 임무 생성 후 무시 처리 진행")
        time.sleep(1)  # 1초 대기
        get_action_first_call = False
        write_log("get_action 최초 호출 무시 (초기화용)")
        try:
            # release lock and return early
            if acquired_get_action_lock:
                get_action_lock.release()
                write_log("🔓 get_action 락 해제 (초기 무시)")
        except Exception:
            write_log("🔔 get_action 락 해제 실패 (초기 무시)")
        return jsonify({"status": "ignored", "control": ""})
    try:
        global global_time
        global global_replan_required
        global global_fire_flag
        global new_fire_point

        # Reset global commands and weights
        QE_command, QE_weight, RF_command, RF_weight = "", 0.0, "", 0.0
        WS_command, WS_weight, AD_command, AD_weight = "", 0.0, "", 0.0
        fire_command = False

        request_data = request.get_json(force=True)
        if not request_data:
            return jsonify({"error": "No JSON received"}), 400

        write_log("아군 전차 정보 업데이트 예정")
        write_log(f"  └ 아군 전차 위치: x={player_x}, y={player_y}, z={player_z}, speed={player_speed}")

        # 아군 전차 정보 업데이트(기동 상태)
        ally_list.add_or_update_ally(
            pos_x=player_x,
            pos_y=player_y,
            pos_z=player_z,
            unit_type="armored",
            identification_time=global_time,
            speed=player_speed,
            body_angle_x=player_body_x,
            body_angle_y=player_body_y,
            body_angle_z=player_body_z,
            turret_angle_x=player_turret_x,
            turret_angle_y=player_turret_y,
            ally_id=31,
            mission_number=0,
            combat_status="active"
        )

        write_log("적 전차 정보 업데이트 예정")
        write_log(f"  └ 적 전차 위치: enemy_x={enemy_x}, enemy_y={enemy_y}, enemy_z={enemy_z}, speed={enemy_speed}")

        # 적 전차 정보 업데이트(정지 상태)
        enemy_list.add_or_update_enemy(
            enemy_id=None,
            pos_x=enemy_x,
            pos_y=enemy_y,
            pos_z=enemy_z,
            body_angle_x=enemy_body_x,
            body_angle_y=enemy_body_y,
            body_angle_z=enemy_body_z,
            unit_type="armored",
            identification_time=global_time,
            speed=enemy_speed,
            threat_level=0.0
        )

        # [IBSM 불러오기] ally_list에서 ID 31번 아군(플레이어 탱크) 가져오기
        ally = ally_list.find_ally(31)
        if not ally:
            write_log("ID 31번 아군(플레이어 탱크)을 찾을 수 없습니다.")
            return jsonify({"error": "No ally with ID 31 found"}), 400

        # [IBSM 불러오기] enemy_list에서 ID 0번 적(탱크) 가져오기
        enemy = enemy_list.find_enemy(0)
        if not enemy:
            write_log("ID 0번 적(탱크)을 찾을 수 없습니다.")
            return jsonify({"error": "No enemy with ID 0 found"}), 400

        # ============================================================================
        # 임무 확인 및 분기 로직
        # ============================================================================

        # 1. 현재 진행 중인 임무 확인
        current_mission = mission_list.get_current_mission()

        write_log(f"🔍 현재 진행 중인 임무 확인 결과: {current_mission}")

        # 2. 진행 중인 임무가 없으면 다음 임무 시작
        if not current_mission:
            # 활성 임무 중 최우선 임무 가져오기
            next_mission = mission_list.get_pending_highest_priority_mission() # 활성 임무 중 우선순위가 가장 높은 임무 검색

            if next_mission and next_mission.status == "pending": # 다음 임무가 존재하고 대기 상태인 경우
                # 임무 시작
                mission_list.start_mission(next_mission.mission_number) # 임무 상태를 'in_progress'로 변경
                current_mission = next_mission
                write_log(f"🎯 새 임무 시작: #{current_mission.mission_number} [{current_mission.mission_type}]")
            else:
                write_log("⚠️ 실행할 임무가 없습니다 - 기본 대기 모드")
                current_mission = None

        # 3. 임무 종류에 따른 분기 처리
        if current_mission:
            write_log(f"📋 현재 임무: #{current_mission.mission_number} [{current_mission.mission_type}] 우선순위:{current_mission.mission_priority}")

            mission_type = current_mission.mission_type

            if mission_type == "hold":
                write_log("대기 임무 진행")
                hold_logic()

            elif mission_type == "defense":
                write_log("방어 임무 진행")
                result = defense_logic(ally, current_mission.target_pos, current_mission.enemy_pos, QE_command, QE_weight, RF_command, RF_weight,
                    WS_command, WS_weight, AD_command, AD_weight, fire_command)
                
                # 결과 받아서 명령 갱신
                QE_command = result["QE_command"]
                QE_weight = result["QE_weight"]
                RF_command = result["RF_command"]
                RF_weight = result["RF_weight"]
                WS_command = result["WS_command"]
                WS_weight = result["WS_weight"]
                AD_command = result["AD_command"]
                AD_weight = result["AD_weight"]
                fire_command = result["fire_command"]

            elif mission_type == "combat":
                write_log("전투 임무 진행")
                # 전투 로직 함수 호출
                result = combat_logic(ally, current_mission.enemy_pos, QE_command, QE_weight, RF_command, RF_weight,
                                      WS_command, WS_weight, AD_command, AD_weight, fire_command)

                # 결과 받아서 명령 갱신
                QE_command = result["QE_command"]
                QE_weight = result["QE_weight"]
                RF_command = result["RF_command"]
                RF_weight = result["RF_weight"]
                WS_command = result["WS_command"]
                WS_weight = result["WS_weight"]
                AD_command = result["AD_command"]
                AD_weight = result["AD_weight"]
                fire_command = result["fire_command"]

            else:
                write_log(f"❓ 알 수 없는 임무 종류: {mission_type}")
        else:
            write_log("⚠️ 임무 없음 - 대기 로직 실행")

        # 기존에 계산된 명령어와 가중치에 따라 행동 결정
        action = {
            "moveWS":  {"command": WS_command, "weight": WS_weight},
            "moveAD":  {"command": AD_command, "weight": AD_weight},
            "turretQE": {"command": QE_command, "weight": QE_weight},
            "turretRF": {"command": RF_command, "weight": RF_weight},
            "fire": fire_command
        }

        write_log(f"get_action()에서 sim으로 전달한 정보: {action}")

        # 명령 전달 후 전역 변수 초기화
        QE_command, QE_weight, RF_command, RF_weight = "", 0.0, "", 0.0
        WS_command, WS_weight, AD_command, AD_weight = "", 0.0, "", 0.0
        fire_command = False

        write_log("✅ get_action() 전역 변수 초기화 완료")

        return jsonify(action)
    finally:
        # 락 해제
        try:
            if acquired_get_action_lock:
                get_action_lock.release()
                write_log("🔓 get_action 락 해제")
        except Exception:
            write_log("🔔 get_action 락 해제 실패")

@app.route('/update_obstacle', methods=['POST'])
def update_obstacle():
    """장애물 정보 업데이트 엔드포인트"""
    write_log("update_obstacle() 호출 받음")

    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'No data received'}), 400
    
    # obstacles 리스트 추출
    obstacles = data.get('obstacles', [])
    
    # 빈 배열은 아예 무시
    if not obstacles:
        write_log("⚠️ 빈 장애물 배열 무시")
        return jsonify({'status': 'ignored', 'message': 'Empty obstacles array ignored'}), 200
    
    write_log("update_obstacle() 적 1번 전차 정보 업데이트 중")
    # 적 전차 정보 업데이트(정지 상태)
    enemy_list.add_or_update_enemy(
        enemy_id=None,
        pos_x=56.7,
        pos_y=10,
        pos_z=121.3,
        body_angle_x=0,
        body_angle_y=0,
        body_angle_z=0,
        unit_type="armored",
        identification_time=global_time,
        speed=enemy_speed,
        threat_level=0.0
    )
    
    unknown_list.clear()  # 기존 장애물 정보 초기화
    write_log(f"obstacle Data: {data}")
    
    # 각 장애물을 UnknownList에 추가
    added_count = 0
    for idx, obstacle in enumerate(obstacles):
        try:
            # 장애물의 중심 좌표 계산
            x_min = obstacle.get('x_min', 0)
            x_max = obstacle.get('x_max', 0)
            z_min = obstacle.get('z_min', 0)
            z_max = obstacle.get('z_max', 0)
            
            # 중심점 계산
            pos_x = (x_min + x_max) / 2.0
            pos_z = (z_min + z_max) / 2.0
            pos_y = 0.0  # 지면 높이

            # 장애물과 플레이어 간의 거리 계산
            obs_distance = math.sqrt((pos_x - player_x) ** 2 + (pos_z - player_z) ** 2)
            write_log(f"장애물 {idx+1} 위치: ({pos_x:.1f}, {pos_y:.1f}, {pos_z:.1f}), 플레이어와 거리: {obs_distance:.1f}m")
            
            # 장애물 크기 계산
            size_x = abs(x_max - x_min)
            size_z = abs(z_max - z_min)
            obstacle_size = max(size_x, size_z)  # 더 큰 값을 크기로 사용
            
            # 장애물의 각도 (기본값 0)
            object_angle_x = 0.0
            object_angle_y = 0.0
            
            # UnknownList에 장애물 추가 (ID는 자동 부여)
            unknown_list.add_or_update_unknown(
                unknown_id=None,  # 자동 ID 부여
                pos_x=pos_x,
                pos_y=pos_y,
                pos_z=pos_z,
                object_angle_x=object_angle_x,
                object_angle_y=object_angle_y,
                unit_type="obstacle",
                identification_time=global_time,
                speed=0.0  # 장애물은 정적이므로 속도 0
            )
            
            added_count += 1
            
        except Exception as e:
            write_log(f"⚠️ 장애물 {idx+1} 추가 실패: {e}")

    
    
    return jsonify({'status': 'success', 'message': 'Obstacle data received'})

@app.route('/update_bullet', methods=['POST'])
def update_bullet():
    write_log("update_bullet() 호출 받음")
    global global_fire_flag, global_replan_required, new_fire_point, global_current_target

    # 1. 현재 진행 중인 임무 확인
    current_mission = mission_list.get_current_mission()

    # 2. 임무 종류에 따른 분기 처리
    if current_mission:
        write_log(f"📋 현재 임무: #{current_mission.mission_number} [{current_mission.mission_type}] 우선순위:{current_mission.mission_priority}")

        mission_type = current_mission.mission_type

        if mission_type == "hold":
            write_log("대기 임무에 대한 사격 판단 로직 진행")
            pass

        elif mission_type == "defense":
            write_log("방어 임무에 대한 사격 판단 로직 진행")
            pass
        elif mission_type == "combat":
            write_log("전투 임무에 대한 사격 판단 로직 진행")
            target_pos = current_mission.enemy_pos # 현재 임무에 대한 타겟 위치 전달

            # 입력 데이터 파싱
            bullet_data = request.get_json()

            # 입력값 검증: bullet_data 존재 여부
            bullet_data_exists = bullet_data is not None
            if not bullet_data_exists:
                return jsonify({
                    'status': 'error',
                    'message': 'No bullet data received.'
                }), 400

            # 값 추출
            bullet_x = bullet_data['x']
            bullet_y = bullet_data['y']
            bullet_z = bullet_data['z']

            write_log(f"수신된 탄환 위치: x={bullet_x}, y={bullet_y}, z={bullet_z}")

            target_x = target_pos['x']
            target_y = target_pos['y']
            target_z = target_pos['z']

            write_log(f"목표 위치: x={target_x}, y={target_y}, z={target_z}")
            # 유클리드 거리 계산
            distance = math.sqrt(
                (bullet_x - target_x) ** 2 +
                (bullet_y - target_y) ** 2 +
                (bullet_z - target_z) ** 2
            )
            """
            IBSM에서 보내야 하는 형식 (발사):
            {
                "type": "fire_event",
                "fire": {
                    "target_tracking_id": 1001,
                    "ally_id": "17TK-101",
                    "class_id": 5
                }
            }
            """

            # 발포 정보 전송
            current_enemy = enemy_list.find_enemy_by_position(pos_x=target_x, pos_y=target_y, pos_z=target_z, unit_type="armored")

            if current_enemy:
                request_data = {
                    'target_tracking_id' : current_enemy.enemy_id,
                    'ally_id': 31  # 아군 전차 ID
                }
                send_fire(request_data)

                write_log(f"거리 계산 결과: distance={distance}")

                # 판정: padding 이내면 명중
                padding = 15.0
                is_within_padding = distance <= padding

                # 명중 시 global_fire_flag 해제
                if is_within_padding:
                    write_log('RESULT: TARGET HIT')
                    # 사망으로 변경
                    current_enemy.status = "destroyed"
                    
                    # 명중 정보 전송
                    """
                    IBSM에서 보내야 하는 형식 (명중 결과):
                    {
                        "type": "hit_result",
                        "data": {
                            "target_tracking_id": 1001,
                            "result": "hit"  # 'hit' | 'miss'
                        }
                    }
                    """
                    request_data = {
                        'target_tracking_id' : current_enemy.enemy_id,
                        'result': 'hit'
                        
                    }
                    send_hit(request_data)

                    write_log(f"적 전차(ID: {current_enemy.enemy_id})가 파괴되었습니다.")
                    # 임무 완료 처리
                    write_log(f"임무 번호 {current_mission.mission_number} 전투 임무 완료 처리 중...")
                    mission_list.complete_mission(current_mission.mission_number)

                    # 관련 변수 초기화
                    global_fire_flag = False  # 사격 모드 최초 비활성화 default 값
                    global_replan_required = True  # TPP 재 계획 플래그, 최초 True로 설정하여, 첫 계획 수립을 유도
                    new_fire_point = None # 사격 불가 시
                    global_current_target = None # 현재 사격 목표
                else:
                    write_log('RESULT: MISS')


                    # 미 명중 정보 전송
                    """
                    IBSM에서 보내야 하는 형식 (미 명중 결과):
                    {
                        "type": "hit_result",
                        "data": {
                            "target_tracking_id": 1001,
                            "result": "hit"  # 'hit' | 'miss'
                        }
                    }
                    """
                    request_data = {
                        'target_tracking_id' : current_enemy.enemy_id,
                        'result': 'miss'

                    }
                    send_hit(request_data)

                # 결과 반환
                return jsonify({
                    'status': 'success',
                    'is_hit': is_within_padding,
                    'distance': distance,
                    'padding': padding
                })
            else: 
                write_log("⚠️ 목표 위치에 해당하는 적 전차를 찾을 수 없습니다.")
        else:
            write_log(f"❓ 알 수 없는 임무 종류: {mission_type}")
    else:
        write_log("⚠️ 임무 없음 - 대기 로직 실행")

@app.route('/api/target', methods=['POST'])
def add_mission():

    global global_mission_number, global_mission_priority

    """
    Frontend에서 목표 위치 받아서 IBSM로 전달
    
    Frontend가 보내는 형식:
    {
        "x": 100.5,
        "z": 200.3,
        "mission": "combat"  # 'defense' | 'combat'
    }
    
    IBSM으로 전달해야 하는 형식 (구현 해야함):
    POST http://127.0.0.1:5000/api/set-target
    { "x": 100.5, "z": 200.3, "mission": "combat" }
    """
    data = request.get_json()

    mission_type = data.get('mission', None)
    pos_x = data.get('x', 0.0)
    pos_z = data.get('z', 0.0)
    
    print(f"\n{'='*60}")
    print(f"[Target] Frontend에서 데이터 수신")
    print(f"   - X: {data.get('x')}")
    print(f"   - Z: {data.get('z')}")
    print(f"   - Mission: {data.get('mission')}")
    print(f"   - 전체 데이터: {data}")
    print(f"{'='*60}\n")

    # 임무 유형 별 임무 추가 진행
    # 1. 새로 배정 받은 임무를 추가
    if mission_type == 'defense':
        # 방어 임무 생성
        mission_list.add_mission(
            mission_number=global_mission_number,
            time=0.0,
            mission_type="defense",
            mission_priority=global_mission_priority,  # 최고 우선순위
            status="pending", # 초기 상태로 설정
            target_pos= {"x":pos_x, "y":0, "z":pos_z},  # 방어 대상 지점
            enemy_pos = None,   # 300, 0.0
            additional_info={"description": "기본 방어 임무 - 적 탐지 및 교전"}
        )

        write_log("[임무 생성] 기본 방어 임무가 성공적으로 생성되었습니다. (ID: 1, 우선순위: 1)")

        global_mission_number += 1
        global_mission_priority += 1


    elif mission_type == 'combat':

        enemy = enemy_list.find_enemy_by_position(pos_x=pos_x, pos_y=0, pos_z=pos_z, unit_type="armored") # 좌표 기반 적 전차 검색 

        if enemy:
            write_log(f"✅ 좌표 기반 적 전차 검색 성공: ID {enemy.enemy_id} 위치 ({enemy.pos_x}, {enemy.pos_y}, {enemy.pos_z})")

            # 전투 임무 생성
            mission_list.add_mission(
                mission_number=global_mission_number,
                time=0.0,
                mission_type="combat",
                mission_priority=global_mission_priority,  # 최고 우선순위
                status="pending", # 초기 상태로 설정
                target_pos= None,
                enemy_pos = {"x":enemy.pos_x, "y":enemy.pos_y, "z":enemy.pos_z},   # 공격 대상 좌표
                additional_info={"description": "기본 전투 임무 - 적 탐지 및 교전"}
            )

            write_log("[임무 생성] 기본 방어 임무가 성공적으로 생성되었습니다. (ID: 1, 우선순위: 1)")

            global_mission_number += 1
            global_mission_priority += 1

    
    return jsonify({"status": "ok", "message": "목표 위치 수신 완료"})

#Endpoint called when the episode starts
@app.route('/init', methods=['GET'])
def init():
    global global_mission_number, global_mission_priority
    config = {
        "startMode": "start",  # Options: "start" or "pause"
        "blStartX": 70,  #Blue Start Position
        "blStartY": 10,
        "blStartZ": 5,
        "rdStartX": 140, #Red Start Position
        "rdStartY": 10,
        "rdStartZ": 280,
        "trackingMode": True,
        "detectMode": False,
        "logMode": True,
        "enemyTracking": False,
        "saveSnapshot": True,
        "saveStereoCamera" : False,
        "saveLog": False,
        "saveLidarData": False,
        "lux": 30000
    }

    # 기본 전투 임무 생성
    mission_list.add_mission(
        mission_number=global_mission_number,
        time=0.0,
        mission_type="defense",
        mission_priority=global_mission_priority,  # 최고 우선순위
        status="pending", # 초기 상태로 설정
        target_pos= {"x":10, "y":0, "z":10},  # 방어 대상 지점
        enemy_pos = None,   # 300, 0.0
        additional_info={"description": "기본 방어 임무 - 적 탐지 및 교전"}
    )

    write_log("[임무 생성] 기본 방어 임무가 성공적으로 생성되었습니다. (ID: 1, 우선순위: 1)")

    global_mission_number += 1
    global_mission_priority += 1

    mission_list.add_mission(
        mission_number=global_mission_number,
        time=0.0,
        mission_type="combat",
        mission_priority=global_mission_priority,  # 최고 우선순위
        status="pending", # 초기 상태로 설정
        target_pos= None,
        enemy_pos = {"x":140, "y":10, "z":280},   # 적 발견 시 자동으로 설정됨
        additional_info={"description": "기본 전투 임무 - 적 탐지 및 교전"}
    )

    write_log("[임무 생성] 기본 전투 임무가 성공적으로 생성되었습니다. (ID: 2, 우선순위: 2)")

    global_mission_number += 1
    global_mission_priority += 1


    mission_list.add_mission(
        mission_number=global_mission_number,
        time=0.0,
        mission_type="combat",
        mission_priority=global_mission_priority,  # 최고 우선순위
        status="pending", # 초기 상태로 설정
        target_pos= None,
        enemy_pos = {"x":56.7, "y":10, "z":121.3},   # 적 발견 시 자동으로 설정됨(56.7, 0.0, 121.3)
        additional_info={"description": "기본 전투 임무 - 적 탐지 및 교전"}
    )

    write_log("[임무 생성] 기본 전투 임무가 성공적으로 생성되었습니다. (ID: 3, 우선순위: 3)")

    global_mission_number += 1
    global_mission_priority += 1

    write_log(f"🛠️ Initialization config sent via /init: {config}")
    return jsonify(config)

# --------------------------------------------------------------------

@app.route('/start', methods=['GET'])
def start():
    write_log("🚀 /start command received")
    return jsonify({"control": ""})

if __name__ == '__main__':
    # app.run(host='0.0.0.0', port=5000) # Simulator API 서버 기동
    socketio.run(app, host='0.0.0.0', port=5000) # Frontend WebSocket 서버 기동
    