"""
Tool 1: Calculator (사칙연산)
=================================
사용자가 수식이나 사칙연산을 요청하면 안전하게 계산합니다.

지원 연산:
  - 기본 사칙연산: + - * /
  - 거듭제곱: ** 또는 ^
  - 괄호 우선순위
  - 정수 나머지: %
  - 복합 수식: "3 + 4 * 2 - (10 / 5)"
"""

import ast
import math
import operator
import re
from typing import Union


# 허용된 연산자만 정의 (코드 인젝션 방지)
_ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_ALLOWED_FUNCTIONS = {
    "sqrt": math.sqrt,
    "abs": abs,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
}


def _safe_eval(node: ast.AST) -> float:
    """AST 노드를 재귀적으로 평가합니다. 허용된 연산만 수행."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"지원하지 않는 상수: {node.value}")
    elif isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_OPERATORS:
            raise ValueError(f"지원하지 않는 연산자: {op_type.__name__}")
        left = _safe_eval(node.left)
        right = _safe_eval(node.right)
        if op_type == ast.Div and right == 0:
            raise ZeroDivisionError("0으로 나눌 수 없습니다.")
        return _ALLOWED_OPERATORS[op_type](left, right)
    elif isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_OPERATORS:
            raise ValueError(f"지원하지 않는 단항 연산자: {op_type.__name__}")
        operand = _safe_eval(node.operand)
        return _ALLOWED_OPERATORS[op_type](operand)
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("복잡한 함수 호출은 지원하지 않습니다.")
        func_name = node.func.id
        if func_name not in _ALLOWED_FUNCTIONS:
            raise ValueError(f"지원하지 않는 함수: {func_name}")
        args = [_safe_eval(arg) for arg in node.args]
        return _ALLOWED_FUNCTIONS[func_name](*args)
    else:
        raise ValueError(f"지원하지 않는 표현식 타입: {type(node).__name__}")


def calculate(expression: str) -> dict:
    """
    수학 수식을 안전하게 계산합니다.

    Args:
        expression: 계산할 수식 문자열 (예: "3 + 4 * 2", "sqrt(16)", "(10 - 5) ** 2")

    Returns:
        계산 결과와 과정을 담은 딕셔너리
    """
    # ^ 를 ** 로 변환 (일반 사용자 입력 지원)
    expression_clean = expression.strip().replace("^", "**")

    try:
        tree = ast.parse(expression_clean, mode="eval")
        result = _safe_eval(tree.body)

        # 정수이면 정수로 표시
        if isinstance(result, float) and result.is_integer():
            result_display = int(result)
        else:
            result_display = round(result, 10)  # 소수점 10자리까지

        return {
            "expression": expression,
            "result": result_display,
            "result_str": f"{expression} = {result_display}",
        }

    except ZeroDivisionError as e:
        return {"expression": expression, "error": str(e), "result": None}
    except (ValueError, SyntaxError, TypeError) as e:
        return {
            "expression": expression,
            "error": f"수식 파싱 오류: {str(e)}",
            "result": None,
        }
    except Exception as e:
        return {
            "expression": expression,
            "error": f"계산 오류: {str(e)}",
            "result": None,
        }


def calculate_two_numbers(
    a: float, b: float, operation: str
) -> dict:
    """
    두 숫자에 대해 지정한 사칙연산을 수행합니다.

    Args:
        a: 첫 번째 피연산자
        b: 두 번째 피연산자
        operation: 연산 종류 ('+', '-', '*', '/', '**', '%')

    Returns:
        계산 결과를 담은 딕셔너리
    """
    op_map = {
        "+": ("더하기", operator.add),
        "-": ("빼기", operator.sub),
        "*": ("곱하기", operator.mul),
        "×": ("곱하기", operator.mul),
        "/": ("나누기", operator.truediv),
        "÷": ("나누기", operator.truediv),
        "**": ("거듭제곱", operator.pow),
        "^": ("거듭제곱", operator.pow),
        "%": ("나머지", operator.mod),
    }

    if operation not in op_map:
        return {
            "error": f"지원하지 않는 연산: {operation}. 사용 가능: {list(op_map.keys())}",
            "result": None,
        }

    op_name, op_func = op_map[operation]

    if operation in ("/", "÷") and b == 0:
        return {"error": "0으로 나눌 수 없습니다.", "result": None}

    try:
        result = op_func(a, b)
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return {
            "a": a,
            "b": b,
            "operation": operation,
            "operation_name": op_name,
            "result": result,
            "result_str": f"{a} {operation} {b} = {result}",
        }
    except Exception as e:
        return {"error": str(e), "result": None}


# ─────────────────────────────────────────────────
# 모듈 단독 실행 테스트
# ─────────────────────────────────────────────────
if __name__ == "__main__":
    test_cases = [
        "3 + 4 * 2",
        "(10 - 5) ** 2",
        "sqrt(144)",
        "100 / 4 + 3 * 7",
        "10 / 0",
        "1 + 2; import os",  # 인젝션 시도 - 오류 발생해야 함
    ]
    for expr in test_cases:
        result = calculate(expr)
        print(result)
