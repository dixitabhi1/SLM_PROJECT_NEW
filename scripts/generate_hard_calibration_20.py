"""
Generate 20 Hard Calibration Compound Items (Spent Benchmark Items).

Requirements:
1. Exactly 20 items.
2. At least 50% 3-stage items (10 three-stage, 10 two-stage).
3. 50% tool-required (10 items), 50% solvable without tools (10 items).
4. Stage-1 values not guessable (large, non-round counts from real databases or multi-step arithmetic).
5. Tool-required items score ~0% without tools.
6. Reference programs execute and compute gold values.
7. Prompts are one natural paragraph with no stage labels, domain labels, or numbering.
8. Component IDs strictly disjoint from dev, heldout, reserve, and spent sets.
"""

import os
import sys
import json
import sqlite3
import math

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from scripts.generate_compound_items import get_table_schema, execute_ref_code
from scripts.build_dev_compound_40 import load_all_used

OUTPUT_PATH = os.path.join(REPO_ROOT, "data", "calibration_hard_20_items.json")


def generate_hard_calibration_20():
    all_used = load_all_used()
    print(f"Total existing used IDs: {len(all_used)}")

    # Load schemas from Spider databases
    sch_world = get_table_schema("world_1", ["country", "city"])
    sch_orchestra = get_table_schema("orchestra", ["conductor"])
    sch_battle = get_table_schema("battle_death", ["death"])
    sch_poker = get_table_schema("poker_player", ["poker_player"])
    sch_flight = get_table_schema("flight_2", ["flights", "airlines"])
    sch_tv = get_table_schema("tvshow", ["TV_series"])
    sch_dogs = get_table_schema("dog_kennels", ["dogs"])

    definitions = [
        # =========================================================================
        # TOOL-REQUIRED ITEMS (Items 1 to 10: Stage 1 queries real SQLite database)
        # =========================================================================

        # 1. 3-stage (SQL -> Math -> Code) [tool-required]
        # Stage 1: world_1 count cities where CountryCode='USA' (274)
        # Stage 2: Ceil(274 / 18) = 16 warehouses
        # Stage 3: Simulation: budget 500, 16 legs, add (i*17)%31 - 14
        (
            ["sql", "math", "code"], "tool-required",
            f"Query the world_1 database{sch_world} to count how many cities have a CountryCode equal to 'USA'; an intercity parcel dispatch service groups these cities into regional delivery sectors with each sector managing at most 18 cities, requiring the minimum whole number of sectors needed to cover all cities; a vehicle dispatch simulator begins with 500 fuel units and processes each sector index from 1 through that sector count, where each sector adds fuel equal to the sector index multiplied by 17 modulo 31 and then expends 14 fuel units for transit operations; compute the final fuel units remaining at the end of the simulation.",
            """import sqlite3
import math

conn = sqlite3.connect('data/spider/database/world_1/world_1.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM city WHERE CountryCode = 'USA'")
s1_count = c.fetchone()[0]

s2_sectors = math.ceil(s1_count / 18)

fuel = 500
for i in range(1, s2_sectors + 1):
    fuel += (i * 17) % 31 - 14

final_answer = fuel
""",
            [("derived from spider_val_0000", "spider_val_0000", 1, "sql"),
             ("derived from gsm8k_test_0000", "gsm8k_test_0000", 2, "math"),
             ("derived from HumanEval/0", "HumanEval/0", 3, "code")]
        ),

        # 2. 3-stage (SQL -> Code -> Math) [tool-required]
        # Stage 1: world_1 count countries where Continent='Asia' (51)
        # Stage 2: Code recurrence: a_0 = 7, a_n = (3*a_{n-1} + 11) % 1000 for 51 terms, sum terms divisible by 3 (6003)
        # Stage 3: Math: (sum * 4) - 250
        (
            ["sql", "code", "math"], "tool-required",
            f"In the world_1 database{sch_world}, count the total number of countries located in the continent of 'Asia'; an algorithmic pseudorandom generator initializes sequence term a_0 to 7 and generates subsequent terms using the relation a_n = (3 * a_(n-1) + 11) modulo 1000 up to that country count of total generated terms indexed from 1 to that count, summing all generated terms that are evenly divisible by 3; take that accumulated sum, multiply it by 4, and subtract 250 to find the final valuation.",
            """import sqlite3

conn = sqlite3.connect('data/spider/database/world_1/world_1.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM country WHERE Continent = 'Asia'")
countries = c.fetchone()[0]

cur = 7
div3_sum = 0
for _ in range(countries):
    cur = (3 * cur + 11) % 1000
    if cur % 3 == 0:
        div3_sum += cur

final_answer = (div3_sum * 4) - 250
""",
            [("derived from spider_val_0001", "spider_val_0001", 1, "sql"),
             ("derived from HumanEval/1", "HumanEval/1", 2, "code"),
             ("derived from gsm8k_test_0001", "gsm8k_test_0001", 3, "math")]
        ),

        # 3. 3-stage (SQL -> Math -> Code) [tool-required]
        # Stage 1: orchestra sum(Year_of_Work) where Age > 35 (160)
        # Stage 2: Math: 160 // 5 + 17 = 49
        # Stage 3: Code: 49th prime number (2 is 1st prime -> 49th prime is 227), sum of digits squared: (2^2 + 2^2 + 7^2 = 4 + 4 + 49 = 57)
        (
            ["sql", "math", "code"], "tool-required",
            f"From the orchestra database{sch_orchestra}, determine the total combined Year_of_Work for all conductors whose Age is strictly greater than 35; divide this cumulative experience by 5 and add 17 to obtain an integer target rank; compute the prime number that occupies this target rank in the sequence of positive primes starting with 2 as rank 1, and calculate the sum of the squares of its decimal digits.",
            """import sqlite3

conn = sqlite3.connect('data/spider/database/orchestra/orchestra.sqlite')
c = conn.cursor()
c.execute("SELECT sum(Year_of_Work) FROM conductor WHERE Age > 35")
s1_years = c.fetchone()[0]

target_rank = (s1_years // 5) + 17

def nth_prime(n):
    primes = []
    num = 2
    while len(primes) < n:
        if all(num % p != 0 for p in primes if p * p <= num):
            primes.append(num)
        num += 1
    return primes[-1]

prime_val = nth_prime(target_rank)
final_answer = sum(int(d)**2 for d in str(prime_val))
""",
            [("derived from spider_val_0002", "spider_val_0002", 1, "sql"),
             ("derived from gsm8k_test_0002", "gsm8k_test_0002", 2, "math"),
             ("derived from HumanEval/3", "HumanEval/3", 3, "code")]
        ),

        # 4. 3-stage (SQL -> Code -> Math) [tool-required]
        # Stage 1: battle_death sum(Killed) (88)
        # Stage 2: Code: Sequence F_0 = 2, F_1 = 5, F_n = (F_{n-1} + 2 * F_{n-2}) % 88 for n=20.
        # Stage 3: Math: (F_20 * 13) - 7
        (
            ["sql", "code", "math"], "tool-required",
            f"Query the battle_death database{sch_battle} to compute the total sum of Killed individuals across all recorded entries; a recurrence relation is defined with initial values F_0 = 2 and F_1 = 5, where each subsequent term F_n is given by (F_(n-1) + 2 * F_(n-2)) modulo that total killed sum; compute the term at index n = 20, multiply it by 13, and subtract 7.",
            """import sqlite3

conn = sqlite3.connect('data/spider/database/battle_death/battle_death.sqlite')
c = conn.cursor()
c.execute("SELECT sum(Killed) FROM death")
mod_val = c.fetchone()[0]

f0, f1 = 2, 5
for _ in range(2, 21):
    f0, f1 = f1, (f1 + 2 * f0) % mod_val

final_answer = (f1 * 13) - 7
""",
            [("derived from spider_val_0003", "spider_val_0003", 1, "sql"),
             ("derived from HumanEval/4", "HumanEval/4", 2, "code"),
             ("derived from gsm8k_test_0004", "gsm8k_test_0004", 3, "math")]
        ),

        # 5. 3-stage (SQL -> Math -> Code) [tool-required]
        # Stage 1: poker_player sum(Final_Table_Made) (118.0 -> 118)
        # Stage 2: Math: (118 % 7) * 25 = 6 * 25 = 150
        # Stage 3: Code: Inventory of 150 items, process 12 orders: order k requests (3k+2 if odd else 2k+1). Remaining inventory.
        (
            ["sql", "math", "code"], "tool-required",
            f"Query the poker_player database{sch_poker} for the sum of Final_Table_Made across all players; take the remainder when this total is divided by 7 and multiply that remainder by 25 to establish an initial warehouse stock; an automated fulfillment line processes 12 incoming batch requests numbered k from 1 through 12, where batch k consumes (3 * k + 2) units if k is odd and (2 * k + 1) units if k is even; determine the remaining stock count after fulfilling all 12 batches.",
            """import sqlite3

conn = sqlite3.connect('data/spider/database/poker_player/poker_player.sqlite')
c = conn.cursor()
c.execute("SELECT sum(Final_Table_Made) FROM poker_player")
total_ft = int(c.fetchone()[0])

stock = (total_ft % 7) * 25
for k in range(1, 13):
    demand = (3 * k + 2) if (k % 2 == 1) else (2 * k + 1)
    stock -= demand

final_answer = stock
""",
            [("derived from spider_val_0004", "spider_val_0004", 1, "sql"),
             ("derived from gsm8k_test_0005", "gsm8k_test_0005", 2, "math"),
             ("derived from HumanEval/5", "HumanEval/5", 3, "code")]
        ),

        # 6. 2-stage (SQL -> Math) [tool-required]
        # Stage 1: flight_2 count flights where Airline = 1 (100)
        # Stage 2: Math: 100 flights * 142 passengers = 14200. 35% checked bags = 4970 bags. 30 dollars per bag = 149100. 10% discount = 134190 net.
        (
            ["sql", "math"], "tool-required",
            f"Using the flight_2 database{sch_flight}, find the total count of flights operated with Airline ID 1; suppose each of these flights carries an average of 142 passengers, exactly 35 percent of all passengers check a piece of luggage, and each checked piece costs 30 dollars; if a corporate loyalty discount waives 10 percent of the total luggage fees, compute the final net luggage revenue in whole dollars.",
            """import sqlite3

conn = sqlite3.connect('data/spider/database/flight_2/flight_2.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM flights WHERE Airline = 1")
num_flights = c.fetchone()[0]

passengers = num_flights * 142
bags = int(passengers * 0.35)
gross_fees = bags * 30
net_revenue = int(gross_fees * 0.90)

final_answer = net_revenue
""",
            [("derived from spider_val_0005", "spider_val_0005", 1, "sql"),
             ("derived from gsm8k_test_0006", "gsm8k_test_0006", 2, "math")]
        ),

        # 7. 2-stage (SQL -> Code) [tool-required]
        # Stage 1: world_1 count cities where Population > 500000 (539)
        # Stage 2: Code: Collatz sequence length starting from 539 until reaching 1. (539 -> 44 steps)
        (
            ["sql", "code"], "tool-required",
            f"In the world_1 database{sch_world}, count the number of cities with a Population strictly greater than 500000; starting from this exact population count as the initial integer n, simulate the Collatz sequence where n transitions to n / 2 if n is even and 3 * n + 1 if n is odd, until n reaches 1; calculate the total number of transition steps taken to reach 1.",
            """import sqlite3

conn = sqlite3.connect('data/spider/database/world_1/world_1.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM city WHERE Population > 500000")
n = c.fetchone()[0]

steps = 0
while n != 1:
    if n % 2 == 0:
        n //= 2
    else:
        n = 3 * n + 1
    steps += 1

final_answer = steps
""",
            [("derived from spider_val_0006", "spider_val_0006", 1, "sql"),
             ("derived from HumanEval/7", "HumanEval/7", 2, "code")]
        ),

        # 8. 2-stage (SQL -> Math) [tool-required]
        # Stage 1: flight_2 count airlines where Country='USA' (12)
        # Stage 2: Math: 12 airlines * 38 jets = 456 jets. 4 jets/airline * 8500 = 34000. 2 jets/airline * 12000 = 24000. Total per airline = 58000. 12 * 58000 = 696000.
        (
            ["sql", "math"], "tool-required",
            f"From the flight_2 database{sch_flight}, query the count of distinct airlines whose Country is 'USA'; each of these airlines manages an active regional fleet, and during an annual safety overhaul, exactly 4 aircraft per airline undergo turbine servicing at 8500 dollars each and 2 aircraft per airline undergo avionics recertification at 12000 dollars each; calculate the total combined overhaul cost across all qualifying airlines.",
            """import sqlite3

conn = sqlite3.connect('data/spider/database/flight_2/flight_2.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM airlines WHERE Country = 'USA'")
airlines_count = c.fetchone()[0]

cost_per_airline = (4 * 8500) + (2 * 12000)
final_answer = airlines_count * cost_per_airline
""",
            [("derived from spider_val_0007", "spider_val_0007", 1, "sql"),
             ("derived from gsm8k_test_0007", "gsm8k_test_0007", 2, "math")]
        ),

        # 9. 2-stage (SQL -> Code) [tool-required]
        # Stage 1: tvshow count TV_series where Share > 5.0 (11)
        # Stage 2: Code: Generate all binary strings of length 11 with no two consecutive 1s (Fibonacci length 11: 377 strings), count how many contain exactly three 1s: C(9, 3) = 84.
        (
            ["sql", "code"], "tool-required",
            f"Query the tvshow database{sch_tv} to count the number of TV series episodes having a Share strictly greater than 5.0; consider all valid binary sequences of this length that contain no two adjacent 1s; write an algorithm to count how many such valid binary sequences contain exactly three 1s.",
            """import sqlite3

conn = sqlite3.connect('data/spider/database/tvshow/tvshow.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM TV_series WHERE Share > 5.0")
length = c.fetchone()[0]

count = 0
for i in range(1 << length):
    b = bin(i)[2:].zfill(length)
    if '11' not in b and b.count('1') == 3:
        count += 1

final_answer = count
""",
            [("derived from spider_val_0008", "spider_val_0008", 1, "sql"),
             ("derived from HumanEval/8", "HumanEval/8", 2, "code")]
        ),

        # 10. 2-stage (SQL -> Math) [tool-required]
        # Stage 1: dog_kennels count dogs where age > 3 (10)
        # Stage 2: Math: 10 dogs * 420 g = 4200 g/day = 4.2 kg/day. 30 days = 126 kg. Bags of 2.5 kg: ceil(126 / 2.5) = 51 bags. 51 * 45 = 2295 dollars.
        (
            ["sql", "math"], "tool-required",
            f"Query the dog_kennels database{sch_dogs} to count the number of registered dogs whose age is strictly greater than 3; a specialized veterinary shelter feeds each of these senior dogs 420 grams of prescription food per day across a 30-day care cycle, purchasing the food in sealed 2.5 kilogram bags at 45 dollars per bag; determining that partial bags cannot be purchased, compute the total dollar expenditure required to buy sufficient bags to cover all feeding needs.",
            """import sqlite3
import math

conn = sqlite3.connect('data/spider/database/dog_kennels/dog_kennels.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM dogs WHERE age > 3")
dogs = c.fetchone()[0]

daily_grams = dogs * 420
cycle_kg = (daily_grams * 30) / 1000.0
bags = math.ceil(cycle_kg / 2.5)
final_answer = bags * 45
""",
            [("derived from spider_val_0010", "spider_val_0010", 1, "sql"),
             ("derived from gsm8k_test_0008", "gsm8k_test_0008", 2, "math")]
        ),


        # =========================================================================
        # SOLVABLE WITHOUT TOOLS ITEMS (Items 11 to 20: Explicit data/parameters)
        # =========================================================================

        # 11. 3-stage (SQL-in-prompt -> Math -> Code) [solvable_without_tools]
        # Explicit table: 8 rows of server telemetry.
        # Stage 1: count servers where cpu_load > 75 and error_code in (500, 502, 503) -> 5
        # Stage 2: Math: each server has 14 failover events, penalty = 5 * 14 * 6 = 420
        # Stage 3: Code: Knapsack/DP: item values [45, 60, 75, 90, 110], weights [15, 20, 25, 30, 40] with capacity 420 // 5 = 84. Max value.
        (
            ["sql", "math", "code"], "solvable_without_tools",
            "A cloud telemetry table server_logs [CREATE TABLE server_logs (server_id int, cpu_load int, error_code int)] contains 8 rows: (101, 82, 500), (102, 65, 200), (103, 91, 502), (104, 74, 500), (105, 88, 503), (106, 79, 404), (107, 85, 500), and (108, 94, 502); query the count of servers with cpu_load strictly greater than 75 that also logged an error_code in (500, 502, 503); each qualifying server experiences 14 failover incidents, with each incident incurring a base latency penalty score of 6 points; an optimization scheduler allocates backup computing tasks to an auxiliary node whose resource capacity equals that total penalty score divided by 5, selecting among candidate tasks with (weight, value) pairs (15, 45), (20, 60), (25, 75), (30, 90), and (40, 110) where each task may be chosen at most once; compute the maximum achievable total task value within this capacity.",
            """# Server rows > 75 and error in (500, 502, 503):
# 101: 82, 500 (yes)
# 103: 91, 502 (yes)
# 105: 88, 503 (yes)
# 107: 85, 500 (yes)
# 108: 94, 502 (yes)
# Count = 5
servers = 5
total_penalty = servers * 14 * 6 # 420
capacity = total_penalty // 5 # 84

tasks = [(15, 45), (20, 60), (25, 75), (30, 90), (40, 110)]
# 0/1 knapsack for capacity 84
dp = [0] * (capacity + 1)
for w, v in tasks:
    for c in range(capacity, w - 1, -1):
        dp[c] = max(dp[c], dp[c - w] + v)

final_answer = dp[capacity]
""",
            [("derived from spider_val_0011", "spider_val_0011", 1, "sql"),
             ("derived from gsm8k_test_0009", "gsm8k_test_0009", 2, "math"),
             ("derived from HumanEval/9", "HumanEval/9", 3, "code")]
        ),

        # 12. 3-stage (Math -> Code -> Math) [solvable_without_tools]
        # Stage 1: Math: 850 parts, 12% rejected = 102, remaining = 748, 75% chrome = 561, remaining nickel = 187
        # Stage 2: Code: Package 187 into containers of size 13, 7, 3 (greedy: 187 // 13 = 14 rem 5; 5 // 3 = 1 rem 2; 2 items unpacked)
        # Stage 3: Math: Total containers = 14 + 0 + 1 = 15 containers. Shipping cost: 14 * 45 + 1 * 15 + 2 unpacked * 5 = 630 + 15 + 10 = 655
        (
            ["math", "code", "math"], "solvable_without_tools",
            "A precision machining facility fabricates 850 turbine components, discarding 12 percent of them during inspection due to tolerance flaws; of the surviving components, exactly 75 percent receive a specialized chrome finish while all remaining components receive a nickel finish; an automated packing station packages these nickel-finished components using a greedy container allocation with container capacities of 13, 7, and 3 in priority order from largest to smallest, where remaining parts smaller than 3 remain unpackaged; if shipping costs are 45 dollars per 13-part container, 25 dollars per 7-part container, 15 dollars per 3-part container, and 5 dollars storage fee per unpackaged part, calculate the total packaging and storage cost.",
            """parts = 850
surviving = parts - int(parts * 0.12) # 748
nickel = surviving - int(surviving * 0.75) # 187

c13 = nickel // 13 # 14 (182 parts)
rem1 = nickel % 13 # 5
c7 = rem1 // 7     # 0
rem2 = rem1 % 7    # 5
c3 = rem2 // 3     # 1 (3 parts)
rem3 = rem2 % 3    # 2 unpacked

cost = (c13 * 45) + (c7 * 25) + (c3 * 15) + (rem3 * 5)
final_answer = cost
""",
            [("derived from gsm8k_test_0010", "gsm8k_test_0010", 1, "math"),
             ("derived from HumanEval/10", "HumanEval/10", 2, "code"),
             ("derived from gsm8k_test_0011", "gsm8k_test_0011", 3, "math")]
        ),

        # 13. 3-stage (Code -> Math -> Code) [solvable_without_tools]
        # Stage 1: Code trace: LCG X_{n+1} = (17 * X_n + 43) % 256, X_0 = 19. Find X_8.
        # X_0 = 19
        # X_1 = (17*19+43)%256 = (323+43)%256 = 366%256 = 110
        # X_2 = (17*110+43)%256 = (1870+43)%256 = 1913%256 = 121
        # X_3 = (17*121+43)%256 = (2057+43)%256 = 2100%256 = 52
        # X_4 = (17*52+43)%256 = (884+43)%256 = 927%256 = 159
        # X_5 = (17*159+43)%256 = (2703+43)%256 = 2746%256 = 186
        # X_6 = (17*186+43)%256 = (3162+43)%256 = 3205%256 = 133
        # X_7 = (17*133+43)%256 = (2261+43)%256 = 2304%256 = 0
        # X_8 = (17*0+43)%256 = 43
        # Stage 2: Math: (X_8 * 14 - 50) // 3 = (43 * 14 - 50) // 3 = (602 - 50) // 3 = 552 // 3 = 184
        # Stage 3: Code: Product of unique prime factors of 184. 184 = 2^3 * 23. Unique prime factors: 2 and 23. Product = 46.
        (
            ["code", "math", "code"], "solvable_without_tools",
            "A pseudorandom generator initializes seed X_0 = 19 and updates terms according to the congruence X_(n+1) = (17 * X_n + 43) modulo 256; compute the value of generated state X_8; multiply X_8 by 14, subtract 50, and divide the result by 3 using integer division; determine the unique prime factors of the resulting integer and calculate their product.",
            """x = 19
for _ in range(8):
    x = (17 * x + 43) % 256

val = (x * 14 - 50) // 3

# Unique prime factors of val
factors = set()
d = 2
temp = val
while d * d <= temp:
    if temp % d == 0:
        factors.add(d)
        while temp % d == 0:
            temp //= d
    d += 1
if temp > 1:
    factors.add(temp)

prod = 1
for f in factors:
    prod *= f

final_answer = prod
""",
            [("derived from HumanEval/11", "HumanEval/11", 1, "code"),
             ("derived from gsm8k_test_0012", "gsm8k_test_0012", 2, "math"),
             ("derived from HumanEval/12", "HumanEval/12", 3, "code")]
        ),

        # 14. 3-stage (SQL-in-prompt -> Code -> Math) [solvable_without_tools]
        # Explicit table: package shipments [CREATE TABLE shipments (pkg_id int, weight_kg int, priority int)]
        # Rows: (1, 14, 1), (2, 28, 2), (3, 35, 1), (4, 18, 1), (5, 42, 2), (6, 25, 1), (7, 50, 2), (8, 32, 1)
        # Stage 1: sum(weight_kg) where priority = 1 -> 14 + 35 + 18 + 25 + 32 = 124
        # Stage 2: Code: Sort priority weights in descending order [35, 32, 25, 18, 14], compute prefix sums, find index (1-based) where prefix sum >= 60% of total (124 * 0.6 = 74.4 -> 35+32=67, 35+32+25=92 >= 74.4 -> index 3)
        # Stage 3: Math: Multiply index by 150 and add 85: 3 * 150 + 85 = 535.
        (
            ["sql", "code", "math"], "solvable_without_tools",
            "Consider table cargo_manifest [CREATE TABLE cargo (pkg_id int, weight_kg int, priority int)] populated with 8 entries: (1, 14, 1), (2, 28, 2), (3, 35, 1), (4, 18, 1), (5, 42, 2), (6, 25, 1), (7, 50, 2), and (8, 32, 1); query the sum of weight_kg for items with priority equal to 1; sort those priority weights in strictly descending order and determine the minimum 1-based count of largest packages whose cumulative weight equals or exceeds 60 percent of that priority sum; multiply this package count by 150 and add 85 to compute the final handling fee.",
            """weights = [14, 35, 18, 25, 32]
total_w = sum(weights) # 124
target = total_w * 0.60 # 74.4

sorted_w = sorted(weights, reverse=True) # [35, 32, 25, 18, 14]
cumsum = 0
count = 0
for w in sorted_w:
    cumsum += w
    count += 1
    if cumsum >= target:
        break

final_answer = count * 150 + 85
""",
            [("derived from spider_val_0014", "spider_val_0014", 1, "sql"),
             ("derived from HumanEval/15", "HumanEval/15", 2, "code"),
             ("derived from gsm8k_test_0013", "gsm8k_test_0013", 3, "math")]
        ),

        # 15. 3-stage (Math -> SQL-in-prompt -> Code) [solvable_without_tools]
        # Stage 1: Math: An investment of 40,000 earns simple annual interest of 6% for 5 years: interest = 40000 * 0.06 * 5 = 12000. Total = 52000.
        # Stage 2: SQL query on provided table: fee_schedule [CREATE TABLE fees (tier_min int, tier_max int, fee_rate int, flat_bonus int)]
        # Rows: (0, 25000, 2, 50), (25001, 50000, 3, 100), (50001, 75000, 4, 250), (75001, 100000, 5, 500)
        # Row matching 52000: tier (50001, 75000), flat_bonus = 250, fee_rate = 4. Total surcharge = 250 + (52000 * 4 // 1000) = 250 + 208 = 458.
        # Stage 3: Code: Checksum of 458: compute sum of (i * digit) for 1-based index of digits: 1*4 + 2*5 + 3*8 = 4 + 10 + 24 = 38.
        (
            ["math", "sql", "code"], "solvable_without_tools",
            "An institutional investor places 40000 dollars into an account generating simple annual interest at 6 percent per year over 5 years; consider the fee bracket table asset_tiers [CREATE TABLE tiers (tier_min int, tier_max int, fee_rate int, flat_bonus int)] containing rows (0, 25000, 2, 50), (25001, 50000, 3, 100), (50001, 75000, 4, 250), and (75001, 100000, 5, 500); find the tier where the total matured account balance falls and compute the combined service cost as flat_bonus plus (balance multiplied by fee_rate divided by 1000 using integer division); taking the decimal digits of this combined service cost from left to right, compute the sum of each digit multiplied by its 1-based digit position.",
            """principal = 40000
interest = principal * 0.06 * 5
balance = int(principal + interest) # 52000

# Matches tier (50001, 75000)
flat_bonus = 250
fee_rate = 4
service_cost = flat_bonus + (balance * fee_rate // 1000) # 458

digits = [int(d) for d in str(service_cost)]
final_answer = sum((i + 1) * d for i, d in enumerate(digits))
""",
            [("derived from gsm8k_test_0014", "gsm8k_test_0014", 1, "math"),
             ("derived from spider_val_0015", "spider_val_0015", 2, "sql"),
             ("derived from HumanEval/16", "HumanEval/16", 3, "code")]
        ),

        # 16. 2-stage (Math -> Code) [solvable_without_tools]
        # Stage 1: Math: Combinatorial round-robin of 8 teams where each pair plays 2 matches: C(8, 2) * 2 = 28 * 2 = 56 matches.
        # Stage 2: Code: Simulation: 56 matches played. Each match outcome: if match_id % 3 == 0 -> draw (1 pt each), elif match_id % 3 == 1 -> team A win (3 pts), else team B win (3 pts). Compute total points awarded across all 56 matches.
        (
            ["math", "code"], "solvable_without_tools",
            "In an 8-team esports league, every pair of teams plays exactly 2 matches against each other across a seasonal tournament; across all scheduled tournament matches indexed from 0 through (total matches - 1), match outcome points are assigned such that if the match index is divisible by 3 the match ends in a draw awarding 1 point to each team (2 total points), whereas all other matches award 3 total points to the winning team; simulate all matches to determine the total points awarded across the entire tournament.",
            """teams = 8
total_matches = (teams * (teams - 1) // 2) * 2 # 56

total_points = 0
for m in range(total_matches):
    if m % 3 == 0:
        total_points += 2
    else:
        total_points += 3

final_answer = total_points
""",
            [("derived from gsm8k_test_0015", "gsm8k_test_0015", 1, "math"),
             ("derived from HumanEval/18", "HumanEval/18", 2, "code")]
        ),

        # 17. 2-stage (Code -> Math) [solvable_without_tools]
        # Stage 1: Code trace: Run length compression of string 'AAAABBBCCCCCCDDDDEEEEEEEFFFF' (4A3B6C4D7E4F) -> compressed string length = 12 characters.
        # Stage 2: Math: Characters transmitted = 12 * 1200 * 18 = 259200 chars. Cost = 259200 * 4 // 1000 = 1036.
        (
            ["code", "math"], "solvable_without_tools",
            "Consider the character sequence 'AAAABBBCCCCCCDDDDEEEEEEEFFFF' compressed using run-length encoding where consecutive identical characters are represented as count followed by character (for example, 4A for AAAA); determine the character count of this compressed representation; if an IoT sensor network transmits 1200 such compressed payloads per hour during an 18-hour operating shift and data transmission costs 4 dollars per 1000 transmitted characters, calculate the total bandwidth transmission cost in whole dollars using integer division.",
            """s = 'AAAABBBCCCCCCDDDDEEEEEEEFFFF'
# Run-length: 4A, 3B, 6C, 4D, 7E, 4F -> '4A3B6C4D7E4F' -> len = 12
compressed_len = len('4A3B6C4D7E4F') # 12

total_chars = compressed_len * 1200 * 18 # 259200
final_answer = (total_chars * 4) // 1000
""",
            [("derived from HumanEval/19", "HumanEval/19", 1, "code"),
             ("derived from gsm8k_test_0016", "gsm8k_test_0016", 2, "math")]
        ),

        # 18. 2-stage (SQL-in-prompt -> Math) [solvable_without_tools]
        # Explicit table: store_sales [CREATE TABLE sales (item_id int, category text, units_sold int, unit_price int)]
        # Rows: (1, 'Tech', 45, 120), (2, 'Home', 80, 25), (3, 'Tech', 30, 200), (4, 'Clothing', 110, 35), (5, 'Tech', 60, 85), (6, 'Home', 40, 45)
        # Stage 1: SQL query: sum(units_sold * unit_price) where category = 'Tech' -> 45*120 + 30*200 + 60*85 = 5400 + 6000 + 5100 = 16500.
        # Stage 2: Math: gross = 16500. pre_tax = 3630. net = 3085.
        (
            ["sql", "math"], "solvable_without_tools",
            "A retail chain tracks electronics revenue in table retail_ledger [CREATE TABLE sales (item_id int, category text, units_sold int, unit_price int)] with records (1, 'Tech', 45, 120), (2, 'Home', 80, 25), (3, 'Tech', 30, 200), (4, 'Clothing', 110, 35), (5, 'Tech', 60, 85), and (6, 'Home', 40, 45); query the total gross revenue (sum of units_sold multiplied by unit_price) generated exclusively from items in the 'Tech' category; if the business operates on an operating margin where pre-tax profit is exactly 22 percent of gross revenue, and corporate tax claims 15 percent of that pre-tax profit, compute the net post-tax profit in whole dollars using integer arithmetic.",
            """# Tech items:
# 1: 45 * 120 = 5400
# 3: 30 * 200 = 6000
# 5: 60 * 85  = 5100
# Total gross = 16500
gross = 5400 + 6000 + 5100 # 16500
pre_tax_profit = int(gross * 0.22) # 3630
net_profit = int(pre_tax_profit * (1.0 - 0.15)) # 3085

final_answer = net_profit
""",
            [("derived from spider_val_0016", "spider_val_0016", 1, "sql"),
             ("derived from gsm8k_test_0017", "gsm8k_test_0017", 2, "math")]
        ),

        # 19. 2-stage (Math -> Code) [solvable_without_tools]
        # Stage 1: Math: CRT N % 5 = 3, N % 7 = 4, N % 11 = 6 -> N = 193.
        # Stage 2: Code: N^3 = 7,189,057. Digit sum = 37.
        (
            ["math", "code"], "solvable_without_tools",
            "Find the smallest positive integer N that leaves a remainder of 3 when divided by 5, a remainder of 4 when divided by 7, and a remainder of 6 when divided by 11; compute the value of N cubed, and calculate the sum of its decimal digits.",
            """# Smallest positive integer N:
n = 1
while True:
    if n % 5 == 3 and n % 7 == 4 and n % 11 == 6:
        break
    n += 1

n_cubed = n ** 3
final_answer = sum(int(d) for d in str(n_cubed))
""",
            [("derived from gsm8k_test_0018", "gsm8k_test_0018", 1, "math"),
             ("derived from HumanEval/22", "HumanEval/22", 2, "code")]
        ),

        # 20. 2-stage (Code -> Math) [solvable_without_tools]
        # Stage 1: Robot grid walk: final dist = 14.
        # Stage 2: Math: 2500 - (14 * 85) = 1310.
        (
            ["code", "math"], "solvable_without_tools",
            "An autonomous warehouse rover starts at coordinate origin (0, 0) and executes a planned sequence of six displacement vectors: (3, 4), (-1, 2), (5, -2), (-2, -1), (4, 3), and (-3, 2); determine the final Manhattan distance (|x| + |y|) of the rover from the origin; if the rover consumes 85 milliwatts of energy per unit of Manhattan distance and starts with a battery charge of 2500 milliwatts, compute the remaining battery capacity in milliwatts.",
            """moves = [(3, 4), (-1, 2), (5, -2), (-2, -1), (4, 3), (-3, 2)]
x, y = 0, 0
for dx, dy in moves:
    x += dx
    y += dy

dist = abs(x) + abs(y) # 14
energy_used = dist * 85 # 1190
final_answer = 2500 - energy_used # 1310
""",
            [("derived from HumanEval/23", "HumanEval/23", 1, "code"),
             ("derived from gsm8k_test_0019", "gsm8k_test_0019", 2, "math")]
        ),
    ]

    items = []
    for idx, (domains, solvability, prompt, ref_code, parts) in enumerate(definitions, 1):
        item_id = f"calib_hard_{idx:04d}"
        exec_locs = execute_ref_code(ref_code)
        gold_val = exec_locs["final_answer"]

        # Check part-level disjointness
        for desc, orig_id, stage, dom in parts:
            if orig_id in all_used:
                raise ValueError(f"CRITICAL: Component {orig_id} in {item_id} already exists in used registry!")

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
            "gold_answer": gold_val,
            "component_parts": [
                {
                    "description": p[0],
                    "original_id": p[1],
                    "stage": p[2],
                    "domain": p[3]
                }
                for p in parts
            ]
        }
        items.append(item)

    # Save to disk
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)

    print(f"Successfully generated {len(items)} hard calibration items -> {OUTPUT_PATH}")
    print(f"  3-stage items: {sum(1 for x in items if x['num_stages'] == 3)} / {len(items)}")
    print(f"  2-stage items: {sum(1 for x in items if x['num_stages'] == 2)} / {len(items)}")
    print(f"  Tool-required items: {sum(1 for x in items if x['solvability'] == 'tool-required')} / {len(items)}")
    print(f"  Solvable w/o tools items: {sum(1 for x in items if x['solvability'] == 'solvable_without_tools')} / {len(items)}")

    return items


if __name__ == "__main__":
    generate_hard_calibration_20()
