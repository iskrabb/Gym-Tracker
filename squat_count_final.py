import time
import statistics
import board
import adafruit_icm20x
from gpiozero import Button

i2c = board.I2C()
imu = adafruit_icm20x.ICM20649(i2c)

BTN_SELECT = Button(26, pull_up=True, bounce_time=0.15)

EMA_ALPHA = 0.22
MIN_REP_TIME = 0.55
BOTTOM_HOLD_TIME = 0.08

SET_END_TIMEOUT = 12.0
MIN_ACTIVITY_DELTA = 0.30


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

print("Now do 3 warmup squats for calibration...")

warmup = {"x": [], "y": [], "z": []}
start = time.time()
while time.time() - start < 8.0:
    vals = get_axes()
    for k in ["x", "y", "z"]:
        ema[k] = ema_update(ema[k], vals[k])
        warmup[k].append(ema[k])
    time.sleep(0.05)

ranges = {k: max(warmup[k]) - min(warmup[k]) for k in ["x", "y", "z"]}
axis = max(ranges, key=ranges.get)

warmup_high = percentile(warmup[axis], 0.80)
warmup_low = percentile(warmup[axis], 0.20)

print("\nCalibration complete")
print(f"Chosen axis: {axis.upper()}")
print(f"Warmup high: {warmup_high:.2f}")
print(f"Warmup low:  {warmup_low:.2f}")
print(f"Warmup range:{warmup_high - warmup_low:.2f}")

print("\nNow stand normally upright for 1.5 seconds...")

top_samples = []
start = time.time()
while time.time() - start < 1.5:
    vals = get_axes()
    ema[axis] = ema_update(ema[axis], vals[axis])
    top_samples.append(ema[axis])
    print(f"standing  axis={axis.upper()} value={ema[axis]:6.2f}")
    time.sleep(0.05)

top_ref = statistics.mean(top_samples)

bottom_candidate_1 = max(warmup[axis])
bottom_candidate_2 = min(warmup[axis])

if abs(bottom_candidate_1 - top_ref) > abs(bottom_candidate_2 - top_ref):
    bottom_ref = bottom_candidate_1
else:
    bottom_ref = bottom_candidate_2

motion_range = abs(bottom_ref - top_ref)
if motion_range < 1.2:
    motion_range = 1.2

squat_goes_down = bottom_ref > top_ref

if squat_goes_down:
    DOWN_ENTER = top_ref + 0.28 * motion_range
    UP_CONFIRM = top_ref + 0.18 * motion_range
    TOP_READY = top_ref + 0.10 * motion_range
else:
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
print("Press SELECT button to end the set.\n")

state = "ready"
reps = 0
last_rep_time = time.time()
last_activity_time = time.time()
valley = None
top_since = None
last_v = ema[axis]


def passed_down_threshold(value, threshold):
    return value > threshold if squat_goes_down else value < threshold


def passed_up_threshold(value, threshold):
    return value < threshold if squat_goes_down else value > threshold


while True:
    if BTN_SELECT.is_pressed:
        print("\nSet ended manually with SELECT.")
        break

    vals = get_axes()
    ema[axis] = ema_update(ema[axis], vals[axis])
    v = ema[axis]
    now = time.time()

    if abs(v - last_v) > MIN_ACTIVITY_DELTA:
        last_activity_time = now
    last_v = v

    if now - last_activity_time > SET_END_TIMEOUT:
        print("\nSet ended automatically because of inactivity.")
        break

    if state == "ready":
        if passed_down_threshold(v, DOWN_ENTER):
            state = "down"
            valley = v
            print(f"DOWN detected | {axis.upper()}={v:.2f}")

    elif state == "down":
        if valley is None:
            valley = v
        else:
            if squat_goes_down and v > valley:
                valley = v
            elif (not squat_goes_down) and v < valley:
                valley = v

        depth = abs(valley - top_ref)

        if depth >= MIN_DEPTH and passed_up_threshold(v, UP_CONFIRM):
            state = "up"
            print(f"UP phase | valley={valley:.2f} v={v:.2f}")

    elif state == "up":
        if passed_up_threshold(v, TOP_READY):
            if now - last_rep_time > MIN_REP_TIME:
                reps += 1
                last_rep_time = now
                last_activity_time = now
                state = "top_lockout"
                top_since = now
                print(f"REP {reps} | {axis.upper()}={v:.2f}")

        elif passed_down_threshold(v, DOWN_ENTER):
            state = "down"
            valley = v

    elif state == "top_lockout":
        if passed_up_threshold(v, TOP_READY):
            if now - top_since >= BOTTOM_HOLD_TIME:
                state = "ready"
                valley = None
        else:
            top_since = now

    print(f"state={state:12s} axis={axis.upper()} value={v:6.2f} reps={reps}")
    time.sleep(0.05)

print(f"\nFinal rep count: {reps}")
