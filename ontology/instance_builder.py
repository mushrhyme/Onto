from owlready2 import Thing
import datetime

def create_team_instances(onto, json_data):
    """
    팀 인스턴스 생성
    Args:
        onto: owlready2 온톨로지 객체
        json_data: dict, lines/products/changeover 데이터
    Returns:
        teams: dict, {'생산1팀': <onto.Team ...>, ...}
    """
    teams = {}
    for team_name in ['생산1팀', '생산2팀']:
        team = onto.Team(team_name.replace('팀', '_team'))
        teams[team_name] = team
    return teams  # {'생산1팀': <onto.Team ...>, ...}


def create_line_instances(onto, json_data, teams):
    """
    라인 인스턴스 생성 및 속성 할당
    Args:
        onto: owlready2 온톨로지 객체
        json_data: dict, lines/products/changeover 데이터
        teams: dict, 팀 인스턴스
    Returns:
        lines: dict, {'L01': <onto.Line ...>, ...}
    """
    lines = {}
    for line_id, info in json_data['lines']['lines'].items():
        line = onto.Line(f"line_{line_id}")
        # 팀 연결
        line.hasTeam = [teams.get(info['team'])]
        line.hasLineCategory = [info['category']]
        track_count = info.get('tracks', 1) or 1
        line.hasTrackCount = [track_count]
        line.hasSetupTime = [info['setup_time_hours']]
        line.hasCleanupTime = [info['cleanup_time_hours']]
        line.hasNormalWorkingTime = [info['working_hours']['normal']]
        line.hasExtendedWorkingTime = [info['working_hours']['extended']]
        if 'line_type' in info:
            line.hasLineType = [info['line_type']]
        
        # 라인별 용량 계산 및 할당
        calculate_line_capacity(line, line_id, json_data)
        
        lines[line_id] = line
    return lines  # {'L01': <onto.Line ...>, ...}


def calculate_line_capacity(line, line_id: str, json_data: dict):
    """
    라인별 용량 계산 및 할당
    박스당 생산량 = (생산시간 × CT율 × 트랙수 × 60) ÷ 개입수
    """
    try:
        # 라인 정보 가져오기
        line_info = json_data['lines']['lines'][line_id]
        tracks = line_info.get('tracks', 1) or 1
        normal_hours = line_info['working_hours']['normal']
        extended_hours = line_info['working_hours']['extended']
        
        # 해당 라인에서 생산 가능한 제품들의 CT율과 개입수 정보 수집
        ct_rates = []
        products_per_box = []
        
        for product_code, product_info in json_data['products']['products'].items():
            if line_id in product_info['lines']:
                line_product_info = product_info['lines'][line_id]
                ct_rate = line_product_info.get('ct_rate', 50) or 50
                ct_rates.append(ct_rate)
                products_per_box.append(product_info['products_per_box'])
        
        if not ct_rates:
            # 기본값 설정
            ct_rates = [50.0]
            products_per_box = [6]
        
        # 평균 CT율과 개입수 계산 (라인별 대표값)
        avg_ct_rate = sum(ct_rates) / len(ct_rates)
        avg_products_per_box = sum(products_per_box) / len(products_per_box)
        
        # 용량 계산
        # 박스당 생산량 = (생산시간 × CT율 × 트랙수 × 60) ÷ 개입수
        normal_capacity = int((normal_hours * avg_ct_rate * tracks * 60) / avg_products_per_box)
        extended_capacity = int((extended_hours * avg_ct_rate * tracks * 60) / avg_products_per_box)
        max_daily_capacity = normal_capacity + extended_capacity
        
        # 온톨로지에 용량 정보 할당
        line.hasNormalCapacity = [normal_capacity]
        line.hasExtendedCapacity = [extended_capacity]
        line.hasMaxDailyCapacity = [max_daily_capacity]
        
    except Exception as e:
        print(f"경고: 라인 {line_id} 용량 계산 중 오류 발생 - {e}")
        # 기본값 설정
        line.hasNormalCapacity = [1000]
        line.hasExtendedCapacity = [1500]
        line.hasMaxDailyCapacity = [2500]


def create_product_instances(onto, json_data, order_data):
    """
    제품 인스턴스 생성 및 속성 할당
    Args:
        onto: owlready2 온톨로지 객체
        json_data: dict, lines/products/changeover 데이터
        order_data: dict, 제품별 생산지시량
    Returns:
        products: dict, {'P001': <onto.Product ...>, ...}
    """
    products = {}
    for product_code, info in json_data['products']['products'].items():
        if product_code in order_data:
            product = onto.Product(f"product_{product_code}")
            product.hasProductCode = [product_code]  # 예: ['101003377']
            if 'name' in info:
                product.hasProductName = [info['name']]  # 예: ['보글보글부대찌개면(멀티팩)']
            if 'category' in info:
                product.hasCategory = [info['category']]  # 예: ['봉지면']
            if 'product_type' in info:
                product.hasProductType = [info['product_type']]  # 예: ['굵은면']
            if 'weight' in info:
                product.hasWeight = [info['weight']]  # 예: [127]
            if 'height' in info:
                product.hasHeight = [info['height']]  # 예: [값이 없을 수도 있음]
            if 'items_per_product' in info:
                product.hasItemsPerProduct = [info['items_per_product']]  # 예: [4]
            if 'products_per_box' in info:
                product.hasProductsPerBox = [info['products_per_box']]  # 예: [8]
            # items_per_box 계산 (둘 다 있을 때만)
            if 'items_per_product' in info and 'products_per_box' in info:
                items_per_box = info['items_per_product'] * info['products_per_box']
                product.hasItemsPerBox = [items_per_box]  # 예: [32]
            if 'market_type' in info and info['market_type'] is not None:
                product.hasMarketType = [info['market_type']]  # 예: ['domestic']
            products[product_code] = product  # {'101003377': <onto.Product ...>, ...}
    return products  # {'P001': <onto.Product ...>, ...}


def create_relations(onto, json_data, order_data, lines, products):
    """
    Line-Product 관계 생성
    Args:
        onto: owlready2 온톨로지 객체
        json_data: dict, lines/products/changeover 데이터
        order_data: dict, 제품별 생산지시량
        lines: dict, 라인 인스턴스
        products: dict, 제품 인스턴스
    Returns:
        relations: list, [<onto.LineProductRelation ...>, ...]
    """
    relations = []
    for product_code, info in json_data['products']['products'].items():
        if product_code in order_data:
            for line_id, line_info in info['lines'].items():
                if line_id in lines:
                    relation = onto.LineProductRelation(f"relation_{line_id}_{product_code}")
                    relation.hasLine = [lines[line_id]]
                    relation.handlesProduct = [products[product_code]]
                    ctrate = line_info.get('ct_rate', 50) or 50
                    relation.hasCTRate = [ctrate]
                    relations.append(relation)
    return relations  # [<onto.LineProductRelation ...>, ...]


def create_changeover_rule_instances(onto, json_data, lines):
    """
    교체 규칙 개체 생성
    Args:
        onto: owlready2 온톨로지 객체
        json_data: dict, lines/products/changeover 데이터
        lines: dict, 라인 인스턴스
    Returns:
        changeover_rules: list, [<onto.ChangeoverRule ...>, ...]
    """
    changeover_rules = []
    counter = 0
    for line_id, rule_info in json_data['changeover']['changeover_rules'].items():
        if line_id in lines:
            # 라인별 rule_type 정보 추출
            rule_type = rule_info.get('rule_type', 'unknown')
            
            for rule in rule_info['rules']:
                rule_inst = onto.ChangeoverRule(f"rule_{line_id}_{counter}")
                rule_inst.appliesTo = [lines[line_id]]
                rule_inst.hasFromCondition = [rule.get('from', 0)]
                rule_inst.hasToCondition = [rule.get('to', 0)]
                rule_inst.hasChangeoverTimeValue = [rule['time']]
                rule_inst.hasRuleDescription = [rule['description']]
                
                # rule_type 정보 추가
                rule_inst.hasRuleType = [rule_type]
                
                changeover_rules.append(rule_inst)
                counter += 1
                
    return changeover_rules  # [<onto.ChangeoverRule ...>, ...]


def create_shift_instances(onto):
    """
    Shift 인스턴스 생성
    Args:
        onto: owlready2 온톨로지 객체
    Returns:
        shifts: dict, {'조간': <onto.Shift ...>, '야간': <onto.Shift ...>}
    """
    shifts = {}
    
    # 조간 Shift 생성
    day_shift = onto.Shift("day_shift")
    day_shift.hasShiftType = ["day"]
    day_shift.hasShiftName = ["조간"]
    shifts["조간"] = day_shift
    
    # 야간 Shift 생성
    night_shift = onto.Shift("night_shift")
    night_shift.hasShiftType = ["night"]
    night_shift.hasShiftName = ["야간"]
    shifts["야간"] = night_shift
    
    return shifts  # {'조간': <onto.Shift ...>, '야간': <onto.Shift ...>}


def create_day_instances(onto, shifts, date_list=None, default_working_hours=None):
    """
    Day 인스턴스 생성
    Args:
        onto: owlready2 온톨로지 객체
        shifts: dict, 시프트 인스턴스
        date_list: list, 날짜 리스트 (예: ['2025-07-21', '2025-07-22', ...])
        default_working_hours: dict, 날짜별 최대 가동시간 (예: {0: 10.5, 1: 10.5, 2: 8.0, ...})
    Returns:
        days: dict, {'2025-07-21': <onto.Day ...>, ...}
    """
    days = {}
    
    if date_list is None:
        # 기본 날짜 설정 (예시: 2025년 7월 21일~25일)
        date_configs = [
            {"date": "2025-07-21", "day_name": "월요일", "max_working_time": 10.5},
            {"date": "2025-07-22", "day_name": "화요일", "max_working_time": 10.5},
            {"date": "2025-07-23", "day_name": "수요일", "max_working_time": 8.0},  # 특별한 날
            {"date": "2025-07-24", "day_name": "목요일", "max_working_time": 10.5},
            {"date": "2025-07-25", "day_name": "금요일", "max_working_time": 10.5}
        ]
    else:
        # 외부에서 받은 날짜 리스트로 설정
        date_configs = []
        for i, date in enumerate(date_list):
            day_names = ["월요일", "화요일", "수요일", "목요일", "금요일"]
            
            # 날짜별 최대 가동시간 설정
            if default_working_hours and i in default_working_hours:
                max_working_time = default_working_hours[i]
            else:
                # 기본값 설정
                if i == 2:  # 수요일 (특별한 날)
                    max_working_time = 8.0
                else:
                    max_working_time = 10.5
            
            date_configs.append({
                "date": date,
                "day_name": day_names[i] if i < 5 else f"요일{i+1}",
                "max_working_time": max_working_time
            })
    
    for config in date_configs:
        # Day 인스턴스 생성 (예: day_2025-07-21)
        day = onto.Day(f"day_{config['date']}")
        
        # 각 Day에 조간/야간 Shift 연결
        day.hasShift = [shifts["조간"], shifts["야간"]]
        
        # 날짜별 최대 가동시간 설정
        day.hasMaxWorkingTime = [config['max_working_time']]
        
        # 다양한 키로 접근 가능하도록 저장
        days[config['date']] = day
        days[config['day_name']] = day
    
    return days  # {'2025-07-21': <onto.Day ...>, ...}


def create_timeslot_instances(onto, days, shifts, default_working_hours=None):
    """
    TimeSlot 인스턴스 생성 (새로 추가된 함수)
    Args:
        onto: owlready2 온톨로지 객체
        days: dict, Day 인스턴스들
        shifts: dict, Shift 인스턴스들
        default_working_hours: dict, 날짜별 최대 가동시간 (예: {0: 10.5, 1: 10.5, 2: 8.0, ...})
    Returns:
        timeslots: dict, {'월요일_조간': <onto.TimeSlot ...>, '월요일_야간': <onto.TimeSlot ...>, ...}
    """
    timeslots = {}
    day_names = ["월요일", "화요일", "수요일", "목요일", "금요일"]
    shift_names = ["조간", "야간"]
    
    for i, day_name in enumerate(day_names):
        # 날짜별 작업시간 설정
        if default_working_hours and i in default_working_hours:
            working_hours = default_working_hours[i]
        else:
            # 기본값 설정
            if i == 2:  # 수요일 (특별한 날)
                working_hours = 8.0
            else:
                working_hours = 10.5
        
        for shift_name in shift_names:
            # 시간대 이름 생성 (예: '월요일_조간')
            timeslot_name = f"{day_name}_{shift_name}"
            
            # TimeSlot 인스턴스 생성
            timeslot = onto.TimeSlot(f"timeslot_{timeslot_name}")
            
            # 속성 할당
            timeslot.hasTimeSlotName = [timeslot_name]
            timeslot.hasDay = [days[day_name]]
            timeslot.hasShift = [shifts[shift_name]]
            timeslot.hasWorkingHours = [working_hours]
            
            # 시작/종료 시간 설정
            if shift_name == "조간":
                timeslot.hasStartTime = [0.0]  # 0시부터 시작
                timeslot.hasEndTime = [working_hours]  # 작업시간만큼
            else:  # 야간
                timeslot.hasStartTime = [working_hours]  # 조간 종료 후 시작
                timeslot.hasEndTime = [working_hours * 2]  # 조간 + 야간
            
            timeslots[timeslot_name] = timeslot
    
    # 시간대 간 순서 관계 설정 (nextTimeSlot, previousTimeSlot)
    _setup_timeslot_sequence(timeslots, day_names, shift_names)
    
    print(f"✅ TimeSlot 인스턴스 생성 완료: {len(timeslots)}개")
    for name, ts in timeslots.items():
        print(f"  - {name}: {ts.hasWorkingHours[0]}시간 ({ts.hasStartTime[0]}~{ts.hasEndTime[0]}시)")
    
    return timeslots  # {'월요일_조간': <onto.TimeSlot ...>, ...}


def _setup_timeslot_sequence(timeslots, day_names, shift_names):
    """
    시간대 간 순서 관계 설정 (내부 함수)
    Args:
        timeslots: dict, TimeSlot 인스턴스들
        day_names: list, 요일 이름 리스트
        shift_names: list, 시프트 이름 리스트
    """
    for i, day_name in enumerate(day_names):
        for j, shift_name in enumerate(shift_names):
            current_name = f"{day_name}_{shift_name}"
            current_timeslot = timeslots[current_name]
            
            # 다음 시간대 설정
            if j < len(shift_names) - 1:  # 같은 날의 다음 시프트
                next_shift_name = shift_names[j + 1]
                next_name = f"{day_name}_{next_shift_name}"
                if next_name in timeslots:
                    current_timeslot.nextTimeSlot = [timeslots[next_name]]
                    timeslots[next_name].previousTimeSlot = [current_timeslot]
            elif i < len(day_names) - 1:  # 다음 날의 첫 번째 시프트
                next_day_name = day_names[i + 1]
                next_name = f"{next_day_name}_{shift_names[0]}"
                if next_name in timeslots:
                    current_timeslot.nextTimeSlot = [timeslots[next_name]]
                    timeslots[next_name].previousTimeSlot = [current_timeslot]


def create_production_segment_instances(onto, lines, days, shifts, timeslots, products, order_data, active_lines=None):
    """
    ProductionSegment 인스턴스 생성 (수정된 함수)
    Args:
        onto: owlready2 온톨로지 객체
        lines: dict, Line 인스턴스들
        days: dict, Day 인스턴스들
        shifts: dict, Shift 인스턴스들
        timeslots: dict, TimeSlot 인스턴스들
        products: dict, Product 인스턴스들
        order_data: dict, 제품별 생산지시량
        active_lines: list, 활성화된 라인 ID 리스트 (None이면 모든 라인 처리)
    Returns:
        segments: list, [<onto.ProductionSegment ...>, ...]
    """
    segments = []
    counter = 0
    
    # 활성화된 라인만 처리 (기본값: 모든 라인)
    if active_lines is None:
        active_lines = list(lines.keys())
    
    print(f"🔍 활성화된 라인만 세그먼트 생성: {active_lines}")
    
    # 각 제품별로 필요한 생산 세그먼트 생성
    for product_code, target_boxes in order_data.items():
        if product_code in products:
            product = products[product_code]
            
            # 활성화된 라인만 처리
            for line_id, line in lines.items():
                if line_id not in active_lines:
                    continue  # 활성화되지 않은 라인은 건너뛰기
                    
                # 제품-라인 관계 확인 (간단한 검증)
                if hasattr(line, 'hasTeam'):  # 라인이 팀에 할당되어 있으면 유효한 라인
                    # 기본 세그먼트 생성 (실제 최적화에서 세부 조정)
                    segment = onto.ProductionSegment(f"segment_{counter}")
                    
                    # 필수 속성 할당
                    segment.occursInLine = [line]
                    segment.occursOnDay = [list(days.values())[0]]  # 첫 번째 Day 인스턴스 사용
                    segment.occursInShift = [shifts["조간"]]  # 기본값, 최적화에서 조정
                    segment.occursInTimeSlot = [timeslots["월요일_조간"]]  # 기본값, 최적화에서 조정
                    segment.producesProduct = [product]
                    
                    # 시간 관련 속성 (기본값)
                    segment.hasProductionHours = [2.0]  # 기본 생산시간
                    segment.hasChangeoverHours = [0.5]  # 기본 교체시간
                    segment.hasCleaningHours = [0.2]   # 기본 청소시간
                    segment.hasTotalSegmentHours = [2.7]  # 총 소요시간
                    
                    # 생산량 (박스 단위)
                    segment.hasProductionQuantity = [target_boxes]
                    
                    # 날짜 (기본값)
                    segment.hasSegmentDate = [datetime.date(2025, 7, 21)]
                    
                    segments.append(segment)
                    counter += 1
    
    print(f"✅ ProductionSegment 인스턴스 생성 완료: {len(segments)}개 (활성 라인: {len(active_lines)}개)")
    return segments  # [<onto.ProductionSegment ...>, ...] 