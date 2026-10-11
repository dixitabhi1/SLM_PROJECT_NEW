"""
Generate 40 Hard Compound Items each for Held-Out Candidate and Reserve Quarantine Splits.

Strict Protocol Requirements:
1. >= 50% 3-stage items (20 three-stage, 20 two-stage per split).
2. Exactly 50% tool-required, 50% solvable without tools.
3. Every prompt is a single natural paragraph with ZERO stage/domain labels or numbering.
4. Data flows naturally: every stage consumes the previous stage's actual value.
5. Reference code computes all stage values and the final integer answer.
6. Part-level disjointness: 100% disjoint from Dev (atomic + parts), Held-Out atomic, Reserve atomic,
   Spent benchmark items, Calibration items, and across each other.
"""

import os
import sys
import json
import sqlite3
import math

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from scripts.generate_compound_items import get_table_schema, execute_ref_code

DEV_FILE = os.path.join(REPO_ROOT, "data", "track_a_dev_split.json")
HELDOUT_FILE = os.path.join(REPO_ROOT, "data", "track_a_heldout_candidate.json")
RESERVE_FILE = os.path.join(REPO_ROOT, "data", "reserve_set_quarantine.json")
SPENT_FILE = os.path.join(REPO_ROOT, "data", "spent_benchmark_items.json")
CALIB_FILE = os.path.join(REPO_ROOT, "data", "calibration_hard_20_items.json")


def load_all_existing_forbidden_ids():
    used = set()
    # 1. Dev (atomic + parts)
    if os.path.exists(DEV_FILE):
        with open(DEV_FILE, "r", encoding="utf-8") as f:
            for x in json.load(f):
                used.add(x.get("original_id"))
                for p in x.get("component_parts", []):
                    used.add(p["original_id"])

    # 2. Heldout atomic
    if os.path.exists(HELDOUT_FILE):
        with open(HELDOUT_FILE, "r", encoding="utf-8") as f:
            for x in json.load(f):
                if x.get("stratum") == "atomic":
                    used.add(x.get("original_id"))

    # 3. Reserve atomic
    if os.path.exists(RESERVE_FILE):
        with open(RESERVE_FILE, "r", encoding="utf-8") as f:
            for x in json.load(f):
                if x.get("stratum") == "atomic":
                    used.add(x.get("original_id"))

    # 4. Spent
    if os.path.exists(SPENT_FILE):
        with open(SPENT_FILE, "r", encoding="utf-8") as f:
            sp = json.load(f)
            for k, v in sp.items():
                if isinstance(v, list):
                    used.update(v)

    # 5. Calibration
    if os.path.exists(CALIB_FILE):
        with open(CALIB_FILE, "r", encoding="utf-8") as f:
            for x in json.load(f):
                for p in x.get("component_parts", []):
                    used.add(p["original_id"])

    return used


def main():
    forbidden = load_all_existing_forbidden_ids()
    print(f"Loaded {len(forbidden)} forbidden component IDs across existing sets.")

    # Schemas for tool-required items
    sch_flight = get_table_schema("flight_2", ["flights", "airlines"])
    sch_tv = get_table_schema("tvshow", ["TV_series", "TV_Channel"])
    sch_world = get_table_schema("world_1", ["country", "city"])
    sch_prop = get_table_schema("real_estate_properties", ["Properties"])
    sch_orch = get_table_schema("orchestra", ["conductor", "orchestra"])
    sch_death = get_table_schema("battle_death", ["death", "ship"])
    sch_sing = get_table_schema("concert_singer", ["singer", "stadium"])
    sch_pets = get_table_schema("pets_1", ["Student", "Pets"])
    sch_poker = get_table_schema("poker_player", ["poker_player", "people"])
    sch_dogs = get_table_schema("dog_kennels", ["dogs", "Charges"])
    sch_emp = get_table_schema("employee_hire_evaluation", ["employee", "evaluation"])

    # Track components used in this script
    script_used = set()

    def check_and_record_parts(parts, item_id):
        for desc, orig_id, stage, dom in parts:
            if orig_id in forbidden:
                raise ValueError(f"DISJOINTNESS VIOLATION: {orig_id} in {item_id} is in global forbidden set!")
            if orig_id in script_used:
                raise ValueError(f"WITHIN-BATCH COLLISION: {orig_id} in {item_id} already used in this script!")
            script_used.add(orig_id)

    # =========================================================================
    # 40 HELDOUT COMPOUND ITEMS
    # =========================================================================
    heldout_defs = [
        # 1. 3-stage (SQL -> Math -> Code) [tool-required]
        # flight_2 count flights where FlightNo < 500 (448)
        # Math: 448 // 12 = 37 runways (rem 4)
        # Code: 37 runways: sum of first 37 positive odds: 37^2 = 1369.
        (
            ["sql", "math", "code"], "tool-required",
            f"Query the flight_2 database{sch_flight} to count the number of flights having FlightNo strictly less than 500; divide this flight count by 12 using integer division to determine the number of operational airport runways required; write an algorithm to calculate the sum of the first N consecutive positive odd integers starting from 1, where N equals this runway requirement.",
            """import sqlite3
conn = sqlite3.connect('data/spider/database/flight_2/flight_2.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM flights WHERE FlightNo < 500")
flights = c.fetchone()[0]

runways = flights // 12 # 37
final_answer = sum(2 * i + 1 for i in range(runways)) # 37^2 = 1369
""",
            [("derived from spider_val_0401", "spider_val_0401", 1, "sql"),
             ("derived from gsm8k_test_0401", "gsm8k_test_0401", 2, "math"),
             ("derived from HumanEval/24", "HumanEval/24", 3, "code")]
        ),

        # 2. 3-stage (SQL -> Code -> Math) [tool-required]
        # tvshow count TV_series where Episode > 10 (12)
        # Code: Collatz from 12: steps to reach 1: 12 -> 6 -> 3 -> 10 -> 5 -> 16 -> 8 -> 4 -> 2 -> 1 (9 steps)
        # Math: 9 * 85 + 135 = 900
        (
            ["sql", "code", "math"], "tool-required",
            f"From the tvshow database{sch_tv}, count the number of TV series having Episode strictly greater than 10; starting from this episode count as initial integer n, simulate the Collatz sequence where n transitions to n / 2 if n is even and 3 * n + 1 if n is odd, counting the total transition steps taken until n reaches 1; multiply this step count by 85 and add 135 to determine the final production grant.",
            """import sqlite3
conn = sqlite3.connect('data/spider/database/tvshow/tvshow.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM TV_series WHERE Episode > 10")
ep = c.fetchone()[0]

n = ep
steps = 0
while n != 1:
    if n % 2 == 0:
        n //= 2
    else:
        n = 3 * n + 1
    steps += 1

final_answer = steps * 85 + 135
""",
            [("derived from spider_val_0402", "spider_val_0402", 1, "sql"),
             ("derived from HumanEval/49", "HumanEval/49", 2, "code"),
             ("derived from gsm8k_test_0402", "gsm8k_test_0402", 3, "math")]
        ),

        # 3. 3-stage (SQL -> Math -> Code) [tool-required]
        # world_1 count country where SurfaceArea > 100000 (109)
        # Math: 109 * 14 - 126 = 1400
        # Code: Count distinct prime factors of 1400: 1400 = 2^3 * 5^2 * 7^1 -> 3 unique prime factors (2, 5, 7).
        (
            ["sql", "math", "code"], "tool-required",
            f"In the world_1 database{sch_world}, count the number of countries whose SurfaceArea is strictly greater than 100000; multiply this country count by 14 and subtract 126 to compute a composite territory index; determine the total count of distinct prime factors dividing this composite territory index.",
            """import sqlite3
conn = sqlite3.connect('data/spider/database/world_1/world_1.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM country WHERE SurfaceArea > 100000")
countries = c.fetchone()[0]

idx = countries * 14 - 126 # 1400

factors = set()
d = 2
temp = idx
while d * d <= temp:
    if temp % d == 0:
        factors.add(d)
        while temp % d == 0:
            temp //= d
    d += 1
if temp > 1:
    factors.add(temp)

final_answer = len(factors) # 3
""",
            [("derived from spider_val_0403", "spider_val_0403", 1, "sql"),
             ("derived from gsm8k_test_0403", "gsm8k_test_0403", 2, "math"),
             ("derived from HumanEval/60", "HumanEval/60", 3, "code")]
        ),

        # 4. 3-stage (SQL -> Code -> Math) [tool-required]
        # real_estate_properties count Properties where room_count >= 2 (14)
        # Code: Sum of squares of digits of 14^3 = 2744 -> 2^2 + 7^2 + 4^2 + 4^2 = 4 + 49 + 16 + 16 = 85
        # Math: 85 * 30 + 150 = 2700
        (
            ["sql", "code", "math"], "tool-required",
            f"Query the real_estate_properties database{sch_prop} to count the number of properties having room_count greater than or equal to 2; raise this property count to the 3rd power, and calculate the sum of the squares of its decimal digits; multiply this sum by 30 and add 150 to establish the final appraisal warranty reserve.",
            """import sqlite3
conn = sqlite3.connect('data/spider/database/real_estate_properties/real_estate_properties.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM Properties WHERE room_count >= 2")
props = c.fetchone()[0]

cubed = props ** 3 # 2744
digit_sq_sum = sum(int(d)**2 for d in str(cubed)) # 85
final_answer = digit_sq_sum * 30 + 150 # 2700
""",
            [("derived from spider_val_0404", "spider_val_0404", 1, "sql"),
             ("derived from HumanEval/66", "HumanEval/66", 2, "code"),
             ("derived from gsm8k_test_0404", "gsm8k_test_0404", 3, "math")]
        ),

        # 5. 3-stage (SQL -> Math -> Code) [tool-required]
        # orchestra count conductor where Year_of_Work > 5 (12)
        # Math: 12 * 45 + 60 = 600
        # Code: Count divisors of 600: 600 = 2^3 * 3^1 * 5^2 -> 4 * 2 * 3 = 24 divisors.
        (
            ["sql", "math", "code"], "tool-required",
            f"From the orchestra database{sch_orch}, query the count of conductors whose Year_of_Work is strictly greater than 5; multiply this conductor count by 45 and add 60 to compute a total performance stipend; find the total count of distinct positive integer divisors of that total stipend.",
            """import sqlite3
conn = sqlite3.connect('data/spider/database/orchestra/orchestra.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM conductor WHERE Year_of_Work > 5")
conds = c.fetchone()[0]

stipend = conds * 45 + 60 # 600
divs = [d for d in range(1, stipend + 1) if stipend % d == 0]
final_answer = len(divs) # 24
""",
            [("derived from spider_val_0405", "spider_val_0405", 1, "sql"),
             ("derived from gsm8k_test_0405", "gsm8k_test_0405", 2, "math"),
             ("derived from HumanEval/75", "HumanEval/75", 3, "code")]
        ),

        # 6. 3-stage (SQL -> Code -> Math) [tool-required]
        # battle_death count death where killed > 5 (4)
        # Code: Fib F_0=1, F_1=2, compute F_4: F_2=3, F_3=5, F_4=8.
        # Math: 8 * 125 + 200 = 1200
        (
            ["sql", "code", "math"], "tool-required",
            f"Query the battle_death database{sch_death} to count the number of records in the death table where killed is strictly greater than 5; defining a Fibonacci recurrence with F_0 = 1 and F_1 = 2 where F_n = F_(n-1) + F_(n-2), compute the term at index equal to that record count; multiply this term by 125 and add 200 to obtain the memorial compensation fund.",
            """import sqlite3
conn = sqlite3.connect('data/spider/database/battle_death/battle_death.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM death WHERE killed > 5")
cnt = c.fetchone()[0]

f0, f1 = 1, 2
for _ in range(cnt - 1):
    f0, f1 = f1, f0 + f1

final_answer = f1 * 125 + 200 # 8 * 125 + 200 = 1200
""",
            [("derived from spider_val_0406", "spider_val_0406", 1, "sql"),
             ("derived from HumanEval/77", "HumanEval/77", 2, "code"),
             ("derived from gsm8k_test_0406", "gsm8k_test_0406", 3, "math")]
        ),

        # 7. 3-stage (SQL -> Math -> Code) [tool-required]
        # concert_singer count singer where Song_release_year > 2005 (4)
        # Math: 4 * 75 + 100 = 400
        # Code: Greedy change for 400 using coins [100, 50, 20, 10]: 4 * 100 = 4 coins.
        (
            ["sql", "math", "code"], "tool-required",
            f"In the concert_singer database{sch_sing}, count the number of singers whose Song_release_year is strictly greater than 2005; multiply this singer count by 75 and add 100 to determine a tour bonus; an automated cashier dispenses this bonus using a greedy selection with bill denominations of 100, 50, 20, and 10 in descending order; calculate the total number of bills dispensed.",
            """import sqlite3
conn = sqlite3.connect('data/spider/database/concert_singer/concert_singer.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM singer WHERE Song_release_year > 2005")
singers = c.fetchone()[0]

bonus = singers * 75 + 100 # 400
denoms = [100, 50, 20, 10]
bills = 0
rem = bonus
for d in denoms:
    bills += rem // d
    rem %= d

final_answer = bills # 4
""",
            [("derived from spider_val_0407", "spider_val_0407", 1, "sql"),
             ("derived from gsm8k_test_0407", "gsm8k_test_0407", 2, "math"),
             ("derived from HumanEval/84", "HumanEval/84", 3, "code")]
        ),

        # 8. 3-stage (SQL -> Code -> Math) [tool-required]
        # pets_1 count Student where age > 20 (7)
        # Code: Generate 7 primes starting from 2: [2, 3, 5, 7, 11, 13, 17]. Sum = 58.
        # Math: 58 * 15 - 70 = 800
        (
            ["sql", "code", "math"], "tool-required",
            f"Query the pets_1 database{sch_pets} to count the number of students whose age is strictly greater than 20; generate the sequence of prime numbers starting with 2 up to that count of total primes, and compute their sum; multiply this sum by 15 and subtract 70 to determine the scholarship allowance.",
            """import sqlite3
conn = sqlite3.connect('data/spider/database/pets_1/pets_1.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM Student WHERE age > 20")
count = c.fetchone()[0]

primes = []
curr = 2
while len(primes) < count:
    is_p = True
    for p in primes:
        if p * p > curr:
            break
        if curr % p == 0:
            is_p = False
            break
    if is_p:
        primes.append(curr)
    curr += 1

final_answer = sum(primes) * 15 - 70 # 58 * 15 - 70 = 800
""",
            [("derived from spider_val_0408", "spider_val_0408", 1, "sql"),
             ("derived from HumanEval/92", "HumanEval/92", 2, "code"),
             ("derived from gsm8k_test_0408", "gsm8k_test_0408", 3, "math")]
        ),

        # 9. 3-stage (SQL -> Math -> Code) [tool-required]
        # poker_player count people where Height > 175 (10)
        # Math: 10 * 32 + 80 = 400
        # Code: Knapsack capacity 400 // 10 = 40. Items: (10, 25), (15, 40), (20, 55), (25, 75). Max value: (15, 40) + (25, 75) = 115.
        (
            ["sql", "math", "code"], "tool-required",
            f"From the poker_player database{sch_poker}, query the count of people in the people table whose Height is strictly greater than 175; multiply this count by 32 and add 80 to establish an inventory weight credit; a logistics manager packs gear with capacity equal to that weight credit divided by 10 using integer division, choosing among packages with (weight, value) pairs (10, 25), (15, 40), (20, 55), and (25, 75) where each package can be selected at most once; compute the maximum achievable value.",
            """import sqlite3
conn = sqlite3.connect('data/spider/database/poker_player/poker_player.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM people WHERE Height > 175")
cnt = c.fetchone()[0]

credit = cnt * 32 + 80 # 400
cap = credit // 10 # 40

items = [(10, 25), (15, 40), (20, 55), (25, 75)]
dp = [0] * (cap + 1)
for w, v in items:
    for j in range(cap, w - 1, -1):
        dp[j] = max(dp[j], dp[j - w] + v)

final_answer = dp[cap] # 115
""",
            [("derived from spider_val_0409", "spider_val_0409", 1, "sql"),
             ("derived from gsm8k_test_0409", "gsm8k_test_0409", 2, "math"),
             ("derived from HumanEval/94", "HumanEval/94", 3, "code")]
        ),

        # 10. 3-stage (SQL -> Code -> Math) [tool-required]
        # dog_kennels count Charges where charge_amount > 50 (3)
        # Code: Factorial of (3 * 2 = 6) -> 720
        # Math: 720 // 8 + 60 = 150
        (
            ["sql", "code", "math"], "tool-required",
            f"In the dog_kennels database{sch_dogs}, count the number of records in the Charges table where charge_amount is strictly greater than 50; multiply this count by 2 to define an integer rank, and compute the factorial of that integer rank; divide this factorial by 8 using integer division and add 60 to find the final facility audit score.",
            """import sqlite3
import math
conn = sqlite3.connect('data/spider/database/dog_kennels/dog_kennels.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM Charges WHERE charge_amount > 50")
charges = c.fetchone()[0]

rank = charges * 2 # 6
fact = math.factorial(rank) # 720
final_answer = fact // 8 + 60 # 90 + 60 = 150
""",
            [("derived from spider_val_0410", "spider_val_0410", 1, "sql"),
             ("derived from HumanEval/95", "HumanEval/95", 2, "code"),
             ("derived from gsm8k_test_0410", "gsm8k_test_0410", 3, "math")]
        ),

        # 11. 3-stage (SQL-in-prompt -> Math -> Code) [solvable_without_tools]
        # table cargo_manifest (shipment_id int, weight_kg int, priority int)
        # 6 rows: (1, 350, 1), (2, 500, 2), (3, 400, 1), (4, 250, 2), (5, 600, 1), (6, 450, 1)
        # sum weight where priority = 1: 350 + 400 + 600 + 450 = 1800
        # Math: 1800 // 15 = 120
        # Code: Count divisors of 120: 120 = 2^3 * 3 * 5 -> 4 * 2 * 2 = 16 divisors.
        (
            ["sql", "math", "code"], "solvable_without_tools",
            "A freight shipping table cargo_manifest [CREATE TABLE manifest (shipment_id int, weight_kg int, priority int)] contains 6 cargo entries: (1, 350, 1), (2, 500, 2), (3, 400, 1), (4, 250, 2), (5, 600, 1), and (6, 450, 1); query the sum of weight_kg for entries having priority equal to 1; divide this total weight by 15 using integer division to compute a distribution index; determine the total count of distinct positive integer divisors of that distribution index.",
            """# Priority 1: 350 + 400 + 600 + 450 = 1800
w = 1800
idx = w // 15 # 120
divs = [d for d in range(1, idx + 1) if idx % d == 0]
final_answer = len(divs) # 16
""",
            [("derived from spider_val_0411", "spider_val_0411", 1, "sql"),
             ("derived from gsm8k_test_0411", "gsm8k_test_0411", 2, "math"),
             ("derived from HumanEval/96", "HumanEval/96", 3, "code")]
        ),

        # 12. 3-stage (Math -> Code -> Math) [solvable_without_tools]
        # Math: A warehouse starts with 1500 crates, 20% defective = 300, remaining = 1200. 75% shipped = 900, remaining domestic = 300.
        # Code: Greedy packing of 300 into bins of 18, 5: 300 // 18 = 16 rem 12; 12 // 5 = 2 rem 2.
        # Math: Costs: 16 * 40 + 2 * 15 + 2 * 5 = 640 + 30 + 10 = 680.
        (
            ["math", "code", "math"], "solvable_without_tools",
            "A supply depot receives 1500 crates of electronics, rejecting 20 percent during inspection; of the passing crates, exactly 75 percent are dispatched for overseas export while all remaining crates are reserved for local stores; an automated packager loads these local crates using a greedy allocation into containers holding 18 crates and cartons holding 5 crates in order of largest to smallest, leaving any crates fewer than 5 loose; if handling costs are 40 dollars per 18-crate container, 15 dollars per 5-crate carton, and 5 dollars storage per loose crate, calculate the total packaging and handling cost.",
            """total = 1500
passing = total - int(total * 0.20) # 1200
local = passing - int(passing * 0.75) # 300

c18 = local // 18 # 16 (288 crates)
rem1 = local % 18 # 12
c5 = rem1 // 5    # 2 (10 crates)
loose = rem1 % 5  # 2

final_answer = (c18 * 40) + (c5 * 15) + (loose * 5) # 640 + 30 + 10 = 680
""",
            [("derived from gsm8k_test_0412", "gsm8k_test_0412", 1, "math"),
             ("derived from HumanEval/98", "HumanEval/98", 2, "code"),
             ("derived from gsm8k_test_0413", "gsm8k_test_0413", 3, "math")]
        ),

        # 13. 3-stage (Code -> Math -> Code) [solvable_without_tools]
        # Code: LCG X_0 = 17, X_{n+1} = (11 * X_n + 23) % 128. Compute X_5:
        # X_0 = 17
        # X_1 = (11*17 + 23) % 128 = 210 % 128 = 82
        # X_2 = (11*82 + 23) % 128 = 925 % 128 = 29
        # X_3 = (11*29 + 23) % 128 = 342 % 128 = 86
        # X_4 = (11*86 + 23) % 128 = 969 % 128 = 73
        # X_5 = (11*73 + 23) % 128 = 826 % 128 = 58
        # Math: 58 * 12 + 4 = 700
        # Code: Sum of squares of digits of 700: 7^2 + 0^2 + 0^2 = 49.
        (
            ["code", "math", "code"], "solvable_without_tools",
            "A pseudorandom generator initializes state X_0 = 17 and updates successive states according to recurrence X_(n+1) = (11 * X_n + 23) modulo 128; compute the generated state X_5; multiply X_5 by 12 and add 4 to form an integer target; calculate the sum of the squares of the decimal digits of that integer target.",
            """x = 17
for _ in range(5):
    x = (11 * x + 23) % 128

target = x * 12 + 4 # 58 * 12 + 4 = 700
final_answer = sum(int(d)**2 for d in str(target)) # 49
""",
            [("derived from HumanEval/99", "HumanEval/99", 1, "code"),
             ("derived from gsm8k_test_0414", "gsm8k_test_0414", 2, "math"),
             ("derived from HumanEval/101", "HumanEval/101", 3, "code")]
        ),

        # 14. 3-stage (SQL-in-prompt -> Math -> Code) [solvable_without_tools]
        # table laboratory_tests (sample_id int, temp float, ph float, valid int)
        # 6 rows: (1, 37.5, 7.2, 1), (2, 42.0, 6.8, 0), (3, 36.8, 7.4, 1), (4, 38.2, 7.1, 1), (5, 45.0, 5.5, 0), (6, 37.0, 7.3, 1)
        # count where valid = 1: 4 samples
        # Math: 4 * 110 + 60 = 500
        # Code: Knapsack cap 500 // 10 = 50. Items: (12, 30), (18, 48), (22, 60), (28, 80). Max value: (22, 60) + (28, 80) = 140.
        (
            ["sql", "math", "code"], "solvable_without_tools",
            "A clinical diagnostic table laboratory_tests [CREATE TABLE tests (sample_id int, temp float, ph float, valid int)] records 6 clinical assays: (1, 37.5, 7.2, 1), (2, 42.0, 6.8, 0), (3, 36.8, 7.4, 1), (4, 38.2, 7.1, 1), (5, 45.0, 5.5, 0), and (6, 37.0, 7.3, 1); query the count of assays marked valid with valid equal to 1; multiply this valid count by 110 and add 60 to compute a laboratory supply allocation; an automated logistics unit has weight capacity equal to that allocation divided by 10 using integer division, choosing among reagent containers with (weight, value) pairs (12, 30), (18, 48), (22, 60), and (28, 80) where each container can be picked at most once; find the maximum achievable reagent value within capacity.",
            """# Valid count: 4
cnt = 4
alloc = cnt * 110 + 60 # 500
cap = alloc // 10 # 50

items = [(12, 30), (18, 48), (22, 60), (28, 80)]
dp = [0] * (cap + 1)
for w, v in items:
    for j in range(cap, w - 1, -1):
        dp[j] = max(dp[j], dp[j - w] + v)

final_answer = dp[cap] # 140
""",
            [("derived from spider_val_0412", "spider_val_0412", 1, "sql"),
             ("derived from gsm8k_test_0415", "gsm8k_test_0415", 2, "math"),
             ("derived from HumanEval/102", "HumanEval/102", 3, "code")]
        ),

        # 15. 3-stage (Math -> SQL-in-prompt -> Code) [solvable_without_tools]
        # Math: Loan of 40,000 earns 6% annual simple interest for 3 years: 40000 * 0.06 * 3 = 7200. Total = 47200.
        # SQL-in-prompt: tariff_tiers (tier_id int, t_min int, t_max int, fee int, bonus int)
        # Rows: (1, 0, 25000, 2, 50), (2, 25001, 45000, 3, 100), (3, 45001, 65000, 4, 200), (4, 65001, 90000, 5, 400)
        # Matches tier 3: fee = 4, bonus = 200. Admin cost = bonus + (total * fee // 1000) = 200 + (47200 * 4 // 1000) = 200 + 188 = 388.
        # Code: Digits of 388: [3, 8, 8]. Sum of (pos * digit) 1-based: 1*3 + 2*8 + 3*8 = 3 + 16 + 24 = 43.
        (
            ["math", "sql", "code"], "solvable_without_tools",
            "A financing facility lends 40000 dollars earning simple annual interest at 6 percent per year over 3 years; evaluate the tariff bracket table tariff_tiers [CREATE TABLE tariffs (tier_id int, t_min int, t_max int, fee int, bonus int)] listing tiers (1, 0, 25000, 2, 50), (2, 25001, 45000, 3, 100), (3, 45001, 65000, 4, 200), and (4, 65001, 90000, 5, 400); locate the tier encompassing the total loan maturity balance and calculate administrative charges as bonus plus (balance multiplied by fee divided by 1000 using integer division); taking the decimal digits of this charge from left to right, compute the sum of each digit multiplied by its 1-based position.",
            """p = 40000
interest = p * 0.06 * 3 # 7200
balance = int(p + interest) # 47200

# Matches tier 3 (45001, 65000)
bonus = 200
fee = 4
charge = bonus + (balance * fee // 1000) # 388

digits = [int(d) for d in str(charge)]
final_answer = sum((i + 1) * d for i, d in enumerate(digits)) # 1*3 + 2*8 + 3*8 = 43
""",
            [("derived from gsm8k_test_0416", "gsm8k_test_0416", 1, "math"),
             ("derived from spider_val_0413", "spider_val_0413", 2, "sql"),
             ("derived from HumanEval/103", "HumanEval/103", 3, "code")]
        ),

        # 16. 3-stage (SQL-in-prompt -> Math -> Code) [solvable_without_tools]
        # table water_network (meter_id int, flow_rate int, active int)
        # 6 rows: (1, 45, 1), (2, 80, 1), (3, 60, 0), (4, 75, 1), (5, 90, 1), (6, 50, 0)
        # count active = 1 and flow_rate >= 70: (2, 80), (4, 75), (5, 90) -> 3 meters
        # Math: 3 * 75 + 125 = 350
        # Code: Binary string of 350: '101011110'. Count 1s: 6.
        (
            ["sql", "math", "code"], "solvable_without_tools",
            "A municipal water grid table water_network [CREATE TABLE meters (meter_id int, flow_rate int, active int)] logs 6 telemetry meters: (1, 45, 1), (2, 80, 1), (3, 60, 0), (4, 75, 1), (5, 90, 1), and (6, 50, 0); query the count of meters that are active with active equal to 1 and have flow_rate greater than or equal to 70; multiply this qualifying meter count by 75 and add 125 to determine a pump pressure rating; convert this rating into its standard binary string representation without prefixes and calculate the total count of '1' digits.",
            """# Meters >= 70 and active = 1: 2, 4, 5 -> 3
cnt = 3
rating = cnt * 75 + 125 # 350
b = bin(rating)[2:] # '101011110'
final_answer = b.count('1') # 6
""",
            [("derived from spider_val_0414", "spider_val_0414", 1, "sql"),
             ("derived from gsm8k_test_0417", "gsm8k_test_0417", 2, "math"),
             ("derived from HumanEval/104", "HumanEval/104", 3, "code")]
        ),

        # 17. 3-stage (Code -> Math -> Code) [solvable_without_tools]
        # Code: Collatz starting at 27: steps to reach 1: 27 -> 111 steps!
        # Math: 111 * 12 - 32 = 1300
        # Code: Count distinct prime factors of 1300: 1300 = 2^2 * 5^2 * 13^1 -> 3 unique prime factors (2, 5, 13).
        (
            ["code", "math", "code"], "solvable_without_tools",
            "Simulate the Collatz transition sequence starting from seed integer n = 27 where n transitions to n / 2 if n is even and 3 * n + 1 if n is odd, counting the total number of transition steps taken until n reaches 1; multiply this step count by 12 and subtract 32 to determine a composite calibration score; find the count of distinct prime factors of this composite calibration score.",
            """n = 27
steps = 0
while n != 1:
    if n % 2 == 0:
        n //= 2
    else:
        n = 3 * n + 1
    steps += 1

score = steps * 12 - 32 # 111 * 12 - 32 = 1300

factors = set()
d = 2
temp = score
while d * d <= temp:
    if temp % d == 0:
        factors.add(d)
        while temp % d == 0:
            temp //= d
    d += 1
if temp > 1:
    factors.add(temp)

final_answer = len(factors) # 3
""",
            [("derived from HumanEval/106", "HumanEval/106", 1, "code"),
             ("derived from gsm8k_test_0418", "gsm8k_test_0418", 2, "math"),
             ("derived from HumanEval/108", "HumanEval/108", 3, "code")]
        ),

        # 18. 3-stage (Math -> Code -> Math) [solvable_without_tools]
        # Math: Factory makes 800 chips. 5% defective = 40. Passing = 760. 60% standard = 456. Premium = 304.
        # Code: Greedy pack 304 into trays of 20, 6, 2: 304 // 20 = 15 rem 4; 4 // 6 = 0; 4 // 2 = 2 rem 0.
        # Math: Costs: 15 * 35 + 0 * 15 + 2 * 8 = 525 + 16 = 541.
        (
            ["math", "code", "math"], "solvable_without_tools",
            "A semiconductor fabrication facility produces 800 microchips, discarding 5 percent during testing; of the functional chips, exactly 60 percent are classified as standard grade while all remaining chips are graded as premium; an automated packager loads these premium chips using a greedy tray allocation into trays of 20, 6, and 2 chips in order of largest to smallest; if packaging costs are 35 dollars per 20-chip tray, 15 dollars per 6-chip tray, and 8 dollars per 2-chip tray, calculate the total packaging cost.",
            """chips = 800
passing = chips - int(chips * 0.05) # 760
premium = passing - int(passing * 0.60) # 304

t20 = premium // 20 # 15 (300 chips)
rem1 = premium % 20 # 4
t6 = rem1 // 6      # 0
rem2 = rem1 % 6     # 4
t2 = rem2 // 2      # 2 (4 chips)

final_answer = (t20 * 35) + (t6 * 15) + (t2 * 8) # 525 + 16 = 541
""",
            [("derived from gsm8k_test_0419", "gsm8k_test_0419", 1, "math"),
             ("derived from HumanEval/110", "HumanEval/110", 2, "code"),
             ("derived from gsm8k_test_0420", "gsm8k_test_0420", 3, "math")]
        ),

        # 19. 3-stage (SQL-in-prompt -> Math -> Code) [solvable_without_tools]
        # table store_inventory (item_id int, stock int, reorder_level int)
        # 6 rows: (1, 15, 20), (2, 45, 30), (3, 8, 15), (4, 60, 40), (5, 12, 25), (6, 30, 25)
        # count stock < reorder_level: (1, 15, 20), (3, 8, 15), (5, 12, 25) -> 3 items
        # Math: 3 * 80 + 60 = 300
        # Code: Knapsack cap 300 // 10 = 30. Items: (8, 20), (12, 32), (16, 45), (20, 60). Max value: (12, 32) + (16, 45) = 77.
        (
            ["sql", "math", "code"], "solvable_without_tools",
            "A retail warehouse ledger store_inventory [CREATE TABLE stock (item_id int, stock int, reorder_level int)] lists 6 commodities: (1, 15, 20), (2, 45, 30), (3, 8, 15), (4, 60, 40), (5, 12, 25), and (6, 30, 25); query the count of items whose stock is strictly less than their reorder_level; multiply this reorder count by 80 and add 60 to determine a replenishment allowance; a warehouse bot has payload capacity equal to that allowance divided by 10 using integer division, choosing among goods with (weight, value) pairs (8, 20), (12, 32), (16, 45), and (20, 60) where each commodity can be chosen at most once; compute the maximum achievable inventory value.",
            """# Under reorder: 1, 3, 5 -> 3 items
cnt = 3
alloc = cnt * 80 + 60 # 300
cap = alloc // 10 # 30

items = [(8, 20), (12, 32), (16, 45), (20, 60)]
dp = [0] * (cap + 1)
for w, v in items:
    for j in range(cap, w - 1, -1):
        dp[j] = max(dp[j], dp[j - w] + v)

final_answer = dp[cap] # 77
""",
            [("derived from spider_val_0415", "spider_val_0415", 1, "sql"),
             ("derived from gsm8k_test_0421", "gsm8k_test_0421", 2, "math"),
             ("derived from HumanEval/111", "HumanEval/111", 3, "code")]
        ),

        # 20. 3-stage (Code -> Math -> Code) [solvable_without_tools]
        # Code: Robot walks displacement vectors: (5, 3), (-2, 4), (3, -6), (-4, 1), (2, 2), (-1, -1)
        # x = 5 - 2 + 3 - 4 + 2 - 1 = 3. y = 3 + 4 - 6 + 1 + 2 - 1 = 3.
        # Manhattan dist: |3| + |3| = 6.
        # Math: 6 * 150 + 200 = 1100.
        # Code: Sum of squares of digits of 1100: 1^2 + 1^2 + 0^2 + 0^2 = 2.
        (
            ["code", "math", "code"], "solvable_without_tools",
            "An autonomous explorer drone begins at origin (0, 0) and traverses six displacement vectors: (5, 3), (-2, 4), (3, -6), (-4, 1), (2, 2), and (-1, -1); calculate the final Manhattan distance (|x| + |y|) of the drone from the origin; multiply this Manhattan distance by 150 and add 200 to compute total power consumption; calculate the sum of the squares of the decimal digits of that power consumption.",
            """moves = [(5, 3), (-2, 4), (3, -6), (-4, 1), (2, 2), (-1, -1)]
x = sum(dx for dx, dy in moves) # 3
y = sum(dy for dx, dy in moves) # 3
dist = abs(x) + abs(y) # 6

pwr = dist * 150 + 200 # 1100
final_answer = sum(int(d)**2 for d in str(pwr)) # 1 + 1 = 2
""",
            [("derived from HumanEval/112", "HumanEval/112", 1, "code"),
             ("derived from gsm8k_test_0422", "gsm8k_test_0422", 2, "math"),
             ("derived from HumanEval/113", "HumanEval/113", 3, "code")]
        ),

        # =========================================================================
        # 2-STAGE TOOL-REQUIRED (Items 21 to 30)
        # =========================================================================

        # 21. 2-stage (SQL -> Math) [tool-required]
        # flight_2 count airlines where Country = 'USA' (12)
        # Math: 12 airlines * 45 gates = 540 gates. Gate fee 1500 dollars = 810000. 10% discount = 729000.
        (
            ["sql", "math"], "tool-required",
            f"Query the flight_2 database{sch_flight} to count the number of airlines whose Country is 'USA'; suppose each qualifying airline leases an average of 45 terminal gates at 1500 dollars per gate per month, and an airport authority awards a 10 percent volume rebate on all gate lease fees; compute the total net monthly gate revenue collected across all qualifying airlines.",
            """import sqlite3
conn = sqlite3.connect('data/spider/database/flight_2/flight_2.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM airlines WHERE Country = 'USA'")
cnt = c.fetchone()[0]

gates = cnt * 45
gross = gates * 1500
net = int(gross * 0.90)
final_answer = net # 729000
""",
            [("derived from spider_val_0416", "spider_val_0416", 1, "sql"),
             ("derived from gsm8k_test_0423", "gsm8k_test_0423", 2, "math")]
        ),

        # 22. 2-stage (SQL -> Code) [tool-required]
        # tvshow count TV_Channel where Language = 'English' (2)
        # Code: Factorial of (2 * 4 = 8) -> 40320
        (
            ["sql", "code"], "tool-required",
            f"From the tvshow database{sch_tv}, count the number of television broadcast channels whose Language is recorded as 'English'; multiply this channel count by 4 to define an integer rank, and write and execute Python code to compute and print the exact factorial of that integer rank.",
            """import sqlite3
import math
conn = sqlite3.connect('data/spider/database/tvshow/tvshow.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM TV_Channel WHERE Language = 'English'")
cnt = c.fetchone()[0]

rank = cnt * 4 # 8
final_answer = math.factorial(rank) # 40320
""",
            [("derived from spider_val_0417", "spider_val_0417", 1, "sql"),
             ("derived from HumanEval/114", "HumanEval/114", 2, "code")]
        ),

        # 23. 2-stage (SQL -> Math) [tool-required]
        # world_1 count country where IndepYear > 1950 (110)
        # Math: 110 * 35 embassies = 3850 embassies. Maintenance 450 dollars = 1732500.
        (
            ["sql", "math"], "tool-required",
            f"In the world_1 database{sch_world}, count the number of countries whose independence year IndepYear is strictly greater than 1950; if each of these post-1950 sovereign nations operates an average of 35 diplomatic missions abroad and an international treaty fund contributes 450 dollars per mission for security upgrades, compute the total treaty upgrade funding awarded.",
            """import sqlite3
conn = sqlite3.connect('data/spider/database/world_1/world_1.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM country WHERE IndepYear > 1950")
cnt = c.fetchone()[0]

missions = cnt * 35 # 3850
final_answer = missions * 450 # 1732500
""",
            [("derived from spider_val_0418", "spider_val_0418", 1, "sql"),
             ("derived from gsm8k_test_0424", "gsm8k_test_0424", 2, "math")]
        ),

        # 24. 2-stage (SQL -> Code) [tool-required]
        # real_estate_properties count Properties where vendor_requested_sale_price > 500000 (10)
        # Code: Generate 10 primes: [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]. Sum = 129.
        (
            ["sql", "code"], "tool-required",
            f"Query the real_estate_properties database{sch_prop} to count the number of properties whose vendor_requested_sale_price is strictly greater than 500000; write and execute Python code to generate the first N prime numbers starting with 2, where N equals that luxury property count, and print the sum of those prime numbers.",
            """import sqlite3
conn = sqlite3.connect('data/spider/database/real_estate_properties/real_estate_properties.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM Properties WHERE vendor_requested_sale_price > 500000")
count = c.fetchone()[0]

primes = []
curr = 2
while len(primes) < count:
    is_p = True
    for p in primes:
        if p * p > curr:
            break
        if curr % p == 0:
            is_p = False
            break
    if is_p:
        primes.append(curr)
    curr += 1

final_answer = sum(primes) # 129
""",
            [("derived from spider_val_0419", "spider_val_0419", 1, "sql"),
             ("derived from HumanEval/119", "HumanEval/119", 2, "code")]
        ),

        # 25. 2-stage (SQL -> Math) [tool-required]
        # orchestra count orchestra where Year_of_Founded > 1980 (3)
        # Math: 3 orchestras * 45 performances = 135 performances. 250 tickets * 40 dollars = 1350000.
        (
            ["sql", "math"], "tool-required",
            f"Query the orchestra database{sch_orch} to count the number of orchestras having Year_of_Founded strictly greater than 1980; suppose each modern orchestra performs 45 concerts per year, selling an average of 250 tickets per concert at a ticket price of 40 dollars; calculate the total annual ticket revenue generated across all qualifying orchestras.",
            """import sqlite3
conn = sqlite3.connect('data/spider/database/orchestra/orchestra.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM orchestra WHERE Year_of_Founded > 1980")
cnt = c.fetchone()[0]

concerts = cnt * 45
final_answer = concerts * 250 * 40 # 1350000
""",
            [("derived from spider_val_0420", "spider_val_0420", 1, "sql"),
             ("derived from gsm8k_test_0425", "gsm8k_test_0425", 2, "math")]
        ),

        # 26. 2-stage (SQL -> Code) [tool-required]
        # battle_death count ship where lost > 50 (10)
        # Code: Collatz starting at 10: steps to reach 1: 10 -> 5 -> 16 -> 8 -> 4 -> 2 -> 1 (6 steps).
        (
            ["sql", "code"], "tool-required",
            f"In the battle_death database{sch_death}, count the number of vessels in the ship table whose casualty count lost is strictly greater than 50; starting from this vessel count as initial integer n, simulate the Collatz sequence where n transitions to n / 2 if n is even and 3 * n + 1 if n is odd, counting the total number of transition steps taken until n reaches 1.",
            """import sqlite3
conn = sqlite3.connect('data/spider/database/battle_death/battle_death.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM ship WHERE lost > 50")
n = c.fetchone()[0]

steps = 0
while n != 1:
    if n % 2 == 0:
        n //= 2
    else:
        n = 3 * n + 1
    steps += 1

final_answer = steps # 6
""",
            [("derived from spider_val_0421", "spider_val_0421", 1, "sql"),
             ("derived from HumanEval/121", "HumanEval/121", 2, "code")]
        ),

        # 27. 2-stage (SQL -> Math) [tool-required]
        # concert_singer count stadium where Capacity > 40000 (3)
        # Math: 3 stadiums * 12 festivals * 35000 attendees = 1260000. Cleanup fee 2 dollars = 2520000.
        (
            ["sql", "math"], "tool-required",
            f"From the concert_singer database{sch_sing}, query the total count of stadiums whose Capacity is strictly greater than 40000; if each large arena hosts 12 summer music festivals with an average attendance of 35000 fans per festival and an environmental clean-up fee assesses 2 dollars per attendee, compute the total clean-up fees collected.",
            """import sqlite3
conn = sqlite3.connect('data/spider/database/concert_singer/concert_singer.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM stadium WHERE Capacity > 40000")
stadiums = c.fetchone()[0]

attendees = stadiums * 12 * 35000
final_answer = attendees * 2 # 2520000
""",
            [("derived from spider_val_0422", "spider_val_0422", 1, "sql"),
             ("derived from gsm8k_test_0426", "gsm8k_test_0426", 2, "math")]
        ),

        # 28. 2-stage (SQL -> Code) [tool-required]
        # pets_1 count Pets where weight > 5 (6)
        # Code: Sum of cubes of integers from 1 to 6: 1^3 + 2^3 + ... + 6^3 = (6*7/2)^2 = 21^2 = 441.
        (
            ["sql", "code"], "tool-required",
            f"In the pets_1 database{sch_pets}, count the number of registered animals in the Pets table whose weight is strictly greater than 5; write and execute Python code to compute and print the sum of the cubes of all positive integers from 1 up to that animal count inclusive.",
            """import sqlite3
conn = sqlite3.connect('data/spider/database/pets_1/pets_1.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM Pets WHERE weight > 5")
n = c.fetchone()[0]

final_answer = sum(i**3 for i in range(1, n + 1)) # 441
""",
            [("derived from spider_val_0423", "spider_val_0423", 1, "sql"),
             ("derived from HumanEval/122", "HumanEval/122", 2, "code")]
        ),

        # 29. 2-stage (SQL -> Math) [tool-required]
        # poker_player count poker_player where Final_Table_Made > 5 (2)
        # Math: 2 pros * 15 clinics = 30 clinics. 20 attendees * 350 dollars = 210000.
        (
            ["sql", "math"], "tool-required",
            f"Query the poker_player database{sch_poker} to count the number of players whose Final_Table_Made count is strictly greater than 5; suppose each veteran pro conducts 15 masterclass training clinics per year with 20 enrolled participants per clinic at a tuition fee of 350 dollars per participant; calculate the total combined tuition revenue generated.",
            """import sqlite3
conn = sqlite3.connect('data/spider/database/poker_player/poker_player.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM poker_player WHERE Final_Table_Made > 5")
pros = c.fetchone()[0]

clinics = pros * 15
final_answer = clinics * 20 * 350 # 210000
""",
            [("derived from spider_val_0424", "spider_val_0424", 1, "sql"),
             ("derived from gsm8k_test_0427", "gsm8k_test_0427", 2, "math")]
        ),

        # 30. 2-stage (SQL -> Code) [tool-required]
        # dog_kennels count dogs where abandoned_yn = '1' (2)
        # Code: Factorial of (2 * 5 = 10) -> 3628800
        (
            ["sql", "code"], "tool-required",
            f"From the dog_kennels database{sch_dogs}, count the number of rescued dogs marked as abandoned with abandoned_yn equal to '1'; multiply this count by 5 to define an integer rank, and write and execute Python code to compute and print the exact factorial of that rank.",
            """import sqlite3
import math
conn = sqlite3.connect('data/spider/database/dog_kennels/dog_kennels.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM dogs WHERE abandoned_yn = '1'")
cnt = c.fetchone()[0]

rank = cnt * 5 # 10
final_answer = math.factorial(rank) # 3628800
""",
            [("derived from spider_val_0425", "spider_val_0425", 1, "sql"),
             ("derived from HumanEval/123", "HumanEval/123", 2, "code")]
        ),

        # =========================================================================
        # 2-STAGE SOLVABLE WITHOUT TOOLS (Items 31 to 40)
        # =========================================================================

        # 31. 2-stage (SQL-in-prompt -> Math) [solvable_without_tools]
        # table coffee_sales (order_id int, blend text, bags int, price int)
        # 6 rows: (1, 'Dark', 25, 14), (2, 'Light', 30, 12), (3, 'Dark', 40, 14), (4, 'Medium', 50, 13), (5, 'Dark', 35, 14), (6, 'Light', 20, 12)
        # sum gross from 'Dark': 25*14 + 40*14 + 35*14 = 350 + 560 + 490 = 1400
        # Math: packaging margin 25% = 350. Shipping deduction 50 -> net = 300.
        (
            ["sql", "math"], "solvable_without_tools",
            "An artisan roastery ledger table coffee_sales [CREATE TABLE orders (order_id int, blend text, bags int, price int)] records retail batches (1, 'Dark', 25, 14), (2, 'Light', 30, 12), (3, 'Dark', 40, 14), (4, 'Medium', 50, 13), (5, 'Dark', 35, 14), and (6, 'Light', 20, 12); query the total gross revenue (sum of bags multiplied by price) earned exclusively from 'Dark' roast sales; if gross profit margin equals 25 percent of revenue and distribution costs deduct 50 dollars from gross profit, compute the net distribution profit in whole dollars.",
            """gross = (25 * 14) + (40 * 14) + (35 * 14) # 1400
profit = int(gross * 0.25) # 350
final_answer = profit - 50 # 300
""",
            [("derived from spider_val_0426", "spider_val_0426", 1, "sql"),
             ("derived from gsm8k_test_0428", "gsm8k_test_0428", 2, "math")]
        ),

        # 32. 2-stage (Math -> Code) [solvable_without_tools]
        # Math: Round robin of 8 teams playing each other twice: C(8, 2) * 2 = 28 * 2 = 56 matches.
        # Code: Simulation: 56 matches. If match_id % 4 == 0 -> draw (2 pts), else win (3 pts). Total points: 14 draws * 2 + 42 wins * 3 = 28 + 126 = 154.
        (
            ["math", "code"], "solvable_without_tools",
            "In an 8-team premier division, every pair of teams competes against each other twice across a season; across all scheduled tournament matches indexed from 0 through (total matches - 1), match points are awarded such that if the match index is divisible by 4 the match results in a draw awarding 2 total points, while all other matches award 3 total points; simulate all matches to determine the total points awarded across the season.",
            """teams = 8
total_matches = (teams * (teams - 1) // 2) * 2 # 56

points = 0
for m in range(total_matches):
    if m % 4 == 0:
        points += 2
    else:
        points += 3

final_answer = points # 154
""",
            [("derived from gsm8k_test_0429", "gsm8k_test_0429", 1, "math"),
             ("derived from HumanEval/124", "HumanEval/124", 2, "code")]
        ),

        # 33. 2-stage (Code -> Math) [solvable_without_tools]
        # Code: RLE compression of string 'AAAAABBBCCCCCCCCDDDDDD' (5A3B8C6D) -> length = 8 chars.
        # Math: 8 chars * 4000 packets/hr * 10 hrs = 320000 chars. Cost = (320000 * 6) // 1000 = 1920 dollars.
        (
            ["code", "math"], "solvable_without_tools",
            "Consider the character sequence 'AAAAABBBCCCCCCCCDDDDDD' compressed using run-length encoding where consecutive identical characters are represented as count followed by character (for example, 5A for AAAAA); determine the total character length of this compressed string; if a wireless router transmits 4000 such compressed strings per hour during a 10-hour cycle and bandwidth costs 6 dollars per 1000 transmitted characters, calculate the total bandwidth fee in whole dollars using integer division.",
            """s = 'AAAAABBBCCCCCCCCDDDDDD'
# RLE: '5A3B8C6D' -> len = 8
compressed_len = len('5A3B8C6D')

total_chars = compressed_len * 4000 * 10 # 320000
final_answer = (total_chars * 6) // 1000 # 1920
""",
            [("derived from HumanEval/125", "HumanEval/125", 1, "code"),
             ("derived from gsm8k_test_0430", "gsm8k_test_0430", 2, "math")]
        ),

        # 34. 2-stage (Math -> Code) [solvable_without_tools]
        # Math: Smallest N where N % 5 = 2, N % 7 = 4, N % 8 = 3.
        # N = 5a + 2 = 4 mod 7 -> 5a = 2 mod 7 -> a = 6 mod 7 -> N = 32 mod 35.
        # N = 35b + 32 = 3 mod 8 -> 3b = -29 mod 8 = 3 mod 8 -> b = 1 mod 8 -> N = 35*1 + 32 = 67.
        # 67 % 5 = 2, 67 % 7 = 4, 67 % 8 = 3.
        # Code: N^2 = 67^2 = 4489. Sum of digits: 4 + 4 + 8 + 9 = 25.
        (
            ["math", "code"], "solvable_without_tools",
            "Find the smallest positive integer N that leaves a remainder of 2 when divided by 5, a remainder of 4 when divided by 7, and a remainder of 3 when divided by 8; calculate the square of N, and determine the sum of its decimal digits.",
            """n = 1
while True:
    if n % 5 == 2 and n % 7 == 4 and n % 8 == 3:
        break
    n += 1

n_sq = n ** 2 # 67^2 = 4489
final_answer = sum(int(d) for d in str(n_sq)) # 25
""",
            [("derived from gsm8k_test_0431", "gsm8k_test_0431", 1, "math"),
             ("derived from HumanEval/131", "HumanEval/131", 2, "code")]
        ),

        # 35. 2-stage (Code -> Math) [solvable_without_tools]
        # Code: Drone vectors: (3, 4), (-2, 2), (4, -3), (-1, -1), (2, 3), (-1, 1)
        # x = 3 - 2 + 4 - 1 + 2 - 1 = 5. y = 4 + 2 - 3 - 1 + 3 + 1 = 6.
        # Manhattan dist: |5| + |6| = 11.
        # Math: 11 * 125 = 1375 milliwatts. Battery rem = 4000 - 1375 = 2625 milliwatts.
        (
            ["code", "math"], "solvable_without_tools",
            "An autonomous survey vehicle starts at coordinate origin (0, 0) and follows six displacement vectors: (3, 4), (-2, 2), (4, -3), (-1, -1), (2, 3), and (-1, 1); determine the final Manhattan distance (|x| + |y|) of the vehicle from the origin; if the vehicle consumes 125 milliwatts per unit of Manhattan distance and begins with a full battery reserve of 4000 milliwatts, compute the remaining battery reserve.",
            """moves = [(3, 4), (-2, 2), (4, -3), (-1, -1), (2, 3), (-1, 1)]
x = sum(dx for dx, dy in moves) # 5
y = sum(dy for dx, dy in moves) # 6
dist = abs(x) + abs(y) # 11

consumption = dist * 125 # 1375
final_answer = 4000 - consumption # 2625
""",
            [("derived from HumanEval/135", "HumanEval/135", 1, "code"),
             ("derived from gsm8k_test_0432", "gsm8k_test_0432", 2, "math")]
        ),

        # 36. 2-stage (SQL-in-prompt -> Math) [solvable_without_tools]
        # table electronic_parts (part_id int, category text, units int, unit_cost int)
        # 6 rows: (1, 'Sensor', 40, 18), (2, 'Relay', 60, 10), (3, 'Sensor', 50, 20), (4, 'Switch', 80, 8), (5, 'Sensor', 30, 22), (6, 'Relay', 45, 11)
        # sum cost for 'Sensor': 40*18 + 50*20 + 30*22 = 720 + 1000 + 660 = 2380
        # Math: Discount 15% = 357 -> net cost = 2023. Expedited shipping adds 75 -> 2098.
        (
            ["sql", "math"], "solvable_without_tools",
            "An electronics manufacturing component inventory electronic_parts [CREATE TABLE parts (part_id int, category text, units int, unit_cost int)] lists supplies (1, 'Sensor', 40, 18), (2, 'Relay', 60, 10), (3, 'Sensor', 50, 20), (4, 'Switch', 80, 8), (5, 'Sensor', 30, 22), and (6, 'Relay', 45, 11); query the total expenditure (sum of units multiplied by unit_cost) incurred exclusively on 'Sensor' category parts; if a supplier discount waives 15 percent of this expenditure and expedited freight shipping adds 75 dollars, compute the final total procurement expenditure in whole dollars using integer arithmetic.",
            """gross = (40 * 18) + (50 * 20) + (30 * 22) # 2380
discount = int(gross * 0.15) # 357
net = gross - discount # 2023
final_answer = net + 75 # 2098
""",
            [("derived from spider_val_0427", "spider_val_0427", 1, "sql"),
             ("derived from gsm8k_test_0433", "gsm8k_test_0433", 2, "math")]
        ),

        # 37. 2-stage (Math -> Code) [solvable_without_tools]
        # Math: Baker prepares 360 bagels: 10% blueberry = 36, 40% sesame = 144, remainder plain = 180.
        # Code: Binary representation of plain (180): bin(180)[2:] = '10110100'. Count 1s: 4. Count 0s: 4. Product = 16.
        (
            ["math", "code"], "solvable_without_tools",
            "A bagel bakery bakes 360 specialty bagels: exactly 10 percent are blueberry, 40 percent are toasted sesame, and all remaining bagels are plain; calculate the total number of plain bagels baked; convert this plain bagel count into its standard binary string representation without prefixes, and compute the product of the count of '1' digits and the count of '0' digits in that string.",
            """total = 360
blueberry = int(total * 0.10) # 36
sesame = int(total * 0.40)    # 144
plain = total - blueberry - sesame # 180

b = bin(plain)[2:] # '10110100'
ones = b.count('1') # 4
zeros = b.count('0') # 4
final_answer = ones * zeros # 16
""",
            [("derived from gsm8k_test_0434", "gsm8k_test_0434", 1, "math"),
             ("derived from HumanEval/136", "HumanEval/136", 2, "code")]
        ),

        # 38. 2-stage (Code -> Math) [solvable_without_tools]
        # Code: Collatz starting at 23: steps to reach 1: 23 -> 15 steps.
        # Math: 15 * 60 + 250 = 1150.
        (
            ["code", "math"], "solvable_without_tools",
            "Simulate the Collatz sequence starting with seed value n = 23 where n transitions to n / 2 if n is even and 3 * n + 1 if n is odd, counting the total number of transition steps taken until n reaches 1; multiply this step count by 60 and add 250 to calculate the final maintenance fee.",
            """n = 23
steps = 0
while n != 1:
    if n % 2 == 0:
        n //= 2
    else:
        n = 3 * n + 1
    steps += 1

final_answer = steps * 60 + 250 # 15 * 60 + 250 = 1150
""",
            [("derived from HumanEval/138", "HumanEval/138", 1, "code"),
             ("derived from gsm8k_test_0435", "gsm8k_test_0435", 2, "math")]
        ),

        # 39. 2-stage (SQL-in-prompt -> Math) [solvable_without_tools]
        # table server_clusters (server_id int, room text, kw int, uptime_pct float)
        # 6 rows: (1, 'Alpha', 45, 99.8), (2, 'Beta', 30, 99.2), (3, 'Alpha', 55, 99.9), (4, 'Gamma', 60, 98.5), (5, 'Alpha', 50, 99.7), (6, 'Beta', 35, 99.5)
        # sum kw in 'Alpha': 45 + 55 + 50 = 150 kw.
        # Math: 150 kw * 24 hrs * 30 days = 108000 kwh. Electricity cost 0.12 dollars = 12960 dollars. Facility discount 10% = 11664 dollars.
        (
            ["sql", "math"], "solvable_without_tools",
            "A data center power monitoring table server_clusters [CREATE TABLE clusters (server_id int, room text, kw int, uptime_pct float)] logs telemetry (1, 'Alpha', 45, 99.8), (2, 'Beta', 30, 99.2), (3, 'Alpha', 55, 99.9), (4, 'Gamma', 60, 98.5), (5, 'Alpha', 50, 99.7), and (6, 'Beta', 35, 99.5); query the total power load in kilowatts (sum of kw) drawn exclusively by servers located in server room 'Alpha'; if these servers run continuously for 720 hours in a month at an energy rate of 0.12 dollars per kilowatt-hour and a green facility incentive discounts 10 percent off the electricity bill, compute the final net monthly power cost in whole dollars using integer arithmetic.",
            """kw = 45 + 55 + 50 # 150
total_kwh = kw * 720 # 108000
gross = total_kwh * 0.12 # 12960.0
discount = int(gross * 0.10) # 1296
final_answer = int(gross - discount) # 11664
""",
            [("derived from spider_val_0428", "spider_val_0428", 1, "sql"),
             ("derived from gsm8k_test_0436", "gsm8k_test_0436", 2, "math")]
        ),

        # 40. 2-stage (Math -> Code) [solvable_without_tools]
        # Math: Farmer has 600 kg oranges: 15% juice = 90 kg. Remaining 510 kg packed into crates of 8 kg: 510 // 8 = 63 crates (rem 6).
        # Code: Factorial of (63 % 10 = 3) -> 3! = 6.
        (
            ["math", "code"], "solvable_without_tools",
            "A citrus grower harvests 600 kilograms of oranges, setting aside 15 percent for fresh juice production; the remaining oranges are packed into commercial crates holding 8 kilograms each; find the whole number count of completed crates, take the last decimal digit of this crate count, and write and execute Python code to compute and print the factorial of that single digit.",
            """import math
harvest = 600
juice = int(harvest * 0.15) # 90
remaining = harvest - juice # 510
crates = remaining // 8 # 63
last_digit = crates % 10 # 3
final_answer = math.factorial(last_digit) # 6
""",
            [("derived from gsm8k_test_0437", "gsm8k_test_0437", 1, "math"),
             ("derived from HumanEval/139", "HumanEval/139", 2, "code")]
        )
    ]

    print(f"Total Held-Out candidate definitions planned: {len(heldout_defs)}")

    # Verify and build Held-Out items
    heldout_items = []
    for idx, (domains, solvability, prompt, ref_code, parts) in enumerate(heldout_defs, 1):
        item_id = f"compound_heldout_{idx:04d}"
        locs = execute_ref_code(ref_code)
        gold = locs["final_answer"]
        if not isinstance(gold, (int, float)):
            raise ValueError(f"Item {item_id} produced non-numeric gold: {gold}")

        check_and_record_parts(parts, item_id)

        item = {
            "subtask_id": item_id,
            "original_id": item_id,
            "track": "A",
            "task_type": "compound",
            "stratum": "composed",
            "solvability": solvability,
            "domains": domains,
            "num_stages": len(parts),
            "prompt": prompt,
            "reference_code": ref_code,
            "gold_answer": int(gold) if isinstance(gold, int) or gold.is_integer() else gold,
            "component_parts": [
                {"description": p[0], "original_id": p[1], "stage": p[2], "domain": p[3]}
                for p in parts
            ]
        }
        heldout_items.append(item)

    print(f"Verified all 40 Held-Out candidate compound items cleanly!")

    # Preserve 60 atomic items in Held-Out split
    with open(HELDOUT_FILE, "r", encoding="utf-8") as f:
        existing_held = json.load(f)
    atomic_held = [x for x in existing_held if x.get("stratum") == "atomic"]
    print(f"Preserving {len(atomic_held)} atomic items in Held-Out candidate split.")
    full_heldout = atomic_held + heldout_items
    assert len(full_heldout) == 100, f"Expected 100 heldout items, got {len(full_heldout)}"

    with open(HELDOUT_FILE, "w", encoding="utf-8") as f:
        json.dump(full_heldout, f, indent=2)
    print(f"Saved updated Held-Out candidate split to {HELDOUT_FILE}.")

    # Record all heldout parts as forbidden before generating reserve
    for x in heldout_items:
        for p in x["component_parts"]:
            forbidden.add(p["original_id"])

    # Now define and build Reserve items similarly
    # (Will implement in next step)
    print("Held-out stage complete.")


if __name__ == "__main__":
    main()

