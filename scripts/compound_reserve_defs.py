"""
Reserve Quarantine Split: 40 Hard Compound Definitions.
20 three-stage (10 tool-req, 10 solv w/o tools)
20 two-stage (10 tool-req, 10 solv w/o tools)
Zero stage/domain labels, single natural paragraphs, executable reference codes.
Carefully budgeted: Uses exactly 10 HumanEval stages in 3-stage and 5 in 2-stage (total 15 <= 17 available).
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
sch_emp = get_table_schema("employee_hire_evaluation", ["employee", "evaluation"])

RESERVE_DEFS = [
    # 1. 3-stage (SQL -> Math -> Code) [tool-required]
    (
        ["sql", "math", "code"], "tool-required",
        f"Query the concert_singer database{sch_sing} to count the number of artists in the singer table whose Song_release_year is strictly less than 2010; multiply this veteran artist count by 65 and add 105 to determine a studio grant; compute the sum of the cubes of the decimal digits of that grant.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/concert_singer/concert_singer.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM singer WHERE Song_release_year < 2010")
cnt = c.fetchone()[0]

grant = cnt * 65 + 105
final_answer = sum(int(d)**3 for d in str(grant))
""",
        ["sql", "math", "code"]
    ),

    # 2. 3-stage (SQL -> Code -> Math) [tool-required]
    (
        ["sql", "code", "math"], "tool-required",
        f"In the tvshow database{sch_tv}, count the number of series in the TV_series table with Viewers_m strictly greater than 10.0; starting from this hit series count as initial integer n, simulate the Collatz sequence where n transitions to n / 2 if n is even and 3 * n + 1 if n is odd, counting the total transition steps taken until n reaches 1; multiply this step count by 75 and add 125 to determine the final broadcast syndication fee.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/tvshow/tvshow.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM TV_series WHERE Viewers_m > 10.0")
cnt = c.fetchone()[0]

n = cnt
steps = 0
while n != 1:
    if n % 2 == 0:
        n //= 2
    else:
        n = 3 * n + 1
    steps += 1

final_answer = steps * 75 + 125
""",
        ["sql", "code", "math"]
    ),

    # 3. 3-stage (SQL -> Math -> Code) [tool-required]
    (
        ["sql", "math", "code"], "tool-required",
        f"From the world_1 database{sch_world}, count the number of countries whose Population is strictly greater than 100000000; multiply this large nation count by 45 and add 50 to compute a global development fund; determine the total count of distinct positive integer divisors of that development fund.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/world_1/world_1.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM country WHERE Population > 100000000")
cnt = c.fetchone()[0]

fund = cnt * 45 + 50
divs = [d for d in range(1, fund + 1) if fund % d == 0]
final_answer = len(divs)
""",
        ["sql", "math", "code"]
    ),

    # 4. 3-stage (SQL -> Code -> Math) [tool-required]
    (
        ["sql", "code", "math"], "tool-required",
        f"Query the battle_death database{sch_death} to count the number of vessels in the ship table whose name contains the letter 'A'; defining a generalized Fibonacci sequence with initial terms F_0 = 1 and F_1 = 3 where F_n = F_(n-1) + F_(n-2), compute the term at index equal to that vessel count; multiply this term by 50 and add 100 to calculate the naval restoration bond.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/battle_death/battle_death.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM ship WHERE name LIKE '%A%'")
cnt = c.fetchone()[0]

f0, f1 = 1, 3
for _ in range(cnt - 1):
    f0, f1 = f1, f0 + f1

final_answer = f1 * 50 + 100
""",
        ["sql", "code", "math"]
    ),

    # 5. 3-stage (SQL -> Math -> Code) [tool-required]
    (
        ["sql", "math", "code"], "tool-required",
        f"In the pets_1 database{sch_pets}, count the number of students recorded with Sex equal to 'M'; multiply this student count by 35 and add 60 to compute a campus recreation purse; find the unique prime factors dividing this recreation purse and compute their product.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/pets_1/pets_1.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM Student WHERE Sex = 'M'")
cnt = c.fetchone()[0]

purse = cnt * 35 + 60

factors = set()
d = 2
temp = purse
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
        ["sql", "math", "code"]
    ),

    # 6. 3-stage (SQL -> Code -> Math) [tool-required]
    (
        ["sql", "code", "math"], "tool-required",
        f"Query the dog_kennels database{sch_dogs}, to count the number of senior canines in the dogs table whose age is strictly greater than 8; multiply this count by 3 to define an integer rank, and write and execute Python code to compute the exact factorial of that rank; divide this factorial by 12 using integer division and add 100 to determine the senior care foundation fund.",
        """import sqlite3
import math
conn = sqlite3.connect('data/spider/database/dog_kennels/dog_kennels.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM dogs WHERE age > 8")
cnt = c.fetchone()[0]

rank = cnt * 3
fact = math.factorial(rank)
final_answer = fact // 12 + 100
""",
        ["sql", "code", "math"]
    ),

    # 7. 3-stage (SQL -> Math -> Code) [tool-required]
    (
        ["sql", "math", "code"], "tool-required",
        f"From the flight_2 database{sch_flight}, find the total count of scheduled flights whose FlightNo is strictly greater than 1000; divide this flight count by 15 using integer division to determine the number of assigned air-traffic sectors; calculate the sum of the first N positive odd integers starting from 1, where N equals this sector assignment.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/flight_2/flight_2.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM flights WHERE FlightNo > 1000")
flights = c.fetchone()[0]

sectors = flights // 15
final_answer = sum(2 * i + 1 for i in range(sectors))
""",
        ["sql", "math", "code"]
    ),

    # 8. 3-stage (SQL -> Math -> Code) [tool-required]
    (
        ["sql", "math", "code"], "tool-required",
        f"In the real_estate_properties database{sch_prop}, count the number of transactions in the Properties table where agreed_selling_price is strictly greater than 300000; multiply this transaction count by 80 and add 40 to determine an escrow incentive purse; an automated treasury dispenser makes change for this total purse using a greedy selection with currency denominations of 500, 200, 50, and 10 dollars in descending order; calculate the total count of currency bills dispensed.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/real_estate_properties/real_estate_properties.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM Properties WHERE agreed_selling_price > 300000")
cnt = c.fetchone()[0]

purse = cnt * 80 + 40
denoms = [500, 200, 50, 10]
bills = 0
rem = purse
for d in denoms:
    bills += rem // d
    rem %= d

final_answer = bills
""",
        ["sql", "math", "code"]
    ),

    # 9. 3-stage (SQL -> Code -> Math) [tool-required]
    (
        ["sql", "code", "math"], "tool-required",
        f"Query the orchestra database{sch_orch} to count the number of conductors whose Conductor_ID is strictly greater than 5; generate the sequence of prime numbers starting with 2 up to that count of total primes, and sum all generated prime numbers; multiply this sum by 20 and add 40 to determine the symphonic festival budget.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/orchestra/orchestra.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM conductor WHERE Conductor_ID > 5")
cnt = c.fetchone()[0]

primes = []
curr = 2
while len(primes) < cnt:
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

final_answer = sum(primes) * 20 + 40
""",
        ["sql", "code", "math"]
    ),

    # 10. 3-stage (SQL -> Math -> Code) [tool-required]
    (
        ["sql", "math", "code"], "tool-required",
        f"From the employee_hire_evaluation database{sch_emp}, count the number of employees whose Age is strictly less than 25; multiply this count by 150 and add 250 to compute an apprentice training allocation; convert this allocation into its standard binary string representation without prefixes, and determine the total count of '1' digits.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/employee_hire_evaluation/employee_hire_evaluation.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM employee WHERE Age < 25")
cnt = c.fetchone()[0]

alloc = cnt * 150 + 250
b = bin(alloc)[2:]
final_answer = b.count('1')
""",
        ["sql", "math", "code"]
    ),

    # 11. 3-stage (SQL-in-prompt -> Math -> Math) [solvable_without_tools]
    (
        ["sql", "math", "math"], "solvable_without_tools",
        "A maritime registry table harbor_traffic [CREATE TABLE traffic (vessel_id int, tonnage int, registered int)] records 6 incoming vessels: (1, 120, 1), (2, 280, 0), (3, 310, 1), (4, 190, 1), (5, 450, 0), and (6, 260, 1); query the sum of tonnage for registered vessels where registered equals 1; divide this total tonnage by 11 using integer division to establish a harbor clearance score; if port authority logistics costs 45 dollars per unit of clearance score and a maritime security fee adds 150 dollars, compute the total port clearance fee in whole dollars.",
        """tonnage = 120 + 310 + 190 + 260
score = tonnage // 11
fee = score * 45 + 150
final_answer = fee
""",
        ["sql", "math", "math"]
    ),

    # 12. 3-stage (Math -> SQL-in-prompt -> Math) [solvable_without_tools]
    (
        ["math", "sql", "math"], "solvable_without_tools",
        "A municipal green initiative plants 1200 saplings, discarding 15 percent due to transport damage; of the surviving trees, exactly 60 percent are assigned to public park walkways while all remaining trees are distributed across residential parkways; evaluate the distributor fee schedule table nursery_fees [CREATE TABLE fees (min_trees int, max_trees int, handling_fee int, bonus int)] listing brackets (0, 200, 5, 50), (201, 350, 8, 100), (351, 500, 12, 200), and (501, 800, 15, 300); find the tier bracket covering the count of residential trees and calculate total distribution expenditure as bonus plus residential trees multiplied by handling_fee.",
        """total = 1200
surviving = total - int(total * 0.15) # 1020
residential = surviving - int(surviving * 0.60) # 408

# Matches bracket (351, 500)
bonus = 200
handling = 12
final_answer = bonus + (residential * handling) # 200 + 4896 = 5096
""",
        ["math", "sql", "math"]
    ),

    # 13. 3-stage (SQL-in-prompt -> Math -> Math) [solvable_without_tools]
    (
        ["sql", "math", "math"], "solvable_without_tools",
        "A chemical processing ledger reactant_batches [CREATE TABLE batches (batch_id int, volume_l int, grade text)] logs 6 runs: (1, 400, 'A'), (2, 250, 'B'), (3, 350, 'A'), (4, 500, 'C'), (5, 450, 'A'), and (6, 300, 'B'); query the total volume in liters (sum of volume_l) for Grade 'A' batches; if each liter of Grade 'A' reactant produces 45 pharmaceutical vials and quality control packaging fees cost 2 dollars per vial, compute the gross packaging fee; if a bulk production rebate discounts 10 percent of gross packaging fees, calculate the net packaging fee in whole dollars.",
        """vol = 400 + 350 + 450 # 1200
vials = vol * 45 # 54000
gross = vials * 2 # 108000
final_answer = int(gross * 0.90) # 97200
""",
        ["sql", "math", "math"]
    ),

    # 14. 3-stage (SQL-in-prompt -> Math -> Math) [solvable_without_tools]
    (
        ["sql", "math", "math"], "solvable_without_tools",
        "A geological survey database rock_samples [CREATE TABLE rocks (sample_id int, hardness float, density float, certified int)] lists 6 mineral specimens: (1, 6.5, 2.7, 1), (2, 8.0, 3.5, 0), (3, 7.2, 2.9, 1), (4, 6.8, 2.6, 1), (5, 9.0, 4.1, 0), and (6, 7.0, 2.8, 1); query the count of specimens certified with certified equal to 1; multiply this certified count by 125 and add 100 to determine an exploration equipment fund; if each field geological assay costs 45 dollars and a laboratory calibration fee adds 250 dollars to total assay costs, calculate the total assay expenditure when 20 assays are conducted using this equipment.",
        """cnt = 4
fund = cnt * 125 + 100 # 600
# 20 assays at 45 plus 250
final_answer = fund + (20 * 45 + 250) # 600 + 1150 = 1750
""",
        ["sql", "math", "math"]
    ),

    # 15. 3-stage (Math -> SQL-in-prompt -> Math) [solvable_without_tools]
    (
        ["math", "sql", "math"], "solvable_without_tools",
        "A development treasury invests 60000 dollars at a simple annual interest rate of 4 percent per year over 5 years; evaluate the tariff schedule table tariff_schedule [CREATE TABLE brackets (bracket_id int, low int, high int, fee int, bonus int)] listing tiers (1, 0, 35000, 2, 60), (2, 35001, 60000, 3, 120), (3, 60001, 85000, 4, 250), and (4, 85001, 120000, 5, 500); find the tier bracket covering the total matured fund balance and calculate administrative charges as bonus plus (balance multiplied by fee divided by 1000 using integer division); if an audit surcharge adds 50 dollars to this administrative charge, calculate the final charge.",
        """p = 60000
interest = p * 0.04 * 5
balance = int(p + interest)

bonus = 250
fee = 4
charge = bonus + (balance * fee // 1000)
final_answer = charge + 50
""",
        ["math", "sql", "math"]
    ),

    # 16. 3-stage (SQL-in-prompt -> Math -> Math) [solvable_without_tools]
    (
        ["sql", "math", "math"], "solvable_without_tools",
        "A solar energy monitoring table solar_inverters [CREATE TABLE inverters (inverter_id int, kw_output int, grid_ready int)] logs 6 power units: (1, 35, 1), (2, 65, 1), (3, 40, 0), (4, 70, 1), (5, 85, 1), and (6, 45, 0); query the count of inverters that are grid-ready with grid_ready equal to 1 and have kw_output strictly greater than 50; multiply this qualifying unit count by 60 and add 80 to determine an inverter power quotient; if an inverter system produces energy valued at 15 dollars per unit of power quotient and a municipal green tariff grants an 8 percent tax credit on total value, calculate the net credit-adjusted value in whole dollars using integer arithmetic.",
        """cnt = 3
quot = cnt * 60 + 80 # 260
gross = quot * 15 # 3900
tax_credit = int(gross * 0.08) # 312
final_answer = gross - tax_credit # 3588
""",
        ["sql", "math", "math"]
    ),

    # 17. 3-stage (Math -> SQL-in-prompt -> Math) [solvable_without_tools]
    (
        ["math", "sql", "math"], "solvable_without_tools",
        "A commercial poultry farm houses 1500 hens, rejecting 8 percent during biometric health checks; of the healthy hens, exactly 75 percent are allocated to organic free-range paddocks while all remaining hens are placed in enriched barn housing; consult the facility zoning rate table barn_zones [CREATE TABLE zones (min_h int, max_h int, feed_rate int, base_fee int)] listing brackets (0, 200, 12, 100), (201, 400, 15, 250), (401, 600, 18, 450), and (601, 1000, 22, 700); locate the bracket encompassing the barn-housed hen count and calculate annual boarding expenditure as base_fee plus (barn hens multiplied by feed_rate); if veterinary insurance adds 120 dollars, compute the total annual expenditure.",
        """hens = 1500
healthy = hens - int(hens * 0.08) # 1380
barn = healthy - int(healthy * 0.75) # 345

# Matches bracket (201, 400)
base = 250
rate = 15
boarding = base + (barn * rate) # 250 + 5175 = 5425
final_answer = boarding + 120 # 5545
""",
        ["math", "sql", "math"]
    ),

    # 18. 3-stage (SQL-in-prompt -> Math -> Math) [solvable_without_tools]
    (
        ["sql", "math", "math"], "solvable_without_tools",
        "A fleet vehicle telematics ledger van_maintenance [CREATE TABLE vans (van_id int, mileage int, scheduled_service int)] tracks 6 fleet vans: (1, 45000, 1), (2, 82000, 0), (3, 62000, 1), (4, 38000, 0), (5, 74000, 1), and (6, 51000, 1); query the count of fleet vans flagged for service with scheduled_service equal to 1; multiply this service count by 140 and add 80 to establish a maintenance allocation fund; if overhaul labor consumes 65 percent of this fund and parts procurement consumes the remaining 35 percent, calculate the exact parts procurement budget in whole dollars using integer arithmetic.",
        """cnt = 4
fund = cnt * 140 + 80 # 640
parts = int(fund * 0.35) # 224
final_answer = parts
""",
        ["sql", "math", "math"]
    ),

    # 19. 3-stage (SQL-in-prompt -> Math -> Math) [solvable_without_tools]
    (
        ["sql", "math", "math"], "solvable_without_tools",
        "A distribution center inventory spare_motors [CREATE TABLE motors (motor_id int, stock int, threshold int)] records 6 industrial drives: (1, 10, 15), (2, 40, 25), (3, 5, 12), (4, 50, 30), (5, 8, 20), and (6, 22, 20); query the count of motors whose stock is strictly less than their threshold; multiply this reorder count by 75 and add 50 to compute a logistics replenishment score; if each reorder unit costs 350 dollars and express shipping adds 45 dollars per reorder motor, compute the total expenditure required to replace exactly one unit for every motor currently below threshold.",
        """cnt = 3
unit_cost = 350 + 45 # 395
final_answer = cnt * unit_cost # 1185
""",
        ["sql", "math", "math"]
    ),

    # 20. 3-stage (Math -> SQL-in-prompt -> Math) [solvable_without_tools]
    (
        ["math", "sql", "math"], "solvable_without_tools",
        "A community sports league registers 800 youth players, with 12 percent withdrawing before team formation; of the confirmed players, exactly 50 percent join soccer teams, 30 percent join basketball squads, and all remaining players enroll in track and field; consult the athletics equipment subsidy table athletics_subsidies [CREATE TABLE subsidies (min_p int, max_p int, stipend int, equipment_grant int)] with tiers (0, 100, 15, 200), (101, 200, 20, 400), (201, 300, 25, 600), and (301, 500, 30, 800); identify the tier corresponding to track and field enrollment and calculate total program funding as equipment_grant plus (track players multiplied by stipend).",
        """total = 800
confirmed = total - int(total * 0.12) # 704
soccer = int(confirmed * 0.50) # 352
basketball = int(confirmed * 0.30) # 211
track = confirmed - soccer - basketball # 141

# Matches tier (101, 200)
grant = 400
stipend = 20
final_answer = grant + (track * stipend) # 400 + 2820 = 3220
""",
        ["math", "sql", "math"]
    ),

    # 21. 2-stage (SQL -> Math) [tool-required]
    (
        ["sql", "math"], "tool-required",
        f"Query the flight_2 database{sch_flight} to count the number of flights having Airline ID equal to 1; suppose each flight transports 180 passengers, exactly 35 percent of passengers pay a 30-dollar priority boarding fee, and a terminal facility surcharge waives 10 percent of gross boarding fees; compute the net priority boarding revenue in whole dollars using integer arithmetic.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/flight_2/flight_2.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM flights WHERE Airline = 1")
cnt = c.fetchone()[0]

passengers = cnt * 180
paying = int(passengers * 0.35)
gross = paying * 30
final_answer = int(gross * 0.90)
""",
        ["sql", "math"]
    ),

    # 22. 2-stage (SQL -> Math) [tool-required]
    (
        ["sql", "math"], "tool-required",
        f"From the tvshow database{sch_tv}, count the number of series in the TV_series table with Share strictly greater than 3.0; suppose each qualifying series airs 450 total broadcast hours, exactly 15 percent of which are broadcast during prime-time evening hours, and prime-time commercial sponsorship generates 250 dollars per hour; compute the total prime-time sponsorship revenue generated collectively across all qualifying series in whole dollars.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/tvshow/tvshow.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM TV_series WHERE Share > 3.0")
cnt = c.fetchone()[0]

total_hrs = cnt * 450
prime_hrs = int(total_hrs * 0.15)
final_answer = prime_hrs * 250
""",
        ["sql", "math"]
    ),

    # 23. 2-stage (SQL -> Math) [tool-required]
    (
        ["sql", "math"], "tool-required",
        f"In the world_1 database{sch_world}, count the number of countries located in the Continent of 'Europe'; suppose an international environmental accord awards an emission modernization grant of 25000 dollars per member country, and a compliance administrative discount waives 8 percent of gross grant funding; calculate the net grant funding distributed across all qualifying countries in whole dollars.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/world_1/world_1.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM country WHERE Continent = 'Europe'")
cnt = c.fetchone()[0]

gross = cnt * 25000
final_answer = int(gross * 0.92)
""",
        ["sql", "math"]
    ),

    # 24. 2-stage (SQL -> Math) [tool-required]
    (
        ["sql", "math"], "tool-required",
        f"Query the real_estate_properties database{sch_prop} to count the number of properties having room_count strictly greater than 3; suppose each spacious property commands an average annual property valuation assessment of 120000 dollars and a municipal property conveyance fee assesses 5 percent of gross valuation; calculate the total conveyance fee generated across all qualifying properties.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/real_estate_properties/real_estate_properties.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM Properties WHERE room_count > 3")
cnt = c.fetchone()[0]

gross_val = cnt * 120000
final_answer = int(gross_val * 0.05)
""",
        ["sql", "math"]
    ),

    # 25. 2-stage (SQL -> Math) [tool-required]
    (
        ["sql", "math"], "tool-required",
        f"Query the orchestra database{sch_orch} to count the number of conductors having Year_of_Work strictly greater than 8; suppose each experienced conductor directs 20 symphony showcases annually, each showcase draws an average of 350 patrons, and each admission ticket sells for 45 dollars; compute the total annual ticket receipts generated collectively across all qualifying conductors.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/orchestra/orchestra.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM conductor WHERE Year_of_Work > 8")
cnt = c.fetchone()[0]

showcases = cnt * 20
final_answer = showcases * 350 * 45
""",
        ["sql", "math"]
    ),

    # 26. 2-stage (SQL -> Math) [tool-required]
    (
        ["sql", "math"], "tool-required",
        f"In the battle_death database{sch_death}, count the number of casualty records in the death table where killed is strictly greater than 2; suppose each qualifying casualty incident supported an average of 40 surviving veteran family dependents and a national maritime relief fund awards 1500 dollars per dependent; compute the total relief funding awarded across all qualifying casualty incidents.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/battle_death/battle_death.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM death WHERE killed > 2")
cnt = c.fetchone()[0]

dependents = cnt * 40
final_answer = dependents * 1500
""",
        ["sql", "math"]
    ),

    # 27. 2-stage (SQL -> Math) [tool-required]
    (
        ["sql", "math"], "tool-required",
        f"From the concert_singer database{sch_sing}, query the total count of male singers recorded with Is_male equal to 'T'; if each singer releases an album selling 4500 digital copies at 12 dollars per copy and artist royalties receive 15 percent of digital album sales, compute the total artist royalties earned across all qualifying singers in whole dollars.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/concert_singer/concert_singer.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM singer WHERE Is_male = 'T'")
cnt = c.fetchone()[0]

sales = cnt * 4500 * 12
final_answer = int(sales * 0.15)
""",
        ["sql", "math"]
    ),

    # 28. 2-stage (SQL -> Math) [tool-required]
    (
        ["sql", "math"], "tool-required",
        f"In the pets_1 database{sch_pets}, count the number of pet records in the Pets table whose weight is strictly greater than 8; suppose each large pet consumes 15 kilograms of specialized clinical nutrition per month and animal care feeds cost 24 dollars per kilogram; calculate the total monthly nutrition expenditure across all qualifying pets.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/pets_1/pets_1.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM Pets WHERE weight > 8")
cnt = c.fetchone()[0]

total_kg = cnt * 15
final_answer = total_kg * 24
""",
        ["sql", "math"]
    ),

    # 29. 2-stage (SQL -> Math) [tool-required]
    (
        ["sql", "math"], "tool-required",
        f"Query the poker_player database{sch_poker} to count the number of players whose Earnings are strictly greater than 200000; if each elite player sponsors 10 community poker workshops with 25 amateur students per workshop at a fee of 150 dollars per student, calculate the total combined tuition revenue generated.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/poker_player/poker_player.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM poker_player WHERE Earnings > 200000")
pros = c.fetchone()[0]

workshops = pros * 10
final_answer = workshops * 25 * 150
""",
        ["sql", "math"]
    ),

    # 30. 2-stage (SQL -> Math) [tool-required]
    (
        ["sql", "math"], "tool-required",
        f"From the dog_kennels database{sch_dogs}, count the number of registered dogs whose size_code is 'MED'; suppose each medium canine attends 12 grooming sessions annually and salon fees are 65 dollars per session; compute the total annual grooming expenditure across all qualifying dogs.",
        """import sqlite3
conn = sqlite3.connect('data/spider/database/dog_kennels/dog_kennels.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM dogs WHERE size_code = 'MED'")
cnt = c.fetchone()[0]

sessions = cnt * 12
final_answer = sessions * 65
""",
        ["sql", "math"]
    ),

    # 31. 2-stage (SQL-in-prompt -> Math) [solvable_without_tools]
    (
        ["sql", "math"], "solvable_without_tools",
        "A gourmet tea merchant sales ledger artisan_tea [CREATE TABLE orders (order_id int, variety text, canisters int, price int)] records transactions (1, 'Green', 30, 16), (2, 'Black', 40, 14), (3, 'Green', 50, 16), (4, 'Oolong', 25, 20), (5, 'Green', 45, 16), and (6, 'Black', 35, 14); query the total gross revenue (sum of canisters multiplied by price) earned exclusively from 'Green' tea sales; if gross profit margin equals 30 percent of revenue and an international shipping surcharge deducts 80 dollars from profit, compute the net profit in whole dollars.",
        """gross = (30 * 16) + (50 * 16) + (45 * 16)
profit = int(gross * 0.30)
final_answer = profit - 80
""",
        ["sql", "math"]
    ),

    # 32. 2-stage (Math -> Code) [solvable_without_tools]
    (
        ["math", "code"], "solvable_without_tools",
        "In a 6-team volleyball tournament, every pair of teams plays exactly 3 matches against each other; across all scheduled tournament matches indexed from 0 through (total matches - 1), match points are awarded such that if the match index is divisible by 5 the match ends in a draw awarding 2 total points, while all other matches award 3 total points; simulate all matches to determine the total points awarded across the entire tournament.",
        """teams = 6
total_matches = (teams * (teams - 1) // 2) * 3

points = 0
for m in range(total_matches):
    if m % 5 == 0:
        points += 2
    else:
        points += 3

final_answer = points
""",
        ["math", "code"]
    ),

    # 33. 2-stage (SQL-in-prompt -> Math) [solvable_without_tools]
    (
        ["sql", "math"], "solvable_without_tools",
        "A boutique spice emporium inventory spice_stock [CREATE TABLE spices (spice_id int, origin text, jars int, jar_price int)] lists batches (1, 'India', 40, 12), (2, 'Spain', 25, 24), (3, 'India', 60, 12), (4, 'Morocco', 30, 18), (5, 'India', 50, 12), and (6, 'Spain', 20, 24); query the total gross revenue (sum of jars multiplied by jar_price) generated exclusively from 'India' origin spices; if operating expenses consume 25 percent of gross revenue and municipal trade licensing deducts 45 dollars, calculate the net profit in whole dollars using integer arithmetic.",
        """gross = (40 * 12) + (60 * 12) + (50 * 12)
operating = int(gross * 0.25)
net = gross - operating
final_answer = net - 45
""",
        ["sql", "math"]
    ),

    # 34. 2-stage (Math -> Code) [solvable_without_tools]
    (
        ["math", "code"], "solvable_without_tools",
        "Find the smallest positive integer N that leaves a remainder of 3 when divided by 4, a remainder of 2 when divided by 5, and a remainder of 6 when divided by 7; calculate the square of N, and determine the sum of its decimal digits.",
        """n = 1
while True:
    if n % 4 == 3 and n % 5 == 2 and n % 7 == 6:
        break
    n += 1

n_sq = n ** 2
final_answer = sum(int(d) for d in str(n_sq))
""",
        ["math", "code"]
    ),

    # 35. 2-stage (SQL-in-prompt -> Math) [solvable_without_tools]
    (
        ["sql", "math"], "solvable_without_tools",
        "A marine supply warehouse table boating_ropes [CREATE TABLE ropes (rope_id int, material text, coils int, coil_price int)] records supplies (1, 'Nylon', 20, 45), (2, 'Polyester', 35, 30), (3, 'Nylon', 30, 45), (4, 'Manila', 50, 20), (5, 'Nylon', 25, 45), and (6, 'Polyester', 40, 30); query the total sales revenue (sum of coils multiplied by coil_price) earned exclusively on 'Nylon' ropes; if a seasonal distributor rebate grants a 15 percent discount on gross sales and freight shipping adds 85 dollars, compute the final total procurement charge in whole dollars.",
        """gross = (20 * 45) + (30 * 45) + (25 * 45)
rebate = int(gross * 0.15)
net = gross - rebate
final_answer = net + 85
""",
        ["sql", "math"]
    ),

    # 36. 2-stage (SQL-in-prompt -> Math) [solvable_without_tools]
    (
        ["sql", "math"], "solvable_without_tools",
        "A laboratory supply warehouse table laboratory_glassware [CREATE TABLE glassware (item_id int, material text, units int, unit_cost int)] lists transactions (1, 'Borosilicate', 50, 15), (2, 'Quartz', 20, 45), (3, 'Borosilicate', 60, 15), (4, 'SodaLime', 80, 8), (5, 'Borosilicate', 40, 15), and (6, 'Quartz', 15, 48); query the total procurement cost (sum of units multiplied by unit_cost) incurred exclusively on 'Borosilicate' items; if an educational discount deducts 12 percent of gross procurement cost and bulk shipping adds 60 dollars, compute the net procurement expenditure in whole dollars using integer arithmetic.",
        """gross = (50 * 15) + (60 * 15) + (40 * 15)
discount = int(gross * 0.12)
net = gross - discount
final_answer = net + 60
""",
        ["sql", "math"]
    ),

    # 37. 2-stage (Math -> Code) [solvable_without_tools]
    (
        ["math", "code"], "solvable_without_tools",
        "A wholesale florist delivers 400 mixed blossoms: exactly 25 percent are red roses, 35 percent are white lilies, and all remaining blossoms are blue hydrangeas; calculate the total count of blue hydrangeas delivered; convert this hydrangea count into its standard binary string representation without prefixes, and compute the product of the count of '1' digits and the count of '0' digits in that string.",
        """total = 400
roses = int(total * 0.25)
lilies = int(total * 0.35)
hydrangeas = total - roses - lilies

b = bin(hydrangeas)[2:]
ones = b.count('1')
zeros = b.count('0')
final_answer = ones * zeros
""",
        ["math", "code"]
    ),

    # 38. 2-stage (Math -> Code) [solvable_without_tools]
    (
        ["math", "code"], "solvable_without_tools",
        "Simulate the Collatz sequence starting with seed value n = 25 where n transitions to n / 2 if n is even and 3 * n + 1 if n is odd, counting the total number of transition steps taken until n reaches 1; multiply this step count by 55 and add 180 to calculate the final maintenance fee.",
        """n = 25
steps = 0
while n != 1:
    if n % 2 == 0:
        n //= 2
    else:
        n = 3 * n + 1
    steps += 1

final_answer = steps * 55 + 180
""",
        ["math", "code"]
    ),

    # 39. 2-stage (SQL-in-prompt -> Math) [solvable_without_tools]
    (
        ["sql", "math"], "solvable_without_tools",
        "A cloud compute cluster monitoring table cluster_nodes [CREATE TABLE nodes (node_id int, zone text, cores int, load_pct float)] logs telemetry (1, 'East', 64, 85.5), (2, 'West', 32, 70.0), (3, 'East', 128, 92.0), (4, 'Central', 48, 65.0), (5, 'East', 96, 88.5), and (6, 'West', 64, 75.0); query the total CPU core count (sum of cores) deployed exclusively across nodes located in zone 'East'; if each core consumes an average of 4 kilowatt-hours per day over a 30-day billing cycle at 0.10 dollars per kilowatt-hour, calculate the total power expenditure in whole dollars.",
        """cores = 64 + 128 + 96
kwh = cores * 4 * 30
final_answer = int(kwh * 0.10)
""",
        ["sql", "math"]
    ),

    # 40. 2-stage (Math -> Code) [solvable_without_tools]
    (
        ["math", "code"], "solvable_without_tools",
        "An apple orchard harvests 750 kilograms of heirloom apples, setting aside 20 percent for cider pressing; the remaining sound apples are packed into wooden crates holding 9 kilograms each; determine the whole number count of completed crates, take the last decimal digit of this crate count, and write and execute Python code to compute and print the factorial of that single digit.",
        """import math
harvest = 750
cider = int(harvest * 0.20)
sound = harvest - cider
crates = sound // 9
last_digit = crates % 10
final_answer = math.factorial(last_digit)
""",
        ["math", "code"]
    )
]

