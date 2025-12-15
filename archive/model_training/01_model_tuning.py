# tune_model.py

from ultralytics import YOLO
import json

def tune_hparams():
    # 제공된 모델 구조 파일 사용
    model = YOLO('yolo12n.yaml') # 
    data_yaml = 'data.yaml' 

    print("--- 1. 하이퍼파라미터 튜닝 시작 (iterations=100) ---")

    # 튜닝 실행: 최적의 인자 조합을 탐색합니다.
    tune_results = model.tune(
        data=data_yaml, 
        iterations=100,      
        imgsz=640,
        batch=16, # 튜닝 시 배치 사이즈를 16으로 고정하거나, batch=[8, 16, 32] 같이 리스트로 제공하여 탐색 범위에 포함할 수 있습니다.
        epochs=10,           # 튜닝은 짧은 epoch으로 빠르게 수행 (예시: 10)
        pretrained=False,    # 스크래치 학습 (사전 학습 가중치 사용 안 함)
        project=r'C:\Users\htw02\HDRT_AI\PART2\final_pj\tw\vdrs\model\yolo2\model_train3', # 튜닝 결과 저장 위치
        name='yolo12n_hpo', 
        exist_ok=True
    )

    best_hparams = tune_results.best_args
    print(f"\n✨ 최적의 하이퍼파라미터 조합을 찾았습니다:")
    
    # 튜닝 결과를 JSON 파일로 저장합니다. 
    # 최종 학습에 필요 없는 인자 (예: epochs, batch)는 제외할 수 있지만, 
    # 여기서는 lr0, lrf, optimizer 등이 포함된 결과를 그대로 저장합니다.
    hparam_file = 'best_hparams_yolo12n.json'
    with open(hparam_file, 'w') as f:
        # 딕셔너리를 직접 저장
        json.dump(best_hparams, f, indent=4)
        
    print(f"✅ 최적 하이퍼파라미터가 {hparam_file} 파일에 저장되었습니다.")
    print(best_hparams)

if __name__ == "__main__":
    tune_hparams()