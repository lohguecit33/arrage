import win32gui
import win32con
import win32process
import win32api
import psutil
import json
import time
import os
import ctypes
from ctypes import wintypes, Structure, POINTER, byref

# Windows API Constants
WM_SIZING = 0x0214
WM_SIZE = 0x0005
SW_SHOWNOACTIVATE = 4
SWP_NOACTIVATE = 0x0010
SWP_NOZORDER = 0x0004
SWP_NOSENDCHANGING = 0x0400

class RECT(Structure):
    _fields_ = [
        ('left', ctypes.c_long),
        ('top', ctypes.c_long),
        ('right', ctypes.c_long),
        ('bottom', ctypes.c_long)
    ]

class RobloxWindowManager:
    def __init__(self, config_file="config.json"):
        self.config_file = config_file
        self.load_config()
        self.user32 = ctypes.windll.user32
        self.dwmapi = ctypes.windll.dwmapi
        
    def load_config(self):
        """Memuat konfigurasi dari file JSON"""
        default_config = {
            "Windows Per Rows": 4,
            "Fixed Size": "530x400",
            "Update Interval": 60
        }
        
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as f:
                loaded_config = json.load(f)
            
            # Merge dengan default config untuk backward compatibility
            self.config = default_config.copy()
            self.config.update(loaded_config)
            
            # Hapus key yang tidak diperlukan lagi
            self.config.pop("Target Process", None)
            self.config.pop("Aggressive Mode", None)
            
            # Save ulang dengan config yang sudah dibersihkan
            self.save_config()
        else:
            self.config = default_config
            self.save_config()
        
        width, height = self.config["Fixed Size"].split("x")
        self.window_width = int(width)
        self.window_height = int(height)
        self.windows_per_row = self.config["Windows Per Rows"]
        self.update_interval = self.config["Update Interval"]
        self.target_process = "RobloxPlayerBeta.exe"
        self.aggressive_mode = True
    
    def save_config(self):
        """Menyimpan konfigurasi ke file JSON"""
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=4)
    
    def get_process_name(self, hwnd):
        """Mendapatkan nama proses dari window handle"""
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process = psutil.Process(pid)
            return process.name()
        except:
            return None
    
    def get_roblox_windows(self):
        """Mencari semua jendela Roblox yang terbuka berdasarkan nama proses"""
        windows = []
        
        def enum_callback(hwnd, results):
            if win32gui.IsWindowVisible(hwnd):
                process_name = self.get_process_name(hwnd)
                if process_name and process_name.lower() == self.target_process.lower():
                    window_title = win32gui.GetWindowText(hwnd)
                    if window_title:
                        results.append((hwnd, window_title, process_name))
        
        win32gui.EnumWindows(enum_callback, windows)
        return windows
    
    def calculate_window_rect(self, width, height, hwnd):
        """Menghitung window rect yang diperlukan untuk mendapatkan client area yang diinginkan"""
        try:
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            
            rect = RECT()
            rect.left = 0
            rect.top = 0
            rect.right = width
            rect.bottom = height
            
            # AdjustWindowRectEx untuk menghitung ukuran window yang tepat
            has_menu = False
            self.user32.AdjustWindowRectEx(
                byref(rect),
                style,
                has_menu,
                ex_style
            )
            
            calculated_width = rect.right - rect.left
            calculated_height = rect.bottom - rect.top
            
            return calculated_width, calculated_height
        except:
            return width, height
    
    def ultra_force_resize(self, hwnd, x, y, width, height):
        """Ultra aggressive resize dengan berbagai teknik"""
        try:
            # 1. Restore dari minimize/maximize
            placement = win32gui.GetWindowPlacement(hwnd)
            if placement[1] != win32con.SW_SHOWNORMAL:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.1)
            
            # 2. Hitung ukuran window yang benar (termasuk border dan titlebar)
            calc_width, calc_height = self.calculate_window_rect(width, height, hwnd)
            
            # 3. Method 1: Direct MoveWindow (paling simple dan kadang berhasil)
            win32gui.MoveWindow(hwnd, x, y, calc_width, calc_height, True)
            time.sleep(0.02)
            
            # 4. Method 2: SetWindowPos dengan berbagai kombinasi flags
            flags_combinations = [
                win32con.SWP_SHOWWINDOW,
                win32con.SWP_SHOWWINDOW | win32con.SWP_FRAMECHANGED,
                win32con.SWP_NOACTIVATE | win32con.SWP_NOZORDER,
                SWP_NOSENDCHANGING | win32con.SWP_SHOWWINDOW,
            ]
            
            for flags in flags_combinations:
                self.user32.SetWindowPos(
                    hwnd, None, x, y, calc_width, calc_height, flags
                )
                time.sleep(0.01)
            
            # 5. Method 3: Langsung manipulasi dengan BeginDeferWindowPos
            hdwp = self.user32.BeginDeferWindowPos(1)
            if hdwp:
                hdwp = self.user32.DeferWindowPos(
                    hdwp, hwnd, None,
                    x, y, calc_width, calc_height,
                    win32con.SWP_SHOWWINDOW | win32con.SWP_NOZORDER
                )
                if hdwp:
                    self.user32.EndDeferWindowPos(hdwp)
            
            time.sleep(0.02)
            
            # 6. Method 4: Force dengan MoveWindow lagi (untuk memastikan)
            win32gui.MoveWindow(hwnd, x, y, calc_width, calc_height, True)
            
            # 7. Force redraw
            win32gui.RedrawWindow(
                hwnd, None, None,
                win32con.RDW_INVALIDATE | win32con.RDW_UPDATENOW | win32con.RDW_ALLCHILDREN
            )
            
            return True
            
        except:
            return False
    
    def continuous_force_resize(self, hwnd, x, y, width, height, attempts=10):
        """Continuous forcing resize sampai berhasil atau max attempts"""
        try:
            calc_width, calc_height = self.calculate_window_rect(width, height, hwnd)
            
            for i in range(attempts):
                try:
                    # Cek ukuran saat ini
                    rect = win32gui.GetWindowRect(hwnd)
                    current_width = rect[2] - rect[0]
                    current_height = rect[3] - rect[1]
                    current_x = rect[0]
                    current_y = rect[1]
                    
                    # Hitung selisih
                    diff_width = abs(current_width - calc_width)
                    diff_height = abs(current_height - calc_height)
                    diff_x = abs(current_x - x)
                    diff_y = abs(current_y - y)
                    
                    # Jika sudah dekat dengan target, stop
                    if diff_width <= 5 and diff_height <= 5 and diff_x <= 5 and diff_y <= 5:
                        return True
                    
                    # Force resize
                    win32gui.MoveWindow(hwnd, x, y, calc_width, calc_height, True)
                    self.user32.SetWindowPos(
                        hwnd, None, x, y, calc_width, calc_height,
                        SWP_NOSENDCHANGING | win32con.SWP_SHOWWINDOW
                    )
                    
                    time.sleep(0.05)
                except:
                    # Window mungkin sudah ditutup
                    return False
            
            return False
        except:
            return False
    
    def resize_and_arrange_windows(self):
        """Mengatur ukuran dan posisi semua jendela Roblox"""
        windows = self.get_roblox_windows()
        
        if not windows:
            return
        
        title_bar_height = 30
        
        for index, (hwnd, title, process) in enumerate(windows):
            try:
                # Cek apakah window masih valid
                if not win32gui.IsWindow(hwnd):
                    continue
                
                row = index // self.windows_per_row
                col = index % self.windows_per_row
                
                x = col * self.window_width
                y = row * (self.window_height + title_bar_height)
                
                # Ultra force resize
                self.continuous_force_resize(hwnd, x, y, self.window_width, self.window_height, attempts=15)
            except:
                # Skip jika window error
                continue
    
    def run(self):
        """Menjalankan loop utama"""
        try:
            while True:
                self.resize_and_arrange_windows()
                time.sleep(self.update_interval)
        except KeyboardInterrupt:
            pass

def main():
    manager = RobloxWindowManager("config.json")
    manager.run()

if __name__ == "__main__":
    main()