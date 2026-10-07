"""
SQL execution tool using SQLite in-memory or file stand-ins.
Executes queries and verifies execution-result equivalence against gold queries.
Zero LLM inside.
"""

import sqlite3
from typing import List, Tuple, Any, Dict, Optional, Set
from dataclasses import dataclass


@dataclass
class SQLResult:
    columns: List[str]
    rows: List[Tuple[Any, ...]]
    row_count: int
    error: Optional[str] = None


@dataclass
class SQLVerdict:
    is_match: bool
    verdict: str  # 'PASS', 'FAIL', 'EXECUTION_ERROR'
    cand_row_count: int
    gold_row_count: int
    details: Optional[str] = None


class SQLExecutionTool:
    """
    Executes SQL queries against SQLite databases and verifies result set equivalence.
    """

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.connection = sqlite3.connect(db_path)

    def execute_script(self, ddl_and_seed_sql: str) -> None:
        """Sets up database schema and seed data."""
        cursor = self.connection.cursor()
        cursor.executescript(ddl_and_seed_sql)
        self.connection.commit()

    def query(self, sql_query: str) -> SQLResult:
        """Executes a single SELECT query and returns rows and columns."""
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql_query)
            rows = cursor.fetchall()
            cols = [desc[0] for desc in cursor.description] if cursor.description else []
            return SQLResult(columns=cols, rows=rows, row_count=len(rows))
        except Exception as e:
            return SQLResult(columns=[], rows=[], row_count=0, error=str(e))

    def verify_query_execution_match(
        self, candidate_sql: str, gold_sql: str, order_matters: bool = False
    ) -> SQLVerdict:
        """
        Executes both candidate and gold queries on the active database
        and compares result sets.
        """
        gold_res = self.query(gold_sql)
        if gold_res.error:
            return SQLVerdict(
                is_match=False,
                verdict="EXECUTION_ERROR",
                cand_row_count=0,
                gold_row_count=0,
                details=f"Gold query failed to execute: {gold_res.error}",
            )

        cand_res = self.query(candidate_sql)
        if cand_res.error:
            return SQLVerdict(
                is_match=False,
                verdict="EXECUTION_ERROR",
                cand_row_count=0,
                gold_row_count=gold_res.row_count,
                details=f"Candidate query failed to execute: {cand_res.error}",
            )

        if cand_res.row_count != gold_res.row_count:
            return SQLVerdict(
                is_match=False,
                verdict="FAIL",
                cand_row_count=cand_res.row_count,
                gold_row_count=gold_res.row_count,
                details=f"Row count mismatch: candidate got {cand_res.row_count}, gold got {gold_res.row_count}",
            )

        # Normalization of rows for comparison (handles tuples of ints, floats, strings)
        def normalize_val(v: Any) -> Any:
            if isinstance(v, float):
                return round(v, 4)
            if isinstance(v, str):
                return v.strip().lower()
            return v

        norm_cand = [tuple(normalize_val(x) for x in row) for row in cand_res.rows]
        norm_gold = [tuple(normalize_val(x) for x in row) for row in gold_res.rows]

        if order_matters:
            is_match = norm_cand == norm_gold
        else:
            # Multi-set equality
            from collections import Counter

            is_match = Counter(norm_cand) == Counter(norm_gold)

        return SQLVerdict(
            is_match=is_match,
            verdict="PASS" if is_match else "FAIL",
            cand_row_count=cand_res.row_count,
            gold_row_count=gold_res.row_count,
            details="Result sets match exactly" if is_match else "Result set values mismatch",
        )

    def close(self):
        self.connection.close()

