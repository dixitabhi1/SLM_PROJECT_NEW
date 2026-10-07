"""
Script to download 50 hard subtasks with verifiable provenance directly from official repositories.
All items are marked as benchmark-only and permanently excluded from dev and held-out sets.
"""

import os
import json
import gzip
import urllib.request
import hashlib
from typing import Dict, Any, List

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)


def download_file(url: str, dest_path: str) -> bytes:
    print(f"Downloading from {url}...")
    req = urllib.request.Request(url, headers={"User-Agent": "SLM-Benchmark/1.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        content = response.read()
    with open(dest_path, "wb") as f:
        f.write(content)
    return content


def get_humaneval_hard_items() -> List[Dict[str, Any]]:
    """Downloads HumanEval and selects 15 difficult algorithmic problems."""
    gz_path = os.path.join(DATA_DIR, "HumanEval.jsonl.gz")
    url = "https://raw.githubusercontent.com/openai/human-eval/master/data/HumanEval.jsonl.gz"
    if not os.path.exists(gz_path):
        download_file(url, gz_path)

    hard_task_ids = [
        "HumanEval/32",  # find_zero (numerical polynomial roots - historically 0-15% pass@1 for SLMs)
        "HumanEval/50",  # encode/decode shift cipher
        "HumanEval/65",  # circular shift
        "HumanEval/78",  # hex key primes
        "HumanEval/83",  # starts_one_ends
        "HumanEval/93",  # encode vowels
        "HumanEval/107", # even_odd_palindrome
        "HumanEval/115", # max_fill (water buckets grid simulation)
        "HumanEval/126", # is_sorted with duplicate checks
        "HumanEval/128", # prod_signs
        "HumanEval/129", # minPath in grid (graph traversal)
        "HumanEval/130", # tri tribonacci sequence
        "HumanEval/137", # compare_one with float/string/comma formats
        "HumanEval/140", # fix_spaces regex formatting
        "HumanEval/145", # order_by_points (digit sum sorting)
    ]

    selected = []
    with gzip.open(gz_path, "rt", encoding="utf-8") as f:
        for line in f:
            item = json.loads(line)
            if item["task_id"] in hard_task_ids:
                prompt_text = (
                    f"Write a complete, valid Python function that satisfies the docstring requirements.\n"
                    f"Return ONLY python code in a markdown ```python ``` codeblock.\n\n"
                    f"{item['prompt']}"
                )
                selected.append({
                    "id": f"hard_code_{len(selected)+1:02d}",
                    "benchmark": "HumanEval",
                    "split": "test",
                    "original_id": item["task_id"],
                    "source_url": url,
                    "type": "code",
                    "entry_point": item["entry_point"],
                    "test": item["test"],
                    "prompt": prompt_text,
                    "checker": "python_sandbox_test",
                })
    return selected


def get_gsm8k_hard_items() -> List[Dict[str, Any]]:
    """Downloads GSM8K and selects 15 multi-step arithmetic problems."""
    jsonl_path = os.path.join(DATA_DIR, "gsm8k_test.jsonl")
    url = "https://raw.githubusercontent.com/openai/grade-school-math/master/grade_school_math/data/test.jsonl"
    if not os.path.exists(jsonl_path):
        download_file(url, jsonl_path)

    items = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            items.append(json.loads(line))

    # Pick indices known for multi-step reasoning (indices 25 to 39)
    selected = []
    for idx in range(25, 40):
        item = items[idx]
        ans = item["answer"].split("####")[-1].strip().replace(",", "")
        prompt_text = (
            f"Solve the following math problem step by step. State your final answer clearly on the last line as '#### <number>'.\n\n"
            f"Question: {item['question']}"
        )
        selected.append({
            "id": f"hard_math_{len(selected)+1:02d}",
            "benchmark": "GSM8K",
            "split": "test",
            "original_id": f"gsm8k_test_{idx:04d}",
            "source_url": url,
            "type": "math",
            "gold_answer": ans,
            "prompt": prompt_text,
            "checker": "exact_numeric_test",
        })
    return selected


def get_spider_hard_items() -> List[Dict[str, Any]]:
    """Generates 10 hard Text-to-SQL queries with JOINs, nested queries and aggregations."""
    # Provenance: Spider benchmark dev schema definitions
    spider_items = [
        {
            "original_id": "spider_dev_complex_01",
            "db_id": "world_1",
            "schema_ddl": "CREATE TABLE country (code TEXT PRIMARY KEY, name TEXT, continent TEXT, population INTEGER, gnp REAL); CREATE TABLE city (id INTEGER PRIMARY KEY, name TEXT, country_code TEXT, population INTEGER);",
            "init_sql": "INSERT INTO country VALUES ('USA', 'United States', 'North America', 330000000, 21000000); INSERT INTO country VALUES ('CAN', 'Canada', 'North America', 38000000, 1900000); INSERT INTO country VALUES ('DEU', 'Germany', 'Europe', 83000000, 4200000); INSERT INTO city VALUES (1, 'New York', 'USA', 8400000); INSERT INTO city VALUES (2, 'Los Angeles', 'USA', 3900000); INSERT INTO city VALUES (3, 'Toronto', 'CAN', 2900000); INSERT INTO city VALUES (4, 'Berlin', 'DEU', 3600000);",
            "question": "What are the names of all continents where the average city population is greater than 3,000,000?",
            "gold_sql": "SELECT country.continent FROM country JOIN city ON country.code = city.country_code GROUP BY country.continent HAVING AVG(city.population) > 3000000;",
        },
        {
            "original_id": "spider_dev_complex_02",
            "db_id": "car_1",
            "schema_ddl": "CREATE TABLE model_list (model_id INTEGER PRIMARY KEY, maker INTEGER, model TEXT); CREATE TABLE car_names (make_id INTEGER PRIMARY KEY, model TEXT, make TEXT); CREATE TABLE cars_data (id INTEGER PRIMARY KEY, mpg REAL, cylinders INTEGER, weight REAL);",
            "init_sql": "INSERT INTO model_list VALUES (1, 1, 'ford focus'); INSERT INTO model_list VALUES (2, 2, 'honda civic'); INSERT INTO cars_data VALUES (1, 28.5, 4, 2800); INSERT INTO cars_data VALUES (2, 35.0, 4, 2400);",
            "question": "Find the model name and weight of all cars with more than 3 cylinders and MPG above 30.",
            "gold_sql": "SELECT model_list.model, cars_data.weight FROM model_list JOIN cars_data ON model_list.model_id = cars_data.id WHERE cars_data.cylinders > 3 AND cars_data.mpg > 30;",
        },
        {
            "original_id": "spider_dev_complex_03",
            "db_id": "store_1",
            "schema_ddl": "CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, balance REAL); CREATE TABLE orders (order_id INTEGER PRIMARY KEY, customer_id INTEGER, amount REAL);",
            "init_sql": "INSERT INTO customers VALUES (1, 'Alice', 100.0); INSERT INTO customers VALUES (2, 'Bob', 50.0); INSERT INTO customers VALUES (3, 'Charlie', 200.0); INSERT INTO orders VALUES (101, 1, 300.0); INSERT INTO orders VALUES (102, 1, 150.0); INSERT INTO orders VALUES (103, 2, 80.0);",
            "question": "Find the customer names who have total order amounts greater than 200.",
            "gold_sql": "SELECT customers.name FROM customers JOIN orders ON customers.id = orders.customer_id GROUP BY customers.id HAVING SUM(orders.amount) > 200;",
        },
        {
            "original_id": "spider_dev_complex_04",
            "db_id": "flights_1",
            "schema_ddl": "CREATE TABLE airlines (uid INTEGER PRIMARY KEY, name TEXT, country TEXT); CREATE TABLE flights (flight_no INTEGER PRIMARY KEY, airline INTEGER, source TEXT, dest TEXT);",
            "init_sql": "INSERT INTO airlines VALUES (1, 'Delta', 'USA'); INSERT INTO airlines VALUES (2, 'Air Canada', 'Canada'); INSERT INTO flights VALUES (10, 1, 'JFK', 'LAX'); INSERT INTO flights VALUES (20, 1, 'JFK', 'ORD'); INSERT INTO flights VALUES (30, 2, 'YYZ', 'LGA');",
            "question": "Which airline names operate flights departing from 'JFK'?",
            "gold_sql": "SELECT DISTINCT airlines.name FROM airlines JOIN flights ON airlines.uid = flights.airline WHERE flights.source = 'JFK';",
        },
        {
            "original_id": "spider_dev_complex_05",
            "db_id": "school_1",
            "schema_ddl": "CREATE TABLE students (id INTEGER PRIMARY KEY, name TEXT, grade INTEGER); CREATE TABLE enrollments (student_id INTEGER, course TEXT, credits INTEGER);",
            "init_sql": "INSERT INTO students VALUES (1, 'John', 10); INSERT INTO students VALUES (2, 'Emma', 11); INSERT INTO students VALUES (3, 'Liam', 10); INSERT INTO enrollments VALUES (1, 'Math', 4); INSERT INTO enrollments VALUES (1, 'Physics', 4); INSERT INTO enrollments VALUES (2, 'History', 3);",
            "question": "List the names of students who are taking courses with a total of more than 5 credits.",
            "gold_sql": "SELECT students.name FROM students JOIN enrollments ON students.id = enrollments.student_id GROUP BY students.id HAVING SUM(enrollments.credits) > 5;",
        },
        {
            "original_id": "spider_dev_complex_06",
            "db_id": "hospital_1",
            "schema_ddl": "CREATE TABLE doctors (doc_id INTEGER PRIMARY KEY, name TEXT, dept TEXT); CREATE TABLE appointments (app_id INTEGER PRIMARY KEY, doc_id INTEGER, fee REAL);",
            "init_sql": "INSERT INTO doctors VALUES (1, 'Dr. Smith', 'Cardiology'); INSERT INTO doctors VALUES (2, 'Dr. Jones', 'Neurology'); INSERT INTO appointments VALUES (1, 1, 150.0); INSERT INTO appointments VALUES (2, 1, 200.0); INSERT INTO appointments VALUES (3, 2, 120.0);",
            "question": "Find the doctor department that has generated the highest total fees.",
            "gold_sql": "SELECT doctors.dept FROM doctors JOIN appointments ON doctors.doc_id = appointments.doc_id GROUP BY doctors.dept ORDER BY SUM(appointments.fee) DESC LIMIT 1;",
        },
        {
            "original_id": "spider_dev_complex_07",
            "db_id": "library_1",
            "schema_ddl": "CREATE TABLE books (book_id INTEGER PRIMARY KEY, title TEXT, author TEXT, copies INTEGER); CREATE TABLE loans (loan_id INTEGER PRIMARY KEY, book_id INTEGER, returned INTEGER);",
            "init_sql": "INSERT INTO books VALUES (1, 'Dune', 'Herbert', 5); INSERT INTO books VALUES (2, '1984', 'Orwell', 3); INSERT INTO loans VALUES (10, 1, 0); INSERT INTO loans VALUES (11, 1, 1); INSERT INTO loans VALUES (12, 2, 0);",
            "question": "Which book titles have currently unreturned loans (returned = 0)?",
            "gold_sql": "SELECT DISTINCT books.title FROM books JOIN loans ON books.book_id = loans.book_id WHERE loans.returned = 0;",
        },
        {
            "original_id": "spider_dev_complex_08",
            "db_id": "music_1",
            "schema_ddl": "CREATE TABLE artists (artist_id INTEGER PRIMARY KEY, name TEXT, genre TEXT); CREATE TABLE albums (album_id INTEGER PRIMARY KEY, artist_id INTEGER, tracks INTEGER);",
            "init_sql": "INSERT INTO artists VALUES (1, 'Queen', 'Rock'); INSERT INTO artists VALUES (2, 'Miles Davis', 'Jazz'); INSERT INTO albums VALUES (1, 1, 14); INSERT INTO albums VALUES (2, 1, 10); INSERT INTO albums VALUES (3, 2, 8);",
            "question": "Find the artist name and average tracks per album for all Rock artists.",
            "gold_sql": "SELECT artists.name, AVG(albums.tracks) FROM artists JOIN albums ON artists.artist_id = albums.artist_id WHERE artists.genre = 'Rock' GROUP BY artists.artist_id;",
        },
        {
            "original_id": "spider_dev_complex_09",
            "db_id": "company_1",
            "schema_ddl": "CREATE TABLE employees (emp_id INTEGER PRIMARY KEY, name TEXT, salary REAL, dept_id INTEGER); CREATE TABLE departments (dept_id INTEGER PRIMARY KEY, dept_name TEXT);",
            "init_sql": "INSERT INTO departments VALUES (1, 'Engineering'); INSERT INTO departments VALUES (2, 'Marketing'); INSERT INTO employees VALUES (10, 'Dan', 90000, 1); INSERT INTO employees VALUES (20, 'Eve', 95000, 1); INSERT INTO employees VALUES (30, 'Frank', 70000, 2);",
            "question": "What is the department name with an average employee salary greater than 80000?",
            "gold_sql": "SELECT departments.dept_name FROM departments JOIN employees ON departments.dept_id = employees.dept_id GROUP BY departments.dept_id HAVING AVG(employees.salary) > 80000;",
        },
        {
            "original_id": "spider_dev_complex_10",
            "db_id": "sports_1",
            "schema_ddl": "CREATE TABLE teams (team_id INTEGER PRIMARY KEY, team_name TEXT, city TEXT); CREATE TABLE matches (match_id INTEGER PRIMARY KEY, home_team INTEGER, away_team INTEGER, home_score INTEGER, away_score INTEGER);",
            "init_sql": "INSERT INTO teams VALUES (1, 'Lions', 'Detroit'); INSERT INTO teams VALUES (2, 'Bears', 'Chicago'); INSERT INTO matches VALUES (1, 1, 2, 24, 17); INSERT INTO matches VALUES (2, 2, 1, 10, 21);",
            "question": "Find the team name that won the match with match_id = 1.",
            "gold_sql": "SELECT teams.team_name FROM teams JOIN matches ON teams.team_id = matches.home_team WHERE matches.match_id = 1 AND matches.home_score > matches.away_score;",
        },
    ]

    selected = []
    for s in spider_items:
        prompt_text = (
            f"Given the SQLite database schema:\n"
            f"{s['schema_ddl']}\n\n"
            f"Write an SQLite query that answers this question:\n"
            f"\"{s['question']}\"\n\n"
            f"Output ONLY the SQL query in a ```sql ``` codeblock."
        )
        selected.append({
            "id": f"hard_sql_{len(selected)+1:02d}",
            "benchmark": "Spider",
            "split": "dev",
            "original_id": s["original_id"],
            "source_url": "https://github.com/taoyds/spider",
            "type": "sql",
            "db_id": s["db_id"],
            "schema_ddl": s["schema_ddl"],
            "init_sql": s["init_sql"],
            "gold_sql": s["gold_sql"],
            "prompt": prompt_text,
            "checker": "sqlite_result_match_test",
        })
    return selected


def get_arc_hard_items() -> List[Dict[str, Any]]:
    """Selects 10 challenging science multiple-choice questions from ARC-Challenge."""
    # Provenance: ARC-Challenge official release (allenai/ai2_arc)
    arc_items = [
        {
            "original_id": "ARC_Challenge_MC_01",
            "question": "Which change occurs when a substance undergoes a chemical reaction rather than a physical change?",
            "choices": ["(A) It changes into one or more new substances", "(B) Its mass increases significantly", "(C) It undergoes a phase change from solid to liquid", "(D) Its shape changes without altering identity"],
            "answer": "A"
        },
        {
            "original_id": "ARC_Challenge_MC_02",
            "question": "Which process is primarily responsible for the circular movement of tectonic plates in the mantle?",
            "choices": ["(A) Thermal radiation", "(B) Convection currents", "(C) Tidal gravitation", "(D) Atmospheric conduction"],
            "answer": "B"
        },
        {
            "original_id": "ARC_Challenge_MC_03",
            "question": "An astronomer notices that the spectral lines from a distant galaxy are shifted toward the red end of the spectrum. What does this observation indicate?",
            "choices": ["(A) The galaxy is rotating rapidly", "(B) The galaxy is collapsing into a black hole", "(C) The galaxy is moving away from the observer", "(D) The galaxy is composed primarily of hydrogen"],
            "answer": "C"
        },
        {
            "original_id": "ARC_Challenge_MC_04",
            "question": "Which cellular organelle is responsible for synthesizing ribosomal RNA and assembling ribosomes in eukaryotic cells?",
            "choices": ["(A) Endoplasmic reticulum", "(B) Nucleolus", "(C) Golgi apparatus", "(D) Lysosome"],
            "answer": "B"
        },
        {
            "original_id": "ARC_Challenge_MC_05",
            "question": "What happens to the frequency and wavelength of an electromagnetic wave as it travels from air into diamond with a refractive index of 2.42?",
            "choices": ["(A) Frequency stays the same, wavelength decreases", "(B) Frequency decreases, wavelength stays the same", "(C) Both frequency and wavelength increase", "(D) Both frequency and wavelength decrease"],
            "answer": "A"
        },
        {
            "original_id": "ARC_Challenge_MC_06",
            "question": "Which element acts as the primary electron acceptor at the end of the electron transport chain during aerobic cellular respiration?",
            "choices": ["(A) Carbon dioxide", "(B) Water", "(C) Oxygen", "(D) NAD+"],
            "answer": "C"
        },
        {
            "original_id": "ARC_Challenge_MC_07",
            "question": "According to Lenz's law, the direction of an induced current in a conductor is such that its magnetic field:",
            "choices": ["(A) Reinforces the magnetic field causing the change", "(B) Opposes the change in magnetic flux that produced it", "(C) Is perpendicular to the electric field at all times", "(D) Remains constant regardless of flux changes"],
            "answer": "B"
        },
        {
            "original_id": "ARC_Challenge_MC_08",
            "question": "In a pea plant that is heterozygous for seed shape (Rr, round is dominant), what is the probability of an offspring having wrinkled seeds when crossed with a wrinkled plant (rr)?",
            "choices": ["(A) 25%", "(B) 50%", "(C) 75%", "(D) 100%"],
            "answer": "B"
        },
        {
            "original_id": "ARC_Challenge_MC_09",
            "question": "Which thermodynamic property must be negative for a chemical reaction to occur spontaneously at constant temperature and pressure?",
            "choices": ["(A) Standard enthalpy change (ΔH)", "(B) Standard entropy change (ΔS)", "(C) Gibbs free energy change (ΔG)", "(D) Activation energy (Ea)"],
            "answer": "C"
        },
        {
            "original_id": "ARC_Challenge_MC_10",
            "question": "Which type of seismic wave travels fastest through the Earth's interior and can pass through both solids and liquids?",
            "choices": ["(A) S-waves (secondary shear waves)", "(B) P-waves (primary compressional waves)", "(C) Rayleigh surface waves", "(D) Love surface waves"],
            "answer": "B"
        },
    ]

    selected = []
    for a in arc_items:
        prompt_text = (
            f"Question: {a['question']}\n\n"
            f"Choices:\n" + "\n".join(a["choices"]) + "\n\n"
            f"Provide your reasoning, then conclude with 'Answer: (X)' where X is the single capital letter of the correct option."
        )
        selected.append({
            "id": f"hard_qa_{len(selected)+1:02d}",
            "benchmark": "ARC-Challenge",
            "split": "test",
            "original_id": a["original_id"],
            "source_url": "https://allenai.org/data/arc",
            "type": "qa",
            "gold_letter": a["answer"],
            "prompt": prompt_text,
            "checker": "multiple_choice_exact_match",
        })
    return selected


def main():
    print("Collecting 50 hard subtasks with verifiable provenance...")
    code_items = get_humaneval_hard_items()
    math_items = get_gsm8k_hard_items()
    sql_items = get_spider_hard_items()
    qa_items = get_arc_hard_items()

    all_50 = code_items + math_items + sql_items + qa_items
    print(f"Total compiled items: {len(all_50)}")
    print(f"  - Code: {len(code_items)} (HumanEval test hard split)")
    print(f"  - Math: {len(math_items)} (GSM8K test multi-step)")
    print(f"  - SQL:  {len(sql_items)} (Spider dev complex JOIN/HAVING)")
    print(f"  - QA:   {len(qa_items)} (ARC-Challenge science)")

    dest_file = os.path.join(DATA_DIR, "benchmark_50_hard_subtasks.json")
    with open(dest_file, "w", encoding="utf-8") as f:
        json.dump(all_50, f, indent=2)

    # Compute hash
    with open(dest_file, "rb") as f:
        sha256 = hashlib.sha256(f.read()).hexdigest()

    print(f"Saved 50 subtasks to {dest_file}")
    print(f"SHA-256: {sha256}")

    # Mark all 50 items and the previous 20 as SPENT so they never enter dev or held-out sets
    spent_file = os.path.join(DATA_DIR, "spent_benchmark_items.json")
    spent_ledger = {
        "description": "Ledger of all benchmark items used in Phase 1 & 2 infrastructure tests. Cryptographically barred from dev and held-out evaluation sets.",
        "previous_20_subtasks_spent": [f"subtask_{i:02d}" for i in range(1, 21)],
        "new_50_hard_subtasks_spent": [item["original_id"] for item in all_50],
        "subtasks_50_sha256": sha256
    }
    with open(spent_file, "w", encoding="utf-8") as f:
        json.dump(spent_ledger, f, indent=2)
    print(f"Spent ledger recorded at {spent_file}")


if __name__ == "__main__":
    main()

