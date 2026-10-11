"""
Test sensitivity of compound reference code.
"""
import os
import sys

ref_code = '''import sqlite3
conn = sqlite3.connect('data/spider/database/world_1/world_1.sqlite')
c = conn.cursor()
c.execute("SELECT count(*) FROM city WHERE CountryCode = 'NLD'")
s1 = c.fetchone()[0]

score = s1 * 15 + 30
cap = score // 8

items = [(10, 35), (15, 50), (20, 70), (25, 90), (30, 115)]
dp = [0] * (cap + 1)
for w, v in items:
    for j in range(cap, w - 1, -1):
        dp[j] = max(dp[j], dp[j - w] + v)

final_answer = dp[cap]
'''

locs_orig = {}
exec(ref_code, {}, locs_orig)
orig_ans = locs_orig['final_answer']
orig_s1 = locs_orig['s1']
orig_score = locs_orig['score']

locs_pert1 = {}
exec(ref_code.replace("s1 = c.fetchone()[0]", f"s1 = {orig_s1 + 5}"), {}, locs_pert1)
ans_pert1 = locs_pert1['final_answer']

locs_pert2 = {}
exec(ref_code.replace("score = s1 * 15 + 30", f"score = {orig_score + 15}"), {}, locs_pert2)
ans_pert2 = locs_pert2['final_answer']

print("Original:", orig_ans)
print("Perturbed Stage 1:", ans_pert1, "Different?", ans_pert1 != orig_ans)
print("Perturbed Stage 2:", ans_pert2, "Different?", ans_pert2 != orig_ans)

