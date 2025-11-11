"""
목적 : 폴더 구조로 정리된 영상(.mp4)들을 자동으로 프레임 이미지(.jpg)로 
변환하고, 규칙적인 파일명(prefix)과 디렉터리 구조로 저장한다.이떄의 폴더저장은 대문자로 저장 
"""
import os
import subprocess
import sys
import shutil
from concurrent.futures import ThreadPoolExecutor
import multiprocessing

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(CURRENT_DIR)
sys.path.append(BASE_DIR)

from settings import INPUT_DIR, OUTPUT_DIR, FRAME_INTERVAL


def make_prefix_from_filename(filename_no_ext: str, map_dir: str) -> str:
    """
    filename_no_ext: 'Country Road_Car 2_전범하'
    map_dir:         'Country Road'

    1) filename 에서 map_dir 길이만큼 앞에서 잘라낸다
       → '_Car 2_전범하'
    2) 앞쪽의 '_' 같은 구분자 제거
       → 'Car 2_전범하'
    3) 첫 번째 덩어리만 사용 ('Car 2')
    4) 첫 글자 + 마지막 글자 → 'C2'
    """
    name = filename_no_ext.strip()

    # 1) 맵 이름 길이만큼 앞에서 제거
    #    ex) 'Country Road_Car 2_전범하' -> (len('Country Road') = 12)
    #        name[12:] -> '_Car 2_전범하'
    if map_dir:
        cut_len = len(map_dir)
        if name.startswith(map_dir):
            name = name[cut_len:]  # 앞부분 떼고
    # 이제 name 은 대략 '_Car 2_전범하' 이런 상태

    # 2) 앞에 남아있는 '_'나 공백을 제거
    name = name.lstrip('_').lstrip()

    # 3) 첫 번째 덩어리만 사용
    #    'Car 2_전범하' -> 'Car 2'
    first_part = name.split('_')[0].strip() if name else ""

    if not first_part:
        return "X0"

    # 4) 첫 글자 + 마지막 글자
    first_char = first_part[0].lower()   # 여기서 lower() 사용
    last_char = first_part[-1].lower()   # 마지막 글자도 소문자로
    return f"{first_char}{last_char}"


def extract_frames_from_mp4(mp4_path, save_dir, interval, prefix):
    os.makedirs(save_dir, exist_ok=True)
    output_pattern = os.path.join(save_dir, f"{prefix}_%05d.jpg")

    command = [
        "ffmpeg",
        "-threads", "16",
        "-i", mp4_path,
        "-vf", f"fps=1/{interval}",
        output_pattern,
    ]
    subprocess.run(command, check=True)


def main():
    if not os.path.exists(INPUT_DIR):
        print(f"[에러] 입력 폴더가 존재하지 않습니다: {INPUT_DIR}")
        return

    # OUTPUT 전체는 지우지 않는다
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    jobs = []

    for root, dirs, files in os.walk(INPUT_DIR):
        for f in files:
            if not f.lower().endswith(".mp4"):
                continue

            mp4_path = os.path.join(root, f)

            # root: INPUT/Country Road/Car 2
            rel_root = os.path.relpath(root, INPUT_DIR)    # 'Country Road/Car 2'
            map_dir = os.path.dirname(rel_root)            # 'Country Road'
            # 파일 이름(확장자 제거)
            filename_no_ext = os.path.splitext(os.path.basename(f))[0]
            # filename_no_ext 예: 'Country Road_Car 2_전범하'

            # prefix 만들 때 map_dir 을 넘겨서 앞부분을 잘라내게 한다
            prefix = make_prefix_from_filename(filename_no_ext, map_dir)

            # 실제 저장 폴더는 기존처럼 맵/오브젝트 구조로
            if map_dir == "":
                # INPUT 바로 아래 mp4 가 있는 경우
                save_dir = os.path.join(OUTPUT_DIR, filename_no_ext)
            else:
                # 파일 이름이 'Country Road_Car 2_전범하' 라도
                # 실제 폴더 이름은 'Car 2' 로 하는 게 자연스러움
                if '_' in filename_no_ext:
                    pure_obj_dir = filename_no_ext.split('_')[1].strip()
                else:
                    pure_obj_dir = filename_no_ext
                save_dir = os.path.join(OUTPUT_DIR, map_dir, pure_obj_dir)

            jobs.append((mp4_path, save_dir, prefix))

    if not jobs:
        print(f"[알림] {INPUT_DIR} 및 하위 폴더에 mp4 파일이 없습니다.")
        return

    CLEAR_EACH_OBSTACLE_DIR = False

    def process(job):
        mp4_path, save_dir, prefix = job
        print(f"[진행] {mp4_path} → {save_dir} ({prefix})")
        try:
            if CLEAR_EACH_OBSTACLE_DIR and os.path.exists(save_dir):
                shutil.rmtree(save_dir)
            extract_frames_from_mp4(mp4_path, save_dir, FRAME_INTERVAL, prefix)
        except Exception as e:
            print(f"[에러] 실패: {mp4_path} -> {e}")

    max_workers = multiprocessing.cpu_count()
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        executor.map(process, jobs)

    print("[완료] 모든 mp4 처리 완료.")


if __name__ == "__main__":
    main()
