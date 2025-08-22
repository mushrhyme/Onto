import os

# 프로젝트 루트 경로
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 결과 폴더 경로
RESULTS_DIR = os.path.join(BASE_DIR, "results")

# 로그 파일 경로
LOG_FILE = os.path.join(RESULTS_DIR, "system.log")

# 기타 전역 상수 예시
DEFAULT_CLEANUP_HOURS = 2.5  # 기본 청소 시간(시간)
DEFAULT_CHANGEOVER_HOURS = 0.6  # 기본 교체 시간(시간) 