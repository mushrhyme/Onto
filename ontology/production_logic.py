import datetime

def create_production_segments(onto, json_data, order_data, lines, products, days, shifts):
    """
    ProductionSegment 인스턴스 생성
    JSON/CSV 데이터를 바탕으로 생산 세그먼트를 생성하고 속성을 연결
    Args:
        onto: owlready2 온톨로지 객체
        json_data: dict, lines/products/changeover 데이터
        order_data: dict, 제품별 생산지시량
        lines: dict, 라인 인스턴스
        products: dict, 제품 인스턴스
        days: dict, 날짜 인스턴스
        shifts: dict, 시프트 인스턴스
    Returns:
        segments: list, [<onto.ProductionSegment ...>, ...]
    """
    segments = []
    segment_counter = 0
    
    # 각 라인별로 세그먼트 생성
    for line_id, line in lines.items():
        line_info = json_data['lines']['lines'][line_id]
        
        # 해당 라인에서 생산 가능한 제품들 찾기
        producible_products = []
        for product_code, product_info in json_data['products']['products'].items():
            if product_code in order_data and line_id in product_info['lines']:
                producible_products.append(product_code)
        
        if not producible_products:
            continue
        
        # 각 요일, 각 시프트별로 세그먼트 생성
        for day_name, day in days.items():
            if not day_name.endswith('요일'):  # 영문 코드는 건너뛰기
                continue
                
            for shift_name, shift in shifts.items():
                # 날짜별 최대 가동시간과 라인별 시프트 시간 중 작은 값 사용
                day_max_hours = list(day.hasMaxWorkingTime)[0] if day.hasMaxWorkingTime else 24.0
                
                if shift_name == "조간":
                    line_shift_hours = line_info['working_hours']['normal']
                else:  # 야간
                    line_shift_hours = line_info['working_hours']['extended']
                
                # 날짜별 제한과 라인별 제한 중 더 엄격한 것 적용
                max_shift_hours = min(day_max_hours, line_shift_hours)
                
                # 각 제품별로 세그먼트 생성
                for product_code in producible_products:
                    # 생산 수량 계산
                    order_quantity = order_data[product_code]
                    ct_rate = json_data['products']['products'][product_code]['lines'][line_id].get('ct_rate', 50)
                    
                    # ct_rate가 None이거나 숫자가 아닌 경우 기본값 사용
                    if ct_rate is None or not isinstance(ct_rate, (int, float)):
                        print(f"⚠️  기본값 사용: 제품 {product_code}의 CT Rate 누락/잘못된 형식 → 50.0 사용 (라인: {line_id})")
                        ct_rate = 50.0
                    else:
                        ct_rate = float(ct_rate)
                    
                    # 세그먼트당 생산량 (전체 수량을 5일로 나누고 2시프트로 나누기)
                    daily_quantity = order_quantity // 5  # 5일로 나누기
                    shift_quantity = daily_quantity // 2  # 2시프트로 나누기
                    
                    if shift_quantity <= 0:
                        continue
                    
                    # 생산 시간 계산 (시간 단위)
                    try:
                        # CT Rate = 분당 생산 개수
                        # 생산 시간 = 생산 수량 / 분당 생산 개수
                        production_minutes = shift_quantity / ct_rate
                        production_hours = production_minutes / 60
                        
                        # 라인별 최대 시프트 시간으로 제한
                        if production_hours > max_shift_hours:
                            production_hours = max_shift_hours
                            shift_quantity = int(max_shift_hours * 60 * ct_rate)  # 수량 조정
                        
                    except (TypeError, ValueError, KeyError) as e:
                        print(f"⚠️  기본값 사용: 생산 시간 계산 오류 → 4.0시간 사용 (제품: {product_code}, 라인: {line_id}, ct_rate: {ct_rate}, shift_quantity: {shift_quantity})")
                        production_hours = 4.0  # 기본값
                        shift_quantity = int(production_hours * 60 * ct_rate)
                    
                    # 교체 시간 계산 (제품 변경 시에만 적용되므로 나중에 계산)
                    changeover_hours = 0.0
                    
                    # 청소 시간 계산 (마지막 세그먼트인 경우에만 적용되므로 나중에 계산)
                    cleaning_hours = 0.0
                    
                    # 초기 총 세그먼트 시간 계산 (교체/청소 시간은 나중에 업데이트됨)
                    total_segment_hours = production_hours + changeover_hours + cleaning_hours
                    
                    # 시프트 시간을 초과하지 않는지 확인
                    if total_segment_hours > max_shift_hours:
                        # 생산 시간을 조정하여 총 시간이 시프트 시간을 넘지 않도록 함
                        available_hours = max_shift_hours - changeover_hours - cleaning_hours
                        if available_hours > 0:
                            production_hours = available_hours
                            shift_quantity = int(production_hours * 60 * ct_rate)
                            total_segment_hours = production_hours + changeover_hours + cleaning_hours
                        else:
                            # 교체/청소 시간이 시프트 시간을 초과하는 경우 스킵
                            continue
                    
                    # 세그먼트 생성
                    segment = onto.ProductionSegment(f"segment_{segment_counter}")
                    segment_counter += 1
                    
                    # 관계 속성 연결
                    segment.occursInLine = [line]
                    segment.occursOnDay = [day]
                    segment.occursInShift = [shift]
                    segment.producesProduct = [products[product_code]]
                    
                    # 실제 날짜 정보 추가 (datetime.date 객체로 변환)
                    day_date_str = day.name.replace('day_', '')  # "day_2025-07-21" → "2025-07-21"
                    day_date = datetime.datetime.strptime(day_date_str, "%Y-%m-%d").date()
                    segment.hasSegmentDate = [day_date]
                    
                    # 시간 속성 설정 (총량 기반)
                    segment.hasProductionHours = [production_hours]
                    segment.hasChangeoverHours = [changeover_hours]
                    segment.hasCleaningHours = [cleaning_hours]
                    segment.hasTotalSegmentHours = [total_segment_hours]
                    segment.hasProductionQuantity = [shift_quantity]
                    
                    segments.append(segment)
    
    return segments  # [<onto.ProductionSegment ...>, ...]


def connect_next_segments_and_calculate_changeover(onto, segments, json_data, get_date_index_func=None):
    """
    연속된 세그먼트들을 nextSegment로 연결하고 교체 시간 계산
    Args:
        onto: owlready2 온톨로지 객체
        segments: list, 세그먼트 인스턴스 리스트
        json_data: dict, lines/products/changeover 데이터
        get_date_index_func: function, 날짜 인덱스 반환 함수 (선택사항)
    """
    # 라인별로만 세그먼트 그룹화 (요일 제거하여 연속 연결 가능)
    segments_by_line = {}
    
    for segment in segments:
        line = list(segment.occursInLine)[0]
        day = list(segment.occursOnDay)[0]
        shift = list(segment.occursInShift)[0]
        
        key = line.name  # 라인만으로 그룹화
        if key not in segments_by_line:
            segments_by_line[key] = []
        segments_by_line[key].append((segment, day, shift))
    
    # 각 라인별로 시간순 정렬 후 연결
    for line_name, segment_day_shifts in segments_by_line.items():
        # 날짜 순서 + 시프트 순서로 정렬
        if get_date_index_func:
            # 동적 접근 방식 (OntologyManager에서 제공하는 함수 사용)
            shift_order = {"조간": 0, "야간": 1}
            segment_day_shifts.sort(key=lambda seg: (
                get_date_index_func(seg[0]), 
                shift_order[list(seg[0].occursInShift)[0].hasShiftName[0]]
            ))
        else:
            # 하드코딩된 방식 (기존 방식)
            day_index = {"day_Monday": 0, "day_Tuesday": 1, "day_Wednesday": 2, "day_Thursday": 3, "day_Friday": 4}
            shift_order = {"조간": 0, "야간": 1}
            segment_day_shifts.sort(key=lambda seg: (
                day_index[list(seg[0].occursOnDay)[0].name], 
                shift_order[list(seg[0].occursInShift)[0].hasShiftName[0]]
            ))
        
        # 연속된 세그먼트들 연결 및 교체 시간 계산
        for i in range(len(segment_day_shifts)):
            current_segment = segment_day_shifts[i][0]
            current_day = segment_day_shifts[i][1]
            current_shift = segment_day_shifts[i][2]
            
            # 다음 세그먼트가 있는 경우 연결 (요일을 넘어서도 연결)
            if i < len(segment_day_shifts) - 1:
                next_segment = segment_day_shifts[i + 1][0]
                next_day = segment_day_shifts[i + 1][1]
                next_shift = segment_day_shifts[i + 1][2]
                
                current_segment.nextSegment = [next_segment]
                
                # 제품이 바뀌었는지 확인하여 교체 시간 설정
                current_product = list(current_segment.producesProduct)[0]
                next_product = list(next_segment.producesProduct)[0]
                
                if current_product != next_product:
                    # 교체 시간 계산 (JSON 파일의 교체 규칙 사용)
                    changeover_hours = calculate_changeover_time(current_segment, next_segment, json_data)
                    current_segment.hasChangeoverHours = [changeover_hours]
                    # 총 세그먼트 시간 재계산
                    production_hours = list(current_segment.hasProductionHours)[0]
                    cleaning_hours = list(current_segment.hasCleaningHours)[0]
                    current_segment.hasTotalSegmentHours = [production_hours + changeover_hours + cleaning_hours]
                    
                    # 연속 생산 구간 종료 및 새로운 구간 시작 표시
                    print(f"🔄 교체 이벤트: {current_day.name} {current_shift.hasShiftName[0]} → {next_day.name} {next_shift.hasShiftName[0]} (제품 변경)")
                else:
                    # 같은 제품 연속 생산
                    print(f"➡️  연속 생산: {current_day.name} {current_shift.hasShiftName[0]} → {next_day.name} {next_shift.hasShiftName[0]} (같은 제품)")
        
        # 마지막 세그먼트에 청소 시간 추가 (라인별 cleanup_time_hours 사용)
        if segment_day_shifts:
            last_segment = segment_day_shifts[-1][0]
            line_id = line_name.replace('line_', '')
            if 'lines' in json_data:
                # lines.json에서 cleanup_time_hours 가져오기
                if line_id in json_data['lines']['lines']:
                    cleanup_hours = json_data['lines']['lines'][line_id].get('cleanup_time_hours', 2.5)
                    if cleanup_hours == 2.5:  # 기본값이 사용된 경우
                        print(f"⚠️  기본값 사용: 라인 {line_id}의 청소시간 누락 → 2.5시간 사용")
                else:
                    print(f"⚠️  기본값 사용: 라인 {line_id} 정보 누락 → 청소시간 2.5시간 사용")
                    cleanup_hours = 2.5  # 기본값
            else:
                print(f"⚠️  기본값 사용: lines 데이터 없음 → 청소시간 2.5시간 사용")
                cleanup_hours = 2.5  # 기본값
            
            last_segment.hasCleaningHours = [cleanup_hours]
            # 총 세그먼트 시간 재계산
            production_hours = list(last_segment.hasProductionHours)[0]
            changeover_hours = list(last_segment.hasChangeoverHours)[0]
            last_segment.hasTotalSegmentHours = [production_hours + changeover_hours + cleanup_hours]


def calculate_changeover_time(current_segment, next_segment, json_data):
    """
    두 세그먼트 간의 교체 시간을 계산
    JSON 파일의 교체 규칙을 사용하여 정확한 교체 시간 반환
    Args:
        current_segment: 현재 세그먼트
        next_segment: 다음 세그먼트
        json_data: dict, lines/products/changeover 데이터
    Returns:
        changeover_time: float, 교체 시간 (시간 단위)
    """
    # 라인 정보 가져오기
    current_line = list(current_segment.occursInLine)[0]
    line_id = current_line.name.replace('line_', '')
    
    # 현재 제품과 다음 제품 정보 가져오기
    current_product = list(current_segment.producesProduct)[0]
    next_product = list(next_segment.producesProduct)[0]
    
    current_product_code = list(current_product.hasProductCode)[0] if current_product.hasProductCode else ""
    next_product_code = list(next_product.hasProductCode)[0] if next_product.hasProductCode else ""
    
    # 라인별 교체 규칙 확인
    if 'changeover_rules' in json_data and line_id in json_data['changeover_rules']:
        rules = json_data['changeover_rules'][line_id]['rules']
        
        # 제품 정보에서 교체 규칙에 필요한 속성들 추출
        current_product_info = None
        next_product_info = None
        
        # products.json에서 제품 정보 찾기
        if 'products' in json_data:
            if current_product_code in json_data['products']['products']:
                current_product_info = json_data['products']['products'][current_product_code]
            if next_product_code in json_data['products']['products']:
                next_product_info = json_data['products']['products'][next_product_code]
        
        # 교체 규칙 매칭
        for rule in rules:
            from_condition = rule['from']
            to_condition = rule['to']
            changeover_time = rule['time']
            
            # 조건 매칭 로직 (라인별 규칙에 따라 다름)
            if match_changeover_condition(line_id, from_condition, to_condition, 
                                       current_product_info, next_product_info):
                return changeover_time
    
    # 매칭되는 규칙이 없으면 기본값 반환
    current_product_code = list(current_product.hasProductCode)[0] if current_product.hasProductCode else "N/A"
    next_product_code = list(next_product.hasProductCode)[0] if next_product.hasProductCode else "N/A"
    print(f"⚠️  기본값 사용: 교체규칙 매칭 실패 → 교체시간 0.6시간 사용 (제품: {current_product_code} → {next_product_code}, 라인: {line_id})")
    return 0.6


def match_changeover_condition(line_id, from_condition, to_condition, 
                               current_product_info, next_product_info):
    """
    교체 조건이 매칭되는지 확인
    Args:
        line_id: str, 라인 ID
        from_condition: str, 이전 조건
        to_condition: str, 다음 조건
        current_product_info: dict, 현재 제품 정보
        next_product_info: dict, 다음 제품 정보
    Returns:
        bool: 조건 매칭 여부
    """
    if not current_product_info or not next_product_info:
        return False
    
    # 라인별 교체 규칙 타입에 따른 매칭
    if line_id in ["12", "13"]:
        # 개입수 기준
        current_units = current_product_info.get('units_per_pack', 0)
        next_units = next_product_info.get('units_per_pack', 0)
        return (str(current_units) == str(from_condition) and 
               str(next_units) == str(to_condition))
    
    elif line_id == "14":
        # 제품 기준
        current_category = current_product_info.get('category', '')
        next_category = next_product_info.get('category', '')
        return (current_category == from_condition and 
               next_category == to_condition)
    
    elif line_id == "16":
        # 용기 높이 기준 (products.json에 height 정보가 있다고 가정)
        current_height = current_product_info.get('height', None)
        next_height = next_product_info.get('height', None)
        return (str(current_height) == str(from_condition) and 
               str(next_height) == str(to_condition))
    
    elif line_id in ["21", "22"]:
        # 고속면 라인 (domestic/export 구분)
        current_type = current_product_info.get('product_type', '')
        next_type = next_product_info.get('product_type', '')
        return (current_type == from_condition and 
               next_type == to_condition)
    
    else:
        # 기본 규칙 (universal)
        return (str(from_condition) == "None" and str(to_condition) == "None")


def identify_continuous_production_runs(onto, segments, get_date_index_func=None):
    """
    연속 생산 구간을 식별하고 ContinuousProductionRun 인스턴스 생성
    Args:
        onto: owlready2 온톨로지 객체
        segments: list, 세그먼트 인스턴스 리스트
        get_date_index_func: function, 날짜 인덱스 반환 함수 (선택사항)
    Returns:
        continuous_runs: list, [<onto.ContinuousProductionRun ...>, ...]
    """
    continuous_runs = []
    run_counter = 0
    
    # 라인별로 세그먼트 그룹화
    segments_by_line = {}
    for segment in segments:
        line = list(segment.occursInLine)[0]
        if line.name not in segments_by_line:
            segments_by_line[line.name] = []
        segments_by_line[line.name].append(segment)
    
    # 각 라인별로 연속 생산 구간 식별
    for line_name, line_segments in segments_by_line.items():
        if not line_segments:
            continue
            
        # 시간순 정렬
        if get_date_index_func:
            # 동적 접근 방식 (OntologyManager에서 제공하는 함수 사용)
            shift_order = {"조간": 0, "야간": 1}
            line_segments.sort(key=lambda seg: (
                get_date_index_func(seg), 
                shift_order[list(seg.occursInShift)[0].hasShiftName[0]]
            ))
        else:
            # 하드코딩된 방식 (기존 방식)
            day_index = {"day_Monday": 0, "day_Tuesday": 1, "day_Wednesday": 2, "day_Thursday": 3, "day_Friday": 4}
            shift_order = {"조간": 0, "야간": 1}
            line_segments.sort(key=lambda seg: (
                day_index[list(seg.occursOnDay)[0].name], 
                shift_order[list(seg.occursInShift)[0].hasShiftName[0]]
            ))
        
        # 연속 생산 구간 찾기
        current_run_segments = []
        current_product = None
        
        for segment in line_segments:
            product = list(segment.producesProduct)[0]
            
            if current_product is None:
                # 첫 번째 세그먼트
                current_product = product
                current_run_segments = [segment]
            elif product == current_product:
                # 같은 제품 연속 생산
                current_run_segments.append(segment)
            else:
                # 제품 변경 - 현재 구간 완료
                if len(current_run_segments) > 0:
                    run = create_continuous_production_run(onto, current_run_segments, run_counter)
                    continuous_runs.append(run)
                    run_counter += 1
                
                # 새로운 구간 시작
                current_product = product
                current_run_segments = [segment]
        
        # 마지막 구간 처리
        if len(current_run_segments) > 0:
            run = create_continuous_production_run(onto, current_run_segments, run_counter)
            continuous_runs.append(run)
            run_counter += 1
    
    return continuous_runs  # [<onto.ContinuousProductionRun ...>, ...]


def create_continuous_production_run(onto, segments, run_counter):
    """
    연속 생산 구간 인스턴스 생성
    Args:
        onto: owlready2 온톨로지 객체
        segments: list, 세그먼트 리스트
        run_counter: int, 구간 카운터
    Returns:
        run: <onto.ContinuousProductionRun ...>
    """
    if len(segments) == 0:
        return None
        
    # 구간 정보 추출
    first_segment = segments[0]
    last_segment = segments[-1]
    
    line = list(first_segment.occursInLine)[0]
    product = list(first_segment.producesProduct)[0]
    product_code = list(product.hasProductCode)[0] if product.hasProductCode else "N/A"
    
    # 시작/종료 시점 정보
    start_day = list(first_segment.occursOnDay)[0]
    start_shift = list(first_segment.occursInShift)[0]
    end_day = list(last_segment.occursOnDay)[0]
    end_shift = list(last_segment.occursInShift)[0]
    
    start_time = f"{start_day.name.replace('day_', '')} {start_shift.hasShiftName[0]}"
    end_time = f"{end_day.name.replace('day_', '')} {end_shift.hasShiftName[0]}"
    
    # 총 생산 시간 계산
    total_duration = sum(list(s.hasTotalSegmentHours)[0] for s in segments)
    
    # ContinuousProductionRun 인스턴스 생성
    run = onto.ContinuousProductionRun(f"continuous_run_{run_counter}")
    run.hasRunDuration = [total_duration]
    run.hasRunProduct = [product_code]
    
    # 시작/종료 포인트 생성
    run_start = onto.ProductionRunStart(f"run_start_{run_counter}")
    run_start.hasRunStartTime = [start_time]
    
    run_end = onto.ProductionRunEnd(f"run_end_{run_counter}")
    run_end.hasRunEndTime = [end_time]
    
    # 관계 설정
    run.hasRunStart = [run_start]
    run.hasRunEnd = [run_end]
    
    # 세그먼트들과 연결
    for segment in segments:
        run.runContainsSegment.append(segment)
    
    # 첫 번째/마지막 세그먼트에 시작/종료 표시
    first_segment.startsRun = [run_start]
    last_segment.endsRun = [run_end]
    
    # 로그 출력
    print(f"🏭 연속 생산 구간 생성: {product_code} ({start_time} → {end_time}, {len(segments)}개 세그먼트, 총 {total_duration:.1f}시간)")
    
    return run  # <onto.ContinuousProductionRun ...>


def create_changeover_event_instances(onto, segments):
    """
    ChangeoverEvent 인스턴스 생성
    연속된 두 세그먼트를 비교해서 제품이 바뀌었을 때 이벤트 생성
    Args:
        onto: owlready2 온톨로지 객체
        segments: list, 세그먼트 인스턴스 리스트
    Returns:
        changeover_events: list, [<onto.ChangeoverEvent ...>, ...]
    """
    changeover_events = []
    event_counter = 0
    
    for segment in segments:
        if segment.nextSegment:  # 다음 세그먼트가 있는 경우
            next_seg = list(segment.nextSegment)[0]
            
            # 현재 세그먼트와 다음 세그먼트의 제품 비교
            current_product = list(segment.producesProduct)[0]
            next_product = list(next_seg.producesProduct)[0]
            
            if current_product != next_product:  # 제품이 바뀌었을 때
                # ChangeoverEvent 생성
                event = onto.ChangeoverEvent(f"changeover_event_{event_counter}")
                event_counter += 1
                
                # 이벤트가 발생한 세그먼트와 연결
                event.triggersEvent = [segment]
                
                changeover_events.append(event)
    
    return changeover_events  # [<onto.ChangeoverEvent ...>, ...] 