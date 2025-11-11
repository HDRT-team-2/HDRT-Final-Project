"""
목적 : 폴더 구조로 정리된 영상(.mp4)들을 자동으로 프레임 이미지(.jpg)로 
변환하고, 규칙적인 파일명(prefix)과 디렉터리 구조로 저장한다. 이떄의 폴더저장은 소문자로 저장 
"""
import os
import subprocess
import sys
import shutil
from concurrent.futures import ThreadPoolExecutor
import multiprocessing

# settings.py 가 프로젝트 한 단계 위에 있다고 가정
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from settings import INPUT_DIR, OUTPUT_DIR, FRAME_INTERVAL


def extract_frames_from_mp4(mp4_path, save_dir, interval):
    """
    하나의 mp4 파일에서 일정 간격으로 프레임을 추출해 save_dir 에 저장한다.
    save_dir 은 이미 [맵이름]/[Obstacle이름] 까지 만들어져 있어야 한다.
    """
    os.makedirs(save_dir, exist_ok=True)

    command = [
        "ffmpeg",
        "-threads", "16",
        "-i", mp4_path,
        "-vf", f"fps=1/{interval}",
        os.path.join(save_dir, "frame_%04d.jpg"),
    ]
    # ffmpeg 실행
    subprocess.run(command, check=True)


def main():
    # 1. 입력 폴더 존재 확인
    if not os.path.exists(INPUT_DIR):
        print(f"입력 폴더가 존재하지 않습니다: {INPUT_DIR}")
        return

    # 2. 출력 폴더 초기화
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 3. INPUT_DIR 아래를 전부 돌면서 mp4 파일을 찾는다
    #    이 때 경로에서 "맵 이름"과 "Obstacle 이름"을 뽑아낼 거다.
    jobs = []  # (mp4_path, save_dir) 튜플을 쌓아두는 리스트

    for root, dirs, files in os.walk(INPUT_DIR):
        for f in files:
            if not f.lower().endswith(".mp4"):
                continue

            mp4_path = os.path.join(root, f)

            # root 예시:
            #   INPUT_DIR/Forest and River
            #   INPUT_DIR/Country Road
            #   INPUT_DIR/Wildness Dry/extra
            #
            # 여기서 INPUT_DIR 를 기준으로 상대경로를 구하면
            #   Forest and River
            #   Country Road
            #   Wildness Dry/extra
            # 이런 식으로 나온다.
            rel_root = os.path.relpath(root, INPUT_DIR)

            # 맵 이름은 상대경로의 가장 앞부분이라고 생각하면 된다.
            # ex) "Forest and River" or "Wildness Dry"
            # 만약 root 가 더 깊다면(ex. .../Wildness Dry/some/sub),
            # 그 전체를 그대로 따라가도 된다.
            # 이번 요구사항에서는 [맵 이름]/[Obstacle 이름]/ 으로만 쓰면 되니까
            # rel_root 전체를 맵 경로로 보자.
            map_dir = rel_root  # "Forest and River"

            # obstacle 이름은 mp4 파일 이름(확장자 제거)
            obstacle_name = os.path.splitext(f)[0]

            # 최종 저장 경로:
            # OUTPUT_DIR / [맵 이름] / [Obstacle 이름]
            save_dir = os.path.join(OUTPUT_DIR, map_dir, obstacle_name)

            jobs.append((mp4_path, save_dir))

    if not jobs:
        print(f"{INPUT_DIR} 및 하위 폴더에 mp4 파일이 없습니다.")
        return

    # 4. 병렬로 프레임 추출
    def process(job):
        mp4_path, save_dir = job
        print(f"프레임 추출 중: {mp4_path} -> {save_dir}")
        try:
            extract_frames_from_mp4(mp4_path, save_dir, FRAME_INTERVAL)
        except Exception as e:
            print(f"실패: {mp4_path} -> {e}")

    max_workers = multiprocessing.cpu_count()
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        executor.map(process, jobs)


if __name__ == "__main__":
    main()