from gpiozero import Button
import time
import os
import subprocess

# --------------------------------
# Buttons
# GPIO5  = UP
# GPIO6  = DOWN
# GPIO26 = SELECT
# --------------------------------
BTN_UP = Button(5, pull_up=True, bounce_time=0.15)
BTN_DOWN = Button(6, pull_up=True, bounce_time=0.15)
BTN_SELECT = Button(26, pull_up=True, bounce_time=0.15)

# --------------------------------
# Menu items
# --------------------------------
menu_items = [
    ("Squat", "squat_count_final.py"),
    ("Bicep Curl", "bicep_curl_counter.py"),
    ("Shoulder Press", "shoulder_press_counter.py"),
    ("Exit", None),
]

selected_index = 0


def clear_terminal():
    os.system("clear")


def draw_menu():
    clear_terminal()
    print("=== GYM TRACKER MENU ===\n")
    print("GPIO5  = UP")
    print("GPIO6  = DOWN")
    print("GPIO26 = SELECT\n")

    for i, (label, _) in enumerate(menu_items):
        if i == selected_index:
            print(f"> {label}")
        else:
            print(f"  {label}")


def wait_for_release():
    while BTN_UP.is_pressed or BTN_DOWN.is_pressed or BTN_SELECT.is_pressed:
        time.sleep(0.05)


def run_selected_item():
    label, script_name = menu_items[selected_index]

    if label == "Exit":
        clear_terminal()
        print("Programm beendet.")
        raise SystemExit

    clear_terminal()
    print(f"Starte {label} ...")
    print("Mit CTRL + C kommst du zurueck.\n")
    time.sleep(1)

    if not os.path.exists(script_name):
        print(f"Datei nicht gefunden: {script_name}")
        print("\nDruecke SELECT, um zurueckzugehen.")
        while not BTN_SELECT.is_pressed:
            time.sleep(0.1)
        wait_for_release()
        return

    try:
        subprocess.run(["python3", script_name], check=False)
    except KeyboardInterrupt:
        pass

    clear_terminal()
    print(f"{label} beendet.")
    print("\nDruecke SELECT, um ins Menue zurueckzukehren.")

    while not BTN_SELECT.is_pressed:
        time.sleep(0.1)

    wait_for_release()


draw_menu()
wait_for_release()

while True:
    if BTN_UP.is_pressed:
        selected_index = (selected_index - 1) % len(menu_items)
        draw_menu()
        wait_for_release()

    elif BTN_DOWN.is_pressed:
        selected_index = (selected_index + 1) % len(menu_items)
        draw_menu()
        wait_for_release()

    elif BTN_SELECT.is_pressed:
        wait_for_release()
        run_selected_item()
        draw_menu()

    time.sleep(0.05)
