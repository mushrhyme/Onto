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
            product.hasProductCode = [product_code]
            product.hasProductName = [info['name']]
            product.hasCategory = [info['category']]
            product.hasProductType = [info['product_type']]
            product.hasWeight = [info['weight']]
            product.hasPackageCount = [info['units_per_pack']]
            product.hasProductsPerBox = [info['products_per_box']]
            if info.get('changeover_group') is not None:
                product.hasChangeoverGroup = [str(info['changeover_group'])]
            products[product_code] = product
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
            for rule in rule_info['rules']:
                rule_inst = onto.ChangeoverRule(f"rule_{line_id}_{counter}")
                rule_inst.appliesTo = [lines[line_id]]
                rule_inst.hasFromCondition = [str(rule.get('from', 'any'))]
                rule_inst.hasToCondition = [str(rule.get('to', 'any'))]
                rule_inst.hasChangeoverTimeValue = [rule['time']]
                rule_inst.hasRuleDescription = [rule['description']]
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