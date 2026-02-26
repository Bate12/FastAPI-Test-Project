import customtkinter as ctk
import requests
import json
import threading
import time
import platform

try:
    if platform.system() == "Windows":
        import winsound
        SOUND_ENABLED = True
    else:
        SOUND_ENABLED = False
except ImportError:
    SOUND_ENABLED = False

API_BASE_URL = "http://127.0.0.1:8000"

class XamppApiGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("XAMPP API GUI Client")
        self.geometry("1280x720")
        self.minsize(900, 600)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        try:
            self.iconbitmap("logo.ico")
        except Exception:
            pass

        # ---------------------------------------------------------------
        # ONE StringVar per logical input field — shared across ALL tab
        # and the method-specific tab. Entries are just views into these.
        # ---------------------------------------------------------------
        self.var_name        = ctk.StringVar()
        self.var_friends     = ctk.StringVar()
        self.var_limit       = ctk.StringVar()
        self.var_get_id      = ctk.StringVar()
        self.var_friends_id  = ctk.StringVar()
        self.var_put_id      = ctk.StringVar()
        self.var_put_name    = ctk.StringVar()
        self.var_del_id      = ctk.StringVar()

        self.api_endpoints = [
            {"method": "POST",   "path": "/users/create",          "tab": "POST",   "builder": self.build_post_user_create},
            {"method": "GET",    "path": "/users",                  "tab": "GET",    "builder": self.build_get_users},
            {"method": "GET",    "path": "/users/{id}",             "tab": "GET",    "builder": self.build_get_user_by_id},
            {"method": "GET",    "path": "/users/get_friends/{id}", "tab": "GET",    "builder": self.build_get_friends},
            {"method": "PUT",    "path": "/users/{id}",             "tab": "PUT",    "builder": self.build_put_user},
            {"method": "DELETE", "path": "/users/{id}",             "tab": "DELETE", "builder": self.build_delete_user},
        ]

        # Debounce & abort state
        self._search_debounce_id = None
        self._render_version     = 0
        self._spinner_after_id   = None
        self._spinner_widget     = None

        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.build_top_bar()

        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.grid(row=1, column=0, sticky="nsew", padx=20, pady=(10, 20))
        self.main_container.grid_columnconfigure(0, weight=3, uniform="split")
        self.main_container.grid_columnconfigure(1, weight=2, uniform="split")
        self.main_container.grid_rowconfigure(0, weight=1)

        self.tabs_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.tabs_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        self.build_console_panel()

        # Permanent tabview — never destroyed, never rebuilt
        self.ALL_TABS = ["ALL", "GET", "POST", "PUT", "DELETE"]
        self.tabview = ctk.CTkTabview(self.tabs_frame)
        self.tabview.pack(fill="both", expand=True)
        self.scroll_frames = {}
        for tab_name in self.ALL_TABS:
            self.tabview.add(tab_name)
            sf = ctk.CTkScrollableFrame(self.tabview.tab(tab_name), fg_color="transparent")
            sf.pack(fill="both", expand=True)
            self.scroll_frames[tab_name] = sf

        self.empty_labels = {}
        self.render_endpoints(self.api_endpoints)

        self.intro_frame = ctk.CTkFrame(self, fg_color="#111111", corner_radius=0)
        self.intro_frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.cube_label = ctk.CTkLabel(self.intro_frame, text="", font=("Courier", 24, "bold"), text_color="#00ffcc")
        self.cube_label.place(relx=0.5, rely=0.5, anchor="center")
        self.after(100, self.animate_intro)

    # =========================================================================
    # AUDIO & ANIMATION HELPERS
    # =========================================================================

    def play_hover_sound(self):
        if SOUND_ENABLED:
            threading.Thread(target=lambda: winsound.Beep(2000, 10), daemon=True).start()

    def play_click_sound(self):
        if SOUND_ENABLED:
            threading.Thread(target=lambda: winsound.Beep(1500, 30), daemon=True).start()

    def bind_interactive_animations(self, widget, hover_color="#00e5ff"):
        original_color = widget.cget("border_color")
        def on_enter(e):
            self.play_hover_sound()
            widget.configure(border_width=2, border_color=hover_color)
        def on_leave(e):
            widget.configure(border_width=0, border_color=original_color)
        def on_click(e):
            self.play_click_sound()
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)
        widget.bind("<Button-1>", on_click, add="+")

    # =========================================================================
    # SPINNER  (pure self.after(), no time.sleep)
    # =========================================================================

    def _start_spinner(self):
        self._stop_spinner()
        self._spinner_widget = ctk.CTkLabel(
            self.tabs_frame, text="",
            font=("Courier", 28, "bold"), text_color="#00ffcc"
        )
        self._spinner_widget.place(relx=0.5, rely=0.5, anchor="center")
        frames = ["|", "/", "—", "\\"]
        self._spinner_frame_idx = 0

        def _tick():
            try:
                if self._spinner_widget is None:
                    return
                char = frames[self._spinner_frame_idx % len(frames)]
                self._spinner_widget.configure(text=f"  {char}  Loading...")
                self._spinner_frame_idx += 1
                self._spinner_after_id = self.after(120, _tick)
            except Exception:
                pass
        _tick()

    def _stop_spinner(self):
        if self._spinner_after_id is not None:
            try:
                self.after_cancel(self._spinner_after_id)
            except Exception:
                pass
            self._spinner_after_id = None
        if self._spinner_widget is not None:
            try:
                self._spinner_widget.destroy()
            except Exception:
                pass
            self._spinner_widget = None

    # =========================================================================
    # SEARCH — DEBOUNCE + ABORT
    # =========================================================================

    def on_search_typing(self, event=None):
        if self._search_debounce_id is not None:
            self.after_cancel(self._search_debounce_id)
            self._search_debounce_id = None
        self._render_version += 1
        self._search_debounce_id = self.after(300, self._execute_search)

    def _execute_search(self):
        self._search_debounce_id = None
        query = self.search_entry.get().lower()
        filtered = [
            ep for ep in self.api_endpoints
            if query in ep["path"].lower() or query in ep["method"].lower()
        ]
        self.render_endpoints(filtered)

    # =========================================================================
    # RENDER ENDPOINTS — only content is rebuilt, tabview stays permanent
    # =========================================================================

    def render_endpoints(self, endpoints_list):
        my_version = self._render_version

        # Clear all scroll frame contents
        for sf in self.scroll_frames.values():
            for child in sf.winfo_children():
                child.destroy()
        for lbl in self.empty_labels.values():
            if lbl:
                try:
                    lbl.destroy()
                except Exception:
                    pass
        self.empty_labels = {}

        self._start_spinner()

        if not endpoints_list:
            def _show_empty():
                if self._render_version != my_version:
                    return
                self._stop_spinner()
                for tab_name in self.ALL_TABS:
                    lbl = ctk.CTkLabel(
                        self.scroll_frames[tab_name],
                        text="❌ No endpoints found",
                        font=("Arial", 18, "bold"),
                        text_color="#ff4444"
                    )
                    lbl.pack(expand=True, pady=40)
                    self.empty_labels[tab_name] = lbl
            self.after(0, _show_empty)
            return

        work_items = []
        color_toggle = {tab: True for tab in self.ALL_TABS}
        for tab_name in self.ALL_TABS:
            tab_eps = endpoints_list if tab_name == "ALL" else [ep for ep in endpoints_list if ep["tab"] == tab_name]
            for ep in tab_eps:
                bg = "#2A2A2A" if color_toggle[tab_name] else "#363636"
                color_toggle[tab_name] = not color_toggle[tab_name]
                work_items.append((tab_name, ep, bg))

        def _build_next(idx):
            if self._render_version != my_version:
                self._stop_spinner()
                for sf in self.scroll_frames.values():
                    for child in sf.winfo_children():
                        child.destroy()
                return
            if idx >= len(work_items):
                self._stop_spinner()
                return
            tab_name, ep, bg_color = work_items[idx]
            ep["builder"](self.scroll_frames[tab_name], bg_color)
            self.after(0, lambda: _build_next(idx + 1))

        self.after(30, lambda: _build_next(0))

    # =========================================================================
    # UI BUILDERS
    # =========================================================================

    def build_top_bar(self):
        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        top_frame.grid_columnconfigure(0, weight=8)
        top_frame.grid_columnconfigure(1, weight=2)

        self.search_entry = ctk.CTkEntry(
            top_frame, height=40,
            placeholder_text="🔍 Search endpoints (e.g., '/users', 'POST')...",
            font=("Arial", 14)
        )
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.search_entry.bind("<KeyRelease>", self.on_search_typing)

        self.reload_btn = ctk.CTkButton(
            top_frame, text="🔄 Reload", height=40,
            font=("Arial", 14, "bold"), command=self.trigger_reload
        )
        self.reload_btn.grid(row=0, column=1, sticky="ew")
        self.bind_interactive_animations(self.reload_btn, hover_color="#ffbb00")

    def build_console_panel(self):
        console_container = ctk.CTkFrame(self.main_container)
        console_container.grid(row=0, column=1, sticky="nsew")
        console_container.grid_rowconfigure(1, weight=1)
        console_container.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            console_container, text="Terminal Output",
            font=("Courier", 16, "bold"), text_color="#55ff55"
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 0))

        self.console_box = ctk.CTkTextbox(console_container, font=("Consolas", 12), wrap="word")
        self.console_box.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        self.console_box.configure(state="disabled")

    # --- SEARCH & RELOAD ---

    def trigger_reload(self):
        self.play_click_sound()
        self.reload_btn.configure(state="disabled", text="⏳ Loading...")

        def loading_task():
            self.console_box.configure(state="normal")
            self.console_box.insert("end", "\n🔄 Fetching endpoints ")
            for _ in range(5):
                time.sleep(0.2)
                self.console_box.insert("end", ".")
                self.console_box.see("end")
            self.console_box.insert("end", "\n")
            self.console_box.configure(state="disabled")

            def _finish():
                self.search_entry.delete(0, "end")
                self._render_version += 1
                self.render_endpoints(self.api_endpoints)
                self.gui_print("✅ Endpoints reloaded successfully.")
                self.reload_btn.configure(state="normal", text="🔄 Reload")

            self.after(0, _finish)

        threading.Thread(target=loading_task, daemon=True).start()

    # --- BLOCK FRAME ---

    def create_block_frame(self, parent, method, path, desc, bg_color, execute_cmd):
        frame = ctk.CTkFrame(parent, fg_color=bg_color, corner_radius=10)
        frame.pack(fill="x", padx=5, pady=8)

        method_colors = {"GET": "#1a73e8", "POST": "#2fa572", "PUT": "#d97706", "DELETE": "#ff4444"}
        m_color = method_colors.get(method, "#00e5ff")

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(10, 5))

        ctk.CTkLabel(header, text=method, font=("Courier", 14, "bold"),
                     text_color=m_color, width=60, anchor="w").pack(side="left")
        ctk.CTkLabel(header, text=path, font=("Courier", 14, "bold"),
                     text_color="#ffffff").pack(side="left", padx=10)

        btn = ctk.CTkButton(
            header, text="▶ Exec", width=65, height=26,
            font=("Arial", 12, "bold"), fg_color=m_color, command=execute_cmd
        )
        btn.pack(side="right")
        self.bind_interactive_animations(btn, hover_color="#ffffff")

        ctk.CTkLabel(frame, text=desc, font=("Arial", 11, "italic"),
                     text_color="#aaaaaa").pack(anchor="w", padx=15, pady=(0, 5))

        return frame

    # --- ENDPOINT BLOCK BUILDERS ---
    # Each builder creates CTkEntry widgets bound to the shared StringVar.
    # It doesn't matter how many times these are rebuilt — the vars hold the values.

    def _make_entry(self, parent, textvariable, placeholder, execute_cmd, pack_kwargs):
        """Create a CTkEntry bound to a StringVar. Pressing Enter fires execute_cmd."""
        entry = ctk.CTkEntry(parent, textvariable=textvariable, placeholder_text=placeholder)
        entry.bind("<Return>", lambda e: execute_cmd())
        entry.pack(**pack_kwargs)
        return entry

    def build_post_user_create(self, parent, bg_color):
        frame = self.create_block_frame(
            parent, "POST", "/users/create", "Create a new user with friends",
            bg_color, self.post_user_create
        )
        self._make_entry(frame, self.var_name,    "Name (e.g. John Pork)",       self.post_user_create, dict(fill="x", padx=15, pady=5))
        self._make_entry(frame, self.var_friends, "Friends IDs (e.g. 1, 2, 3)",  self.post_user_create, dict(fill="x", padx=15, pady=(5, 15)))

    def build_get_users(self, parent, bg_color):
        frame = self.create_block_frame(
            parent, "GET", "/users", "Fetch all users (or apply limit)",
            bg_color, self.get_users
        )
        self._make_entry(frame, self.var_limit, "Limit (optional, integer)", self.get_users, dict(fill="x", padx=15, pady=(5, 15)))

    def build_get_user_by_id(self, parent, bg_color):
        frame = self.create_block_frame(
            parent, "GET", "/users/{id}", "Fetch specific user by ID",
            bg_color, self.get_user_by_id
        )
        self._make_entry(frame, self.var_get_id, "User ID", self.get_user_by_id, dict(fill="x", padx=15, pady=(5, 15)))

    def build_get_friends(self, parent, bg_color):
        frame = self.create_block_frame(
            parent, "GET", "/users/get_friends/{id}", "Fetch friends list array by User ID",
            bg_color, self.get_friends
        )
        self._make_entry(frame, self.var_friends_id, "User ID", self.get_friends, dict(fill="x", padx=15, pady=(5, 15)))

    def build_put_user(self, parent, bg_color):
        frame = self.create_block_frame(
            parent, "PUT", "/users/{id}", "Update an existing user's name",
            bg_color, self.put_user
        )
        self._make_entry(frame, self.var_put_id,   "User ID",  self.put_user, dict(fill="x", padx=15, pady=5))
        self._make_entry(frame, self.var_put_name, "New Name", self.put_user, dict(fill="x", padx=15, pady=(5, 15)))

    def build_delete_user(self, parent, bg_color):
        frame = self.create_block_frame(
            parent, "DELETE", "/users/{id}", "Permanently remove a user",
            bg_color, self.delete_user
        )
        self._make_entry(frame, self.var_del_id, "User ID", self.delete_user, dict(fill="x", padx=15, pady=(5, 15)))

    # =========================================================================
    # CORE UTILS
    # =========================================================================

    def animate_intro(self):
        frames = [
            (".", 10), ("o", 20), ("O", 40), ("■", 80),
            ("⧄", 120), ("⧅", 160), ("⧆", 200), ("■", 250),
            ("▃", 150), ("_", 100), ("* SPLAT *", 60)
        ]

        def play_animation():
            for char, size in frames:
                self.cube_label.configure(text=char, font=("Courier", size, "bold"))
                if char == "* SPLAT *":
                    self.cube_label.configure(text_color="#ff4444")
                    self.play_click_sound()
                time.sleep(0.08)
            time.sleep(0.5)
            self.intro_frame.destroy()
            self.gui_print("🚀 Intro finished. API GUI Client Ready.")
            self.gui_print(f"🔗 Target Server: {API_BASE_URL}")

        threading.Thread(target=play_animation, daemon=True).start()

    def gui_print(self, text: str, is_warning=False):
        self.console_box.configure(state="normal")
        tag_name = "normal"
        if is_warning:
            tag_name = "warning"
            self.console_box.tag_config(tag_name, foreground="#fbbf24")
        elif "success" in text.lower() or "✅" in text:
            tag_name = "success"
            self.console_box.tag_config(tag_name, foreground="#4ade80")
        elif "error" in text.lower() or "❌" in text or "fail" in text.lower():
            tag_name = "error"
            self.console_box.tag_config(tag_name, foreground="#ff4444")
        elif any(m in text.lower() for m in ["post", "get", "put", "delete"]) or "→" in text:
            tag_name = "info"
            self.console_box.tag_config(tag_name, foreground="#A020F0")
        elif any(e in text for e in ["🚀", "🔗", "🔄"]):
            tag_name = "highlight"
            self.console_box.tag_config(tag_name, foreground="#00ffcc")

        start_idx = self.console_box.index("end-1c")
        self.console_box.insert("end", text + "\n")
        end_idx = self.console_box.index("end-1c")
        if tag_name != "normal":
            self.console_box.tag_add(tag_name, start_idx, end_idx)
        self.console_box.see("end")
        self.console_box.configure(state="disabled")

    def make_request(self, method, endpoint, **kwargs):
        self.gui_print("-" * 50)
        self.gui_print(f"📡 Request: {method.upper()} {endpoint}")
        url = f"{API_BASE_URL}{endpoint}"
        try:
            response = requests.request(method, url, **kwargs)
            try:
                data = response.json()
                formatted_data = json.dumps(data, indent=4, ensure_ascii=False)
            except Exception:
                formatted_data = response.text
            if response.status_code in [200, 201]:
                self.gui_print(f"✅ Success ({response.status_code}):\n{formatted_data}")
            else:
                self.gui_print(f"❌ Error ({response.status_code}):\n{formatted_data}")
        except requests.exceptions.ConnectionError:
            self.gui_print("❌ CONNECTION ERROR: Is the FastAPI server running?")
        except Exception as e:
            self.gui_print(f"❌ UNEXPECTED ERROR: {e}")

    # =========================================================================
    # API ENDPOINT EXECUTORS — read from StringVars, never from self.input_*
    # =========================================================================

    def post_user_create(self):
        name = self.var_name.get().strip() or "John Pork"
        friends_str = self.var_friends.get().strip()
        friends = []
        if friends_str:
            try:
                friends = [int(x.strip()) for x in friends_str.split(",") if x.strip().isdigit()]
            except ValueError:
                self.gui_print("❌ Invalid friends input. Use comma-separated integers.")
                return
        payload = {"name": name, "friends": friends}
        threading.Thread(
            target=self.make_request, args=("POST", "/users/create"),
            kwargs={"json": payload}
        ).start()

    def get_users(self):
        limit_str = self.var_limit.get().strip()
        params = {}
        if limit_str:
            if not limit_str.isdigit():
                self.gui_print("❌ Limit must be an integer.")
                return
            params["limit"] = int(limit_str)
        threading.Thread(
            target=self.make_request, args=("GET", "/users"),
            kwargs={"params": params}
        ).start()

    def get_user_by_id(self):
        uid = self.var_get_id.get().strip()
        if not uid.isdigit():
            self.gui_print("❌ User ID must be an integer.")
            return
        threading.Thread(target=self.make_request, args=("GET", f"/users/{uid}")).start()

    def get_friends(self):
        uid = self.var_friends_id.get().strip()
        if not uid.isdigit():
            self.gui_print("❌ User ID must be an integer.")
            return
        threading.Thread(target=self.make_request, args=("GET", f"/users/get_friends/{uid}")).start()

    def put_user(self):
        uid = self.var_put_id.get().strip()
        new_name = self.var_put_name.get().strip()
        if not uid.isdigit() or not new_name:
            self.gui_print("❌ Invalid input. Ensure ID is an integer and Name is not empty.")
            return
        params = {"new_name": new_name}
        threading.Thread(
            target=self.make_request, args=("PUT", f"/users/{uid}"),
            kwargs={"params": params}
        ).start()

    def delete_user(self):
        uid = self.var_del_id.get().strip()
        if not uid.isdigit():
            self.gui_print("❌ User ID must be an integer.")
            return
        threading.Thread(target=self.make_request, args=("DELETE", f"/users/{uid}")).start()


if __name__ == "__main__":
    app = XamppApiGUI()
    app.mainloop()
