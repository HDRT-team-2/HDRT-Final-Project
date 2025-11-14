"""
베이스맵 생성용 세그멘테이션 모델 학습
간단한 CNN 기반 픽셀 분류기
"""
import numpy as np
import cv2
from pathlib import Path
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
import joblib

class BaseMapSegmenter:
    def __init__(self):
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=15,
            random_state=42,
            n_jobs=-1,
            verbose=1
        )
        # 라벨 정보
        self.labels = {
            0: {"name": "배경", "color": (209, 209, 209)},
            1: {"name": "물", "color": (105, 195, 255)},
            2: {"name": "돌", "color": (99, 99, 99)},
            3: {"name": "건물", "color": (179, 179, 179)},
            4: {"name": "길", "color": (255, 255, 255)},
            5: {"name": "숲", "color": (141, 201, 141)},
            6: {"name": "땅", "color": (209, 209, 209)},
        }
    
    def extract_features(self, img_rgb):
        """픽셀별 특징 추출 (RGB + HSV + 주변 정보)"""
        h, w = img_rgb.shape[:2]
        img_hsv = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2HSV)
        
        # 간단한 특징: RGB + HSV
        features = np.concatenate([
            img_rgb.reshape(-1, 3),
            img_hsv.reshape(-1, 3)
        ], axis=1)
        
        return features
    
    def load_training_data(self, image_dir=None, mask_dir=None):
        """라벨링된 데이터 로드"""
        import os
        if image_dir is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            base_map_dir = os.path.join(script_dir, '..', '..')
            image_dir = os.path.join(base_map_dir, 'map_images')
        if mask_dir is None:
            mask_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'labeled_masks')
        img_path = Path(image_dir)
        mask_path = Path(mask_dir)
        
        all_features = []
        all_labels = []
        
        mask_files = list(mask_path.glob("*_mask.npy"))
        print(f"\n라벨 데이터: {len(mask_files)}개")
        
        for mask_file in mask_files:
            img_name = mask_file.stem.replace("_mask", "")
            
            # 이미지 찾기
            img_file = None
            for ext in ['.PNG', '.png']:
                candidate = img_path / f"{img_name}{ext}"
                if candidate.exists():
                    img_file = candidate
                    break
            
            if img_file is None:
                continue
            
            print(f"\n로드 중: {img_file.name}")
            
            # 이미지 및 마스크 로드
            img = cv2.imread(str(img_file))
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            mask = np.load(mask_file)
            
            # 특징 추출
            features = self.extract_features(img_rgb)
            labels = mask.flatten()
            
            # 라벨링된 픽셀만 사용
            labeled_idx = labels > 0
            
            all_features.append(features[labeled_idx])
            all_labels.append(labels[labeled_idx])
            
            print(f"  라벨링된 픽셀: {labeled_idx.sum():,}개")
            for label_id in np.unique(labels[labeled_idx]):
                count = (labels[labeled_idx] == label_id).sum()
                print(f"    {self.labels[label_id]['name']}: {count:,}개")
        
        X = np.vstack(all_features)
        y = np.concatenate(all_labels)
        
        print(f"\n총 학습 데이터: {len(X):,}개 픽셀")
        
        return X, y
    
    def train(self):
        """모델 학습"""
        print("=" * 60)
        print("베이스맵 세그멘테이션 모델 학습")
        print("=" * 60)
        
        # 데이터 로드
        X, y = self.load_training_data()
        
        # 학습/테스트 분할
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )
        
        print(f"\n학습 데이터: {len(X_train):,}개")
        print(f"테스트 데이터: {len(X_test):,}개")
        
        # 모델 학습
        print("\n학습 시작...")
        self.model.fit(X_train, y_train)
        
        # 평가
        train_score = self.model.score(X_train, y_train)
        test_score = self.model.score(X_test, y_test)
        
        print(f"\n학습 정확도: {train_score:.3f}")
        print(f"테스트 정확도: {test_score:.3f}")
        
        # 모델 저장
        model_dir = Path("models")
        model_dir.mkdir(exist_ok=True)
        model_path = model_dir / "5차-sam_03/models/basemap_model.pkl"
        joblib.dump(self.model, model_path)
        
        print(f"\n모델 저장: {model_path}")
        
        return True
    
    def predict(self, image_path, model_path=None):
        """이미지 예측"""
        # 기본 경로: 스크립트와 같은 폴더의 models/basemap_model.pkl
        if model_path is None:
            script_dir = Path(__file__).parent
            model_path = script_dir / "models" / "basemap_model.pkl"
        
        # 모델 로드
        if Path(model_path).exists():
            self.model = joblib.load(model_path)
            print(f"모델 로드: {model_path}")
        else:
            print(f"오류: 모델 파일이 없습니다: {model_path}")
            print(f"현재 작업 디렉토리: {Path.cwd()}")
            return None
        
        # 이미지 로드
        img = cv2.imread(str(image_path))
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w = img_rgb.shape[:2]
        
        print(f"\n예측 중: {Path(image_path).name}")
        
        # 특징 추출
        features = self.extract_features(img_rgb)
        
        # 예측
        predictions = self.model.predict(features)
        pred_map = predictions.reshape(h, w)
        
        # 베이스맵 생성 (색상 적용)
        basemap = np.zeros((h, w, 3), dtype=np.uint8)
        for label_id, info in self.labels.items():
            basemap[pred_map == label_id] = info["color"]
        
        return img_rgb, pred_map, basemap
    
    def create_all_basemaps(self, image_dir=None):
        """모든 이미지에 대해 베이스맵 생성"""
        import os
        if image_dir is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            base_map_dir = os.path.join(script_dir, '..', '..')
            image_dir = os.path.join(base_map_dir, 'map_images')
        img_path = Path(image_dir)
        result_dir = Path("basemaps")
        result_dir.mkdir(exist_ok=True)
        
        image_files = sorted(list(img_path.glob("*.PNG")) + list(img_path.glob("*.png")))
        
        print("\n" + "=" * 60)
        print("베이스맵 생성")
        print("=" * 60)
        
        results = []
        
        for img_file in image_files:
            original, pred_map, basemap = self.predict(img_file)
            
            if basemap is None:
                continue
            
            # 베이스맵 저장
            basemap_path = result_dir / f"{img_file.stem}_basemap.png"
            cv2.imwrite(str(basemap_path), cv2.cvtColor(basemap, cv2.COLOR_RGB2BGR))
            print(f"저장: {basemap_path}")
            
            results.append({
                'name': img_file.name,
                'original': original,
                'basemap': basemap,
                'pred_map': pred_map
            })
        
        # 시각화
        self.visualize_results(results, result_dir)
        
        return results
    
    def visualize_results(self, results, result_dir):
        """결과 시각화"""
        n = len(results)
        fig, axes = plt.subplots(n, 2, figsize=(14, 5*n))
        
        if n == 1:
            axes = axes.reshape(1, -1)
        
        for idx, result in enumerate(results):
            # 원본
            axes[idx, 0].imshow(result['original'])
            axes[idx, 0].set_title(f"Original: {result['name']}", fontsize=12)
            axes[idx, 0].axis('off')
            
            # 베이스맵
            axes[idx, 1].imshow(result['basemap'])
            axes[idx, 1].set_title("Base Map", fontsize=12)
            axes[idx, 1].axis('off')
        
        plt.suptitle("Base Map Generation Results", fontsize=16, fontweight='bold')
        plt.tight_layout()
        
        save_path = result_dir / "all_basemaps_comparison.png"
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"\n전체 비교 저장: {save_path}")
        
        plt.show()
    
    def print_info(self):
        """모델 정보 출력 (포트폴리오용)"""
        print("\n" + "=" * 60)
        print("베이스맵 생성 시스템")
        print("=" * 60)
        print("모델: Random Forest Classifier")
        print("특징: RGB + HSV 색상 정보")
        print("분류 클래스:")
        for label_id, info in self.labels.items():
            print(f"  {label_id}: {info['name']} - RGB{info['color']}")
        print("=" * 60)


if __name__ == "__main__":
    segmenter = BaseMapSegmenter()
    
    print("\n베이스맵 생성 시스템")
    print("1. 모델 학습")
    print("2. 베이스맵 생성")
    print("3. 모델 정보")
    
    choice = input("\n선택 (1-3): ").strip()
    
    if choice == "1":
        segmenter.train()
        print("\n✅ 학습 완료! 이제 '2'를 선택하여 베이스맵을 생성할 수 있습니다.")
    elif choice == "2":
        segmenter.create_all_basemaps()
        print("\n✅ 베이스맵 생성 완료! 'basemaps/' 폴더를 확인하세요.")
    elif choice == "3":
        segmenter.print_info()
    else:
        print("잘못된 입력")
