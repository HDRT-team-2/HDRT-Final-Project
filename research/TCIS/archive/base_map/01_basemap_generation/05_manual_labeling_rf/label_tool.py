"""
간단한 라벨링 도구 - 베이스맵용
마우스로 드래그해서 물/숲/도로/사막 등을 라벨링
"""
import cv2
import numpy as np
from pathlib import Path

class SimpleLabelTool:
    def __init__(self, image_path):
        img = cv2.imread(str(image_path))
        if img is None:
            raise ValueError(f"이미지를 불러올 수 없습니다: {image_path}")
        
        self.original = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        self.display = self.original.copy()
        self.mask = np.zeros(self.original.shape[:2], dtype=np.uint8)
        
        self.labels = {
            1: {"name": "물", "color": (100, 150, 255), "key": "1"},
            2: {"name": "돌", "color": (120, 120, 120), "key": "2"},
            3: {"name": "건물", "color": (200, 150, 150), "key": "3"},
            4: {"name": "길", "color": (180, 180, 180), "key": "4"},
            5: {"name": "숲", "color": (100, 200, 100), "key": "5"},
            6: {"name": "땅", "color": (250, 233, 210), "key": "6"}
        }
        
        self.current_label = 1
        self.brush_size = 20
        self.drawing = False
        
    def mouse_callback(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drawing = True
            self.paint(x, y)
        elif event == cv2.EVENT_MOUSEMOVE and self.drawing:
            self.paint(x, y)
        elif event == cv2.EVENT_LBUTTONUP:
            self.drawing = False
    
    def paint(self, x, y):
        # 마스크에 라벨 그리기
        cv2.circle(self.mask, (x, y), self.brush_size, self.current_label, -1)
        self.update_display()
    
    def update_display(self):
        # 원본 + 반투명 오버레이
        self.display = self.original.copy()
        
        for label_id, info in self.labels.items():
            mask_region = (self.mask == label_id)
            if np.any(mask_region):
                self.display[mask_region] = (
                    self.original[mask_region] * 0.5 + 
                    np.array(info["color"]) * 0.5
                ).astype(np.uint8)
        
        # BGR로 변환
        display_bgr = cv2.cvtColor(self.display, cv2.COLOR_RGB2BGR)
        
        # UI 텍스트
        label_info = self.labels.get(self.current_label, {"name": "지우개 (배경)", "key": "0"})
        cv2.putText(display_bgr, f"Label: {label_info['name']}", 
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.putText(display_bgr, f"Brush: {self.brush_size} (+/- to change)", 
                   (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(display_bgr, "S: Save | Q: Quit | C: Clear", 
                   (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        cv2.imshow('Labeling Tool', display_bgr)
    
    def run(self):
        cv2.namedWindow('Labeling Tool')
        cv2.setMouseCallback('Labeling Tool', self.mouse_callback)
        
        self.update_display()
        
        print("\n=== 조작법 ===")
        print("1-6: 라벨 선택 (1:물, 2:돌, 3:건물, 4:길, 5:숲 , 6:땅)")
        print("0: 지우개 (배경으로 되돌림)")
        print("+/-: 브러시 크기 조절")
        print("마우스 드래그: 라벨링")
        print("C: 전체 지우기")
        print("S: 저장")
        print("Q: 종료\n")
        
        while True:
            key = cv2.waitKey(1) & 0xFF
            
            # 라벨 선택
            if ord('1') <= key <= ord('6'):
                self.current_label = key - ord('0')
                self.update_display()
                print(f"라벨 변경: {self.labels[self.current_label]['name']}")
            elif key == ord('0'):
                self.current_label = 0
                self.update_display()
                print(f"라벨 변경: 지우개 (배경)")
            
            # 브러시 크기
            elif key == ord('+') or key == ord('='):
                self.brush_size = min(100, self.brush_size + 5)
                self.update_display()
            elif key == ord('-') or key == ord('_'):
                self.brush_size = max(5, self.brush_size - 5)
                self.update_display()
            
            # 전체 지우기
            elif key == ord('c') or key == ord('C'):
                self.mask = np.zeros_like(self.mask)
                self.update_display()
                print("라벨 초기화")
            
            # 저장
            elif key == ord('s') or key == ord('S'):
                cv2.destroyAllWindows()
                return self.mask
            
            # 종료
            elif key == ord('q') or key == ord('Q'):
                cv2.destroyAllWindows()
                return None
        
        return None


def main():
    """라벨링 작업 시작"""
    image_dir = Path("map_images")
    label_dir = Path("labeled_masks")
    label_dir.mkdir(exist_ok=True)
    
    # 이미지 파일 찾기
    image_files = sorted(list(image_dir.glob("*.PNG")) + list(image_dir.glob("*.png")))
    
    print(f"\n발견된 이미지: {len(image_files)}개")
    for i, img in enumerate(image_files):
        print(f"  {i+1}. {img.name}")
    
    print("\n라벨링할 이미지를 선택하세요 (번호 입력, 전체는 'all'):")
    choice = input("> ").strip()
    
    if choice.lower() == 'all':
        selected = image_files
    else:
        try:
            idx = int(choice) - 1
            selected = [image_files[idx]]
        except:
            print("잘못된 입력")
            return
    
    # 라벨링 시작
    for img_path in selected:
        print(f"\n{'='*60}")
        print(f"라벨링: {img_path.name}")
        print(f"{'='*60}")
        
        # 기존 마스크가 있으면 불러오기
        mask_path = label_dir / f"{img_path.stem}_mask.npy"
        
        tool = SimpleLabelTool(img_path)
        
        if mask_path.exists():
            print(f"기존 마스크 발견: {mask_path.name}")
            load = input("불러오기? (y/n): ").strip().lower()
            if load == 'y':
                tool.mask = np.load(mask_path)
        
        result_mask = tool.run()
        
        if result_mask is not None:
            # 마스크 저장
            np.save(mask_path, result_mask)
            print(f"✅ 저장: {mask_path}")
            
            # 시각화 이미지도 저장
            vis_img = tool.original.copy()  # 배경은 원본 이미지 사용
            for label_id, info in tool.labels.items():
                vis_img[result_mask == label_id] = info["color"]
            
            vis_path = label_dir / f"{img_path.stem}_visual.png"
            cv2.imwrite(str(vis_path), cv2.cvtColor(vis_img, cv2.COLOR_RGB2BGR))
            print(f"✅ 시각화 저장: {vis_path}")
        else:
            print("❌ 저장 안 함")


if __name__ == "__main__":
    main()
