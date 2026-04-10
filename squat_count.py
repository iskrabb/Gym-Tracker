import time
import board
import adafruit_icm20x

i2c = board.I2C()
imu = adafruit_icm20x.ICM20649(i2c)

print("Stand still for 2 seconds to calibrate...")
samples = []
start = time.time()
while time.time() - start < 2.0:
    ax, ay, az = imu.acceleration
    samples.append(ax)
    time.sleep(0.05)

baseline_x = sum(samples) / len(samples)

# --- Tunable parameters ---
EMA_ALPHA = 0.25              # smoothing strength (0.2-0.35 good)
DOWN_OFFSET = 0.9             # how far below baseline counts as "down"
TOP_OFFSET = 0.35             # how close to baseline counts as "back at top"
RECOVER_FRACTION = 0.55       # rise fraction from valley to baseline
MIN_REP_TIME = 0.65           # minimum time between reps
TOP_HOLD_TIME = 0.15          # must stay near top briefly to re-arm

DOWN_THRESHOLD = baseline_x - DOWN_OFFSET
TOP_THRESHOLD = baseline_x - TOP_OFFSET

print(f"Baseline X: {baseline_x:.2f}")
print(f"DOWN threshold: {DOWN_THRESHOLD:.2f}")
print(f"TOP threshold:  {TOP_THRESHOLD:.2f}")
print("\nStart squatting...\n")

state = "ready"
reps = 0
last_rep_time = 0
valley = None
ema = None
top_since = time.time()

while True:
    ax, ay, az = imu.acceleration
    now = time.time()

    # --- EMA smoothing ---
    if ema is None:
        ema = ax
    else:
        ema = EMA_ALPHA * ax + (1 - EMA_ALPHA) * ema

    # --- State machine ---
    if state == "ready":
        # only start a squat if we are actually going below threshold
        if ema < DOWN_THRESHOLD:
            state = "down"
            valley = ema
            print(f"DOWN detected | ema={ema:.2f}")

    elif state == "down":
        # track lowest point
        if ema < valley:
            valley = ema

        # dynamic recovery threshold based on how deep the squat went
        depth = baseline_x - valley
        recover_threshold = valley + RECOVER_FRACTION * depth

        if ema > recover_threshold:
            state = "up"
            print(f"UP phase | valley={valley:.2f} recover={recover_threshold:.2f} ema={ema:.2f}")

    elif state == "up":
        # must come back near top before counting
        if ema > TOP_THRESHOLD:
            if now - last_rep_time > MIN_REP_TIME:
                reps += 1
                last_rep_time = now
                state = "top_lockout"
                top_since = now
                print(f"REP {reps} | ema={ema:.2f}")
        elif ema < DOWN_THRESHOLD:
            # went down again before finishing previous rep
            state = "down"
            valley = ema

    elif state == "top_lockout":
        # stay near top a tiny bit before re-arming
        if ema > TOP_THRESHOLD:
            if now - top_since >= TOP_HOLD_TIME:
                state = "ready"
        else:
            top_since = now

    print(f"state={state:10s} ax={ax:6.2f} ema={ema:6.2f} reps={reps}")
    time.sleep(0.06)
