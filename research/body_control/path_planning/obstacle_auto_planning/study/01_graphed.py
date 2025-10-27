
# OpenMP 중복 오류 임시 우회 (libiomp5md.dll)
import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import matplotlib.pyplot as plt
import numpy as np

def visualize_obstacle_pattern(obstacles):
    """
    장애물 좌표를 before/after 그래프로 시각화
    
    Args:
        obstacles: 장애물 리스트 [{'x_min': ..., 'x_max': ..., 'z_min': ..., 'z_max': ...}, ...]
    """
    if len(obstacles) != 9:
        print(f"⚠️ 장애물 개수가 9개가 아닙니다. 현재: {len(obstacles)}개")
        return
    
    # 1. group1에 9개 장애물 저장 (원본 순서)
    group1 = obstacles.copy()
    
    # 2. z_max 기준으로 그룹 분류
    a_group = []  # z_max <= 100
    b_group = []  # 100 < z_max <= 200  
    c_group = []  # z_max > 200
    
    # 원본 인덱스 저장
    for i, obstacle in enumerate(group1):
        obstacle['original_index'] = i + 1
        z_max = obstacle['z_max']
        if z_max <= 100:
            a_group.append(obstacle)
        elif z_max <= 200:
            b_group.append(obstacle)
        else:
            c_group.append(obstacle)
    
    # 3. 정렬
    a_group.sort(key=lambda x: x['x_max'])
    c_group.sort(key=lambda x: x['x_max'])
    b_group.sort(key=lambda x: x['x_max'], reverse=True)
    
    # 4. group2 생성 (정렬된 순서)
    group2 = a_group + b_group + c_group
    
    # 5. 시각화
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    
    # Before 그래프 (원본 순서)
    x_coords_before = [obs['x_max'] for obs in group1]
    z_coords_before = [obs['z_max'] for obs in group1]
    
    ax1.scatter(x_coords_before, z_coords_before, c='red', s=100, alpha=0.7)
    for i, (x, z) in enumerate(zip(x_coords_before, z_coords_before)):
        ax1.annotate(str(i+1), (x, z), xytext=(5, 5), textcoords='offset points', 
                    fontsize=12, fontweight='bold')
    
    ax1.set_xlabel('X_max')
    ax1.set_ylabel('Z_max')
    ax1.set_title('Before (입력 순서)')
    ax1.grid(True, alpha=0.3)
    
    # After 그래프 (정렬된 순서)
    x_coords_after = [obs['x_max'] for obs in group2]
    z_coords_after = [obs['z_max'] for obs in group2]
    
    ax2.scatter(x_coords_after, z_coords_after, c='blue', s=100, alpha=0.7)
    for i, obs in enumerate(group2):
        x, z = obs['x_max'], obs['z_max']
        original_idx = obs['original_index']
        new_idx = i + 1
        # (원본순서, 정렬후순서) 표시
        ax2.annotate(f'({original_idx},{new_idx})', (x, z), xytext=(5, 5), 
                    textcoords='offset points', fontsize=10, fontweight='bold')
    
    ax2.set_xlabel('X_max')
    ax2.set_ylabel('Z_max')
    ax2.set_title('After (지그재그 패턴 정렬)')
    ax2.grid(True, alpha=0.3)
    
    # 레이아웃 조정
    plt.tight_layout()
    
    # 그래프 저장 (여러 형식으로 저장)
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # PNG 고화질 저장
    plt.savefig('obstacle_pattern_visualization.png', dpi=300, bbox_inches='tight', 
                facecolor='white', edgecolor='none')
    
    # 타임스탬프가 포함된 파일명으로도 저장
    plt.savefig(f'obstacle_pattern_{timestamp}.png', dpi=300, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    
    # PDF 형식으로도 저장 (벡터 그래픽)
    plt.savefig(f'obstacle_pattern_{timestamp}.pdf', bbox_inches='tight',
                facecolor='white', edgecolor='none')
    
    # 서버/멀티스레드 환경에서는 plt.show()를 호출하지 않습니다.
    # plt.show()  # (로컬/테스트 시에만 사용)
    print("📊 시각화 완료!")
    print(f"   - obstacle_pattern_visualization.png (기본 파일)")
    print(f"   - obstacle_pattern_{timestamp}.png (타임스탬프 파일)")
    print(f"   - obstacle_pattern_{timestamp}.pdf (PDF 형식)")
    print("   파일들로 저장되었습니다.")
    return group2

def print_pattern_analysis(obstacles):
    """패턴 분석 결과 출력"""
    if len(obstacles) != 9:
        return
    
    print("\n🔍 패턴 분석:")
    print(f"{'순서':<4} {'X_max':<10} {'Z_max':<10} {'그룹':<6}")
    print("-" * 35)
    
    for i, obs in enumerate(obstacles, 1):
        z_max = obs['z_max']
        if z_max <= 100:
            group = "A그룹"
        elif z_max <= 200:
            group = "B그룹"  
        else:
            group = "C그룹"
        
        print(f"{i:<4} {obs['x_max']:<10.2f} {obs['z_max']:<10.2f} {group:<6}")