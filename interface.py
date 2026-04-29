import tkinter as tk
from tkinter import messagebox


class MeetingInterface:
    def __init__(self, root, client_controller):
        self.root = root
        self.root.title("SD Meeting App")
        self.root.geometry("800x600")

        self.client = client_controller

        self.show_login_screen()

    def show_login_screen(self):
        self.clear_window()

        frame = tk.Frame(self.root, padx=20, pady=20)
        frame.pack(expand=True)

        tk.Label(frame, text="SD Meeting App", font=("Arial", 24, "bold")).pack(pady=20)

        tk.Label(frame, text="Username:").pack(anchor="w")
        self.username_entry = tk.Entry(frame, width=30)
        self.username_entry.pack(pady=5)

        tk.Button(frame, text="Connect", command=self.on_login, width=15).pack(pady=10)

    def on_login(self):
        username = self.username_entry.get().strip()

        if not username:
            messagebox.showerror("Error", "Please enter a username")
            return

        try:
            self.client.login(username)
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

        self.preview_frame = tk.LabelFrame(
            self.root, text="VIDEO PREVIEW", padx=5, pady=5
        )
        self.preview_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.preview_label = tk.Label(
            self.preview_frame, text="(local camera feed)", bg="black", fg="white"
        )
        self.preview_label.pack(fill="both", expand=True)

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

        self.refresh_lists()

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

    def refresh_lists(self):
        self.users_listbox.delete(0, tk.END)
        for user in self.client.get_online_users():
            self.users_listbox.insert(tk.END, user)

        self.rooms_listbox.delete(0, tk.END)
        for room in self.client.get_rooms():
            self.rooms_listbox.insert(tk.END, room)

    def on_join(self):
        target = self.connect_entry.get().strip()
        if not target:
            messagebox.showwarning(
                "Warning", "Please enter a room name or user to connect to"
            )
            return

        if not self.client.join_room(target):
            messagebox.showerror(
                "Error", f"User or room '{target}' does not exist"
            )
            return

        self.current_room = target
        self.show_call_screen()

    def on_create_room(self):
        room_name = self.connect_entry.get().strip()
        if not room_name:
            messagebox.showwarning("Warning", "Please enter a room name")
            return

        if not self.client.create_room(room_name):
            messagebox.showerror("Error", f"Room '{room_name}' already exists")
            return

        self.current_room = room_name
        self.show_call_screen()

    def show_call_screen(self):
        self.clear_window()

        top_frame = tk.Frame(self.root)
        top_frame.pack(fill="x", padx=10, pady=5)

        room_title = self.current_room if self.current_room else "1:1 Call"
        tk.Label(
            top_frame, text=f"SD Meeting App - {room_title}", font=("Arial", 16, "bold")
        ).pack(side="left")
        tk.Button(top_frame, text="Leave", command=self.on_leave).pack(side="right")

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

    def on_leave(self):
        self.client.leave_room()
        self.current_room = None
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


def main():
    from client import Client

    root = tk.Tk()
    client = Client()
    interface = MeetingInterface(root, client)
    interface.run()


if __name__ == "__main__":
    main()

