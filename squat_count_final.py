import time
import statistics
import board
import adafruit_icm20x

i2c = board.I2C()
imu = adafruit_icm20x.ICM20649(i2c)

EMA_ALPHA = 0.25
MIN_REP_TIME = 0.70
TOP_HOLD_TIME = 0.10


def ema_update(prev, value, alpha=EMA_ALPHA):
    if prev is None:
        return value
    return alpha * value + (1 - alpha) * prev


def get_axes():
    ax, ay, az = imu.acceleration
    return {"x": ax, "y": ay, "z": az}


def percentile(data, p):
    s = sorted(data)
    if not s:
        return 0
    idx = int((len(s) - 1) * p)
    return s[idx]


print("Stand still for 2 seconds...")
ema = {"x": None, "y": None, "z": None}
rest = {"x": [], "y": [], "z": []}

start = time.time()
while time.time() - start < 2.0:
    vals = get_axes()
    for k in ["x", "y", "z"]:
        ema[k] = ema_update(ema[k], vals[k])
        rest[k].append(ema[k])
    time.sleep(0.05)

baseline = {k: statistics.mean(rest[k]) for k in ["x", "y", "z"]}

print("Now do 3 warmup squats for calibration...")
warmup = {"x": [], "y": [], "z": []}
start = time.time()
while time.time() - start < 10.0:
    vals = get_axes()
    for k in ["x", "y", "z"]:
        ema[k] = ema_update(ema[k], vals[k])
        warmup[k].append(ema[k])
    time.sleep(0.05)

ranges = {k: max(warmup[k]) - min(warmup[k]) for k in ["x", "y", "z"]}
axis = max(ranges, key=ranges.get)

warmup_top = percentile(warmup[axis], 0.80)
warmup_bottom = percentile(warmup[axis], 0.20)
if warmup_top < warmup_bottom:
    warmup_top, warmup_bottom = warmup_bottom, warmup_top

print("\nCalibration complete")
print(f"Chosen axis: {axis.upper()}")
print(f"Warmup top:    {warmup_top:.2f}")
print(f"Warmup bottom: {warmup_bottom:.2f}")
print(f"Warmup range:  {warmup_top - warmup_bottom:.2f}")

print("\nNow stand normally upright for 1.5 seconds...")
standing = []
start = time.time()
while time.time() - start < 1.5:
    vals = get_axes()
    ema[axis] = ema_update(ema[axis], vals[axis])
    standing.append(ema[axis])
    print(f"standing  axis={axis.upper()} value={ema[axis]:6.2f}")
    time.sleep(0.05)

top_ref = statistics.mean(standing)
bottom_ref = warmup_bottom
motion_range = abs(top_ref - bottom_ref)

if motion_range < 1.5:
    motion_range = 1.5

DOWN_ENTER = top_ref - 0.28 * motion_range
UP_CONFIRM = top_ref - 0.18 * motion_range
TOP_READY = top_ref - 0.10 * motion_range
MIN_DEPTH = 0.22 * motion_range

print("\nFinal thresholds")
print(f"Top ref:      {top_ref:.2f}")
print(f"Bottom ref:   {bottom_ref:.2f}")
print(f"Range:        {motion_range:.2f}")
print(f"DOWN_ENTER:   {DOWN_ENTER:.2f}")
print(f"UP_CONFIRM:   {UP_CONFIRM:.2f}")
print(f"TOP_READY:    {TOP_READY:.2f}")
print(f"MIN_DEPTH:    {MIN_DEPTH:.2f}")
print("\nStart real squats...\n")

state = "ready"
reps = 0
last_rep_time = 0
valley = None
top_since = None

while True:
    vals = get_axes()
    ema[axis] = ema_update(ema[axis], vals[axis])
    v = ema[axis]
    now = time.time()

    if state == "ready":
        if v < DOWN_ENTER:
            state = "down"
            valley = v
            print(f"DOWN detected | {axis}={v:.2f}")

    elif state == "down":
        if valley is None or v < valley:
            valley = v

        depth = top_ref - valley

        if depth >= MIN_DEPTH and v > UP_CONFIRM:
            state = "up"
            print(f"UP phase | valley={valley:.2f} v={v:.2f}")

    elif state == "up":
        if v > TOP_READY and now - last_rep_time > MIN_REP_TIME:
            reps += 1
            last_rep_time = now
            state = "top_lockout"
            top_since = now
            print(f"REP {reps} | {axis}={v:.2f}")

        elif v < DOWN_ENTER:
            state = "down"
            if valley is None or v < valley:
                valley = v

    elif state == "top_lockout":
        if v > TOP_READY:
            if now - top_since >= TOP_HOLD_TIME:
                state = "ready"
                valley = None
        else:
            top_since = now

    print(f"state={state:10s} axis={axis.upper()} value={v:6.2f} reps={reps}")
    time.sleep(0.05)
