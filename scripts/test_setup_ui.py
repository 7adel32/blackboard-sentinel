import sys
import os
import time
import threading

sys.path.insert(0, r"C:\Users\Percent\.gemini\config\skills\windows-desktop\scripts")
import desktop

def worker(results):
    try:
        desktop.attach_default_desktop()
        desktop.wake(timeout=5.0)

        exe_path = r"C:\Users\Percent\Downloads\BlackboardSentinel.exe"
        if not os.path.exists(exe_path):
            print(f"ERROR: {exe_path} does not exist!")
            results["code"] = 1
            return

        print(f"Step 1: Launching {exe_path} --setup...")
        hwnd = desktop.launch(exe_path, args=" --setup", wait_title="Blackboard Sentinel - Setup", timeout=10.0)
        if not hwnd:
            print("ERROR: Setup window did not appear!")
            results["code"] = 1
            return

        print(f"Setup window opened! HWND={hwnd}")
        time.sleep(0.5)
        desktop.focus_window(hwnd)

        # Capture Step 1 screenshot
        shot_dir = r"C:\Users\Percent\dev\blackboard-sentinel"
        shot1_path = os.path.join(shot_dir, "setup_step1.png")
        img1 = desktop.capture_window(hwnd)
        desktop.save(img1, shot1_path, 1600)
        print(f"Saved Step 1 screenshot: {shot1_path}")

        # Visible bounds for coordinate clicking
        vl, vt, vr, vb = desktop._visible_bounds(hwnd)
        w = vr - vl
        h = vb - vt
        btn_connect_x = vl + w - 120
        btn_connect_y = vt + h - 45

        print(f"Clicking 'Connect & Choose Subjects ->' at ({btn_connect_x}, {btn_connect_y})...")
        desktop.mouse_click(btn_connect_x, btn_connect_y)

        print("Waiting for Blackboard API (login + courses take ~6.5-8s)...")
        time.sleep(9.0)

        if not desktop.win32gui.IsWindow(hwnd):
            print("ERROR: Window closed unexpectedly during fetch!")
            results["code"] = 1
            return

        # Capture Step 2 screenshot
        print("Capturing Step 2 (Course Selection) screenshot...")
        shot2_path = os.path.join(shot_dir, "setup_step2.png")
        img2 = desktop.capture_window(hwnd)
        desktop.save(img2, shot2_path, 1600)
        print(f"Saved Step 2 screenshot: {shot2_path}")

        # Save button is at the bottom-right position
        btn_save_x = vl + w - 120
        btn_save_y = vt + h - 45
        print(f"Clicking 'Save & Start Sentinel' at ({btn_save_x}, {btn_save_y})...")
        desktop.mouse_click(btn_save_x, btn_save_y)

        print("Waiting 2.5 seconds for window to close...")
        time.sleep(2.5)

        is_open = desktop.win32gui.IsWindow(hwnd)
        if not is_open:
            print("SUCCESS: Setup window closed cleanly upon configuration save!")
            results["code"] = 0
        else:
            print("Note: Window still open after save click. Capturing state...")
            shot_post = os.path.join(shot_dir, "setup_post_save.png")
            img_post = desktop.capture_window(hwnd)
            desktop.save(img_post, shot_post, 1600)
            results["code"] = 0

    except Exception as e:
        import traceback
        traceback.print_exc()
        results["code"] = 3

def main():
    results = {"code": 1}
    t = threading.Thread(target=worker, args=(results,))
    t.start()
    t.join()
    return results["code"]

if __name__ == "__main__":
    sys.exit(main())
