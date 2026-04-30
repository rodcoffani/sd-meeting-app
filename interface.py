import tkinter as tk
from tkinter import messagebox
import threading
import cv2
import numpy as np
import pyaudio
import yaml
from PIL import Image, ImageTk

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)


class MeetingInterface:
    def __init__(self, root, client_controller):
        self.root = root
        self.root.title("SD Meeting App")
        self.root.geometry("800x800")

        self.client = client_controller
        self.current_room = None
        self.video_thread = None
        self.audio_thread = None
        self.p = None

        self.show_login_screen()

    def show_login_screen(self):
        self.clear_window()

        frame = tk.Frame(self.root, padx=20, pady=20)
        frame.pack(expand=True)

        tk.Label(frame, text="SD Meeting App", font=("Arial", 24, "bold")).pack(pady=20)

        tk.Label(frame, text="Username:").pack(anchor="w")
        self.username_entry = tk.Entry(frame, width=30)
        self.username_entry.pack(pady=5)

        button_frame = tk.Frame(frame)
        button_frame.pack(pady=10)
        tk.Button(button_frame, text="Connect", command=self.on_login, width=15).pack(
            side="left", padx=5
        )
        tk.Button(button_frame, text="Close", command=self.root.quit, width=15).pack(
            side="left", padx=5
        )

    def on_login(self):
        username = self.username_entry.get().strip()

        if not username:
            messagebox.showerror("Error", "Please enter a username")
            return

        try:
            self.client.login(username)
            self.client.set_message_callback(self.display_message)
            self.client.set_lists_callback(self.on_lists_updated)
            self.show_main_screen()
        except Exception as e:
            messagebox.showerror(
                "Connection Error", f"Could not connect to broker: {e}"
            )

    def show_main_screen(self):
        self.clear_window()

        top_frame = tk.Frame(self.root)
        top_frame.pack(fill="x", padx=10, pady=5)

        tk.Label(top_frame, text="SD Meeting App", font=("Arial", 16, "bold")).pack(
            side="left"
        )
        self.user_label = tk.Label(
            top_frame, text=f"User: {self.client.username}", font=("Arial", 12)
        )
        self.user_label.pack(side="right")
        tk.Button(top_frame, text="Close", command=self.root.quit).pack(
            side="right", padx=5
        )

        self.preview_frame = tk.LabelFrame(
            self.root, text="VIDEO PREVIEW", padx=5, pady=5
        )
        self.preview_frame.pack(fill="both", padx=10, pady=5)
        self.preview_label = tk.Label(
            self.preview_frame,
            text="(local camera feed)",
            bg="black",
            fg="white",
            font=("Arial", 14),
        )
        self.preview_label.pack(fill="both")

        self.start_video_preview()

        lists_frame = tk.Frame(self.root)
        lists_frame.pack(fill="both", expand=True, padx=10, pady=5)

        users_frame = tk.LabelFrame(lists_frame, text="ONLINE USERS", padx=5, pady=5)
        users_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))

        self.users_listbox = tk.Listbox(users_frame)
        self.users_listbox.pack(fill="both", expand=True)

        rooms_frame = tk.LabelFrame(lists_frame, text="ROOMS", padx=5, pady=5)
        rooms_frame.pack(side="left", fill="both", expand=True, padx=(5, 0))

        self.rooms_listbox = tk.Listbox(rooms_frame)
        self.rooms_listbox.pack(fill="both", expand=True)

        self.client.refresh_lists()

        bottom_frame = tk.Frame(self.root)
        bottom_frame.pack(fill="x", padx=10, pady=10)

        tk.Label(bottom_frame, text="Connect to:").pack(side="left")
        self.connect_entry = tk.Entry(bottom_frame, width=30)
        self.connect_entry.pack(side="left", padx=5)

        tk.Button(bottom_frame, text="Join", command=self.on_join).pack(
            side="left", padx=5
        )
        tk.Button(bottom_frame, text="Create room", command=self.on_create_room).pack(
            side="left", padx=5
        )

    def start_video_preview(self):
        self.cap = cv2.VideoCapture(config["client"]["video"]["device_index"])
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, config["client"]["video"]["frame_width"])
        self.cap.set(
            cv2.CAP_PROP_FRAME_HEIGHT, config["client"]["video"]["frame_height"]
        )

        def capture():
            while self.current_room is None and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    img = Image.fromarray(frame)
                    photo = ImageTk.PhotoImage(img)
                    self.preview_label.configure(image=photo)
                    self.preview_label.image = photo

        self.video_thread = threading.Thread(target=capture, daemon=True)
        self.video_thread.start()

    def on_lists_updated(self, users, rooms):
        self.users_listbox.delete(0, tk.END)
        for user in users:
            self.users_listbox.insert(tk.END, user)

        self.rooms_listbox.delete(0, tk.END)
        for room in rooms:
            self.rooms_listbox.insert(tk.END, room)

    def on_join(self):
        target = self.connect_entry.get().strip()
        if not target:
            messagebox.showwarning(
                "Warning", "Please enter a room name or user to connect to"
            )
            return

        if self.client.join_room(target):
            self.current_room = target
            self.show_call_screen()
        else:
            messagebox.showerror("Error", f"Room '{target}' does not exist")

    def on_create_room(self):
        room_name = self.connect_entry.get().strip()
        if not room_name:
            messagebox.showwarning("Warning", "Please enter a room name")
            return

        if self.client.create_room(room_name):
            self.current_room = room_name
            self.show_call_screen()
        else:
            messagebox.showerror("Error", f"Room '{room_name}' already exists")

    def show_call_screen(self):
        self.clear_window()

        top_frame = tk.Frame(self.root)
        top_frame.pack(fill="x", padx=10, pady=5)

        room_title = self.current_room if self.current_room else "1:1 Call"
        tk.Label(
            top_frame, text=f"SD Meeting App - {room_title}", font=("Arial", 16, "bold")
        ).pack(side="left")
        tk.Button(top_frame, text="Leave", command=self.on_leave).pack(
            side="right", padx=5
        )
        tk.Button(top_frame, text="Close", command=self.root.quit).pack(
            side="right", padx=5
        )

        video_frame = tk.Frame(self.root)
        video_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.video1_label = tk.Label(
            video_frame, text="(remote video 1)", bg="black", fg="white"
        )
        self.video1_label.pack(side="left", fill="both", expand=True, padx=(0, 2))

        self.video2_label = tk.Label(
            video_frame, text="(remote video 2)", bg="black", fg="white"
        )
        self.video2_label.pack(side="left", fill="both", expand=True, padx=(2, 0))

        self.client.set_video_callback(self.display_video)

        chat_frame = tk.LabelFrame(self.root, text="CHAT", padx=5, pady=5)
        chat_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.chat_text = tk.Text(chat_frame, height=8, state="disabled")
        self.chat_text.pack(fill="both", expand=True)

        chat_input_frame = tk.Frame(self.root)
        chat_input_frame.pack(fill="x", padx=10, pady=10)

        self.chat_entry = tk.Entry(chat_input_frame)
        self.chat_entry.pack(side="left", fill="x", expand=True)

        tk.Button(chat_input_frame, text="Send", command=self.on_send_message).pack(
            side="left", padx=5
        )

        self.chat_entry.bind("<Return>", lambda e: self.on_send_message())

    def display_video(self, frame_data):
        try:
            frame = cv2.imdecode(np.frombuffer(frame_data, dtype=np.uint8), 1)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame)
            photo = ImageTk.PhotoImage(img)
            self.video1_label.configure(image=photo)
            self.video1_label.image = photo
        except:
            pass

    def on_leave(self):
        self.client.leave_room()
        self.current_room = None
        if hasattr(self, "cap"):
            self.cap.release()
        self.show_main_screen()

    def on_send_message(self):
        message = self.chat_entry.get().strip()
        if not message:
            return

        self.chat_entry.delete(0, tk.END)
        self.client.send_text_message(message)
        self.display_message(f"{self.client.username}: {message}")

    def display_message(self, message):
        self.chat_text.config(state="normal")
        self.chat_text.insert(tk.END, message + "\n")
        self.chat_text.see(tk.END)
        self.chat_text.config(state="disabled")

    def clear_window(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    def run(self):
        self.root.mainloop()
        if hasattr(self, "cap"):
            self.cap.release()


def main():
    from client import Client
    import tkinter as tk

    root = tk.Tk()
    client = Client()
    interface = MeetingInterface(root, client)
    interface.run()


if __name__ == "__main__":
    main()
