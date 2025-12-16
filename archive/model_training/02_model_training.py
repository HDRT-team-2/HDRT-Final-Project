# train_final.py


from ultralytics import YOLO
import yaml


def train_with_best_hparams():
    model = YOLO('yolo12n.yaml')
    data_yaml = 'data.yaml'

    # 1. 튜닝 결과 불러오기 (YAML)
    hparam_file = r'yolo12n_hpo/best_hyperparameters.yaml'
    try:
        with open(hparam_file, 'r', encoding='utf-8') as f:
            best_hparams = yaml.safe_load(f)
        print(f"✅ {hparam_file}에서 최적의 하이퍼파라미터 설정을 불러왔습니다.")
        print(best_hparams)
    except FileNotFoundError:
        print(f"🚨 {hparam_file} 파일이 없습니다. 수동으로 기본값을 사용합니다.")
        best_hparams = {'optimizer': 'AdamW', 'lr0': 0.001, 'lrf': 0.01}

    # 2. 최종 학습 인자 설정
    final_train_args = {
        'data': data_yaml,
        'epochs': 1000,          # 최종 목표 epoch 수
        'imgsz': 640,
        'batch': 16, 
        'pretrained': False,
        'patience': 50, # validation loss 개선 없을 때 50 epoch 후 early stopping
        'save_period': 10, # 
        'project': r'C:\Users\htw02\HDRT_AI\PART2\final_pj\tw\vdrs\model\yolo2\model_final_train',
        'name': '',
        'exist_ok': True,
    }

    # 3. 튜닝된 하이퍼파라미터 적용
    final_train_args.update(best_hparams)

    print("\n--- 2. 최적의 인자를 사용하여 최종 학습 시작 (1000 epochs) ---")

    # 최종 학습 실행
    model.train(**final_train_args)

    print("--- 2. COCO 사전학습 없이 최적의 설정으로 최종 학습 완료! ---")

if __name__ == "__main__":
    train_with_best_hparams()