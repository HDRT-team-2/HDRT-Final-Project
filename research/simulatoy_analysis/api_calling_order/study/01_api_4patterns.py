"""
목적 : 'collision', 'get_action', 'detect', 'info'의 모든 순서 조합(4! = 24가지)을 만들어서
       각 패턴이 로그 안에 몇 번 등장했는지 출력하는 코드
"""
import re
import itertools

def analyze_all_patterns(log: str):
    words = ["collision", "get_action", "detect", "info"]

    # 4개 단어의 모든 순서 조합 생성 (24가지)
    all_patterns = list(itertools.permutations(words, 4))

    print("────────────────────────────")
    print("로그 패턴 분석 결과 (총 24가지 조합)")
    print("────────────────────────────")

    # 각 패턴의 등장 횟수 세기
    for idx, p in enumerate(all_patterns, start=1):
        pattern_str = r"\s*→\s*".join(p)  # "단어 → 단어 → 단어 → 단어" 형식
        regex = rf"{pattern_str}"
        count = len(re.findall(regex, log))
        print(f"{idx:2d}. {' → '.join(p)} : {count}회")

    print("────────────────────────────")


# 🔹 예시 실행 (로그 문자열 예시)
log_text = """
get_action → info → detect → update_bullet → info
→ get_action → detect → info → get_action → info → detect
→ get_action → info → get_action → detect → info → get_action
→ collision → detect → collision → collision → info → collision
→ get_action → info → collision → detect → get_action → info
→ collision → detect → get_action → info → collision → collision
→ collision → detect → get_action → info → get_action → info
→ detect → info → get_action → collision → detect → info
→ get_action → info → detect → get_action → info → get_action
→ detect → update_bullet → info → get_action → collision
→ detect → collision → collision → info → collision → collision
→ collision → collision → collision → collision → get_action
→ collision → collision → collision → info → collision
→ collision → detect → get_action → info → detect → get_action
→ info → get_action → detect → info → get_action → info
→ detect → info → get_action → detect → info → get_action
→ info → detect → get_action → info → detect → get_action
→ info → update_bullet → get_action → detect → info → get_action
→ info → detect → get_action → info → detect → get_action
→ info → detect → get_action → info → detect → get_action
→ info → info → get_action → detect → info → get_action
→ detect → info → get_action → detect → info → get_action
→ detect → info → get_action → detect → info → get_action
→ detect → info → get_action → detect → info → start
"""

# 함수 실행
analyze_all_patterns(log_text)


