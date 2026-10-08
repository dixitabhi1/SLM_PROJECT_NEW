"""
Builds and runs 10 calibration compound items on the base model (Phi-4-mini).
Target base model accuracy: 30% to 60%.
"""

import os
import sys
import json
import time
import requests
import sqlite3

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from scripts.generate_compound_items import get_table_schema, execute_ref_code
from src.eval.subtask_checkers import evaluate_subtask

CALIB_FILE = os.path.join(REPO_ROOT, "data", "calibration_10_compound_items.json")
SPENT_FILE = os.path.join(REPO_ROOT, "data", "spent_benchmark_items.json")

def build_calibration_items():
    items = []

    # 1. SQL + Math (tool-required)
    schema_concert = get_table_schema("concert_singer", ["concert", "stadium"])
    ref_01 = """import sqlite3
conn = sqlite3.connect('data/spider/database/concert_singer/concert_singer.sqlite')
c = conn.cursor()
c.execute("SELECT max(T2.capacity) FROM concert AS T1 JOIN stadium AS T2 ON T1.stadium_id = T2.stadium_id WHERE T1.year = 2014")
max_cap = c.fetchone()[0]
attendees = int(max_cap * 0.85)
gross = attendees * 45
final_answer = int(gross * 0.90)
"""
    gold_01 = execute_ref_code(ref_01)["final_answer"]
    items.append({
        "subtask_id": "calib_compound_01",
        "task_type": "composed",
        "stratum": "composed",
        "is_compound": True,
        "domains": ["sql", "math"],
        "solvability": "tool-required",
        "prompt": f"In the concert_singer database{schema_concert}, find the maximum capacity among all stadiums that hosted a concert in the year 2014 by joining the concert and stadium tables; if a musical festival in that stadium sells tickets filling exactly 85 percent of that maximum capacity at a flat rate of 45 dollars per ticket and pays a 10 percent venue service tax on the gross ticket sales, compute the net ticket revenue in whole dollars.",
        "component_parts": [
            {"label": "derived from spider_val_0024", "original_id": "spider_val_0024", "stage": 1, "domain": "sql"},
            {"label": "derived from gsm8k_test_0050", "original_id": "gsm8k_test_0050", "stage": 2, "domain": "math"}
        ],
        "reference_program": ref_01,
        "gold_answer": str(gold_01),
        "checker_type": "exact_match"
    })

    # 2. Math + Code (solvable without tools)
    ref_02 = """b1 = 120
b2 = int(b1 * 1.25)
b3 = (b1 + b2) // 2
total = b1 + b2 + b3
primes = [p for p in [2, 3, 5, 7, 11, 13] if total % p == 0]
final_answer = sum(primes)
"""
    gold_02 = execute_ref_code(ref_02)["final_answer"]
    items.append({
        "subtask_id": "calib_compound_02",
        "task_type": "composed",
        "stratum": "composed",
        "is_compound": True,
        "domains": ["math", "code"],
        "solvability": "solvable_without_tools",
        "prompt": "An artisan bakery produces bread across three morning batches where the first batch yields 120 loaves, the second batch yields 25 percent more loaves than the first, and the third batch yields exactly half the combined sum of the first two batches; calculate the total number of loaves produced across all three batches, and then write and execute Python code to find and print the sum of all distinct prime factors of that total production count.",
        "component_parts": [
            {"label": "derived from gsm8k_test_0042", "original_id": "gsm8k_test_0042", "stage": 1, "domain": "math"},
            {"label": "derived from HumanEval/24", "original_id": "HumanEval/24", "stage": 2, "domain": "code"}
        ],
        "reference_program": ref_02,
        "gold_answer": str(gold_02),
        "checker_type": "exact_match"
    })

    # 3. SQL + Code (tool-required)
    schema_pets = get_table_schema("pets_1", ["pets"])
    ref_03 = """import sqlite3
import math
conn = sqlite3.connect('data/spider/database/pets_1/pets_1.sqlite')
c = conn.cursor()
c.execute("SELECT avg(pet_age) FROM pets GROUP BY petType HAVING count(*) >= 2")
avgs = [r[0] for r in c.fetchall()]
val = int(max(avgs))
fact = math.factorial(val)
final_answer = bin(fact).count('1')
"""
    gold_03 = execute_ref_code(ref_03)["final_answer"]
    items.append({
        "subtask_id": "calib_compound_03",
        "task_type": "composed",
        "stratum": "composed",
        "is_compound": True,
        "domains": ["sql", "code"],
        "solvability": "tool-required",
        "prompt": f"Query the pets_1 database{schema_pets} to group pets by petType and compute the average pet age for pet types that have at least 2 registered pets, take the integer floor of the maximum average age obtained, and write and execute Python code to calculate the factorial of that integer floor and print the total count of binary 1-bits in its standard binary representation.",
        "component_parts": [
            {"label": "derived from spider_val_0049", "original_id": "spider_val_0049", "stage": 1, "domain": "sql"},
            {"label": "derived from HumanEval/84", "original_id": "HumanEval/84", "stage": 2, "domain": "code"}
        ],
        "reference_program": ref_03,
        "gold_answer": str(gold_03),
        "checker_type": "exact_match"
    })

    # 4. Math + Code (solvable without tools)
    ref_04 = """tank = 500 + (35 - 15) * 8
k = 0
while 2 ** (k + 1) <= tank:
    k += 1
final_answer = k
"""
    gold_04 = execute_ref_code(ref_04)["final_answer"]
    items.append({
        "subtask_id": "calib_compound_04",
        "task_type": "composed",
        "stratum": "composed",
        "is_compound": True,
        "domains": ["math", "code"],
        "solvability": "solvable_without_tools",
        "prompt": "An industrial water reservoir initially holds 500 liters; an inlet pipe pumps in 35 liters per hour while an outlet drainage valve discharges 15 liters per hour continuously for 8 hours; determine the final volume of water in liters, and write and execute Python code to determine and print the largest non-negative integer power of 2 that is less than or equal to this final reservoir volume.",
        "component_parts": [
            {"label": "derived from gsm8k_test_0060", "original_id": "gsm8k_test_0060", "stage": 1, "domain": "math"},
            {"label": "derived from HumanEval/60", "original_id": "HumanEval/60", "stage": 2, "domain": "code"}
        ],
        "reference_program": ref_04,
        "gold_answer": str(gold_04),
        "checker_type": "exact_match"
    })

    # 5. SQL + Math (solvable without tools)
    ref_05 = """conductors = 3
apprentices = conductors * 4
final_answer = apprentices * 2 * 6
"""
    gold_05 = execute_ref_code(ref_05)["final_answer"]
    items.append({
        "subtask_id": "calib_compound_05",
        "task_type": "composed",
        "stratum": "composed",
        "is_compound": True,
        "domains": ["sql", "math"],
        "solvability": "solvable_without_tools",
        "prompt": "Given the conductor table schema [CREATE TABLE conductor (Conductor_ID int, Name text, Age int, Nationality text, Year_of_Work int)] populated with the four records (1, 'Kip', 45, 'USA', 6), (2, 'Marta', 52, 'Poland', 12), (3, 'Lars', 38, 'Sweden', 4), and (4, 'Elena', 61, 'Spain', 15), query the count of conductors whose Year_of_Work is strictly greater than 5; if each of these qualifying conductors mentors 4 apprentices and each apprentice performs 2 recitals per month, calculate the total number of apprentice recitals performed over a 6-month season.",
        "component_parts": [
            {"label": "derived from spider_val_0011", "original_id": "spider_val_0011", "stage": 1, "domain": "sql"},
            {"label": "derived from gsm8k_test_0050", "original_id": "gsm8k_test_0050", "stage": 2, "domain": "math"}
        ],
        "reference_program": ref_05,
        "gold_answer": str(gold_05),
        "checker_type": "exact_match"
    })

    # 6. SQL + Math + Code (tool-required)
    schema_poker = get_table_schema("poker_player", ["poker_player", "people"])
    ref_06 = """import sqlite3
conn = sqlite3.connect('data/spider/database/poker_player/poker_player.sqlite')
c = conn.cursor()
c.execute("SELECT max(T1.Earnings) FROM poker_player AS T1 JOIN people AS T2 ON T1.People_ID = T2.People_ID WHERE T2.Nationality IN ('China', 'Russia')")
max_earn = c.fetchone()[0]
rem = (max_earn * 0.75) / 5
payout_int = int(rem)
final_answer = sum(int(d) for d in str(payout_int))
"""
    gold_06 = execute_ref_code(ref_06)["final_answer"]
    items.append({
        "subtask_id": "calib_compound_06",
        "task_type": "composed",
        "stratum": "composed",
        "is_compound": True,
        "domains": ["sql", "math", "code"],
        "solvability": "tool-required",
        "prompt": f"From the poker_player database{schema_poker}, join the poker_player and people tables to query the maximum Earnings recorded for players whose Nationality is either 'China' or 'Russia', deduct a 25 percent tournament entrance and administrative fee from this winning sum, divide the remaining prize equally among 5 syndicate co-owners, take the integer floor of an individual share, and write and execute Python code to compute and print the sum of the decimal digits of this individual share.",
        "component_parts": [
            {"label": "derived from spider_val_0676", "original_id": "spider_val_0676", "stage": 1, "domain": "sql"},
            {"label": "derived from gsm8k_test_0045", "original_id": "gsm8k_test_0045", "stage": 2, "domain": "math"},
            {"label": "derived from HumanEval/84", "original_id": "HumanEval/84", "stage": 3, "domain": "code"}
        ],
        "reference_program": ref_06,
        "gold_answer": str(gold_06),
        "checker_type": "exact_match"
    })

    # 7. Math + Code (solvable without tools)
    ref_07 = """import math
t1 = 180 / 60 * 60
stop = 30
t2 = 240 / 80 * 60
total_min = int(t1 + stop + t2)
final_answer = math.gcd(total_min, 260)
"""
    gold_07 = execute_ref_code(ref_07)["final_answer"]
    items.append({
        "subtask_id": "calib_compound_07",
        "task_type": "composed",
        "stratum": "composed",
        "is_compound": True,
        "domains": ["math", "code"],
        "solvability": "solvable_without_tools",
        "prompt": "A cargo train travels 180 kilometers at a constant speed of 60 km/h, halts at an interchange station for 30 minutes for inspection, and then completes a second leg of 240 kilometers at 80 km/h; compute the total trip duration in minutes from initial departure to final arrival, and then write and execute Python code to calculate and print the greatest common divisor (GCD) of that total duration in minutes and 260.",
        "component_parts": [
            {"label": "derived from gsm8k_test_0075", "original_id": "gsm8k_test_0075", "stage": 1, "domain": "math"},
            {"label": "derived from HumanEval/24", "original_id": "HumanEval/24", "stage": 2, "domain": "code"}
        ],
        "reference_program": ref_07,
        "gold_answer": str(gold_07),
        "checker_type": "exact_match"
    })

    # 8. SQL + Math (solvable without tools)
    ref_08 = """cap = (3 * 150) + (2 * 280)
passengers = cap * 0.80
final_answer = int(passengers * 0.95)
"""
    gold_08 = execute_ref_code(ref_08)["final_answer"]
    items.append({
        "subtask_id": "calib_compound_08",
        "task_type": "composed",
        "stratum": "composed",
        "is_compound": True,
        "domains": ["sql", "math"],
        "solvability": "solvable_without_tools",
        "prompt": "Consider an airline operating table aircraft_fleet [CREATE TABLE fleet (tail_id text, model text, seats int)] with data entries: 4 regional jets with 70 seats each, 3 narrowbodies with 150 seats each, and 2 widebodies with 280 seats each; query the total seat capacity contributed strictly by aircraft models that seat at least 100 passengers; if the airline books flights at an average 80 percent load factor and 5 percent of booked passengers cancel before boarding, compute the net number of boarded passengers in whole persons.",
        "component_parts": [
            {"label": "derived from spider_val_0180", "original_id": "spider_val_0180", "stage": 1, "domain": "sql"},
            {"label": "derived from gsm8k_test_0050", "original_id": "gsm8k_test_0050", "stage": 2, "domain": "math"}
        ],
        "reference_program": ref_08,
        "gold_answer": str(gold_08),
        "checker_type": "exact_match"
    })

    # 9. SQL + Code (tool-required)
    schema_tv = get_table_schema("tvshow", ["TV_Channel", "Cartoon"])
    ref_09 = """import sqlite3
conn = sqlite3.connect('data/spider/database/tvshow/tvshow.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM Cartoon AS T1 JOIN TV_Channel AS T2 ON T1.Channel = T2.id WHERE T2.Country = (SELECT Country FROM TV_Channel GROUP BY Country ORDER BY count(*) DESC LIMIT 1)")
diff = c.fetchone()[0]
final_answer = 4 + (15 - 1) * diff
"""
    gold_09 = execute_ref_code(ref_09)["final_answer"]
    items.append({
        "subtask_id": "calib_compound_09",
        "task_type": "composed",
        "stratum": "composed",
        "is_compound": True,
        "domains": ["sql", "code"],
        "solvability": "tool-required",
        "prompt": f"Using the tvshow database{schema_tv}, join the Cartoon and TV_Channel tables to count how many cartoons air on channels belonging to whichever country possesses the greatest total number of TV channels, and then write and execute Python code to compute and print the 15th term of an arithmetic progression whose first term is 4 and whose common difference is that exact cartoon count.",
        "component_parts": [
            {"label": "derived from spider_val_0595", "original_id": "spider_val_0595", "stage": 1, "domain": "sql"},
            {"label": "derived from HumanEval/15", "original_id": "HumanEval/15", "stage": 2, "domain": "code"}
        ],
        "reference_program": ref_09,
        "gold_answer": str(gold_09),
        "checker_type": "exact_match"
    })

    # 10. Math + Code (solvable without tools)
    ref_10 = """score = 12 * 9 + 8 * 10 - 5
m = 2
while True:
    prod = score * m
    r = int(prod ** 0.5)
    if r * r == prod:
        final_answer = m
        break
    m += 1
"""
    gold_10 = execute_ref_code(ref_10)["final_answer"]
    items.append({
        "subtask_id": "calib_compound_10",
        "task_type": "composed",
        "stratum": "composed",
        "is_compound": True,
        "domains": ["math", "code"],
        "solvability": "solvable_without_tools",
        "prompt": "During a regional archery tournament Robin scores 9 points per target on the first 12 targets, 10 points per target on the next 8 targets, and suffers a 5-point deduction for a line-fault violation; determine Robin's net score, and then write and execute Python code to search for and print the smallest integer multiplier m strictly greater than 1 such that Robin's net score multiplied by m forms a perfect square.",
        "component_parts": [
            {"label": "derived from gsm8k_test_0040", "original_id": "gsm8k_test_0040", "stage": 1, "domain": "math"},
            {"label": "derived from HumanEval/77", "original_id": "HumanEval/77", "stage": 2, "domain": "code"}
        ],
        "reference_program": ref_10,
        "gold_answer": str(gold_10),
        "checker_type": "exact_match"
    })

    with open(CALIB_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)

    # Mark spent in spent_benchmark_items.json
    with open(SPENT_FILE, "r", encoding="utf-8") as f:
        sp_data = json.load(f)
    calib_ids = [item["subtask_id"] for item in items]
    sp_data["calibration_compound_items_spent"] = calib_ids
    with open(SPENT_FILE, "w", encoding="utf-8") as f:
        json.dump(sp_data, f, indent=2)

    print(f"Generated {len(items)} calibration items in {CALIB_FILE}.")
    print(f"Marked {len(calib_ids)} calibration items as spent in {SPENT_FILE}.")
    return items

if __name__ == "__main__":
    build_calibration_items()
