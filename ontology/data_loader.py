import json
import pandas as pd


def load_json_data(products_path: str, lines_path: str, changeover_path: str) -> dict:
    """
    JSON 파일 3종(products, lines, changeover) 로드
    반환 예시:
    {
        'products': {...},
        'lines': {...},
        'changeover': {...}
    }
    """
    with open(products_path, 'r', encoding='utf-8') as f:
        products_data = json.load(f)
    with open(lines_path, 'r', encoding='utf-8') as f:
        lines_data = json.load(f)
    with open(changeover_path, 'r', encoding='utf-8') as f:
        changeover_data = json.load(f)

    return {'products': products_data, 'lines': lines_data, 'changeover': changeover_data}  # dict 형태


def load_order_csv(order_path: str) -> dict:
    """
    생산 지시 수량 CSV 파일 로드

    Args:
        order_path: 주문 CSV 파일 경로

    Returns:
        제품별 생산 지시량 딕셔너리
        예시: {'P001': 100, 'P002': 200}
    """
    order_df = pd.read_csv(order_path)
    order_dict = {}
    for _, row in order_df.iterrows():
        product_code = str(row['제품코드'])  # 예: 'P001'
        quantity = int(row['수량'])         # 예: 100
        order_dict[product_code] = quantity
    return order_dict  # {'P001': 100, ...} 