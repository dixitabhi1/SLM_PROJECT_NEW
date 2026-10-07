"""
Symbolic mathematics tool using SymPy.
Evaluates expressions, solves equations, and verifies exact mathematical equivalence.
Zero LLM inside.
"""

from typing import Union, Optional, Tuple, Any
from dataclasses import dataclass
import sympy
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
)

_TRANSFORMATIONS = standard_transformations + (implicit_multiplication_application,)


@dataclass
class MathVerdict:
    is_equivalent: bool
    verdict: str  # 'PASS', 'FAIL', 'PARSE_ERROR'
    diff_simplified: Optional[str] = None
    details: Optional[str] = None


class SymbolicMathTool:
    """
    Evaluates and verifies mathematical and algebraic answers using SymPy.
    """

    @staticmethod
    def parse(expression_str: str) -> Optional[sympy.Expr]:
        """Safely parses a string into a SymPy expression."""
        cleaned = expression_str.strip()
        # Remove common formatting markers e.g. '$', '\$', 'box{...}', 'pi'
        cleaned = cleaned.replace("\\$", "").replace("$", "")
        if cleaned.startswith("\\boxed{") and cleaned.endswith("}"):
            cleaned = cleaned[7:-1].strip()
        cleaned = cleaned.replace("\\frac{", "(").replace("}{", ")/(").replace("}", ")")
        cleaned = cleaned.replace("\\cdot", "*").replace("\\times", "*")

        try:
            return parse_expr(cleaned, transformations=_TRANSFORMATIONS, evaluate=True)
        except Exception:
            return None

    @classmethod
    def verify_equivalence(
        cls, candidate_answer: str, gold_answer: str, tolerance: float = 1e-9
    ) -> MathVerdict:
        """
        Tests whether candidate_answer is mathematically equivalent to gold_answer.
        Checks:
        1. Exact string/integer equality
        2. SymPy algebraic simplification: simplify(candidate - gold) == 0
        3. Floating point numerical closeness if numeric
        """
        cand_str = candidate_answer.strip()
        gold_str = gold_answer.strip()

        # 1. Direct text match
        if cand_str == gold_str:
            return MathVerdict(
                is_equivalent=True, verdict="PASS", details="Exact textual match"
            )

        cand_expr = cls.parse(cand_str)
        gold_expr = cls.parse(gold_str)

        if cand_expr is None or gold_expr is None:
            # Fallback to direct numerical string cast
            try:
                c_val = float(cand_str)
                g_val = float(gold_str)
                if abs(c_val - g_val) <= tolerance:
                    return MathVerdict(
                        is_equivalent=True,
                        verdict="PASS",
                        details="Numeric float match within tolerance",
                    )
            except ValueError:
                pass

            return MathVerdict(
                is_equivalent=False,
                verdict="PARSE_ERROR",
                details=f"Could not parse into symbolic expression. Cand: '{cand_str}', Gold: '{gold_str}'",
            )

        try:
            # 2. Exact symbolic equivalence: simplify(cand - gold) == 0
            diff = sympy.simplify(cand_expr - gold_expr)
            if diff == 0:
                return MathVerdict(
                    is_equivalent=True,
                    verdict="PASS",
                    diff_simplified="0",
                    details="Exact symbolic algebraic equivalence",
                )

            # 3. Numerical evaluation if expressions have no free symbols
            if len(cand_expr.free_symbols) == 0 and len(gold_expr.free_symbols) == 0:
                c_val = float(cand_expr.evalf())
                g_val = float(gold_expr.evalf())
                if abs(c_val - g_val) <= tolerance:
                    return MathVerdict(
                        is_equivalent=True,
                        verdict="PASS",
                        details=f"Numerical equivalence ({c_val} == {g_val})",
                    )

            return MathVerdict(
                is_equivalent=False,
                verdict="FAIL",
                diff_simplified=str(diff),
                details=f"Symbolic difference is non-zero: {diff}",
            )

        except Exception as e:
            return MathVerdict(
                is_equivalent=False,
                verdict="FAIL",
                details=f"Simplification error: {e}",
            )

