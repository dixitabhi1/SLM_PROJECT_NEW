"""
Held-Out Candidate Split: 40 Hard Compound Definitions.
20 three-stage (10 tool-req, 10 solv w/o tools)
20 two-stage (10 tool-req, 10 solv w/o tools)
Zero stage/domain labels, single natural paragraphs, executable reference codes.
"""

from scripts.generate_compound_items import get_table_schema

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

HELDOUT_DEFS = [
    # 1. 3-stage (SQL -> Math -> Code) [tool-required]
    (
        ["sql", "math", "code"], "tool-required",
        f"Query the flight_2 database{sch_flight} to count the number of flights having FlightNo strictly less than 500; divide this flight count by 12 using integer division to determine the number of operational airport runways required; write an algorithm to calculate the sum of the first N consecutive positive odd integers starting from 1, where N equals this runway requirement.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/flight_2/flight_2.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM flights WHERE FlightNo < 500")
flights = c.fetchone()[0]

runways = flights // 12
final_answer = sum(2 * i + 1 for i in range(runways))
""",
        ["sql", "math", "code"]
    ),

    # 2. 3-stage (SQL -> Code -> Math) [tool-required]
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
        ["sql", "code", "math"]
    ),

    # 3. 3-stage (SQL -> Math -> Code) [tool-required]
    (
        ["sql", "math", "code"], "tool-required",
        f"In the world_1 database{sch_world}, count the number of countries whose SurfaceArea is strictly greater than 100000; multiply this country count by 14 and subtract 126 to compute a composite territory index; determine the total count of distinct prime factors dividing this composite territory index.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/world_1/world_1.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM country WHERE SurfaceArea > 100000")
countries = c.fetchone()[0]

idx = countries * 14 - 126

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

final_answer = len(factors)
""",
        ["sql", "math", "code"]
    ),

    # 4. 3-stage (SQL -> Code -> Math) [tool-required]
    (
        ["sql", "code", "math"], "tool-required",
        f"Query the real_estate_properties database{sch_prop} to count the number of properties having room_count greater than or equal to 2; raise this property count to the 3rd power, and calculate the sum of the squares of its decimal digits; multiply this sum by 30 and add 150 to establish the final appraisal warranty reserve.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/real_estate_properties/real_estate_properties.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM Properties WHERE room_count >= 2")
props = c.fetchone()[0]

cubed = props ** 3
digit_sq_sum = sum(int(d)**2 for d in str(cubed))
final_answer = digit_sq_sum * 30 + 150
""",
        ["sql", "code", "math"]
    ),

    # 5. 3-stage (SQL -> Math -> Code) [tool-required]
    (
        ["sql", "math", "code"], "tool-required",
        f"From the orchestra database{sch_orch}, query the count of conductors whose Year_of_Work is strictly greater than 5; multiply this conductor count by 45 and add 60 to compute a total performance stipend; find the total count of distinct positive integer divisors of that total stipend.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/orchestra/orchestra.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM conductor WHERE Year_of_Work > 5")
conds = c.fetchone()[0]

stipend = conds * 45 + 60
divs = [d for d in range(1, stipend + 1) if stipend % d == 0]
final_answer = len(divs)
""",
        ["sql", "math", "code"]
    ),

    # 6. 3-stage (SQL -> Code -> Math) [tool-required]
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

final_answer = f1 * 125 + 200
""",
        ["sql", "code", "math"]
    ),

    # 7. 3-stage (SQL -> Math -> Code) [tool-required]
    (
        ["sql", "math", "code"], "tool-required",
        f"In the concert_singer database{sch_sing}, count the number of singers whose Song_release_year is strictly greater than 2005; multiply this singer count by 75 and add 100 to determine a tour bonus; an automated cashier dispenses this bonus using a greedy selection with bill denominations of 100, 50, 20, and 10 in descending order; calculate the total number of bills dispensed.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/concert_singer/concert_singer.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM singer WHERE Song_release_year > 2005")
singers = c.fetchone()[0]

bonus = singers * 75 + 100
denoms = [100, 50, 20, 10]
bills = 0
rem = bonus
for d in denoms:
    bills += rem // d
    rem %= d

final_answer = bills
""",
        ["sql", "math", "code"]
    ),

    # 8. 3-stage (SQL -> Code -> Math) [tool-required]
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

final_answer = sum(primes) * 15 - 70
""",
        ["sql", "code", "math"]
    ),

    # 9. 3-stage (SQL -> Math -> Code) [tool-required]
    (
        ["sql", "math", "code"], "tool-required",
        f"From the poker_player database{sch_poker}, query the count of people in the people table whose Height is strictly greater than 175; multiply this count by 32 and add 80 to establish an inventory weight credit; a logistics manager packs gear with capacity equal to that weight credit divided by 10 using integer division, choosing among packages with (weight, value) pairs (10, 25), (15, 40), (20, 55), and (25, 75) where each package can be selected at most once; compute the maximum achievable value.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/poker_player/poker_player.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM people WHERE Height > 175")
cnt = c.fetchone()[0]

credit = cnt * 32 + 80
cap = credit // 10

items = [(10, 25), (15, 40), (20, 55), (25, 75)]
dp = [0] * (cap + 1)
for w, v in items:
    for j in range(cap, w - 1, -1):
        dp[j] = max(dp[j], dp[j - w] + v)

final_answer = dp[cap]
""",
        ["sql", "math", "code"]
    ),

    # 10. 3-stage (SQL -> Code -> Math) [tool-required]
    (
        ["sql", "code", "math"], "tool-required",
        f"In the dog_kennels database{sch_dogs}, count the number of records in the Charges table where charge_amount is strictly greater than 50; multiply this count by 2 to define an integer rank, and compute the factorial of that integer rank; divide this factorial by 8 using integer division and add 60 to find the final facility audit score.",
        """import sqlite3
import math
conn = sqlite3.connect('data/spider/database/dog_kennels/dog_kennels.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM Charges WHERE charge_amount > 50")
charges = c.fetchone()[0]

rank = charges * 2
fact = math.factorial(rank)
final_answer = fact // 8 + 60
""",
        ["sql", "code", "math"]
    ),

    # 11. 3-stage (SQL-in-prompt -> Math -> Code) [solvable_without_tools]
    (
        ["sql", "math", "code"], "solvable_without_tools",
        "A freight shipping table cargo_manifest [CREATE TABLE manifest (shipment_id int, weight_kg int, priority int)] contains 6 cargo entries: (1, 350, 1), (2, 500, 2), (3, 400, 1), (4, 250, 2), (5, 600, 1), and (6, 450, 1); query the sum of weight_kg for entries having priority equal to 1; divide this total weight by 15 using integer division to compute a distribution index; determine the total count of distinct positive integer divisors of that distribution index.",
        """w = 1800
idx = w // 15
divs = [d for d in range(1, idx + 1) if idx % d == 0]
final_answer = len(divs)
""",
        ["sql", "math", "code"]
    ),

    # 12. 3-stage (Math -> Code -> Math) [solvable_without_tools]
    (
        ["math", "code", "math"], "solvable_without_tools",
        "A supply depot receives 1500 crates of electronics, rejecting 20 percent during inspection; of the passing crates, exactly 75 percent are dispatched for overseas export while all remaining crates are reserved for local stores; an automated packager loads these local crates using a greedy allocation into containers holding 18 crates and cartons holding 5 crates in order of largest to smallest, leaving any crates fewer than 5 loose; if handling costs are 40 dollars per 18-crate container, 15 dollars per 5-crate carton, and 5 dollars storage per loose crate, calculate the total packaging and handling cost.",
        """total = 1500
passing = total - int(total * 0.20)
local = passing - int(passing * 0.75)

c18 = local // 18
rem1 = local % 18
c5 = rem1 // 5
loose = rem1 % 5

final_answer = (c18 * 40) + (c5 * 15) + (loose * 5)
""",
        ["math", "code", "math"]
    ),

    # 13. 3-stage (Code -> Math -> Code) [solvable_without_tools]
    (
        ["code", "math", "code"], "solvable_without_tools",
        "A pseudorandom generator initializes state X_0 = 17 and updates successive states according to recurrence X_(n+1) = (11 * X_n + 23) modulo 128; compute the generated state X_5; multiply X_5 by 12 and add 4 to form an integer target; calculate the sum of the squares of the decimal digits of that integer target.",
        """x = 17
for _ in range(5):
    x = (11 * x + 23) % 128

target = x * 12 + 4
final_answer = sum(int(d)**2 for d in str(target))
""",
        ["code", "math", "code"]
    ),

    # 14. 3-stage (SQL-in-prompt -> Math -> Code) [solvable_without_tools]
    (
        ["sql", "math", "code"], "solvable_without_tools",
        "A clinical diagnostic table laboratory_tests [CREATE TABLE tests (sample_id int, temp float, ph float, valid int)] records 6 clinical assays: (1, 37.5, 7.2, 1), (2, 42.0, 6.8, 0), (3, 36.8, 7.4, 1), (4, 38.2, 7.1, 1), (5, 45.0, 5.5, 0), and (6, 37.0, 7.3, 1); query the count of assays marked valid with valid equal to 1; multiply this valid count by 110 and add 60 to compute a laboratory supply allocation; an automated logistics unit has weight capacity equal to that allocation divided by 10 using integer division, choosing among reagent containers with (weight, value) pairs (12, 30), (18, 48), (22, 60), and (28, 80) where each container can be picked at most once; find the maximum achievable reagent value within capacity.",
        """cnt = 4
alloc = cnt * 110 + 60
cap = alloc // 10

items = [(12, 30), (18, 48), (22, 60), (28, 80)]
dp = [0] * (cap + 1)
for w, v in items:
    for j in range(cap, w - 1, -1):
        dp[j] = max(dp[j], dp[j - w] + v)

final_answer = dp[cap]
""",
        ["sql", "math", "code"]
    ),

    # 15. 3-stage (Math -> SQL-in-prompt -> Code) [solvable_without_tools]
    (
        ["math", "sql", "code"], "solvable_without_tools",
        "A financing facility lends 40000 dollars earning simple annual interest at 6 percent per year over 3 years; evaluate the tariff bracket table tariff_tiers [CREATE TABLE tariffs (tier_id int, t_min int, t_max int, fee int, bonus int)] listing tiers (1, 0, 25000, 2, 50), (2, 25001, 45000, 3, 100), (3, 45001, 65000, 4, 200), and (4, 65001, 90000, 5, 400); locate the tier encompassing the total loan maturity balance and calculate administrative charges as bonus plus (balance multiplied by fee divided by 1000 using integer division); taking the decimal digits of this charge from left to right, compute the sum of each digit multiplied by its 1-based position.",
        """p = 40000
interest = p * 0.06 * 3
balance = int(p + interest)

bonus = 200
fee = 4
charge = bonus + (balance * fee // 1000)

digits = [int(d) for d in str(charge)]
final_answer = sum((i + 1) * d for i, d in enumerate(digits))
""",
        ["math", "sql", "code"]
    ),

    # 16. 3-stage (SQL-in-prompt -> Math -> Code) [solvable_without_tools]
    (
        ["sql", "math", "code"], "solvable_without_tools",
        "A municipal water grid table water_network [CREATE TABLE meters (meter_id int, flow_rate int, active int)] logs 6 telemetry meters: (1, 45, 1), (2, 80, 1), (3, 60, 0), (4, 75, 1), (5, 90, 1), and (6, 50, 0); query the count of meters that are active with active equal to 1 and have flow_rate greater than or equal to 70; multiply this qualifying meter count by 75 and add 125 to determine a pump pressure rating; convert this rating into its standard binary string representation without prefixes and calculate the total count of '1' digits.",
        """cnt = 3
rating = cnt * 75 + 125
b = bin(rating)[2:]
final_answer = b.count('1')
""",
        ["sql", "math", "code"]
    ),

    # 17. 3-stage (Code -> Math -> Code) [solvable_without_tools]
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

score = steps * 12 - 32

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

final_answer = len(factors)
""",
        ["code", "math", "code"]
    ),

    # 18. 3-stage (Math -> Code -> Math) [solvable_without_tools]
    (
        ["math", "code", "math"], "solvable_without_tools",
        "A semiconductor fabrication facility produces 800 microchips, discarding 5 percent during testing; of the functional chips, exactly 60 percent are classified as standard grade while all remaining chips are graded as premium; an automated packager loads these premium chips using a greedy tray allocation into trays of 20, 6, and 2 chips in order of largest to smallest; if packaging costs are 35 dollars per 20-chip tray, 15 dollars per 6-chip tray, and 8 dollars per 2-chip tray, calculate the total packaging cost.",
        """chips = 800
passing = chips - int(chips * 0.05)
premium = passing - int(passing * 0.60)

t20 = premium // 20
rem1 = premium % 20
t6 = rem1 // 6
rem2 = rem1 % 6
t2 = rem2 // 2

final_answer = (t20 * 35) + (t6 * 15) + (t2 * 8)
""",
        ["math", "code", "math"]
    ),

    # 19. 3-stage (SQL-in-prompt -> Math -> Code) [solvable_without_tools]
    (
        ["sql", "math", "code"], "solvable_without_tools",
        "A retail warehouse ledger store_inventory [CREATE TABLE stock (item_id int, stock int, reorder_level int)] lists 6 commodities: (1, 15, 20), (2, 45, 30), (3, 8, 15), (4, 60, 40), (5, 12, 25), and (6, 30, 25); query the count of items whose stock is strictly less than their reorder_level; multiply this reorder count by 80 and add 60 to determine a replenishment allowance; a warehouse bot has payload capacity equal to that allowance divided by 10 using integer division, choosing among goods with (weight, value) pairs (8, 20), (12, 32), (16, 45), and (20, 60) where each commodity can be chosen at most once; compute the maximum achievable inventory value.",
        """cnt = 3
alloc = cnt * 80 + 60
cap = alloc // 10

items = [(8, 20), (12, 32), (16, 45), (20, 60)]
dp = [0] * (cap + 1)
for w, v in items:
    for j in range(cap, w - 1, -1):
        dp[j] = max(dp[j], dp[j - w] + v)

final_answer = dp[cap]
""",
        ["sql", "math", "code"]
    ),

    # 20. 3-stage (Code -> Math -> Code) [solvable_without_tools]
    (
        ["code", "math", "code"], "solvable_without_tools",
        "An autonomous explorer drone begins at origin (0, 0) and traverses six displacement vectors: (5, 3), (-2, 4), (3, -6), (-4, 1), (2, 2), and (-1, -1); calculate the final Manhattan distance (|x| + |y|) of the drone from the origin; multiply this Manhattan distance by 150 and add 200 to compute total power consumption; calculate the sum of the squares of the decimal digits of that power consumption.",
        """moves = [(5, 3), (-2, 4), (3, -6), (-4, 1), (2, 2), (-1, -1)]
x = sum(dx for dx, dy in moves)
y = sum(dy for dx, dy in moves)
dist = abs(x) + abs(y)

pwr = dist * 150 + 200
final_answer = sum(int(d)**2 for d in str(pwr))
""",
        ["code", "math", "code"]
    ),

    # 21. 2-stage (SQL -> Math) [tool-required]
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
final_answer = net
""",
        ["sql", "math"]
    ),

    # 22. 2-stage (SQL -> Code) [tool-required]
    (
        ["sql", "code"], "tool-required",
        f"From the tvshow database{sch_tv}, count the number of television broadcast channels whose Language is recorded as 'English'; multiply this channel count by 4 to define an integer rank, and write and execute Python code to compute and print the exact factorial of that integer rank.",
        """import sqlite3
import math
conn = sqlite3.connect('data/spider/database/tvshow/tvshow.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM TV_Channel WHERE Language = 'English'")
cnt = c.fetchone()[0]

rank = cnt * 4
final_answer = math.factorial(rank)
""",
        ["sql", "code"]
    ),

    # 23. 2-stage (SQL -> Math) [tool-required]
    (
        ["sql", "math"], "tool-required",
        f"In the world_1 database{sch_world}, count the number of countries whose independence year IndepYear is strictly greater than 1950; if each of these post-1950 sovereign nations operates an average of 35 diplomatic missions abroad and an international treaty fund contributes 450 dollars per mission for security upgrades, compute the total treaty upgrade funding awarded.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/world_1/world_1.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM country WHERE IndepYear > 1950")
cnt = c.fetchone()[0]

missions = cnt * 35
final_answer = missions * 450
""",
        ["sql", "math"]
    ),

    # 24. 2-stage (SQL -> Code) [tool-required]
    (
        ["sql", "code"], "tool-required",
        f"Query the real_estate_properties database{sch_prop} to count the number of properties whose vendor_requested_price is strictly greater than 500000; write and execute Python code to generate the first N prime numbers starting with 2, where N equals that luxury property count, and print the sum of those prime numbers.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/real_estate_properties/real_estate_properties.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM Properties WHERE vendor_requested_price > 500000")
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

final_answer = sum(primes)
""",
        ["sql", "code"]
    ),

    # 25. 2-stage (SQL -> Math) [tool-required]
    (
        ["sql", "math"], "tool-required",
        f"Query the orchestra database{sch_orch} to count the number of orchestras having Year_of_Founded strictly greater than 1980; suppose each modern orchestra performs 45 concerts per year, selling an average of 250 tickets per concert at a ticket price of 40 dollars; calculate the total annual ticket revenue generated across all qualifying orchestras.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/orchestra/orchestra.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM orchestra WHERE Year_of_Founded > 1980")
cnt = c.fetchone()[0]

concerts = cnt * 45
final_answer = concerts * 250 * 40
""",
        ["sql", "math"]
    ),

    # 26. 2-stage (SQL -> Code) [tool-required]
    (
        ["sql", "code"], "tool-required",
        f"In the battle_death database{sch_death}, count the number of vessels in the ship table whose tonnage is strictly greater than 5000; starting from this vessel count as initial integer n, simulate the Collatz sequence where n transitions to n / 2 if n is even and 3 * n + 1 if n is odd, counting the total number of transition steps taken until n reaches 1.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/battle_death/battle_death.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM ship WHERE tonnage > 5000")
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
        ["sql", "code"]
    ),

    # 27. 2-stage (SQL -> Math) [tool-required]
    (
        ["sql", "math"], "tool-required",
        f"From the concert_singer database{sch_sing}, query the total count of stadiums whose Capacity is strictly greater than 40000; if each large arena hosts 12 summer music festivals with an average attendance of 35000 fans per festival and an environmental clean-up fee assesses 2 dollars per attendee, compute the total clean-up fees collected.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/concert_singer/concert_singer.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM stadium WHERE Capacity > 40000")
stadiums = c.fetchone()[0]

attendees = stadiums * 12 * 35000
final_answer = attendees * 2
""",
        ["sql", "math"]
    ),

    # 28. 2-stage (SQL -> Code) [tool-required]
    (
        ["sql", "code"], "tool-required",
        f"In the pets_1 database{sch_pets}, count the number of registered animals in the Pets table whose weight is strictly greater than 5; write and execute Python code to compute and print the sum of the cubes of all positive integers from 1 up to that animal count inclusive.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/pets_1/pets_1.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM Pets WHERE weight > 5")
n = c.fetchone()[0]

final_answer = sum(i**3 for i in range(1, n + 1))
""",
        ["sql", "code"]
    ),

    # 29. 2-stage (SQL -> Math) [tool-required]
    (
        ["sql", "math"], "tool-required",
        f"Query the poker_player database{sch_poker} to count the number of players whose Final_Table_Made count is strictly greater than 5; suppose each veteran pro conducts 15 masterclass training clinics per year with 20 enrolled participants per clinic at a tuition fee of 350 dollars per participant; calculate the total combined tuition revenue generated.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/poker_player/poker_player.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM poker_player WHERE Final_Table_Made > 5")
pros = c.fetchone()[0]

clinics = pros * 15
final_answer = clinics * 20 * 350
""",
        ["sql", "math"]
    ),

    # 30. 2-stage (SQL -> Code) [tool-required]
    (
        ["sql", "code"], "tool-required",
        f"From the dog_kennels database{sch_dogs}, count the number of rescued dogs marked as abandoned with abandoned_yn equal to '1'; multiply this count by 5 to define an integer rank, and write and execute Python code to compute and print the exact factorial of that rank.",
        """import sqlite3
import math
conn = sqlite3.connect('data/spider/database/dog_kennels/dog_kennels.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM dogs WHERE abandoned_yn = '1'")
cnt = c.fetchone()[0]

rank = cnt * 5
final_answer = math.factorial(rank)
""",
        ["sql", "code"]
    ),

    # 31. 2-stage (SQL-in-prompt -> Math) [solvable_without_tools]
    (
        ["sql", "math"], "solvable_without_tools",
        "An artisan roastery ledger table coffee_sales [CREATE TABLE orders (order_id int, blend text, bags int, price int)] records retail batches (1, 'Dark', 25, 14), (2, 'Light', 30, 12), (3, 'Dark', 40, 14), (4, 'Medium', 50, 13), (5, 'Dark', 35, 14), and (6, 'Light', 20, 12); query the total gross revenue (sum of bags multiplied by price) earned exclusively from 'Dark' roast sales; if gross profit margin equals 25 percent of revenue and distribution costs deduct 50 dollars from gross profit, compute the net distribution profit in whole dollars.",
        """gross = (25 * 14) + (40 * 14) + (35 * 14)
profit = int(gross * 0.25)
final_answer = profit - 50
""",
        ["sql", "math"]
    ),

    # 32. 2-stage (Math -> Code) [solvable_without_tools]
    (
        ["math", "code"], "solvable_without_tools",
        "In an 8-team premier division, every pair of teams competes against each other twice across a season; across all scheduled tournament matches indexed from 0 through (total matches - 1), match points are awarded such that if the match index is divisible by 4 the match results in a draw awarding 2 total points, while all other matches award 3 total points; simulate all matches to determine the total points awarded across the season.",
        """teams = 8
total_matches = (teams * (teams - 1) // 2) * 2

points = 0
for m in range(total_matches):
    if m % 4 == 0:
        points += 2
    else:
        points += 3

final_answer = points
""",
        ["math", "code"]
    ),

    # 33. 2-stage (Code -> Math) [solvable_without_tools]
    (
        ["code", "math"], "solvable_without_tools",
        "Consider the character sequence 'AAAAABBBCCCCCCCCDDDDDD' compressed using run-length encoding where consecutive identical characters are represented as count followed by character (for example, 5A for AAAAA); determine the total character length of this compressed string; if a wireless router transmits 4000 such compressed strings per hour during a 10-hour cycle and bandwidth costs 6 dollars per 1000 transmitted characters, calculate the total bandwidth fee in whole dollars using integer division.",
        """compressed_len = len('5A3B8C6D')
total_chars = compressed_len * 4000 * 10
final_answer = (total_chars * 6) // 1000
""",
        ["code", "math"]
    ),

    # 34. 2-stage (Math -> Code) [solvable_without_tools]
    (
        ["math", "code"], "solvable_without_tools",
        "Find the smallest positive integer N that leaves a remainder of 2 when divided by 5, a remainder of 4 when divided by 7, and a remainder of 3 when divided by 8; calculate the square of N, and determine the sum of its decimal digits.",
        """n = 1
while True:
    if n % 5 == 2 and n % 7 == 4 and n % 8 == 3:
        break
    n += 1

n_sq = n ** 2
final_answer = sum(int(d) for d in str(n_sq))
""",
        ["math", "code"]
    ),

    # 35. 2-stage (Code -> Math) [solvable_without_tools]
    (
        ["code", "math"], "solvable_without_tools",
        "An autonomous survey vehicle starts at coordinate origin (0, 0) and follows six displacement vectors: (3, 4), (-2, 2), (4, -3), (-1, -1), (2, 3), and (-1, 1); determine the final Manhattan distance (|x| + |y|) of the vehicle from the origin; if the vehicle consumes 125 milliwatts per unit of Manhattan distance and begins with a full battery reserve of 4000 milliwatts, compute the remaining battery reserve.",
        """moves = [(3, 4), (-2, 2), (4, -3), (-1, -1), (2, 3), (-1, 1)]
x = sum(dx for dx, dy in moves)
y = sum(dy for dx, dy in moves)
dist = abs(x) + abs(y)

consumption = dist * 125
final_answer = 4000 - consumption
""",
        ["code", "math"]
    ),

    # 36. 2-stage (SQL-in-prompt -> Math) [solvable_without_tools]
    (
        ["sql", "math"], "solvable_without_tools",
        "An electronics manufacturing component inventory electronic_parts [CREATE TABLE parts (part_id int, category text, units int, unit_cost int)] lists supplies (1, 'Sensor', 40, 18), (2, 'Relay', 60, 10), (3, 'Sensor', 50, 20), (4, 'Switch', 80, 8), (5, 'Sensor', 30, 22), and (6, 'Relay', 45, 11); query the total expenditure (sum of units multiplied by unit_cost) incurred exclusively on 'Sensor' category parts; if a supplier discount waives 15 percent of this expenditure and expedited freight shipping adds 75 dollars, compute the final total procurement expenditure in whole dollars using integer arithmetic.",
        """gross = (40 * 18) + (50 * 20) + (30 * 22)
discount = int(gross * 0.15)
net = gross - discount
final_answer = net + 75
""",
        ["sql", "math"]
    ),

    # 37. 2-stage (Math -> Code) [solvable_without_tools]
    (
        ["math", "code"], "solvable_without_tools",
        "A bagel bakery bakes 360 specialty bagels: exactly 10 percent are blueberry, 40 percent are toasted sesame, and all remaining bagels are plain; calculate the total number of plain bagels baked; convert this plain bagel count into its standard binary string representation without prefixes, and compute the product of the count of '1' digits and the count of '0' digits in that string.",
        """total = 360
blueberry = int(total * 0.10)
sesame = int(total * 0.40)
plain = total - blueberry - sesame

b = bin(plain)[2:]
ones = b.count('1')
zeros = b.count('0')
final_answer = ones * zeros
""",
        ["math", "code"]
    ),

    # 38. 2-stage (Code -> Math) [solvable_without_tools]
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

final_answer = steps * 60 + 250
""",
        ["code", "math"]
    ),

    # 39. 2-stage (SQL-in-prompt -> Math) [solvable_without_tools]
    (
        ["sql", "math"], "solvable_without_tools",
        "A data center power monitoring table server_clusters [CREATE TABLE clusters (server_id int, room text, kw int, uptime_pct float)] logs telemetry (1, 'Alpha', 45, 99.8), (2, 'Beta', 30, 99.2), (3, 'Alpha', 55, 99.9), (4, 'Gamma', 60, 98.5), (5, 'Alpha', 50, 99.7), and (6, 'Beta', 35, 99.5); query the total power load in kilowatts (sum of kw) drawn exclusively by servers located in server room 'Alpha'; if these servers run continuously for 720 hours in a month at an energy rate of 0.12 dollars per kilowatt-hour and a green facility incentive discounts 10 percent off the electricity bill, compute the final net monthly power cost in whole dollars using integer arithmetic.",
        """kw = 45 + 55 + 50
total_kwh = kw * 720
gross = total_kwh * 0.12
discount = int(gross * 0.10)
final_answer = int(gross - discount)
""",
        ["sql", "math"]
    ),

    # 40. 2-stage (Math -> Code) [solvable_without_tools]
    (
        ["math", "code"], "solvable_without_tools",
        "A citrus grower harvests 600 kilograms of oranges, setting aside 15 percent for fresh juice production; the remaining oranges are packed into commercial crates holding 8 kilograms each; find the whole number count of completed crates, take the last decimal digit of this crate count, and write and execute Python code to compute and print the factorial of that single digit.",
        """import math
harvest = 600
juice = int(harvest * 0.15)
remaining = harvest - juice
crates = remaining // 8
last_digit = crates % 10
final_answer = math.factorial(last_digit)
""",
        ["math", "code"]
    )
]
