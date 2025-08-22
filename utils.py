import logging
import os
import datetime

def setup_logger(log_file):
    """
    로그 파일 경로를 받아 로깅을 설정합니다.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


def get_week_dates(start_date_str):
    """
    시작일(월요일, YYYY-MM-DD) 기준 5일간(월~금) 날짜 리스트 반환
    예시: '2025-07-14' -> ['2025-07-14', '2025-07-15', ..., '2025-07-18']
    """
    start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
    return [(start_date + datetime.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(5)]  # ['2025-07-14', ...] 




def _add_changeover_constraints(self):
        """
        교체 결정 변수 제약조건 추가 (단순화된 구조)
        - 교체 발생 여부만 결정
        - 교체시간 계산은 _add_improved_constraints에서 처리
        """
        self.logger.info("교체 결정 변수 제약조건 추가 중...")
        
        # === 교체 발생 조건 설정 ===
        for line in self.lines:
            for time_slot_idx, time_slot in enumerate(self.time_slots):
                if time_slot_idx > 0:  # 첫 번째 시간대 제외
                    prev_time_slot = self.time_slots[time_slot_idx - 1]
                    
                    for p1, line1 in self.valid_product_line_combinations:
                        for p2, line2 in self.valid_product_line_combinations:
                            if line1 == line2 == line and p1 != p2:
                                # 이전 시간대에 p1 생산, 현재 시간대에 p2 생산하면 교체 발생
                                self.model += (
                                    self.variables['changeover'][p1, p2, line, time_slot] >=
                                    self.variables['production'][p1, line, prev_time_slot] +
                                    self.variables['production'][p2, line, time_slot] - 1
                                ), f"changeover_decision_{p1}_{p2}_{line}_{time_slot}"
        
        self.logger.info("교체 결정 변수 제약조건 추가 완료")
        self.logger.info("교체시간 계산은 _add_improved_constraints에서 처리")