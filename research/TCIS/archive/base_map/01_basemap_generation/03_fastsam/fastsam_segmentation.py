"""
FastSAM을 사용한 지형 세그멘테이션
사전학습된 FastSAM 모델로 4개 이미지 자동 세그멘테이션
"""
from ultralytics import FastSAM
from pathlib import Path
import cv2
import numpy as np
import matplotlib.pyplot as plt
import os

class FastSAMSegmentation:
    def __init__(self, model_size='s'):
        """
        FastSAM 모델 초기화
        model_size: 's' (small, 빠름) 또는 'x' (extra large, 정확)
        """
        print(f"FastSAM 모델 로드 중... (크기: {model_size})")
        self.model = FastSAM(f'FastSAM-{model_size}.pt')
        print("모델 로드 완료!")
        
    def segment_image(self, image_path, output_dir="results_fastsam"):
        """단일 이미지 세그멘테이션"""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        img_path = Path(image_path)
        print(f"\n처리 중: {img_path.name}")
        
        # FastSAM 실행
        results = self.model(
            str(image_path),
            device='cpu',  # GPU 있으면 'cuda'로 변경
            retina_masks=True,
            imgsz=1024,
            conf=0.4,
            iou=0.9,
        )
        
        # 원본 이미지 로드
        img = cv2.imread(str(image_path))
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        # 결과 시각화 및 저장
        result_img = results[0].plot()  # 세그멘테이션 결과 그리기
        result_rgb = cv2.cvtColor(result_img, cv2.COLOR_BGR2RGB)
        
        # 저장
        save_path = output_path / f"{img_path.stem}_fastsam.png"
        cv2.imwrite(str(save_path), result_img)
        print(f"저장: {save_path}")
        
        return img_rgb, result_rgb, results[0]
    
    def segment_all_images(self, image_dir=None):
        """모든 이미지 세그멘테이션"""
        if image_dir is None:
            # 현재 파일 기준 상대 경로로 map_images 폴더 접근
            script_dir = os.path.dirname(os.path.abspath(__file__))
            base_map_dir = os.path.join(script_dir, '..', '..')
            image_dir = os.path.join(base_map_dir, 'map_images')
        img_dir = Path(image_dir)
        image_files = list(img_dir.glob("*.PNG")) + list(img_dir.glob("*.png"))
        
        print(f"\n총 {len(image_files)}개 이미지 처리")
        print("=" * 60)
        
        # 결과 저장용
        results_all = []
        
        for img_path in image_files:
            original, segmented, result_data = self.segment_image(img_path)
            results_all.append({
                'name': img_path.name,
                'original': original,
                'segmented': segmented,
                'data': result_data
            })
        
        # 전체 결과 시각화
        self.visualize_all(results_all)
        
        return results_all
    
    def visualize_all(self, results_all):
        """모든 결과를 한 번에 시각화"""
        n_images = len(results_all)
        fig, axes = plt.subplots(n_images, 2, figsize=(14, 5*n_images))
        
        if n_images == 1:
            axes = axes.reshape(1, -1)
        
        for idx, result in enumerate(results_all):
            # 원본
            axes[idx, 0].imshow(result['original'])
            axes[idx, 0].set_title(f"Original: {result['name']}", fontsize=12)
            axes[idx, 0].axis('off')
            
            # 세그멘테이션 결과
            axes[idx, 1].imshow(result['segmented'])
            axes[idx, 1].set_title(f"FastSAM Segmentation", fontsize=12)
            axes[idx, 1].axis('off')
        
        plt.suptitle("FastSAM Terrain Segmentation Results", 
                    fontsize=16, fontweight='bold', y=0.995)
        plt.tight_layout()
        
        # 저장
        save_path = Path("results_fastsam") / "all_results_comparison.png"
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"\n전체 결과 저장: {save_path}")
        
        plt.show()
    
    def print_model_info(self):
        """모델 정보 출력 (포트폴리오용)"""
        print("\n" + "=" * 60)
        print("사용 모델: FastSAM (Fast Segment Anything Model)")
        print("=" * 60)
        print("개발: Ultralytics")
        print("기반: YOLOv8 + SAM (Segment Anything)")
        print("특징:")
        print("  - 실시간 세그멘테이션 가능")
        print("  - CPU에서도 빠른 처리 속도")
        print("  - 사전학습된 모델로 별도 학습 불필요")
        print("  - 다양한 객체 자동 인식 및 분할")
        print("=" * 60)


if __name__ == "__main__":
    # FastSAM 세그멘테이션 실행
    segmenter = FastSAMSegmentation(model_size='s')  # 's' 또는 'x'
    
    # 모델 정보 출력
    segmenter.print_model_info()
    
    # 모든 이미지 처리
    results = segmenter.segment_all_images()
    
    print("\n✅ 세그멘테이션 완료!")
    print(f"결과 저장 위치: results_fastsam/")
