import ast
import operator
from collections.abc import Callable
from decimal import Decimal, Underflow, localcontext

from .numbers import validate_number

OPERATORS: dict[type[ast.operator], Callable[[Decimal, Decimal], Decimal]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


def calculate(expression: str, values: dict[str, Decimal]) -> Decimal:
    try:
        with localcontext() as context:
            context.traps[Underflow] = True
            return _calculate(expression, values)
    except SyntaxError as exc:
        raise ValueError("Invalid arithmetic syntax") from exc
    except ArithmeticError as exc:
        raise ValueError("Undefined arithmetic operation") from exc


def _calculate(expression: str, values: dict[str, Decimal]) -> Decimal:
    tree = ast.parse(expression, mode="eval")
    if len(list(ast.walk(tree))) > 100:
        raise ValueError("Expression is too complex")
    used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    if not used or not used <= values.keys():
        raise ValueError("Expression must use supplied evidence variables")

    def evaluate(node: ast.AST) -> Decimal:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Name):
            result = values[node.id]
        elif isinstance(node, ast.Constant) and type(node.value) in (int, float):
            result = Decimal(str(node.value))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            result = evaluate(node.operand) * (1 if isinstance(node.op, ast.UAdd) else -1)
        elif isinstance(node, ast.BinOp):
            result = binary(node, evaluate(node.left), evaluate(node.right))
        else:
            raise ValueError(
                "Only numbers, supplied variables, and arithmetic operators are allowed"
            )
        return validate_number(result)

    return evaluate(tree)


def binary(node: ast.BinOp, left: Decimal, right: Decimal) -> Decimal:
    if isinstance(node.op, ast.Pow):
        if right != int(right) or abs(right) > 8:
            raise ValueError("Only small integer powers are allowed")
        return left ** int(right)
    operation = OPERATORS.get(type(node.op))
    if operation is None:
        raise ValueError("Unsupported arithmetic operation")
    if isinstance(node.op, ast.Div) and right == 0:
        raise ValueError("Division by zero")
    return operation(left, right)
