import json
import re

SEC = ['Company Name', 'Address', 'Shipping Information', 'Goods Description']
merged_text = open(r'C:\Users\silwa\AppData\Local\Temp\merged__doc13.txt', encoding='utf-8').read()
merged = json.loads(merged_text)
ours = {p: [] for p in SEC}
for k, v in merged.items():
    for p in SEC:
        if k.startswith(p):
            ours[p].append(v.strip())
            break
print('Company Name ours:')
for v in ours['Company Name']:
    print(' ', repr(v))

# Test exact match
nv = 'tt club mutual insurance'
gv = 'TT Club Mutual Insurance'
ng = ' '.join(gv.lower().split())
nv2 = ' '.join(nv.split())
print()
print('nv:', repr(nv2))
print('ng:', repr(ng))
print('substring nv in ng:', nv2 in ng)
print('substring ng in nv:', ng in nv2)

# Test word overlap
nv_words = set(nv2.split())
ng_words = set(ng.split())
common = nv_words & ng_words
print('common:', common)
print('overlap:', len(common) / min(len(nv_words), len(ng_words)))
