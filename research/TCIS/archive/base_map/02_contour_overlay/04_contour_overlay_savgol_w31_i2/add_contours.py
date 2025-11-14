"""
베이스맵에 등고선 추가
CSV 데이터에서 고도 정보를 읽어 등고선 오버레이
"""
import numpy as np
import pandas as pd
import cv2
import matplotlib.pyplot as plt
from pathlib import Path
from scipy.interpolate import griddata

class ContourOverlay:
    def __init__(self):
        self.contour_color = (100, 100, 100)  # 등고선 색상 (회색)
        self.contour_thickness = 1
        
    def load_altitude_data(self, csv_path):
        """CSV에서 고도 데이터 로드"""
        print(f"\n고도 데이터 로드 중: {Path(csv_path).name}")
        
        df = pd.read_csv(csv_path)
        
        # X, Z, Y(고도) 추출
        x = df['Player_Pos_X'].values
        z = df['Player_Pos_Z'].values
        altitude = df['Player_Pos_Y'].values
        
        print(f"데이터 포인트: {len(x):,}개")
        print(f"고도 범위: {altitude.min():.1f} ~ {altitude.max():.1f}")
        
        return x, z, altitude
    
    def create_altitude_grid(self, x, z, altitude, image_shape):
        """불규칙한 데이터를 그리드로 보간"""
        height, width = image_shape[:2]
        
        print(f"\n그리드 생성 중... ({width}x{height})")
        
        # 이미지 좌표계로 변환
        x_min, x_max = x.min(), x.max()
        z_min, z_max = z.min(), z.max()
        
        # 그리드 생성
        grid_x = np.linspace(x_min, x_max, width)
        grid_z = np.linspace(z_min, z_max, height)
        grid_x, grid_z = np.meshgrid(grid_x, grid_z)
        
        # 고도 보간
        print("고도 보간 중...")
        grid_altitude = griddata(
            (x, z), altitude, 
            (grid_x, grid_z), 
            method='linear',
            fill_value=altitude.mean()
        )
        
        # Savitzky-Golay 필터 적용 (곡선 형태 유지하면서 노이즈 제거)
        from scipy.signal import savgol_filter
        print("Savitzky-Golay 필터 적용 중...")
        
        window_length = 31  # 윈도우 크기 (홀수, 11/21/31 등)
        polyorder = 3       # 다항식 차수 (2~3 권장)
        
        # 각 행에 대해 필터 적용
        for i in range(height):
            grid_altitude[i, :] = savgol_filter(grid_altitude[i, :], 
                                                window_length=window_length, 
                                                polyorder=polyorder,
                                                mode='nearest')
        
        # 각 열에 대해 필터 적용
        for j in range(width):
            grid_altitude[:, j] = savgol_filter(grid_altitude[:, j], 
                                                window_length=window_length, 
                                                polyorder=polyorder,
                                                mode='nearest')
                
        # 0.5 단위로 반올림
        print("고도 반올림 중 (0.5 단위)...")
        grid_altitude = np.round(grid_altitude * 2) / 2
        
        return grid_altitude
    
    def draw_contours(self, basemap, altitude_grid, interval=5, label_interval=10):
        """
        베이스맵에 등고선 그리기
        
        Args:
            basemap: 베이스맵 이미지 (RGB)
            altitude_grid: 고도 그리드 데이터
            interval: 등고선 간격 (기본 5)
            label_interval: 주등고선 간격 (기본 10, 굵게 표시)
        """
        print(f"\n등고선 그리기 (간격: {interval})")
        
        result = basemap.copy()
        height, width = basemap.shape[:2]
        
        # 고도 데이터 통계 확인
        alt_min = np.nanmin(altitude_grid)
        alt_max = np.nanmax(altitude_grid)
        alt_mean = np.nanmean(altitude_grid)
        alt_std = np.nanstd(altitude_grid)
        
        print(f"고도 통계:")
        print(f"  최소: {alt_min:.2f}m")
        print(f"  최대: {alt_max:.2f}m")
        print(f"  평균: {alt_mean:.2f}m")
        print(f"  표준편차: {alt_std:.2f}m")
        
        # 등고선 레벨 계산
        levels = np.arange(
            np.floor(alt_min / interval) * interval,
            np.ceil(alt_max / interval) * interval + interval,
            interval
        )
        
        print(f"등고선 레벨: {len(levels)}개 ({alt_min:.1f} ~ {alt_max:.1f})")
        print(f"레벨 값: {levels}")
        
        # matplotlib로 등고선 계산
        fig, ax = plt.subplots(figsize=(width/100, height/100), dpi=100)
        ax.set_xlim(0, width)
        ax.set_ylim(0, height)
        ax.axis('off')
        
        # 등고선 그리기
        contours = ax.contour(
            altitude_grid,
            levels=levels,
            colors='black',
            linewidths=0.5,
            extent=[0, width, 0, height]
        )
        
        # 주등고선 강조
        major_levels = levels[levels % label_interval == 0]
        if len(major_levels) > 0:
            major_contours = ax.contour(
                altitude_grid,
                levels=major_levels,
                colors='black',
                linewidths=1.5,
                extent=[0, width, 0, height]
            )
            # 레이블 추가 (고도 표시)
            labels = ax.clabel(
                major_contours, 
                inline=True,           # 선 위에 표시
                inline_spacing=50,     # 레이블 간격 (넓게)
                fontsize=12,           # 글씨 크기 증가
                fmt='%.0fm',           # 포맷 (소수점 없이)
                colors='red'           # 빨간색으로 눈에 띄게
            )
            # 레이블에 흰색 배경 추가
            for label in labels:
                label.set_bbox(dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='none', alpha=0.8))
                label.set_fontweight('bold')  # 굵은 글씨
        
        plt.tight_layout(pad=0)
        
        # matplotlib figure를 임시 파일로 저장 후 읽기
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            tmp_path = tmp.name
        
        plt.savefig(tmp_path, dpi=100, bbox_inches='tight', pad_inches=0)
        plt.close(fig)
        
        # 저장된 이미지 읽기
        contour_img = cv2.imread(tmp_path)
        contour_img = cv2.cvtColor(contour_img, cv2.COLOR_BGR2RGB)
        os.unlink(tmp_path)  # 임시 파일 삭제
        
        # 크기 조정
        if contour_img.shape[:2] != (height, width):
            contour_img = cv2.resize(contour_img, (width, height))
        
        # 등고선만 추출 (검은색 부분)
        contour_mask = cv2.cvtColor(contour_img, cv2.COLOR_RGB2GRAY) < 250
        
        # 베이스맵에 오버레이
        result[contour_mask] = self.contour_color
        
        return result
    
    def add_contours_to_basemap(self, basemap_path, csv_path, output_path=None, 
                                interval=5, label_interval=10):
        """베이스맵에 등고선 추가 (전체 프로세스)"""
        
        # 베이스맵 로드
        basemap_path = Path(basemap_path)
        basemap = cv2.imread(str(basemap_path.absolute()))
        
        if basemap is None:
            print(f"오류: 이미지를 불러올 수 없습니다: {basemap_path}")
            return None, None
        
        basemap = cv2.cvtColor(basemap, cv2.COLOR_BGR2RGB)
        
        print(f"베이스맵 크기: {basemap.shape}")
        
        # 고도 데이터 로드
        x, z, altitude = self.load_altitude_data(csv_path)
        
        # 그리드 생성
        altitude_grid = self.create_altitude_grid(x, z, altitude, basemap.shape)
        
        # 등고선 그리기
        result = self.draw_contours(basemap, altitude_grid, interval, label_interval)
        
        # 저장
        if output_path is None:
            # 현재 스크립트가 있는 폴더의 results 디렉토리에 저장
            script_dir = Path(__file__).parent
            results_dir = script_dir / "results"
            results_dir.mkdir(exist_ok=True)
            base_name = basemap_path.stem
            output_path = results_dir / f"{base_name}_with_contours.png"
        else:
            output_path = Path(output_path)
        
        cv2.imwrite(str(output_path.absolute()), cv2.cvtColor(result, cv2.COLOR_RGB2BGR))
        print(f"\n저장: {output_path}")
        
        return result, altitude_grid
    
    def process_all_basemaps(self, basemap_dir=None, 
                            altitude_dir=None):
        """모든 베이스맵에 등고선 추가"""
        import os
        if basemap_dir is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            contour_overlay_dir = os.path.dirname(script_dir)
            basemap_dir = os.path.join(contour_overlay_dir, 'basemaps')
        if altitude_dir is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            base_map_dir = os.path.join(script_dir, '..', '..')
            altitude_dir = os.path.join(base_map_dir, 'map_altitude_300')
        basemap_path = Path(basemap_dir)
        altitude_path = Path(altitude_dir)
        
        # 베이스맵 파일 찾기
        basemap_files = sorted(basemap_path.glob("*_basemap.png"))
        
        print("=" * 60)
        print("베이스맵에 등고선 추가")
        print("=" * 60)
        print(f"\n베이스맵: {len(basemap_files)}개")
        
        results = []
        
        for basemap_file in basemap_files:
            # 해당하는 CSV 파일 찾기
            base_name = basemap_file.stem.replace("_basemap", "")
            
            # 맵 이름 추출 (공통 단어 찾기)
            # 예: "01_forest_and_river" -> ["forest", "and", "river"]
            name_parts = base_name.split('_')[1:]  # 번호 제외
            
            # CSV 파일 중에서 매칭되는 것 찾기
            csv_file = None
            for csv_candidate in altitude_path.glob("*.csv"):
                csv_name = csv_candidate.stem.lower()
                # 맵 이름의 주요 단어들이 CSV 파일명에 포함되어 있는지 확인
                if all(part.lower() in csv_name for part in name_parts if len(part) > 2):
                    csv_file = csv_candidate
                    break
            
            if csv_file is None:
                print(f"\n⚠️  {basemap_file.name}에 대한 CSV 파일을 찾을 수 없습니다.")
                print(f"   찾은 키워드: {name_parts}")
                continue
            
            print(f"\n{'='*60}")
            print(f"처리 중: {basemap_file.name}")
            print(f"고도 데이터: {csv_file.name}")
            print(f"{'='*60}")
            
            result, grid = self.add_contours_to_basemap(
                basemap_file, csv_file,
                interval=2, label_interval=10  # 2.5m 간격 (소수점 가능)
            )
            
            results.append({
                'name': basemap_file.name,
                'result': result,
                'altitude': grid
            })
        
        # 결과 시각화
        self.visualize_results(results, basemap_path)
        
        return results
    
    def visualize_results(self, results, output_dir):
        """결과 시각화"""
        n = len(results)
        fig, axes = plt.subplots(n, 1, figsize=(12, 6*n))
        
        if n == 1:
            axes = [axes]
        
        for idx, result in enumerate(results):
            axes[idx].imshow(result['result'])
            axes[idx].set_title(f"Base Map with Contours: {result['name']}", fontsize=14)
            axes[idx].axis('off')
        
        plt.tight_layout()
        
        # 현재 스크립트가 있는 폴더의 results 디렉토리에 저장
        script_dir = Path(__file__).parent
        results_dir = script_dir / "results"
        results_dir.mkdir(exist_ok=True)
        save_path = results_dir / "all_basemaps_with_contours.png"
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"\n전체 결과 저장: {save_path}")
        
        plt.show()


if __name__ == "__main__":
    overlay = ContourOverlay()
    
    print("\n등고선 오버레이")
    print("1. 단일 베이스맵에 등고선 추가")
    print("2. 모든 베이스맵에 등고선 추가")
    
    choice = input("\n선택 (1-2): ").strip()
    
    if choice == "1":
        basemap = input("베이스맵 경로: ").strip()
        csv = input("CSV 경로: ").strip()
        overlay.add_contours_to_basemap(basemap, csv)
    elif choice == "2":
        overlay.process_all_basemaps()
    else:
        print("잘못된 입력")
