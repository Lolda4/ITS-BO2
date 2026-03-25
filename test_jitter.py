import time
import random

def get_stats(num_packets):
    print("Generating", num_packets, "packets...")
    packets = [(i, int(time.monotonic() * 1000000) + random.randint(0, 1000)) for i in range(num_packets)]
    print("Generated. Starting stats...")
    
    start_time = time.monotonic()
    
    seqs = sorted(p[0] for p in packets)
    arrivals = [p[1] for p in packets]
    inter_arrivals = [arrivals[i + 1] - arrivals[i] for i in range(len(arrivals) - 1)]
    if len(inter_arrivals) > 1:
        jitter_values = [
            abs(inter_arrivals[i + 1] - inter_arrivals[i])
            for i in range(len(inter_arrivals) - 1)
        ]
        jitter_ms = sum(jitter_values) / len(jitter_values) / 1000
    
    print("Done. Took", time.monotonic() - start_time, "seconds")

get_stats(1500000)
