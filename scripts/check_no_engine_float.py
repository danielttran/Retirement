from __future__ import annotations

import ast
import sys
from pathlib import Path

ENGINE_ROOT = Path("packages/planner_engine")


class FloatVisitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.errors: list[str] = []

    def visit_Constant(self, node: ast.Constant) -> None:  # noqa: N802
        if isinstance(node.value, float):
            self.errors.append(f"{self.path}:{node.lineno}:{node.col_offset} float literal")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        if isinstance(node.func, ast.Name) and node.func.id == "float":
            self.errors.append(f"{self.path}:{node.lineno}:{node.col_offset} float() cast")
        self.generic_visit(node)


def main() -> int:
    errors: list[str] = []
    for path in ENGINE_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = FloatVisitor(path)
        visitor.visit(tree)
        errors.extend(visitor.errors)

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

