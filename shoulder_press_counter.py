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
MIN_ACTIVITY_DELTA = 0.25


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


print("Arm/Hantel locker halten und 2 Sekunden still bleiben...")

ema = {"x": None, "y": None, "z": None}
rest = {"x": [], "y": [], "z": []}

start = time.time()
while time.time() - start < 2.0:
    vals = get_axes()
    for k in ["x", "y", "z"]:
        ema[k] = ema_update(ema[k], vals[k])
        rest[k].append(ema[k])
    time.sleep(0.05)

print("Jetzt 3 Warmup-Shoulder-Press-Reps machen...")

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

print("\nKalibrierung fertig")
print(f"Gewählte Achse: {axis.upper()}")
print(f"Warmup high: {warmup_high:.2f}")
print(f"Warmup low:  {warmup_low:.2f}")
print(f"Range:       {warmup_high - warmup_low:.2f}")

print("\nJetzt Arm/Hantel UNTEN auf Schulterhöhe für 1.5 Sekunden ruhig halten...")

bottom_samples = []
start = time.time()
while time.time() - start < 1.5:
    vals = get_axes()
    ema[axis] = ema_update(ema[axis], vals[axis])
    bottom_samples.append(ema[axis])
    print(f"bottom_ref axis={axis.upper()} value={ema[axis]:6.2f}")
    time.sleep(0.05)

bottom_ref = statistics.mean(bottom_samples)

top_candidate_1 = max(warmup[axis])
top_candidate_2 = min(warmup[axis])

if abs(top_candidate_1 - bottom_ref) > abs(top_candidate_2 - bottom_ref):
    top_ref = top_candidate_1
else:
    top_ref = top_candidate_2

motion_range = abs(top_ref - bottom_ref)
if motion_range < 1.2:
    motion_range = 1.2

press_goes_up = top_ref > bottom_ref

if press_goes_up:
    PRESS_ENTER = bottom_ref + 0.25 * motion_range
    TOP_CONFIRM = bottom_ref + 0.60 * motion_range
    BOTTOM_READY = bottom_ref + 0.12 * motion_range
else:
    PRESS_ENTER = bottom_ref - 0.25 * motion_range
    TOP_CONFIRM = bottom_ref - 0.60 * motion_range
    BOTTOM_READY = bottom_ref - 0.12 * motion_range

MIN_PRESS = 0.22 * motion_range

print("\nFinale Werte")
print(f"Bottom ref:   {bottom_ref:.2f}")
print(f"Top ref:      {top_ref:.2f}")
print(f"Range:        {motion_range:.2f}")
print(f"PRESS_ENTER:  {PRESS_ENTER:.2f}")
print(f"TOP_CONFIRM:  {TOP_CONFIRM:.2f}")
print(f"BOTTOM_READY: {BOTTOM_READY:.2f}")
print(f"MIN_PRESS:    {MIN_PRESS:.2f}")
print("\nStart echte Shoulder Press Reps...\n")
print("Press SELECT button to end the set.\n")

state = "ready"
reps = 0
last_rep_time = time.time()
last_activity_time = time.time()
peak = None
bottom_since = None
last_v = ema[axis]


def passed_up_threshold(value, threshold):
    return value > threshold if press_goes_up else value < threshold


def passed_down_threshold(value, threshold):
    return value < threshold if press_goes_up else value > threshold


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
        if passed_up_threshold(v, PRESS_ENTER):
            state = "pressing"
            peak = v
            print(f"PRESS detected | {axis.upper()}={v:.2f}")

    elif state == "pressing":
        if peak is None:
            peak = v
        else:
            if press_goes_up and v > peak:
                peak = v
            elif (not press_goes_up) and v < peak:
                peak = v

        press_amount = abs(peak - bottom_ref)

        if press_amount >= MIN_PRESS and passed_up_threshold(v, TOP_CONFIRM):
            state = "top"
            print(f"TOP reached | peak={peak:.2f} value={v:.2f}")

        elif passed_down_threshold(v, BOTTOM_READY):
            state = "ready"
            peak = None

    elif state == "top":
        if passed_down_threshold(v, BOTTOM_READY):
            if now - last_rep_time > MIN_REP_TIME:
                reps += 1
                last_rep_time = now
                last_activity_time = now
                state = "bottom_lockout"
                bottom_since = now
                print(f"REP {reps} | {axis.upper()}={v:.2f}")

    elif state == "bottom_lockout":
        if passed_down_threshold(v, BOTTOM_READY):
            if now - bottom_since >= BOTTOM_HOLD_TIME:
                state = "ready"
                peak = None
        else:
            bottom_since = now

    print(f"state={state:12s} axis={axis.upper()} value={v:6.2f} reps={reps}")
    time.sleep(0.05)

print(f"\nFinal rep count: {reps}")
