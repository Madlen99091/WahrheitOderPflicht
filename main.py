import os
import json
import random
import urllib.request
import urllib.parse
from datetime import datetime

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.clock import Clock
from kivy.core.window import Window

# Feste Fenstergröße für PC-Tests (Mobil-Look)
Window.size = (380, 680)

# ---------- Supabase / Local Fallback ----------
SUPABASE_URL = os.getenv("VITE_SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("VITE_SUPABASE_ANON_KEY", "")
USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_ANON_KEY)
LOCAL_STORE = "local_games.json"

def _local_load_all():
    if not os.path.exists(LOCAL_STORE):
        return {"games": [], "questions": []}
    try:
        with open(LOCAL_STORE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"games": [], "questions": []}

def _local_save_all(data):
    with open(LOCAL_STORE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def make_request(method, table, data=None, filters=None, order=None):
    if not USE_SUPABASE:
        store = _local_load_all()
        if method == "GET":
            if table == "games":
                items = store.get("games", [])
                if order and order[0] == "created_at":
                    return sorted(items, key=lambda x: x.get("created_at", ""), reverse=True)
                return items
            elif table == "questions":
                items = store.get("questions", [])
                if filters and "game_id" in filters:
                    return [q for q in items if q.get("game_id") == filters["game_id"]]
                return items
        elif method == "POST":
            if table == "games":
                new_id = str(int(datetime.utcnow().timestamp() * 1000))
                obj = {"id": new_id, "name": data.get("name", "Neues Spiel"), "current_index": 0, "created_at": datetime.utcnow().isoformat()}
                store["games"].append(obj)
                _local_save_all(store)
                return [obj]
            elif table == "questions":
                new_id = str(int(datetime.utcnow().timestamp() * 1000)) + str(len(store["questions"]))
                obj = {"id": new_id, "game_id": data["game_id"], "type": data["type"], "content": data["content"], "order_index": len(store["questions"])}
                store["questions"].append(obj)
                _local_save_all(store)
                return [obj]
        elif method == "PATCH":
            if "id=eq." in table:
                gid = table.split("id=eq.")[-1]
                for g in store.get("games", []):
                    if g["id"] == gid:
                        g.update(data)
                        _local_save_all(store)
                        return [g]
        return []
    return []

# ---------- GUI Screens ----------
class HomeScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=20, spacing=15)
        
        layout.add_widget(Label(text="Wahrheit oder Pflicht", font_size='24sp', bold=True, size_hint_y=0.2))
        
        btn_play = Button(text="Spielen", size_hint_y=0.15, background_color=(0.2, 0.6, 1, 1))
        btn_play.bind(on_release=lambda x: self.start_game())
        
        btn_admin = Button(text="Admin / Neues Spiel", size_hint_y=0.15)
        btn_admin.bind(on_release=lambda x: setattr(self.manager, 'current', 'admin'))
        
        layout.add_widget(btn_play)
        layout.add_widget(btn_admin)
        layout.add_widget(Label(size_hint_y=0.5))
        self.add_widget(layout)

    def start_game(self):
        games = make_request("GET", "games", order=("created_at", "desc"))
        if not games:
            popup = Popup(title='Kein Spiel', content=Label(text='Erstelle zuerst ein Spiel im Admin-Bereich.'), size_hint=(0.8, 0.4))
            popup.open()
            return
        
        play_screen = self.manager.get_screen('play')
        play_screen.load_game(games[0])
        self.manager.current = 'play'

class AdminScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=20, spacing=10)
        
        layout.add_widget(Label(text="Neues Spiel erstellen", font_size='20sp', size_hint_y=0.1))
        
        self.name_input = TextInput(hint_text="Spielname", multiline=False, size_hint_y=0.1)
        layout.add_widget(self.name_input)
        
        btn_create = Button(text="Spiel Speichern", size_hint_y=0.12, background_color=(0.2, 0.8, 0.2, 1))
        btn_create.bind(on_release=self.create_game)
        layout.add_widget(btn_create)

        layout.add_widget(Label(text="Frage hinzufügen", font_size='20sp', size_hint_y=0.1))
        
        self.type_input = TextInput(hint_text="Typ: 'truth' oder 'dare'", multiline=False, size_hint_y=0.1)
        self.q_input = TextInput(hint_text="Fragetext", multiline=True, size_hint_y=0.2)
        
        layout.add_widget(self.type_input)
        layout.add_widget(self.q_input)
        
        btn_add_q = Button(text="Frage Hinzufügen", size_hint_y=0.12)
        btn_add_q.bind(on_release=self.add_question)
        layout.add_widget(btn_add_q)

        btn_back = Button(text="Zurück", size_hint_y=0.1)
        btn_back.bind(on_release=lambda x: setattr(self.manager, 'current', 'home'))
        layout.add_widget(btn_back)

        self.add_widget(layout)
        self.active_game = None

    def create_game(self, instance):
        if self.name_input.text:
            res = make_request("POST", "games", data={"name": self.name_input.text})
            if res:
                self.active_game = res[0]
                Popup(title='Erfolg', content=Label(text='Spiel erstellt! Füge jetzt Fragen hinzu.'), size_hint=(0.8, 0.3)).open()

    def add_question(self, instance):
        if not self.active_game:
            games = make_request("GET", "games", order=("created_at", "desc"))
            if games:
                self.active_game = games[0]
            else:
                Popup(title='Fehler', content=Label(text='Erstelle zuerst ein Spiel!'), size_hint=(0.8, 0.3)).open()
                return

        qtype = self.type_input.text.strip().lower()
        if qtype in ("truth", "dare") and self.q_input.text:
            make_request("POST", "questions", data={
                "game_id": self.active_game["id"],
                "type": qtype,
                "content": self.q_input.text
            })
            self.q_input.text = ""
            Popup(title='Erfolg', content=Label(text='Frage gespeichert!'), size_hint=(0.8, 0.3)).open()

class PlayScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.game = None
        self.questions = []
        self.index = 0
        self.timer_event = None
        self.seconds = 0

        layout = BoxLayout(orientation='vertical', padding=20, spacing=10)
        
        self.lbl_title = Label(text="", font_size='18sp', size_hint_y=0.1)
        self.lbl_card = Label(text="Drücke auf Aufdecken", font_size='18sp', halign='center', valign='middle', size_hint_y=0.5)
        self.lbl_card.bind(size=self.lbl_card.setter('text_size'))
        
        self.lbl_timer = Label(text="", font_size='16sp', size_hint_y=0.1, color=(1, 0.3, 0.5, 1))

        btn_reveal = Button(text="Aufdecken", size_hint_y=0.1, background_color=(0.9, 0.3, 0.5, 1))
        btn_reveal.bind(on_release=self.reveal)

        btn_next = Button(text="Nächste Frage", size_hint_y=0.1)
        btn_next.bind(on_release=self.next_q)

        btn_timer = Button(text="⏱ 1 Min Timer", size_hint_y=0.1)
        btn_timer.bind(on_release=self.start_timer)

        btn_back = Button(text="Beenden", size_hint_y=0.08)
        btn_back.bind(on_release=self.exit_play)

        layout.add_widget(self.lbl_title)
        layout.add_widget(self.lbl_card)
        layout.add_widget(self.lbl_timer)
        layout.add_widget(btn_reveal)
        layout.add_widget(btn_next)
        layout.add_widget(btn_timer)
        layout.add_widget(btn_back)
        self.add_widget(layout)

    def load_game(self, game):
        self.game = game
        self.questions = make_request("GET", "questions", filters={"game_id": game["id"]})
        self.index = 0
        self.lbl_title.text = game.get("name", "Spiel")
        self.show_question_placeholder()

    def show_question_placeholder(self):
        if not self.questions:
            self.lbl_card.text = "Keine Fragen vorhanden."
            return
        qtype = "WAHRHEIT" if self.questions[self.index]["type"] == "truth" else "PFLICHT"
        self.lbl_card.text = f"[{qtype}]\n\n???"

    def reveal(self, instance):
        if self.questions and self.index < len(self.questions):
            self.lbl_card.text = self.questions[self.index]["content"]

    def next_q(self, instance):
        if self.questions:
            self.index = (self.index + 1) % len(self.questions)
            self.show_question_placeholder()

    def start_timer(self, instance):
        if self.timer_event:
            self.timer_event.cancel()
        self.seconds = 60
        self.timer_event = Clock.schedule_interval(self.update_timer, 1)

    def update_timer(self, dt):
        self.seconds -= 1
        if self.seconds <= 0:
            self.lbl_timer.text = "💥 Zeit abgelaufen!"
            self.timer_event.cancel()
        else:
            self.lbl_timer.text = f"⏱ 00:{self.seconds:02d}"

    def exit_play(self, instance):
        if self.timer_event:
            self.timer_event.cancel()
        self.manager.current = 'home'

# ---------- App Startup ----------
class TruthOrDareApp(App):
    def build(self):
        sm = ScreenManager()
        sm.add_widget(HomeScreen(name='home'))
        sm.add_widget(AdminScreen(name='admin'))
        sm.add_widget(PlayScreen(name='play'))
        return sm

if __name__ == '__main__':
    TruthOrDareApp().run()