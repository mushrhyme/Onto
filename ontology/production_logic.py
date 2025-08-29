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
                    
                    # ProductionSegment 인스턴스 생성
                    segment = onto.ProductionSegment(f"segment_{segment_counter}")
                    
                    # 기본 속성 설정
                    segment.occursInLine = [line]
                    segment.occursOnDay = [day]
                    segment.occursInShift = [shift]
                    segment.producesProduct = [products[product_code]]
                    
                    # 시간 관련 속성 설정
                    segment.hasProductionHours = [production_hours]
                    segment.hasChangeoverHours = [changeover_hours]
                    segment.hasCleaningHours = [cleaning_hours]
                    segment.hasTotalSegmentHours = [total_segment_hours]
                    
                    # 생산 수량 설정
                    segment.hasProductionQuantity = [shift_quantity]
                    
                    # 날짜 정보 설정
                    segment.hasSegmentDate = [day.name.replace('day_', '')]
                    
                    segments.append(segment)
                    segment_counter += 1
                    
                    # 로그 출력 (선택사항)
                    print(f"🏭 세그먼트 생성: {product_code} (라인: {line_id}, {day_name} {shift_name}, {production_hours:.1f}h, {shift_quantity}개)")
    
    return segments  # [<onto.ProductionSegment ...>, ...]


def connect_next_segments_and_calculate_changeover(onto, segments, json_data, get_date_index_func=None, active_lines=None):
    """
    세그먼트들을 시간순으로 연결하고 교체 시간 계산
    Args:
        onto: owlready2 온톨로지 객체
        segments: list, 세그먼트 인스턴스 리스트
        json_data: dict, lines/products/changeover 데이터
        get_date_index_func: function, 날짜 인덱스 반환 함수 (선택사항)
        active_lines: list, 활성화된 라인 ID 리스트 (None이면 모든 라인 처리)
    """
    if not segments:
        return
    
    # 라인별로 세그먼트 그룹화
    segments_by_line = {}
    for segment in segments:
        line = list(segment.occursInLine)[0]
        line_id = line.name.replace('line_', '')
        if line_id not in segments_by_line:
            segments_by_line[line_id] = []
        segments_by_line[line_id].append(segment)
    
    # 각 라인별로 세그먼트 연결 및 교체 시간 계산
    for line_id, line_segments in segments_by_line.items():
        # 활성화되지 않은 라인은 건너뛰기
        if active_lines is not None and line_id not in active_lines:
            continue
            
        if len(line_segments) < 2:
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
        
        # 세그먼트 연결 및 교체 시간 계산
        for i in range(len(line_segments) - 1):
            current_segment = line_segments[i]
            next_segment = line_segments[i + 1]
            
            # 다음 세그먼트 연결
            current_segment.nextSegment = [next_segment]
            
            # 교체 시간 계산 (제품이 바뀌었을 때만)
            current_product = list(current_segment.producesProduct)[0]
            next_product = list(next_segment.producesProduct)[0]
            
            if current_product != next_product:
                # 교체 시간 계산
                changeover_hours = calculate_changeover_time(
                    json_data, line_id, current_product, next_product
                )
                
                # 교체 시간 업데이트
                current_segment.hasChangeoverHours = [changeover_hours]
                
                # 총 세그먼트 시간 재계산
                production_hours = list(current_segment.hasProductionHours)[0]
                cleaning_hours = list(current_segment.hasCleaningHours)[0]
                current_segment.hasTotalSegmentHours = [production_hours + changeover_hours + cleaning_hours]
                
                print(f"🔄 교체 시간 계산: {current_product.hasProductCode[0]} → {next_product.hasProductCode[0]} (라인: {line_id}, 시간: {changeover_hours:.1f}h)")
        
        # 마지막 세그먼트의 청소 시간 설정 (라인별 기본값)
        if line_segments:
            last_segment = line_segments[-1]
            line_info = json_data['lines']['lines'].get(line_id, {})
            cleanup_hours = line_info.get('cleanup_time_hours', 0.5)
            
            last_segment.hasCleaningHours = [cleanup_hours]
            
            # 총 세그먼트 시간 재계산
            production_hours = list(last_segment.hasProductionHours)[0]
            changeover_hours = list(last_segment.hasChangeoverHours)[0]
            last_segment.hasTotalSegmentHours = [production_hours + changeover_hours + cleanup_hours]


def calculate_changeover_time(json_data, line_id, from_product, to_product):
    """
    두 제품 간의 교체 시간 계산
    Args:
        json_data: dict, lines/products/changeover 데이터
        from_product: Product 인스턴스, 이전 제품
        to_product: Product 인스턴스, 이후 제품
        line_id: str, 라인 ID
    Returns:
        float: 교체 시간 (시간 단위)
    """
    try:
        # changeover_rules에서 해당 라인의 규칙 찾기
        if 'changeover' in json_data and 'changeover_rules' in json_data['changeover']:
            line_rules = json_data['changeover']['changeover_rules'].get(line_id, {})
            
            if 'rules' in line_rules:
                # 제품별 교체 조건 확인 - hasChangeoverGroup 속성 안전하게 접근
                try:
                    from_condition = from_product.hasChangeoverGroup[0] if hasattr(from_product, 'hasChangeoverGroup') and from_product.hasChangeoverGroup else "any"
                    to_condition = to_product.hasChangeoverGroup[0] if hasattr(to_product, 'hasChangeoverGroup') and to_product.hasChangeoverGroup else "any"
                except (AttributeError, IndexError):
                    # hasChangeoverGroup 속성이 없거나 비어있는 경우
                    from_condition = "any"
                    to_condition = "any"
                
                # 정확한 매칭 규칙 찾기
                for rule in line_rules['rules']:
                    if (rule.get('from') == from_condition and rule.get('to') == to_condition):
                        return rule['time']
                
                # 기본 교체 시간 (규칙이 없는 경우)
                return 1.0  # 기본값 1시간
        
        # 기본값 반환
        return 1.0
        
    except Exception as e:
        print(f"⚠️ 교체 시간 계산 오류 (라인: {line_id}): {e}")
        return 1.0  # 오류 시 기본값 