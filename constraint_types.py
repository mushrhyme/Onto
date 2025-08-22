"""
제약조건 유형 정의
호기별 생산 제약조건을 위한 상수 및 설정 클래스
"""

class ConstraintTypes:
    """제약조건 유형 상수"""
    
    # 시작 제품 제약
    START_PRODUCT = "start_product"
    
    # 시작+끝 제품 제약  
    START_END_PRODUCT = "start_end_product"
    
    # 마지막 제품 제약
    LAST_PRODUCT = "last_product"
    
    # 순서 제약
    PRODUCT_SEQUENCE = "product_sequence"
    
    # 블록 단위 순서 제약
    BLOCK_SEQUENCE = "block_sequence"
    
    # 금지 조합 제약
    FORBIDDEN_COMBINATION = "forbidden_combination"
    
    # 제약 없음
    NO_CONSTRAINT = "no_constraint"


class LineConstraintConfig:
    """호기별 제약조건 설정 클래스"""
    
    def __init__(self):
        self.constraints = {}
        self.available_products = []  # 사용 가능한 제품코드 목록
        self.available_lines = []     # 사용 가능한 라인 목록
    
    def set_available_products(self, products: list):
        """사용 가능한 제품코드 목록 설정"""
        self.available_products = products
    
    def set_available_lines(self, lines: list):
        """사용 가능한 라인 목록 설정"""
        self.available_lines = lines
    
    def validate_product_code(self, product_code: str) -> bool:
        """제품코드 유효성 검증"""
        if not self.available_products:
            return True  # 검증 목록이 없으면 통과
        return product_code in self.available_products
    
    def validate_line_id(self, line_id: str) -> bool:
        """라인 ID 유효성 검증"""
        if not self.available_lines:
            return True  # 검증 목록이 없으면 통과
        return line_id in self.available_lines
    
    def add_line_constraint(self, line_id: str, constraint_type: str, **kwargs):
        """
        특정 호기에 제약조건 추가
        Args:
            line_id: 호기 ID (예: '13', '14', '15')
            constraint_type: 제약조건 유형
            **kwargs: 제약조건 세부 설정
        """
        # 라인 ID 유효성 검증
        if not self.validate_line_id(line_id):
            raise ValueError(f"유효하지 않은 라인 ID: {line_id}")
        
        # 제품코드 유효성 검증
        if constraint_type in [ConstraintTypes.START_PRODUCT, ConstraintTypes.START_END_PRODUCT, ConstraintTypes.LAST_PRODUCT]:
            product_code = kwargs.get('product')
            if product_code and not self.validate_product_code(product_code):
                raise ValueError(f"유효하지 않은 제품코드: {product_code}")
        
        elif constraint_type == ConstraintTypes.PRODUCT_SEQUENCE:
            sequence = kwargs.get('sequence', [])
            for product_code in sequence:
                if not self.validate_product_code(product_code):
                    raise ValueError(f"유효하지 않은 제품코드: {product_code}")
        
        elif constraint_type == ConstraintTypes.BLOCK_SEQUENCE:
            block_sequence = kwargs.get('block_sequence', [])
            for block_info in block_sequence:
                if not isinstance(block_info, dict) or 'product' not in block_info or 'blocks' not in block_info:
                    raise ValueError(f"블록 순서 정보 형식이 잘못되었습니다: {block_info}")
                
                product_code = block_info['product']
                blocks_count = block_info['blocks']
                
                if not self.validate_product_code(product_code):
                    raise ValueError(f"유효하지 않은 제품코드: {product_code}")
                
                if not isinstance(blocks_count, int) or blocks_count <= 0:
                    raise ValueError(f"블록 수는 양의 정수여야 합니다: {blocks_count}")
        
        elif constraint_type == ConstraintTypes.FORBIDDEN_COMBINATION:
            forbidden_pairs = kwargs.get('forbidden_pairs', [])
            for product1, product2 in forbidden_pairs:
                if not self.validate_product_code(product1):
                    raise ValueError(f"유효하지 않은 제품코드: {product1}")
                if not self.validate_product_code(product2):
                    raise ValueError(f"유효하지 않은 제품코드: {product2}")
        
        if line_id not in self.constraints:
            self.constraints[line_id] = []
        
        self.constraints[line_id].append({
            'type': constraint_type,
            'params': kwargs
        })
    
    def get_line_constraints(self, line_id: str):
        """특정 호기의 제약조건 반환"""
        return self.constraints.get(line_id, [])
    
    def has_constraints(self, line_id: str) -> bool:
        """특정 호기에 제약조건이 있는지 확인"""
        return line_id in self.constraints and len(self.constraints[line_id]) > 0
    
    def get_all_constrained_lines(self) -> list:
        """제약조건이 설정된 모든 호기 반환"""
        return list(self.constraints.keys())
    
    def print_constraints_summary(self, product_name_mapper=None):
        """
        제약조건 설정 요약 출력
        Args:
            product_name_mapper: 제품코드 -> 제품명 매핑 함수 (선택사항)
        """
        print("=== 호기별 제약조건 설정 요약 ===")
        for line_id, constraints in self.constraints.items():
            print(f"호기 {line_id}:")
            for i, constraint in enumerate(constraints, 1):
                constraint_type = constraint['type']
                params = constraint['params']
                
                # 제품명 매핑이 있는 경우 제품코드와 제품명을 함께 표시
                if product_name_mapper:
                    if constraint_type in [ConstraintTypes.START_PRODUCT, ConstraintTypes.START_END_PRODUCT, ConstraintTypes.LAST_PRODUCT]:
                        product_code = params.get('product')
                        if product_code:
                            product_name = product_name_mapper(product_code)
                            print(f"  {i}. {constraint_type}: 제품코드 {product_code} ({product_name})")
                        else:
                            print(f"  {i}. {constraint_type}: {params}")
                    
                    elif constraint_type == ConstraintTypes.PRODUCT_SEQUENCE:
                        sequence = params.get('sequence', [])
                        sequence_with_names = []
                        for product_code in sequence:
                            product_name = product_name_mapper(product_code)
                            sequence_with_names.append(f"{product_code}({product_name})")
                        print(f"  {i}. {constraint_type}: {' > '.join(sequence_with_names)}")
                    
                    elif constraint_type == ConstraintTypes.BLOCK_SEQUENCE:
                        block_sequence = params.get('block_sequence', [])
                        block_info_with_names = []
                        for block_info in block_sequence:
                            product_code = block_info['product']
                            blocks_count = block_info['blocks']
                            product_name = product_name_mapper(product_code)
                            block_info_with_names.append(f"{product_name}({blocks_count}블록)")
                        print(f"  {i}. {constraint_type}: {' → '.join(block_info_with_names)}")
                    
                    elif constraint_type == ConstraintTypes.FORBIDDEN_COMBINATION:
                        forbidden_pairs = params.get('forbidden_pairs', [])
                        forbidden_with_names = []
                        for product1, product2 in forbidden_pairs:
                            product1_name = product_name_mapper(product1)
                            product2_name = product_name_mapper(product2)
                            forbidden_with_names.append(f"{product1}({product1_name}) ↔ {product2}({product2_name})")
                        print(f"  {i}. {constraint_type}: {', '.join(forbidden_with_names)}")
                    
                    else:
                        print(f"  {i}. {constraint_type}: {params}")
                else:
                    print(f"  {i}. {constraint_type}: {params}")
        print("=" * 40)
