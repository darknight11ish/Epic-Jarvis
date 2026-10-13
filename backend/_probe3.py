import sys, time
sys.path.insert(0, '.')
import test_gate_no_expiry as T

d, why = T.built()
G = T.load_module('jarvis_gate', d)
with T.simulated_clock(G):
    box = {}
    t = T.ask(G, 'pair_device', box)
    row = T.wait_for_row(G, box)
    print('1st row:', row and row['id'], 'db:', G.DB_PATH)
    G.decide(row['id'], False, by='test')
    t.join(timeout=5)
    print('alive:', t.is_alive())

G2 = T.load_module('jarvis_gate', d)
print('2nd db:', G2.DB_PATH, 'same?', G2.DB_PATH == G.DB_PATH)
print('2nd module file:', G2.__file__)
with T.simulated_clock(G2) as clock:
    box2 = {}
    t2 = T.ask(G2, 'send_email', box2)
    time.sleep(1.0)
    print('2nd pending():', [r['action'] for r in G2.pending()])
    t2.join(timeout=3)
    print('2nd box:', box2)
