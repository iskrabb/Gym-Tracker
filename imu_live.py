import time
import math
import board
import adafruit_icm20x

i2c = board.I2C()
imu = adafruit_icm20x.ICM20649(i2c)

print("ICM-20649 live reader started")
print("Press CTRL+C to stop\n")

while True:
    ax, ay, az = imu.acceleration
    gx, gy, gz = imu.gyro
    total_acc = math.sqrt(ax**2 + ay**2 + az**2)

    print(
        f"ACC  X:{ax:7.2f}  Y:{ay:7.2f}  Z:{az:7.2f}   "
        f"| GYRO X:{gx:7.2f} Y:{gy:7.2f} Z:{gz:7.2f}   "
        f"| |A|:{total_acc:7.2f}"
    )

    time.sleep(0.10)
