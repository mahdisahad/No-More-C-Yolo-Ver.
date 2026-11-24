import curses
import ctypes
import random
import sys
import threading
import time
import pygame
MAX_WID = 80
MAX_HT = 22
MIN_WID = 20
MIN_HT = 10
WID = MAX_WID
HT = MAX_HT
OFFSET_X = 0
OFFSET_Y = 0
TERM_ROWS = 0
TERM_COLS = 0
D_H = 3
D_W = 5
O_W = 1
O_H = 2
J_H = 4
REF_T = 100000
COLORS = [1, 2, 3, 4, 5, 6, 7]
IS_WINDOWS = sys.platform == "win32"
CAMERA_WINDOW = "No More C - Hand Tracking"
MODEL_NAME = "yolo11n-pose.pt"
INFER_SIZE = 640
ENTER_KEYS = (10, 13, curses.KEY_ENTER)
GESTURE_BUFFER_S = 0.4
MIN_OBS_GAP = 16
MAX_OBS_GAP = 34
class Obs:
    def __init__(self, x=0, y=0, w=0, h=0):
        self.x = x
        self.y = y
        self.w = w
        self.h = h
class Dino:
    def __init__(self):
        self.x = 5
        self.y = HT - 3
        self.jump = 0
        self.j_height = 0
        self.orig_y = HT - 3
        self.jump_start = 0
        self.peak_time = 0
    def set_ground(self, ground_y):
        """Follow the ground line when the playfield is resized."""
        self.orig_y = ground_y
        if not self.jump:
            self.y = ground_y
class Star:
    """A star stored as a fraction of the playfield so it survives resizes."""
    def __init__(self, fx=0.0, fy=0.0):
        self.fx = fx
        self.fy = fy
class Round:
    """Everything that belongs to one play-through (reset on replay)."""
    def __init__(self):
        self.stars = generate_stars()
        self.dino = Dino()
        self.obstacles = []
        self.start_time = time.time()
        self.end_time = None
        self.last_color_time = 0
        self.color_idx = 0
        self.spawn_in = random.randint(MIN_OBS_GAP, MAX_OBS_GAP)
def handle_resize(stdscr):
    """Tell curses the window changed size (needed for PDCurses/Windows)."""
    try:
        curses.resize_term(0, 0)
    except (AttributeError, curses.error):
        pass
    stdscr.clear()
def update_layout(stdscr):
    """Fit the playfield to the terminal and center it."""
    global WID, HT, OFFSET_X, OFFSET_Y, TERM_ROWS, TERM_COLS
    try:
        rows, cols = stdscr.getmaxyx()
        if curses.is_term_resized(rows, cols):
            handle_resize(stdscr)
    except (AttributeError, curses.error):
        pass
    rows, cols = stdscr.getmaxyx()
    TERM_ROWS, TERM_COLS = rows, cols
    WID = max(MIN_WID, min(MAX_WID, cols))
    HT = max(MIN_HT, min(MAX_HT, rows))
    OFFSET_X = max(0, (cols - WID) // 2)
    OFFSET_Y = max(0, (rows - HT) // 2)
def add_text(stdscr, y, x, value, attr=0):
    """Draw at playfield coordinates, clipped to the playfield and terminal."""
    if y < 0 or y >= HT:
        return
    if x < 0:
        value = value[-x:]
        x = 0
    value = value[:max(0, WID - x)]
    screen_y = y + OFFSET_Y
    screen_x = x + OFFSET_X
    if not value or screen_y >= TERM_ROWS or screen_x >= TERM_COLS:
        return
    value = value[:TERM_COLS - screen_x]
    try:
        stdscr.addstr(screen_y, screen_x, value, attr)
    except curses.error:
        pass
def add_centered(stdscr, y, value, attr=0):
    """Draw a line horizontally centered in the playfield."""
    add_text(stdscr, y, (WID - len(value)) // 2, value, attr)
def bdr(stdscr):
    for xx in range(WID):
        add_text(stdscr, 0, xx, "-")
        add_text(stdscr, HT - 1, xx, "-")
    for yy in range(HT):
        add_text(stdscr, yy, 0, "|")
        add_text(stdscr, yy, WID - 1, "|")
def dino(stdscr, d):
    if d.jump:
        add_text(stdscr, d.y - d.j_height, d.x, " ^_^ ")
        add_text(stdscr, d.y - d.j_height + 1, d.x, " /|\\ ")
        add_text(stdscr, d.y - d.j_height + 2, d.x, " / \\ ")
    else:
        add_text(stdscr, d.y, d.x, " >_< ")
        add_text(stdscr, d.y + 1, d.x, " /|\\ ")
        add_text(stdscr, d.y + 2, d.x, " / \\ ")
def obstacle(stdscr, o):
    for i in range(o.h):
        for j in range(o.w):
            add_text(stdscr, o.y + i, o.x + j, "#")
def background(stdscr, stars):
    scene = [
        "                                                |>>>",
        "                                            _  _|_  _",
        "                                           |;|_|;|_|;|",
        "                                           \\.    .  /",
        "                                            \\:  .  /",
        "                                             ||:   |",
        "                                             ||:.  |",
        "                                             ||:   |",
        "                                             ||: , |",
        "                                             ||: . |",
        "              __                            _||_   |",
        "     ____--`~    '--~~__            __ ----~    ~`---,              ___",
        "-~--~                   ~---__ ,--~'                  ~~----_____-~'   `~----~~",
    ]
    for row, line in enumerate(scene, start=1):
        add_text(stdscr, row, 1, line)
    for star in stars:
        x = 1 + int(star.fx * (WID - 2))
        y = 1 + int(star.fy * (HT - 4))
        add_text(stdscr, y, x, "*")
def add_obs(obstacles, num):
    if num < 5:
        n_x = WID - 2
        o_type = random.randrange(2)
        obstacles.append(Obs(
            x=n_x,
            y=HT - 3,
            w=O_W if o_type == 0 else 2,
            h=O_H,
        ))
def update_obs(obstacles):
    i = 0
    while i < len(obstacles):
        obstacles[i].x -= 1
        obstacles[i].y = HT - 3
        if obstacles[i].x < 1 or obstacles[i].x >= WID - 1:
            obstacles.pop(i)
        else:
            i += 1
def check_collision(d, obstacles):
    if d.jump:
        return 0
    for o in obstacles:
        if (d.x + D_W > o.x and d.x < o.x + o.w
                and d.y + D_H >= o.y):
            return 1
    return 0
def draw_round(stdscr, rnd, name, vision_status):
    """Draw one full frame of the game (also used behind the game-over text)."""
    if curses.has_colors():
        stdscr.bkgd(" ", curses.color_pair(COLORS[rnd.color_idx]))
    background(stdscr, rnd.stars)
    bdr(stdscr)
    dino(stdscr, rnd.dino)
    for obs in rnd.obstacles:
        obstacle(stdscr, obs)
    player_info(stdscr, name, rnd.start_time, rnd.end_time)
def gameover(stdscr, gameover_sound, rnd, name, vision_status):
    """Show GAME OVER and wait. Returns True to replay, False to quit."""
    pygame.mixer.music.stop()
    gameover_sound.play()
    curses.flushinp()
    accept_keys_at = time.time() + 1.0
    while True:
        stdscr.erase()
        update_layout(stdscr)
        draw_round(stdscr, rnd, name, vision_status)
        for row in range(HT // 2 - 2, HT // 2 + 3):
            add_text(stdscr, row, 1, " " * (WID - 2))
        add_centered(
            stdscr, HT // 2 - 1,
            "GAME OVER! You have to Code in C forever!", curses.A_BOLD,
        )
        add_centered(stdscr, HT // 2 + 1, "Press Enter to replay")
        add_centered(stdscr, HT // 2 + 2, "Press q to quit")
        stdscr.refresh()
        ch = stdscr.getch()
        if ch == curses.KEY_RESIZE:
            handle_resize(stdscr)
            continue
        if time.time() < accept_keys_at:
            continue
        if ch in ENTER_KEYS:
            gameover_sound.stop()
            return True
        if ch in (ord("q"), ord("Q")):
            return False
def player_info(stdscr, name, start_time, end_time=None):
    now = end_time if end_time is not None else time.time()
    elapsed_us = int((now - start_time) * 1_000_000)
    sec = elapsed_us // 1_000_000
    msec = (elapsed_us % 1_000_000) // 1000
    lines = (f"Player: {name}", f"Time: {sec}.{msec:03d}")
    x = WID - 2 - max(len(line) for line in lines)
    add_text(stdscr, 1, x, lines[0])
    add_text(stdscr, 2, x, lines[1])
def generate_stars():
    return [Star(random.random(), random.random()) for _ in range(25)]
def initialize_audio():
    pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=4096)
    jump_sound = pygame.mixer.Sound("jump_sound.wav")
    gameover_sound = pygame.mixer.Sound("game_over_sound.wav")
    background_music = "background_music.wav"
    pygame.mixer.music.load(background_music)
    pygame.mixer.music.play(-1)
    return jump_sound, gameover_sound
def enable_dpi_awareness():
    """Use real pixel coordinates when placing windows (Windows only)."""
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
def arrange_windows(camera_title):
    """
    Windows only: split the screen in half. The PowerShell/terminal window
    takes the left half and the YOLO camera window takes the right half.
    Returns True when both windows were placed.
    """
    if not IS_WINDOWS:
        return False
    try:
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
            ]
        kernel32.GetConsoleWindow.restype = wintypes.HWND
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetAncestor.restype = wintypes.HWND
        user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        user32.FindWindowW.restype = wintypes.HWND
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.MonitorFromWindow.restype = wintypes.HANDLE
        user32.GetMonitorInfoW.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(MONITORINFO)
        ]
        user32.GetWindowRect.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.RECT)
        ]
        user32.IsZoomed.argtypes = [wintypes.HWND]
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetWindowPos.argtypes = [
            wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, wintypes.UINT,
        ]
        dwmapi.DwmGetWindowAttribute.argtypes = [
            wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD
        ]
        terminal = kernel32.GetConsoleWindow()
        if not terminal:
            return False
        terminal = user32.GetAncestor(terminal, 3) or terminal
        camera = user32.FindWindowW(None, camera_title)
        if not camera:
            return False
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        monitor = user32.MonitorFromWindow(terminal, 2)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return False
        area = info.rcWork
        left, top = area.left, area.top
        width = area.right - area.left
        height = area.bottom - area.top
        half = width // 2
        def place(hwnd, x, y, w, h):
            if user32.IsZoomed(hwnd) or user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)
            outer = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(outer))
            frame = wintypes.RECT()
            inset = (0, 0, 0, 0)
            if dwmapi.DwmGetWindowAttribute(
                    hwnd, 9, ctypes.byref(frame), ctypes.sizeof(frame)) == 0:
                inset = (
                    frame.left - outer.left, frame.top - outer.top,
                    outer.right - frame.right, outer.bottom - frame.bottom,
                )
            user32.SetWindowPos(
                hwnd, None,
                x - inset[0], y - inset[1],
                w + inset[0] + inset[2], h + inset[1] + inset[3],
                0x0004 | 0x0010,
            )
        place(terminal, left, top, half, height)
        place(camera, left + half, top, width - half, height)
        user32.SetForegroundWindow(terminal)
        return True
    except Exception:
        return False
def fit_to_window(cv2, np, window_name, frame):
    """Letterbox the camera frame into its window so it is never stretched."""
    try:
        _, _, win_w, win_h = cv2.getWindowImageRect(window_name)
    except (cv2.error, AttributeError):
        return frame
    if win_w < 50 or win_h < 50:
        return frame
    height, width = frame.shape[:2]
    scale = min(win_w / width, win_h / height)
    new_w = max(1, int(width * scale))
    new_h = max(1, int(height * scale))
    resized = cv2.resize(frame, (new_w, new_h))
    canvas = np.full((win_h, win_w, 3), 20, dtype=np.uint8)
    x0 = (win_w - new_w) // 2
    y0 = (win_h - new_h) // 2
    canvas[y0:y0 + new_h, x0:x0 + new_w] = resized
    return canvas
class JumpGesture:
    """
    Turns the wrist height (pixels, y grows downwards) into jump triggers.
    A jump fires when the hand rises RAISE_FRAC of the frame height above its
    recent lowest point.
    After that the detector waits until the hand has come back down by
    LOWER_FRAC from its peak (or was lost / held up for a while) and then
    re-arms from wherever the hand is *now*. It never depends on one fixed
    "neutral" position, so every raise-and-lower makes exactly one jump.
    """
    RAISE_FRAC = 0.10
    LOWER_FRAC = 0.025
    DRIFT_FRAC_PER_S = 0.074
    LOST_AFTER_S = 0.5
    REARM_AFTER_S = 0.4
    def __init__(self):
        self.armed = True
        self.smoothed = None
        self.ref = None
        self.peak = None
        self.fired_at = 0.0
        self.last_seen = None
        self.last_time = None
    def update(self, wrist_y, now, frame_height=540):
        """Feed one frame (wrist_y is None if no hand). True = jump now."""
        raise_px = self.RAISE_FRAC * frame_height
        lower_px = self.LOWER_FRAC * frame_height
        drift_px_s = self.DRIFT_FRAC_PER_S * frame_height
        dt = 0.0 if self.last_time is None else min(0.25, now - self.last_time)
        self.last_time = now
        if wrist_y is None:
            if (self.last_seen is not None
                    and now - self.last_seen > self.LOST_AFTER_S):
                self.smoothed = self.ref = self.peak = None
                self.armed = True
            return False
        self.last_seen = now
        if self.smoothed is None:
            self.smoothed = float(wrist_y)
        else:
            self.smoothed = 0.65 * self.smoothed + 0.35 * wrist_y
        y = self.smoothed
        if self.ref is None:
            self.ref = y
        if self.armed:
            self.ref = max(y, self.ref - drift_px_s * dt)
            if self.ref - y >= raise_px:
                self.armed = False
                self.peak = y
                self.fired_at = now
                return True
            return False
        self.peak = min(self.peak, y)
        if (y - self.peak >= lower_px
                or now - self.fired_at >= self.REARM_AFTER_S):
            self.armed = True
            self.ref = y
        return False
def hand_tracking_worker(jump_event, stop_event, vision_status, jumping_event):
    """
    Run YOLO pose inference on the webcam in a separate thread.
    COCO pose keypoints 9 and 10 are the left and right wrists. The wrist
    location is used as an approximate hand-position signal for the gesture.
    """
    try:
        import cv2
        import numpy as np
        from ultralytics import YOLO
    except ImportError as exc:
        vision_status["error"] = (
            "Missing vision packages. Install requirements.txt "
            f"({exc})"
        )
        return
    camera = None
    try:
        vision_status["message"] = "Loading YOLO pose model..."
        model = YOLO(MODEL_NAME)
        camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not camera.isOpened():
            camera.release()
            camera = cv2.VideoCapture(0)
        if not camera.isOpened():
            vision_status["error"] = "Could not open webcam. Check camera access."
            return
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 540)
        try:
            camera.set(getattr(cv2, "CAP_PROP_BUFFERSIZE", 38), 1)
        except Exception:
            pass
        window_name = CAMERA_WINDOW
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, 960, 540)
        gesture = JumpGesture()
        fps = 0.0
        last_tick = time.monotonic()
        jump_flash_started = None
        cam_w = int(camera.get(cv2.CAP_PROP_FRAME_WIDTH))
        cam_h = int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
        vision_status["message"] = (
            f"Show one hand and raise it to jump (camera {cam_w}x{cam_h})"
        )
        layout_tries = 0
        layout_done = False
        while not stop_event.is_set():
            ok, frame = camera.read()
            if not ok:
                vision_status["error"] = "Webcam frame could not be read."
                break
            frame = cv2.flip(frame, 1)
            height, width = frame.shape[:2]
            tick = time.monotonic()
            if tick > last_tick:
                instant = 1.0 / (tick - last_tick)
                fps = instant if fps == 0.0 else 0.9 * fps + 0.1 * instant
            last_tick = tick
            info_text = (
                f"Camera {width}x{height} | {MODEL_NAME} @{INFER_SIZE} "
                f"| {fps:.0f} FPS"
            )
            (info_w, _), _ = cv2.getTextSize(
                info_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1
            )
            cv2.putText(
                frame, info_text, (max(8, width - info_w - 12), 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1,
                cv2.LINE_AA
            )
            results = model.predict(
                frame, imgsz=INFER_SIZE, conf=0.35, verbose=False
            )
            wrist_candidates = []
            if results and results[0].keypoints is not None:
                keypoints = results[0].keypoints
                if keypoints.xy is not None and len(keypoints.xy) > 0:
                    points = keypoints.xy[0].cpu().numpy()
                    confidences = None
                    if keypoints.conf is not None:
                        confidences = keypoints.conf[0].cpu().numpy()
                    for wrist_index in (9, 10):
                        if wrist_index >= len(points):
                            continue
                        confidence = (
                            float(confidences[wrist_index])
                            if confidences is not None else 1.0
                        )
                        x, y = points[wrist_index]
                        if confidence >= 0.35 and x > 0 and y > 0:
                            wrist_candidates.append(
                                (confidence, int(x), int(y))
                            )
            now = time.monotonic()
            if wrist_candidates:
                confidence, wrist_x, wrist_y = min(
                    wrist_candidates, key=lambda item: item[2]
                )
                if gesture.update(wrist_y, now, height):
                    jump_event.set()
                    jump_flash_started = now
                cv2.circle(frame, (wrist_x, wrist_y), 13, (255, 220, 70), 3)
                cv2.circle(frame, (wrist_x, wrist_y), 4, (255, 255, 255), -1)
                label = "HAND DETECTED"
                label_y = max(35, wrist_y - 24)
                (label_w, label_h), _ = cv2.getTextSize(
                    label, cv2.FONT_HERSHEY_DUPLEX, 0.75, 2
                )
                label_x = max(8, min(width - label_w - 8, wrist_x - label_w // 2))
                cv2.rectangle(
                    frame,
                    (label_x - 7, label_y - label_h - 9),
                    (label_x + label_w + 7, label_y + 7),
                    (35, 35, 35),
                    -1,
                )
                cv2.putText(
                    frame, label, (label_x, label_y),
                    cv2.FONT_HERSHEY_DUPLEX, 0.75,
                    (100, 255, 170), 2, cv2.LINE_AA
                )
                status_text = (
                    "RAISE HAND TO JUMP" if gesture.armed
                    else "LOWER HAND TO RESET"
                )
                cv2.putText(
                    frame, status_text, (20, height - 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                    (255, 220, 70), 2, cv2.LINE_AA
                )
            else:
                gesture.update(None, now)
                cv2.putText(
                    frame, "NO HAND / WRIST DETECTED", (20, 42),
                    cv2.FONT_HERSHEY_DUPLEX, 0.75,
                    (80, 150, 255), 2, cv2.LINE_AA
                )
                cv2.putText(
                    frame, "Show your upper body and one visible hand",
                    (20, height - 22), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (220, 220, 220), 1, cv2.LINE_AA
                )
            if jump_flash_started is not None:
                progress = (time.monotonic() - jump_flash_started) / 0.5
                if progress >= 1.0:
                    jump_flash_started = None
                else:
                    alpha = max(0.0, 1.0 - progress)
                    overlay = frame.copy()
                    center = (width // 2, height // 2)
                    radius = int(35 + 155 * progress)
                    cv2.circle(
                        overlay, center, radius, (255, 225, 90),
                        max(2, int(9 * alpha)), cv2.LINE_AA
                    )
                    cv2.circle(
                        overlay, center, max(8, radius - 20),
                        (255, 170, 55), max(1, int(3 * alpha)),
                        cv2.LINE_AA
                    )
                    jump_text = "JUMP!"
                    font = cv2.FONT_HERSHEY_DUPLEX
                    scale = 2.1
                    thickness = 5
                    (text_w, text_h), _ = cv2.getTextSize(
                        jump_text, font, scale, thickness
                    )
                    text_x = (width - text_w) // 2
                    text_y = (height + text_h) // 2
                    cv2.putText(
                        overlay, jump_text, (text_x, text_y),
                        font, scale, (255, 235, 130),
                        thickness, cv2.LINE_AA
                    )
                    frame = cv2.addWeighted(
                        overlay, alpha, frame, 1.0 - alpha, 0
                    )
            cv2.imshow(window_name, fit_to_window(cv2, np, window_name, frame))
            key = cv2.waitKey(1) & 0xFF
            if IS_WINDOWS and not layout_done and layout_tries < 30:
                layout_tries += 1
                layout_done = arrange_windows(window_name)
            if not vision_status["ready"] and (
                    not IS_WINDOWS or layout_done or layout_tries >= 30):
                vision_status["ready"] = True
            if key in (ord("q"), 27):
                stop_event.set()
                break
    except Exception as exc:
        vision_status["error"] = f"Vision system error: {exc}"
    finally:
        if camera is not None:
            camera.release()
        try:
            import cv2
            cv2.destroyAllWindows()
        except Exception:
            pass
        vision_status["message"] = "Hand tracking stopped"
def start_hand_tracking():
    """Start the webcam/YOLO worker and return its shared controls."""
    jump_event = threading.Event()
    stop_event = threading.Event()
    vision_status = {
        "message": "Starting hand tracking...", "error": "", "ready": False,
    }
    jumping_event = threading.Event()
    worker = threading.Thread(
        target=hand_tracking_worker,
        args=(jump_event, stop_event, vision_status, jumping_event),
        daemon=True,
        name="YOLO-Hand-Tracking",
    )
    worker.start()
    return jump_event, stop_event, vision_status, jumping_event, worker
def loading_screen(stdscr, vision_status, vision_thread):
    """
    Wait until YOLO and the camera are ready. Returns True when the game
    should start and False if the player quit. If hand tracking fails the
    player may continue with the keyboard only.
    """
    spinner = "|/-\\"
    tick = 0
    stdscr.timeout(100)
    while True:
        failed = not vision_status["ready"] and (
            vision_status["error"] or not vision_thread.is_alive()
        )
        stdscr.erase()
        update_layout(stdscr)
        bdr(stdscr)
        if failed:
            error = vision_status["error"] or vision_status["message"]
            add_centered(stdscr, HT // 2 - 2, "Hand tracking is not available",
                         curses.A_BOLD)
            add_centered(stdscr, HT // 2, error[:WID - 4])
            add_centered(stdscr, HT // 2 + 2,
                         "Press Enter to play with the keyboard (Space)")
            add_centered(stdscr, HT // 2 + 3, "Press q to quit")
        else:
            add_centered(
                stdscr, HT // 2 - 1,
                "Loading YOLO hand tracking... " + spinner[tick % 4],
                curses.A_BOLD,
            )
            add_centered(stdscr, HT // 2 + 1,
                         "The game starts as soon as everything is ready.")
            add_centered(stdscr, HT // 2 + 3, vision_status["message"][:WID - 4])
        stdscr.refresh()
        if vision_status["ready"]:
            curses.flushinp()
            return True
        ch = stdscr.getch()
        tick += 1
        if ch == curses.KEY_RESIZE:
            handle_resize(stdscr)
        elif ch in (ord("q"), ord("Q")):
            return False
        elif failed and ch in ENTER_KEYS:
            return True
def play_round(stdscr, name, jump_event, jumping_event, vision_status,
               jump_sound):
    """Play one round. Returns (round, "dead") or (round, "quit")."""
    rnd = Round()
    d = rnd.dino
    jump_event.clear()
    jumping_event.clear()
    gesture_until = 0.0
    while True:
        stdscr.clear()
        update_layout(stdscr)
        d.set_ground(HT - 3)
        elapsed_secs = int(time.time() - rnd.start_time)
        if elapsed_secs - rnd.last_color_time >= 1:
            rnd.color_idx = (rnd.color_idx + 1) % 7
            rnd.last_color_time = elapsed_secs
        draw_round(stdscr, rnd, name, vision_status)
        ch = stdscr.getch()
        if ch == curses.KEY_RESIZE:
            handle_resize(stdscr)
            continue
        if ch == ord("q"):
            return rnd, "quit"
        if jump_event.is_set():
            jump_event.clear()
            gesture_until = time.time() + GESTURE_BUFFER_S
        gesture_jump = time.time() < gesture_until
        if (ch == ord(" ") or gesture_jump) and not d.jump:
            gesture_until = 0.0
            current_time = time.time()
            d.jump = 1
            d.j_height = 0
            d.jump_start = current_time
            d.peak_time = 0
            jumping_event.set()
            pygame.mixer.find_channel(True).play(jump_sound)
        if d.jump:
            jump_time = time.time()
            jump_duration_us = int((jump_time - d.jump_start) * 1_000_000)
            if jump_duration_us < 125000:
                d.j_height = int(jump_duration_us / 125000 * J_H)
                d.y = d.orig_y - d.j_height
            elif jump_duration_us < 900000:
                if d.peak_time == 0:
                    d.peak_time = time.time()
                d.j_height = J_H
                d.y = d.orig_y - d.j_height
            else:
                descent_duration_us = jump_duration_us - 900000
                if descent_duration_us < 125000:
                    d.j_height = int(
                        (125000 - descent_duration_us) / 125000 * J_H
                    )
                    d.y = d.orig_y - d.j_height
                else:
                    d.jump = 0
                    d.j_height = 0
                    d.y = d.orig_y
                    jumping_event.clear()
        update_obs(rnd.obstacles)
        rnd.spawn_in -= 1
        if rnd.spawn_in <= 0:
            add_obs(rnd.obstacles, len(rnd.obstacles))
            rnd.spawn_in = random.randint(MIN_OBS_GAP, MAX_OBS_GAP)
        if not d.jump and check_collision(d, rnd.obstacles):
            rnd.end_time = time.time()
            return rnd, "dead"
        stdscr.refresh()
def game(stdscr):
    try:
        pygame.mixer.pre_init(22050, -16, 2, 4096)
        pygame.init()
        jump_sound, gameover_sound = initialize_audio()
    except pygame.error as exc:
        raise RuntimeError(f"Audio initialization/loading failed: {exc}") from exc
    random.seed()
    curses.noecho()
    curses.curs_set(0)
    update_layout(stdscr)
    if curses.has_colors():
        curses.start_color()
        curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(4, curses.COLOR_BLUE, curses.COLOR_BLACK)
        curses.init_pair(5, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
        curses.init_pair(6, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(7, curses.COLOR_WHITE, curses.COLOR_BLACK)
    add_centered(stdscr, HT // 2 - 4, "Welcome to No more 'C' !", curses.A_BOLD)
    add_centered(
        stdscr, HT // 2 - 3,
        "Your mission is to escape the '#'s that make your life hell.",
    )
    add_centered(
        stdscr, HT // 2 - 2,
        "If you lose, you'll have to #include C in every moment of your life!",
    )
    field_width = 15
    field_x = (WID - field_width) // 2
    add_centered(stdscr, HT // 2 - 1, "Enter your name:")
    add_text(stdscr, HT // 2, field_x, "_" * field_width)
    stdscr.move(HT // 2 + OFFSET_Y, field_x + OFFSET_X)
    stdscr.refresh()
    stdscr.timeout(-1)
    curses.echo()
    try:
        name = stdscr.getstr(
            HT // 2 + OFFSET_Y,
            field_x + OFFSET_X,
            field_width,
        ).decode("utf-8", errors="replace")
    finally:
        curses.noecho()
        stdscr.timeout(100)
    stdscr.clear()
    add_centered(stdscr, HT // 2 - 2, "Press Enter to start...")
    add_centered(
        stdscr, HT // 2 - 1,
        "Raise your hand or press Space to jump. Press q to quit.",
    )
    stdscr.refresh()
    while True:
        ch = stdscr.getch()
        if ch in ENTER_KEYS:
            break
    jump_event, vision_stop, vision_status, jumping_event, vision_thread = start_hand_tracking()
    try:
        if not loading_screen(stdscr, vision_status, vision_thread):
            return
        while True:
            rnd, outcome = play_round(
                stdscr, name, jump_event, jumping_event, vision_status,
                jump_sound,
            )
            if outcome == "quit":
                break
            if not gameover(stdscr, gameover_sound, rnd, name, vision_status):
                break
            pygame.mixer.music.play(-1)
    finally:
        vision_stop.set()
        if vision_thread.is_alive():
            vision_thread.join(timeout=2.0)
        pygame.mixer.music.stop()
        pygame.mixer.quit()
        pygame.quit()
def main():
    enable_dpi_awareness()
    try:
        curses.wrapper(game)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
