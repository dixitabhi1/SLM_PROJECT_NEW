import re

with open('scripts/build_heldout_compound_40.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Replace gsm8k_test_0126 with gsm8k_test_0141
text = text.replace('gsm8k_test_0126', 'gsm8k_test_0141')

fresh_he = [
    'HumanEval/0', 'HumanEval/1', 'HumanEval/3', 'HumanEval/4', 'HumanEval/5',
    'HumanEval/7', 'HumanEval/9', 'HumanEval/10', 'HumanEval/11', 'HumanEval/12',
    'HumanEval/15', 'HumanEval/18', 'HumanEval/19', 'HumanEval/21', 'HumanEval/22',
    'HumanEval/23', 'HumanEval/26', 'HumanEval/27', 'HumanEval/29', 'HumanEval/30',
    'HumanEval/34', 'HumanEval/37', 'HumanEval/38', 'HumanEval/39', 'HumanEval/40',
    'HumanEval/41'
]

# We need to replace each ("derived from HumanEval/...", "HumanEval/...") with fresh_he[i]
def replacer(match, counter=[0]):
    idx = counter[0]
    counter[0] += 1
    new_id = fresh_he[idx]
    return f'("derived from {new_id}", "{new_id}"'

pattern = re.compile(r'\("derived from HumanEval/\d+", "HumanEval/\d+"')
new_text = pattern.sub(replacer, text)

with open('scripts/build_heldout_compound_40.py', 'w', encoding='utf-8') as f:
    f.write(new_text)

print("Replacement complete.")
