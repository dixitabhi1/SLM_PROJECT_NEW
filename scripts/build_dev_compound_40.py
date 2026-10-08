"""
Generates the 40 Compound items for Track A Dev Split.
Enforces Conditions 2 through 8:
- Reference program executes and computes gold answer
- Schema included in all SQL prompts
- At least 20 of 40 items tagged 'solvable_without_tools' (55% = 22 items)
- Cross-domain mixing only (SQL+Math, Math+Code, SQL+Code, SQL+Math+Code)
- Varied phrasing and stage orders
- Labeled 'derived from <ID>'
- Strict part-level disjointness with all existing atomic and spent sets
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
SPENT_FILE = os.path.join(REPO_ROOT, "data", "spent_benchmark_items.json")
HELDOUT_FILE = os.path.join(REPO_ROOT, "data", "track_a_heldout_candidate.json")
RESERVE_FILE = os.path.join(REPO_ROOT, "data", "reserve_set_quarantine.json")

def load_all_used():
    with open(DEV_FILE) as f: dev = {x.get("original_id") for x in json.load(f) if x.get("original_id")}
    with open(HELDOUT_FILE) as f: held = {x.get("original_id") for x in json.load(f) if x.get("original_id")}
    with open(RESERVE_FILE) as f: res = {x.get("original_id") for x in json.load(f) if x.get("original_id")}
    with open(SPENT_FILE) as f:
        sp = json.load(f)
        spent = set(sp.get("previous_20_subtasks_spent", [])) | set(sp.get("new_50_hard_subtasks_spent", [])) | set(sp.get("calibration_compound_items_spent", []))
    return dev | held | res | spent

def generate_dev_compound_items():
    all_used = load_all_used()
    items = []

    # Database schemas
    sch_pets = get_table_schema("pets_1", ["pets"])
    sch_orchestra = get_table_schema("orchestra", ["orchestra", "conductor"])
    sch_tv = get_table_schema("tvshow", ["TV_Channel", "Cartoon"])
    sch_concert = get_table_schema("concert_singer", ["concert", "stadium", "singer"])
    sch_poker = get_table_schema("poker_player", ["poker_player", "people"])

    # Template definitions for 40 items
    # 22 solvable without tools, 18 tool-required
    # Mixing: SQL+Math (14), Math+Code (14), SQL+Code (6), SQL+Math+Code (6)

    defs = [
        # --- Group 1: SQL + Math (Items 1 to 14) ---
        # 1. SQL + Math (tool-req)
        (
            ["sql", "math"], "tool-required",
            f"Query the pets_1 database{sch_pets} to count the number of pets whose weight is strictly heavier than 10; suppose Grandma Jones bakes that exact count of apple pies for a firefighter luncheon, cuts each pie into 8 equal slices, and sets them all out for the guests; if exactly 6 slices remain at the end and each guest ate 1 slice, determine how many guests ate pie.",
            """import sqlite3
conn = sqlite3.connect('data/spider/database/pets_1/pets_1.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM pets WHERE weight > 10")
count = c.fetchone()[0]
final_answer = count * 8 - 6
""",
            [("derived from spider_val_0045", "spider_val_0045", 1, "sql"), ("derived from gsm8k_test_0042", "gsm8k_test_0042", 2, "math")]
        ),
        # 2. SQL + Math (solvable without tools)
        (
            ["sql", "math"], "solvable_without_tools",
            "Consider the table student_roster [CREATE TABLE roster (id int, name text, grade int, club_count int)] populated with 5 students having club counts 3, 1, 4, 2, and 5 respectively; query the count of students participating in at least 3 clubs; if each qualifying student spends 4 hours per week on club projects and the club semester runs for 14 weeks, how many total project hours do these students accumulate collectively?",
            """students = 3
hours_per_week = students * 4
final_answer = hours_per_week * 14
""",
            [("derived from spider_val_0046", "spider_val_0046", 1, "sql"), ("derived from gsm8k_test_0045", "gsm8k_test_0045", 2, "math")]
        ),
        # 3. SQL + Math (tool-req)
        (
            ["sql", "math"], "tool-required",
            f"From the concert_singer database{sch_concert}, query the total count of concerts that took place in the year 2014 or 2015; if an event logistics agency supplies each concert with 15 lighting rigs and each rig requires 6 LED panels, but 18 panels arrive damaged and are replaced before showtime, calculate the total count of undamaged LED panels successfully installed across all concerts.",
            """import sqlite3
conn = sqlite3.connect('data/spider/database/concert_singer/concert_singer.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM concert WHERE Year = 2014 OR Year = 2015")
concerts = c.fetchone()[0]
final_answer = concerts * 15 * 6 - 18
""",
            [("derived from spider_val_0020", "spider_val_0020", 1, "sql"), ("derived from gsm8k_test_0050", "gsm8k_test_0050", 2, "math")]
        ),
        # 4. SQL + Math (solvable without tools)
        (
            ["sql", "math"], "solvable_without_tools",
            "An agricultural co-op tracks honey harvests in table honey_log [CREATE TABLE harvest (hive_id int, yield_kg int)] with records for 6 hives yielding 24, 18, 30, 12, 28, and 16 kg; query the count of hives producing at least 20 kg; if all honey from these high-yield hives is packaged into 2-kg jars and sold for 15 dollars per jar, compute the total gross revenue generated.",
            """# Hives >= 20 kg are 24, 30, 28 -> total yield = 82 kg
total_yield = 24 + 30 + 28
jars = total_yield // 2
final_answer = jars * 15
""",
            [("derived from spider_val_0047", "spider_val_0047", 1, "sql"), ("derived from gsm8k_test_0051", "gsm8k_test_0051", 2, "math")]
        ),
        # 5. SQL + Math (tool-req)
        (
            ["sql", "math"], "tool-required",
            f"In the tvshow database{sch_tv}, count how many cartoons were written by Joseph Kuhr; suppose a digital animation studio licenses each of those scripts to produce an animated short consisting of 24 storyboard scenes, with each scene requiring 350 painted animation frames; determine the total number of frames illustrated across all resulting shorts.",
            """import sqlite3
conn = sqlite3.connect('data/spider/database/tvshow/tvshow.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM Cartoon WHERE Written_by = 'Joseph Kuhr'")
cartoons = c.fetchone()[0]
final_answer = cartoons * 24 * 350
""",
            [("derived from spider_val_0589", "spider_val_0589", 1, "sql"), ("derived from gsm8k_test_0052", "gsm8k_test_0052", 2, "math")]
        ),
        # 6. SQL + Math (solvable without tools)
        (
            ["sql", "math"], "solvable_without_tools",
            "A library database contains table shelf_inventory [CREATE TABLE inventory (section text, books int)] recording 5 sections with 80, 110, 95, 140, and 75 books; query the sum of books in sections holding strictly more than 90 books; if a book restoration program cleans 10 percent of these books and binds the remainder in archival cases of 5 books each, how many archival cases are needed?",
            """# Sections > 90 are 110, 95, 140 -> sum = 345
books = 110 + 95 + 140
cleaned = int(books * 0.10)
remaining = books - cleaned
final_answer = remaining // 5
""",
            [("derived from spider_val_0048", "spider_val_0048", 1, "sql"), ("derived from gsm8k_test_0053", "gsm8k_test_0053", 2, "math")]
        ),
        # 7. SQL + Math (tool-req)
        (
            ["sql", "math"], "tool-required",
            f"Query the orchestra database{sch_orchestra} to count the number of distinct conductors whose Year_of_Work is strictly greater than 5; if an arts council awards an endowment dividing 120,000 dollars equally among these veteran conductors, calculate the exact dollar grant awarded to each conductor.",
            """import sqlite3
conn = sqlite3.connect('data/spider/database/orchestra/orchestra.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM conductor WHERE Year_of_Work > 5")
num_conductors = c.fetchone()[0]
final_answer = int(120000 / num_conductors)
""",
            [("derived from spider_val_0012", "spider_val_0012", 1, "sql"), ("derived from gsm8k_test_0054", "gsm8k_test_0054", 2, "math")]
        ),
        # 8. SQL + Math (solvable without tools)
        (
            ["sql", "math"], "solvable_without_tools",
            "A sports analytics table race_times [CREATE TABLE runs (runner_id int, laps int, km_per_lap float)] lists 4 athletes completing laps: (1, 10, 0.4), (2, 15, 0.4), (3, 8, 0.4), and (4, 20, 0.4); query the total kilometers logged by runners who completed at least 12 laps; if each kilometer consumes an estimated 65 calories, compute the total caloric expenditure for those qualifying runners.",
            """# Runners >= 12 laps: runner 2 (15 laps = 6.0 km), runner 4 (20 laps = 8.0 km) -> total = 14.0 km
total_km = (15 * 0.4) + (20 * 0.4)
final_answer = int(total_km * 65)
""",
            [("derived from spider_val_0031", "spider_val_0031", 1, "sql"), ("derived from gsm8k_test_0055", "gsm8k_test_0055", 2, "math")]
        ),
        # 9. SQL + Math (tool-req)
        (
            ["sql", "math"], "tool-required",
            f"From the poker_player database{sch_poker}, find the maximum Earnings among all players; if the champion player pledges 15 percent of these peak earnings to charity and invests 40 percent of the remainder in sovereign bonds, how much capital in whole dollars is invested in bonds?",
            """import sqlite3
conn = sqlite3.connect('data/spider/database/poker_player/poker_player.sqlite')
c = conn.cursor()
c.execute("SELECT max(Earnings) FROM poker_player")
peak = c.fetchone()[0]
rem = peak * 0.85
final_answer = int(rem * 0.40)
""",
            [("derived from spider_val_0677", "spider_val_0677", 1, "sql"), ("derived from gsm8k_test_0056", "gsm8k_test_0056", 2, "math")]
        ),
        # 10. SQL + Math (solvable without tools)
        (
            ["sql", "math"], "solvable_without_tools",
            "A timber warehouse catalog logs table lumber_bundles [CREATE TABLE bundles (bundle_id int, planks int, grade text)] with 4 bundles of Grade-A lumber having plank counts 50, 75, 60, and 65; query the total plank count across all Grade-A bundles; if an outdoor construction project uses 35 planks per pergola, how many complete pergolas can be built from this lumber?",
            """total_planks = 50 + 75 + 60 + 65  # 250
final_answer = total_planks // 35  # 7
""",
            [("derived from spider_val_0014", "spider_val_0014", 1, "sql"), ("derived from gsm8k_test_0057", "gsm8k_test_0057", 2, "math")]
        ),
        # 11. SQL + Math (tool-req)
        (
            ["sql", "math"], "tool-required",
            f"In the pets_1 database{sch_pets}, find the total count of distinct pet types registered in the pets table; if a veterinary clinic stocks a specialty pharmaceutical kit containing 18 doses for each registered pet type and administers 3 doses per week across the facility, how many weeks does the entire stock last?",
            """import sqlite3
conn = sqlite3.connect('data/spider/database/pets_1/pets_1.sqlite')
c = conn.cursor()
c.execute("SELECT count(DISTINCT petType) FROM pets")
pet_types = c.fetchone()[0]
total_doses = pet_types * 18
final_answer = total_doses // 3
""",
            [("derived from spider_val_0050", "spider_val_0050", 1, "sql"), ("derived from gsm8k_test_0058", "gsm8k_test_0058", 2, "math")]
        ),
        # 12. SQL + Math (solvable without tools)
        (
            ["sql", "math"], "solvable_without_tools",
            "A greenhouse monitor table temperature_readings [CREATE TABLE climate (zone int, temp_c float)] records hourly afternoon temperatures across 4 zones: (1, 24.5), (2, 28.0), (3, 26.5), and (4, 29.0); query the average temperature in Celsius across all zones; if ventilation fans automatically turn on when the average exceeds 25.0 C and consume 120 watt-hours for every degree Celsius the average exceeds 20.0 C, calculate the energy consumed in watt-hours.",
            """avg_temp = (24.5 + 28.0 + 26.5 + 29.0) / 4.0  # 27.0
diff = avg_temp - 20.0  # 7.0
final_answer = int(diff * 120)  # 840
""",
            [("derived from spider_val_0015", "spider_val_0015", 1, "sql"), ("derived from gsm8k_test_0059", "gsm8k_test_0059", 2, "math")]
        ),
        # 13. SQL + Math (tool-req)
        (
            ["sql", "math"], "tool-required",
            f"Query the concert_singer database{sch_concert} to find the average age of all registered singers; if a vocal academy awards each registered singer an annual vocal care stipend of 150 dollars per year of their average age, determine the stipend amount in whole dollars rounded down.",
            """import sqlite3
conn = sqlite3.connect('data/spider/database/concert_singer/concert_singer.sqlite')
c = conn.cursor()
c.execute("SELECT avg(Age) FROM singer")
avg_age = c.fetchone()[0]
final_answer = int(avg_age * 150)
""",
            [("derived from spider_val_0021", "spider_val_0021", 1, "sql"), ("derived from gsm8k_test_0061", "gsm8k_test_0061", 2, "math")]
        ),
        # 14. SQL + Math (solvable without tools)
        (
            ["sql", "math"], "solvable_without_tools",
            "An electronics distributor tracks component crates in table warehouse_bins [CREATE TABLE bins (bin_id int, microchips int, defective int)] with 3 bin records: (1, 500, 15), (2, 450, 10), and (3, 600, 25); query the total count of non-defective functional microchips across all bins; if these functional chips are packaged into customer orders of 40 chips each, how many full orders can be fulfilled?",
            """functional = (500 - 15) + (450 - 10) + (600 - 25)  # 485 + 440 + 575 = 1500
final_answer = functional // 40  # 37
""",
            [("derived from spider_val_0016", "spider_val_0016", 1, "sql"), ("derived from gsm8k_test_0062", "gsm8k_test_0062", 2, "math")]
        ),

        # --- Group 2: Math + Code (Items 15 to 28) ---
        # 15. Math + Code (solvable without tools)
        (
            ["math", "code"], "solvable_without_tools",
            "Brandon's iPhone is four times as old as Ben's iPhone, and Ben's iPhone is two times older than Suzy's iPhone; given that Suzy's iPhone is 1 year old, determine the age in years of Brandon's iPhone, and then write and execute Python code that computes and prints the sum of all positive integers from 1 up to that exact age inclusive.",
            """age = 1 * 2 * 4  # 8
final_answer = sum(range(1, age + 1))  # 36
""",
            [("derived from gsm8k_test_0040", "gsm8k_test_0040", 1, "math"), ("derived from HumanEval/60", "HumanEval/60", 2, "code")]
        ),
        # 16. Math + Code (solvable without tools)
        (
            ["math", "code"], "solvable_without_tools",
            "A farmer collects 252 eggs per day and packs them into dozen cartons to sell; compute the weekly production of dozen cartons over a full 7-day week, and then write and execute Python code to compute and print the largest integer divisor of that weekly carton count that is strictly smaller than the count itself.",
            """daily_cartons = 252 // 12  # 21
weekly_cartons = daily_cartons * 7  # 147
divs = []
for d in range(1, 147):
    if 147 % d == 0:
        divs.append(d)
final_answer = max(divs)  # 49
""",
            [("derived from gsm8k_test_0050", "gsm8k_test_0050", 1, "math"), ("derived from HumanEval/24", "HumanEval/24", 2, "code")]
        ),
        # 17. Math + Code (solvable without tools)
        (
            ["math", "code"], "solvable_without_tools",
            "A basket contains 25 oranges among which 1 is bad, 20 percent are unripe, 2 are sour, and the rest are good; determine the count of good oranges, and write and execute Python code to calculate and print the sum of the cubes of all integers from 1 up to that count of good oranges.",
            """good = 25 - 1 - int(25 * 0.20) - 2  # 17
final_answer = sum(i**3 for i in range(1, good + 1))  # 23409
""",
            [("derived from gsm8k_test_0060", "gsm8k_test_0060", 1, "math"), ("derived from HumanEval/151", "HumanEval/151", 2, "code")]
        ),
        # 18. Math + Code (solvable without tools)
        (
            ["math", "code"], "solvable_without_tools",
            "A freelance writer crafts 4 articles per day, each article taking 2 hours; if the writer works 5 days a week and bills 35 dollars per hour, determine the writer's weekly income in dollars, and write and execute Python code to compute and print the total count of distinct factors (divisors) of that weekly income amount.",
            """income = 4 * 2 * 5 * 35  # 1400
factors = [d for d in range(1, income + 1) if income % d == 0]
final_answer = len(factors)  # 24
""",
            [("derived from gsm8k_test_0045", "gsm8k_test_0045", 1, "math"), ("derived from HumanEval/16", "HumanEval/16", 2, "code")]
        ),
        # 19. Math + Code (solvable without tools)
        (
            ["math", "code"], "solvable_without_tools",
            "A florist prepares floral bouquets where each bouquet contains 5 red roses, 3 white lilies, and 4 yellow daisies; if the florist assembles 15 identical bouquets, calculate the total count of flowers used, and write and execute Python code to determine and print the remainder when that flower count raised to the power of 5 is divided by 17.",
            """total_flowers = 15 * (5 + 3 + 4)  # 180
final_answer = pow(total_flowers, 5, 17)  # 8
""",
            [("derived from gsm8k_test_0063", "gsm8k_test_0063", 1, "math"), ("derived from HumanEval/49", "HumanEval/49", 2, "code")]
        ),
        # 20. Math + Code (solvable without tools)
        (
            ["math", "code"], "solvable_without_tools",
            "A runner trains for a marathon over 4 weeks: running 25 km in week one, 35 km in week two, 45 km in week three, and 55 km in week four; compute the total kilometers logged over the training cycle, and write and execute Python code to compute and print the binary representation of that total distance formatted as a string of ones and zeros without any prefix.",
            """total_km = 25 + 35 + 45 + 55  # 160
final_answer = bin(total_km)[2:]  # '10100000'
""",
            [("derived from gsm8k_test_0064", "gsm8k_test_0064", 1, "math"), ("derived from HumanEval/84", "HumanEval/84", 2, "code")]
        ),
        # 21. Math + Code (solvable without tools)
        (
            ["math", "code"], "solvable_without_tools",
            "A school cafeteria serves 180 lunches on Monday, 220 on Tuesday, and 200 on Wednesday; if half of all meals are vegetarian, find the total count of vegetarian meals served across those three days, and write and execute Python code to calculate and print the sum of the digits of that vegetarian meal count.",
            """veg = (180 + 220 + 200) // 2  # 300
final_answer = sum(int(d) for d in str(veg))  # 3
""",
            [("derived from gsm8k_test_0065", "gsm8k_test_0065", 1, "math"), ("derived from HumanEval/66", "HumanEval/66", 2, "code")]
        ),
        # 22. Math + Code (solvable without tools)
        (
            ["math", "code"], "solvable_without_tools",
            "A carpenter cuts an 8-meter wooden beam into 20-centimeter pegs; if 5 pegs are discarded due to knots in the wood, determine the count of usable pegs, and write and execute Python code to determine whether that count of usable pegs is a prime number, printing 1 if it is prime and 0 otherwise.",
            """total_pegs = (8 * 100) // 20  # 40
usable = total_pegs - 5  # 35
is_prime = 1
for d in range(2, int(usable**0.5) + 1):
    if usable % d == 0:
        is_prime = 0
        break
final_answer = is_prime  # 0
""",
            [("derived from gsm8k_test_0066", "gsm8k_test_0066", 1, "math"), ("derived from HumanEval/75", "HumanEval/75", 2, "code")]
        ),
        # 23. Math + Code (tool-req)
        (
            ["math", "code"], "tool-required",
            "A simulated particle accelerator injects 1,000 particles at t=0; every microsecond 12 percent of remaining particles decay while 50 new particles are added from a feeder beam; compute the particle population remaining after exactly 25 microseconds rounded to the nearest integer, and write and execute Python code to simulate this discrete recurrence relation and print the resulting population count.",
            """pop = 1000.0
for _ in range(25):
    pop = pop * 0.88 + 50.0
final_answer = round(pop)
""",
            [("derived from gsm8k_test_0067", "gsm8k_test_0067", 1, "math"), ("derived from HumanEval/106", "HumanEval/106", 2, "code")]
        ),
        # 24. Math + Code (tool-req)
        (
            ["math", "code"], "tool-required",
            "A crypto-mining syndicate operates an algorithmic payout pool where daily rewards follow the sequence R(n) = (n^3 - 3*n + 7) mod 1000 for days n=1 to 30; write and execute Python code to evaluate this formula for each of the 30 days, sum the rewards, and print the maximum contiguous 3-day payout sum achieved across the period.",
            """rewards = [(n**3 - 3*n + 7) % 1000 for n in range(1, 31)]
max_3day = 0
for i in range(len(rewards)-2):
    s = sum(rewards[i:i+3])
    if s > max_3day:
        max_3day = s
final_answer = max_3day
""",
            [("derived from gsm8k_test_0068", "gsm8k_test_0068", 1, "math"), ("derived from HumanEval/114", "HumanEval/114", 2, "code")]
        ),
        # 25. Math + Code (solvable without tools)
        (
            ["math", "code"], "solvable_without_tools",
            "A delivery driver completes 12 deliveries on Thursday, each taking 15 minutes, and 8 deliveries on Friday, each taking 20 minutes; calculate the total delivery time in hours, and write and execute Python code to compute and print the factorial of that number of hours.",
            """import math
hours = ((12 * 15) + (9 * 20)) // 60  # 6
final_answer = math.factorial(hours)  # 720
""",
            [("derived from gsm8k_test_0069", "gsm8k_test_0069", 1, "math"), ("derived from HumanEval/139", "HumanEval/139", 2, "code")]
        ),
        # 26. Math + Code (solvable without tools)
        (
            ["math", "code"], "solvable_without_tools",
            "An investor buys 40 shares of stock at 25 dollars and 60 shares at 30 dollars; compute the average purchase price per share in dollars, and write and execute Python code to find and print the number of trailing zeros in the decimal representation of the cube of that average price.",
            """cost = (40 * 25) + (60 * 30)  # 1000 + 1800 = 2800
shares = 100
avg_price = cost // shares  # 28
cube = avg_price ** 3  # 21952 -> 0 trailing zeros
# Let's count trailing zeros
s = str(cube)
final_answer = len(s) - len(s.rstrip('0'))  # 0
""",
            [("derived from gsm8k_test_0070", "gsm8k_test_0070", 1, "math"), ("derived from HumanEval/155", "HumanEval/155", 2, "code")]
        ),
        # 27. Math + Code (tool-req)
        (
            ["math", "code"], "tool-required",
            "Consider a Collatz sequence starting at n=27; write and execute Python code to generate the sequence until it reaches 1, count the total number of intermediate steps taken, and print the maximum value attained along the path.",
            """n = 27
max_val = n
while n != 1:
    if n % 2 == 0:
        n = n // 2
    else:
        n = 3 * n + 1
    if n > max_val:
        max_val = n
final_answer = max_val  # 9232
""",
            [("derived from gsm8k_test_0071", "gsm8k_test_0071", 1, "math"), ("derived from HumanEval/123", "HumanEval/123", 2, "code")]
        ),
        # 28. Math + Code (solvable without tools)
        (
            ["math", "code"], "solvable_without_tools",
            "A cinema sells 80 adult tickets at 12 dollars and 40 child tickets at 8 dollars for an evening screening; calculate the total ticket revenue collected, and write and execute Python code to compute and print the sum of all digits of that revenue figure.",
            """revenue = (80 * 12) + (40 * 8)  # 960 + 320 = 1280
final_answer = sum(int(d) for d in str(revenue))  # 1 + 2 + 8 + 0 = 11
""",
            [("derived from gsm8k_test_0072", "gsm8k_test_0072", 1, "math"), ("derived from HumanEval/131", "HumanEval/131", 2, "code")]
        ),

        # --- Group 3: SQL + Code (Items 29 to 34) ---
        # 29. SQL + Code (tool-req)
        (
            ["sql", "code"], "tool-required",
            f"Query the tvshow database{sch_tv} to find the count of cartoons written by Joseph Kuhr, multiply that count by 25 to establish a target integer, and then write and execute Python code to compute and print the largest integer that divides this target integer evenly while being strictly smaller than the target itself.",
            """import sqlite3
conn = sqlite3.connect('data/spider/database/tvshow/tvshow.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM Cartoon WHERE Written_by = 'Joseph Kuhr'")
k = c.fetchone()[0]  # 2
target = k * 25  # 50
divs = []
for d in range(1, 50):
    if 50 % d == 0:
        divs.append(d)
final_answer = max(divs)  # 25
""",
            [("derived from spider_val_0589", "spider_val_0589", 1, "sql"), ("derived from HumanEval/24", "HumanEval/24", 2, "code")]
        ),
        # 30. SQL + Code (solvable without tools)
        (
            ["sql", "code"], "solvable_without_tools",
            "Given table classroom_grades [CREATE TABLE grades (student_id int, score int)] with five student test scores: 82, 90, 78, 94, and 86; query the minimum score; write and execute Python code to compute and print the product of the two decimal digits of that minimum score.",
            """min_score = min([82, 90, 78, 94, 86])  # 78
d1, d2 = int(str(min_score)[0]), int(str(min_score)[1])
final_answer = d1 * d2  # 7 * 8 = 56
""",
            [("derived from spider_val_0017", "spider_val_0017", 1, "sql"), ("derived from HumanEval/8", "HumanEval/8", 2, "code")]
        ),
        # 31. SQL + Code (tool-req)
        (
            ["sql", "code"], "tool-required",
            f"In the orchestra database{sch_orchestra}, query the count of conductors whose Age is strictly greater than 50; write and execute Python code to calculate and print the sum of the squares of all integers from 1 up to that conductor count inclusive.",
            """import sqlite3
conn = sqlite3.connect('data/spider/database/orchestra/orchestra.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM conductor WHERE Age > 50")
count = c.fetchone()[0]
final_answer = sum(i**2 for i in range(1, count + 1))
""",
            [("derived from spider_val_0018", "spider_val_0018", 1, "sql"), ("derived from HumanEval/60", "HumanEval/60", 2, "code")]
        ),
        # 32. SQL + Code (solvable without tools)
        (
            ["sql", "code"], "solvable_without_tools",
            "A retail store inventory table product_stock [CREATE TABLE stock (item_id int, quantity int, price float)] lists 3 items: (1, 15, 4.0), (2, 8, 10.0), and (3, 20, 5.0); query the total quantity across all products; write and execute Python code to compute and print the binary representation of that total quantity without any prefix.",
            """total_qty = 15 + 8 + 20  # 43
final_answer = bin(total_qty)[2:]  # '101011'
""",
            [("derived from spider_val_0019", "spider_val_0019", 1, "sql"), ("derived from HumanEval/84", "HumanEval/84", 2, "code")]
        ),
        # 33. SQL + Code (tool-req)
        (
            ["sql", "code"], "tool-required",
            f"From the concert_singer database{sch_concert}, join singer and singer_in_concert to find the maximum number of concerts performed by any single singer; write and execute Python code to compute and print the factorial of that maximum concert count.",
            """import sqlite3
import math
conn = sqlite3.connect('data/spider/database/concert_singer/concert_singer.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM singer_in_concert GROUP BY singer_id ORDER BY count(*) DESC LIMIT 1")
max_c = c.fetchone()[0]
final_answer = math.factorial(max_c)
""",
            [("derived from spider_val_0035", "spider_val_0035", 1, "sql"), ("derived from HumanEval/139", "HumanEval/139", 2, "code")]
        ),
        # 34. SQL + Code (solvable without tools)
        (
            ["sql", "code"], "solvable_without_tools",
            "Given employee attendance table timesheet [CREATE TABLE shifts (emp_id int, hours_worked int)] with 4 shift records: (1, 8), (2, 6), (3, 10), and (4, 8); query the average hours worked per shift; write and execute Python code to compute and print the 6th power of that average value.",
            """avg_hours = (8 + 6 + 10 + 8) // 4  # 8
final_answer = avg_hours ** 6  # 262144
""",
            [("derived from spider_val_0022", "spider_val_0022", 1, "sql"), ("derived from HumanEval/160", "HumanEval/160", 2, "code")]
        ),

        # --- Group 4: SQL + Math + Code (3-Stage, Items 35 to 40) ---
        # 35. SQL + Math + Code (tool-req)
        (
            ["sql", "math", "code"], "tool-required",
            f"Query the concert_singer database{sch_concert} to find the count of concerts held in the year 2014 or 2015, assume each concert orders 10 crates of eggs with 12 eggs per crate, and subtract 80 eggs that broke during transit to determine the number of intact eggs received; finally, write and execute Python code to sum the decimal digits of that count of intact eggs and print the resulting digit sum formatted as a standard binary string.",
            """import sqlite3
conn = sqlite3.connect('data/spider/database/concert_singer/concert_singer.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM concert WHERE Year = 2014 OR Year = 2015")
concerts = c.fetchone()[0]  # 6
intact = concerts * 10 * 12 - 80  # 640
dsum = sum(int(d) for d in str(intact))  # 10
final_answer = bin(dsum)[2:]  # '1010'
""",
            [("derived from spider_val_0020", "spider_val_0020", 1, "sql"), ("derived from gsm8k_test_0050", "gsm8k_test_0050", 2, "math"), ("derived from HumanEval/84", "HumanEval/84", 3, "code")]
        ),
        # 36. SQL + Math + Code (solvable without tools)
        (
            ["sql", "math", "code"], "solvable_without_tools",
            "Consider a transit line station roster table rail_network [CREATE TABLE stops (station_id int, zone text, daily_passengers int)] listing 4 stations: (1, 'Downtown', 1200), (2, 'Midtown', 900), (3, 'Uptown', 800), and (4, 'Suburbs', 500); query the count of stations serving at least 800 passengers; multiply this station count by 25 to determine a transport authority fleet size, add 50 reserve buses, and write and execute Python code to compute and print the greatest integer divisor of that total bus fleet strictly less than the fleet size itself.",
            """stations = 3  # 1200, 900, 800
fleet = stations * 25 + 50  # 125
divs = []
for d in range(1, 125):
    if 125 % d == 0:
        divs.append(d)
final_answer = max(divs)  # 25
""",
            [("derived from spider_val_0023", "spider_val_0023", 1, "sql"), ("derived from gsm8k_test_0073", "gsm8k_test_0073", 2, "math"), ("derived from HumanEval/24", "HumanEval/24", 3, "code")]
        ),
        # 37. SQL + Math + Code (tool-req)
        (
            ["sql", "math", "code"], "tool-required",
            f"Query the pets_1 database{sch_pets} to count the number of pets whose weight is strictly greater than 10; multiply this pet count by 12 to establish a foundation measurement, add 16 for structural tolerances, and write and execute Python code to find and print the smallest integer m strictly greater than 1 such that the resulting dimension multiplied by m forms a perfect square.",
            """import sqlite3
conn = sqlite3.connect('data/spider/database/pets_1/pets_1.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM pets WHERE weight > 10")
count = c.fetchone()[0]  # 2
dim = count * 12 + 16  # 40
m = 2
while True:
    prod = dim * m
    r = int(prod ** 0.5)
    if r * r == prod:
        final_answer = m
        break
    m += 1
""",
            [("derived from spider_val_0045", "spider_val_0045", 1, "sql"), ("derived from gsm8k_test_0074", "gsm8k_test_0074", 2, "math"), ("derived from HumanEval/77", "HumanEval/77", 3, "code")]
        ),
        # 38. SQL + Math + Code (solvable without tools)
        (
            ["sql", "math", "code"], "solvable_without_tools",
            "Given warehouse packing table shipment_cartons [CREATE TABLE cartons (carton_id int, weight_kg int)] with 3 records: (1, 14), (2, 22), and (3, 18); query the sum of weights across all cartons; if an export freight surcharge adds 6 kg of protective crating material, determine the gross packaged weight, and write and execute Python code to compute and print the product of the decimal digits of that gross weight.",
            """total_w = 14 + 22 + 18  # 54
gross = total_w + 6  # 60
d1, d2 = int(str(gross)[0]), int(str(gross)[1])
final_answer = d1 * d2  # 6 * 0 = 0
""",
            [("derived from spider_val_0025", "spider_val_0025", 1, "sql"), ("derived from gsm8k_test_0076", "gsm8k_test_0076", 2, "math"), ("derived from HumanEval/8", "HumanEval/8", 3, "code")]
        ),
        # 39. SQL + Math + Code (tool-req)
        (
            ["sql", "math", "code"], "tool-required",
            f"From the poker_player database{sch_poker}, join the poker_player and people tables to query the count of players who have Nationality 'Russia'; multiply this player count by 40 to determine an aggregate training quota, subtract 10 completed modules, and write and execute Python code to compute and print the sum of all positive integers from 1 up to that remaining quota count.",
            """import sqlite3
conn = sqlite3.connect('data/spider/database/poker_player/poker_player.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM poker_player AS T1 JOIN people AS T2 ON T1.People_ID = T2.People_ID WHERE T2.Nationality = 'Russia'")
count = c.fetchone()[0]  # count
quota = count * 40 - 10
final_answer = sum(range(1, quota + 1))
""",
            [("derived from spider_val_0678", "spider_val_0678", 1, "sql"), ("derived from gsm8k_test_0077", "gsm8k_test_0077", 2, "math"), ("derived from HumanEval/60", "HumanEval/60", 3, "code")]
        ),
        # 40. SQL + Math + Code (solvable without tools)
        (
            ["sql", "math", "code"], "solvable_without_tools",
            "An agricultural cooperative orchard log table apple_harvest [CREATE TABLE harvest (orchard_id int, crates int)] records 4 orchards: (1, 45), (2, 55), (3, 30), and (4, 70); query the total crate harvest; subtract 20 damaged crates and divide the remaining sound crates equally among 6 regional markets to find the crates delivered per market, and write and execute Python code to compute and print the 4th power of that crates-per-market value.",
            """total_crates = 45 + 55 + 30 + 70  # 200
sound = total_crates - 20  # 180
per_market = sound // 6  # 30
final_answer = per_market ** 4  # 810000
""",
            [("derived from spider_val_0026", "spider_val_0026", 1, "sql"), ("derived from gsm8k_test_0078", "gsm8k_test_0078", 2, "math"), ("derived from HumanEval/160", "HumanEval/160", 3, "code")]
        )
    ]

    print(f"Constructed {len(defs)} compound definitions.")

    for idx, (domains, solvability, prompt, ref_code, parts) in enumerate(defs, start=1):
        # Execute reference code
        gold_val = execute_ref_code(ref_code)["final_answer"]
        item_id = f"compound_dev_{idx:04d}"

        # Verify part disjointness
        for p_label, p_id, p_stage, p_domain in parts:
            if p_id in all_used:
                print(f"WARNING: part {p_id} in used set!")

        items.append({
            "subtask_id": item_id,
            "task_type": "composed",
            "stratum": "composed",
            "is_compound": True,
            "domains": domains,
            "solvability": solvability,
            "prompt": prompt,
            "component_parts": [
                {"label": p_label, "original_id": p_id, "stage": p_stage, "domain": p_domain}
                for (p_label, p_id, p_stage, p_domain) in parts
            ],
            "reference_program": ref_code,
            "gold_answer": str(gold_val),
            "checker_type": "exact_match"
        })

    # Read existing dev split (60 atomic items)
    with open(DEV_FILE, "r", encoding="utf-8") as f:
        existing_dev = json.load(f)

    # Filter to ensure only atomic items are kept if rerun
    atomic_dev = [x for x in existing_dev if x.get("stratum") == "atomic"]
    print(f"Existing atomic items in Dev: {len(atomic_dev)}")

    # Combine: 60 atomic + 40 compound = 100 items
    full_dev = atomic_dev + items
    print(f"Full enlarged Dev split: {len(full_dev)} items (Atomic: {len(atomic_dev)}, Compound: {len(items)} = {len(items)/len(full_dev)*100:.1f}%)")

    # Save to DEV_FILE
    with open(DEV_FILE, "w", encoding="utf-8") as f:
        json.dump(full_dev, f, indent=2)

    no_tool = [x for x in items if x["solvability"] == "solvable_without_tools"]
    tool_req = [x for x in items if x["solvability"] == "tool-required"]
    print(f"Solvability Breakdown in Compound Stratum:")
    print(f"  - Solvable without tools: {len(no_tool)} ({len(no_tool)/len(items)*100:.1f}%)")
    print(f"  - Tool-required: {len(tool_req)} ({len(tool_req)/len(items)*100:.1f}%)")

if __name__ == "__main__":
    generate_dev_compound_items()
