# assistant.py
import speech_recognition as sr
import pyttsx3
import pywhatkit
import datetime
import wikipedia
import pyjokes
import webbrowser
import requests
import sys
import random
import time
import threading
import re
import os
import ctypes
import queue
import ast
from queue import Queue

# ---------------- USER CONFIG ---------------- #
OWM_API_KEY = "ff13306cb2826f960c54e7e0468aea94"  # your OpenWeatherMap API key (already provided)

# ---------------- TTS QUEUE & WORKER ---------------- #
_tts_queue: "Queue[str]" = Queue()
_tts_worker_thread = None

def _tts_worker():
    engine = pyttsx3.init()
    # pick a female voice if available
    try:
        voices = engine.getProperty("voices")
        chosen = None
        for v in voices:
            name = (v.name or "").lower()
            if "female" in name or "zira" in name or "heera" in name or "aadi" in name or "aditi" in name:
                chosen = v.id
                break
        if chosen:
            engine.setProperty("voice", chosen)
    except Exception:
        pass
    engine.setProperty("rate", 170)
    while True:
        text = _tts_queue.get()
        if text is None:
            _tts_queue.task_done()
            break
        try:
            engine.say(str(text))
            engine.runAndWait()
        except Exception as e:
            # shouldn't crash main app
            print("TTS worker error:", e)
        _tts_queue.task_done()

def speak(text):
    """Queue text for non-blocking TTS."""
    print(f"SARA: {text}")
    try:
        _tts_queue.put_nowait(text)
    except Exception as e:
        print("Failed to queue TTS:", e)

def start_tts_worker():
    global _tts_worker_thread
    if _tts_worker_thread is None:
        _tts_worker_thread = threading.Thread(target=_tts_worker, daemon=True)
        _tts_worker_thread.start()

def stop_tts_worker_and_wait():
    """Send sentinel, wait until all queued speech finishes."""
    try:
        # wait until queue empty
        _tts_queue.join()
    except:
        pass
    try:
        _tts_queue.put_nowait(None)
    except:
        pass

start_tts_worker()

# ---------------- LISTEN ---------------- #
def take_command(timeout=6, phrase_time_limit=8):
    r = sr.Recognizer()
    with sr.Microphone() as source:
        print("\n🎧 Listening...")
        r.adjust_for_ambient_noise(source, duration=0.7)
        try:
            audio = r.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
        except sr.WaitTimeoutError:
            return ""
    try:
        print("Recognizing...")
        cmd = r.recognize_google(audio, language='en-in')
        print(f"You said: {cmd}")
        return cmd.lower()
    except sr.UnknownValueError:
        return ""
    except sr.RequestError:
        speak("Speech service is unavailable right now.")
        return ""
    except Exception as e:
        print("Listen error:", e)
        return ""

# ---------------- SAFE CALCULATOR ---------------- #
# Evaluate arithmetic expressions safely using AST
ALLOWED_AST_NODES = {
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Num, ast.Constant,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.USub,
    ast.UAdd, ast.FloorDiv, ast.LShift, ast.RShift, ast.BitOr, ast.BitAnd,
    ast.BitXor, ast.Call, ast.Name
}
# we'll only allow numbers, + - * / ** % // and parentheses. No names/calls allowed in final check.

def _safe_eval(node):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant):  # python3.8+
        if isinstance(node.value, (int, float)):
            return node.value
        else:
            raise ValueError("Only numbers allowed")
    if isinstance(node, ast.Num):  # older python
        return node.n
    if isinstance(node, ast.BinOp):
        left = _safe_eval(node.left)
        right = _safe_eval(node.right)
        op = node.op
        if isinstance(op, ast.Add):
            return left + right
        if isinstance(op, ast.Sub):
            return left - right
        if isinstance(op, ast.Mult):
            return left * right
        if isinstance(op, ast.Div):
            return left / right
        if isinstance(op, ast.Pow):
            return left ** right
        if isinstance(op, ast.Mod):
            return left % right
        if isinstance(op, ast.FloorDiv):
            return left // right
        raise ValueError("Operator not allowed")
    if isinstance(node, ast.UnaryOp):
        operand = _safe_eval(node.operand)
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return +operand
        raise ValueError("Unary operator not allowed")
    raise ValueError("Expression not allowed")

def calculate_expression(spoken_text):
    # normalize common words to operators
    t = spoken_text.lower()
    t = t.replace("plus", "+")
    t = t.replace("add", "+")
    t = t.replace("minus", "-")
    t = t.replace("subtract", "-")
    t = t.replace("times", "*").replace("x", "*").replace("into", "*").replace("multiply", "*")
    t = t.replace("divided by", "/").replace("divide by", "/").replace("divide", "/")
    t = t.replace("power", "**").replace("^", "**")
    t = t.replace("percent", "/100")
    # remove any characters except numbers, operators, parentheses, dot and space
    cleaned = re.sub(r"[^0-9\+\-\*\/\.\(\)\s\%]+", "", t)
    try:
        tree = ast.parse(cleaned, mode='eval')
        # ensure AST contains only allowed nodes
        for n in ast.walk(tree):
            if not isinstance(n, tuple(ALLOWED_AST_NODES)):
                raise ValueError("Disallowed expression")
        result = _safe_eval(tree)
        return result
    except Exception as e:
        # fallback: try simple extraction of digits (not ideal)
        print("Calc error:", e)
        return None

# ---------------- FACTS & QUOTES ---------------- #
facts = [
    "Honey never spoils.",
    "Bananas are berries, but strawberries are not.",
    "Octopuses have three hearts.",
    "Sharks existed before trees.",
    "A day on Venus is longer than a year on Venus.",
    "Butterflies taste with their feet.",
    "The Eiffel Tower can be 15 cm taller in summer.",
    "There are more stars in the universe than grains of sand on Earth.",
    "Wombat poop is cube-shaped.",
    "Some turtles can breathe through their butt.",
    "Koalas sleep up to 22 hours a day.",
    "Sea otters hold hands while sleeping.",
    "There is a species of jellyfish that is effectively immortal.",
    "Dolphins call each other by unique whistles.",
    "A cloud can weigh over a million pounds.",
    "It rains diamonds on Jupiter and Saturn.",
    "The human nose can distinguish about 1 trillion smells.",
    "The blue whale's heart is the size of a small car.",
    "Penguins often propose with pebbles.",
    "There are more stars in the universe than grains of sand on Earth."
]

quotes = [
   "The best way to get started is to quit talking and begin doing.",
    "Don’t let yesterday take up too much of today.",
    "It always seems impossible until it’s done.",
    "You are never too old to set another goal or to dream a new dream.",
    "Success is not final, failure is not fatal: it is the courage to continue that counts.",
    "Believe you can and you're halfway there.",
    "Dream big and dare to fail.",
    "Happiness is not something ready-made. It comes from your own actions.",
    "Do what you can, with what you have, where you are.",
    "The only limit to our realization of tomorrow will be our doubts of today.",
    "Don't watch the clock; do what it does. Keep going.",
    "Everything you’ve ever wanted is on the other side of fear.",
    "Octopus have three hearts.",
    "The first computer mouse was made of wood.",
    "A day on Venus is longer than a year on Venus."
]
# ---------------- ALARM / TIME PARSING ---------------- #
def parse_alarm_time(spoken: str):
    if not spoken:
        return None
    s = spoken.lower().replace(".", "").strip()
    s = s.replace("o'clock", "")
    # 7:20 pm, 7 20 pm, 19:20, 7 pm, etc.
    m = re.search(r'(\d{1,2})[:\s]?(\d{2})\s*(am|pm)?', s)
    if m:
        hour = int(m.group(1)); minute = int(m.group(2))
        period = m.group(3)
        if period:
            if period == 'pm' and hour != 12:
                hour += 12
            if period == 'am' and hour == 12:
                hour = 0
        return f"{hour:02d}:{minute:02d}"
    m2 = re.search(r'(\d{1,2})\s*(am|pm)', s)
    if m2:
        hour = int(m2.group(1)); minute = 0
        period = m2.group(2)
        if period == 'pm' and hour != 12:
            hour += 12
        if period == 'am' and hour == 12:
            hour = 0
        return f"{hour:02d}:{minute:02d}"
    # 24-hour
    m3 = re.search(r'(\d{2}):(\d{2})', s)
    if m3:
        return m3.group(0)
    return None

def alarm_thread_worker(target_hm, message):
    speak(f"Alarm scheduled for {target_hm}.")
    while True:
        now = datetime.datetime.now().strftime("%H:%M")
        if now == target_hm:
            for _ in range(6):
                speak(message or f"Alarm! It's {datetime.datetime.now().strftime('%I:%M %p')}")
                time.sleep(1)
            break
        time.sleep(10)

# ---------------- WEATHER ---------------- #
def get_weather(city):
    if not city:
        speak("Please tell me the city name.")
        return
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OWM_API_KEY}&units=metric"
        r = requests.get(url, timeout=8)
        data = r.json()
        if data.get("cod") != 200:
            speak(f"Sorry, I couldn't find weather for {city}.")
            return
        temp = data["main"]["temp"]
        desc = data["weather"][0]["description"]
        speak(f"The temperature in {city} is {temp}°C with {desc}.")
    except Exception as e:
        print("Weather error:", e)
        speak("Weather service is unavailable right now.")

# ---------------- SYSTEM VOLUME (key events) ---------------- #
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
def press_key(vk):
    ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY, 0)
    time.sleep(0.05)
    ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)

def increase_system_volume(steps=2):
    for _ in range(steps):
        press_key(VK_VOLUME_UP)
        time.sleep(0.05)
    speak("Increased volume.")

def decrease_system_volume(steps=2):
    for _ in range(steps):
        press_key(VK_VOLUME_DOWN)
        time.sleep(0.05)
    speak("Decreased volume.")

def mute_system_volume():
    press_key(VK_VOLUME_MUTE)
    speak("Toggled mute.")

# ---------------- BRIGHTNESS CONTROL (PowerShell fallback) ---------------- #
def set_brightness(level):
    try:
        level = int(level)
        level = max(0, min(100, level))
        # Try WMI method (works on many Windows machines)
        ps = f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{level})"
        ret = os.system(f"powershell -Command \"{ps}\"")
        if ret == 0:
            speak(f"Brightness set to {level} percent.")
            return True
        else:
            speak("Brightness control failed on this machine. It may not be supported.")
            return False
    except Exception as e:
        print("Brightness error:", e)
        speak("Brightness command failed.")
        return False

# ---------------- WHATSAPP SEND ---------------- #
def send_whatsapp_message():
    # Ask user for number and message
    speak("Please tell the phone number,including country code.")
    phone = take_command()
    if not phone:
        speak("I didn't get the phone number.")
        return
    # Normalize phone number spoken like "plus nine one nine eight" -> +9198...
    digits = re.findall(r'\+?\d+', phone.replace(" ", ""))
    phone_num = digits[0] if digits else phone.strip()
    # Ensure it starts with +
    if not phone_num.startswith("+"):
        # try adding + if country code likely present without plus
        if len(phone_num) >= 10:
            phone_num = "+" + phone_num
    speak("What message should I send?")
    message = take_command()
    if not message:
        speak("No message detected. Cancelling.")
        return
    speak("Sending WhatsApp message. Please wait and do not close the browser.")
    try:
        # sendwhatmsg_instantly opens WhatsApp web and sends immediately (may require a logged-in session)
        pywhatkit.sendwhatmsg_instantly(phone_num, message, wait_time=10, tab_close=True)
        speak("Message sent (or scheduled).")
    except Exception as e:
        print("WhatsApp send error:", e)
        speak("I couldn't send the WhatsApp message. Make sure you are logged into WhatsApp Web in your default browser.")

# ---------------- UTILITIES (open website/app) ---------------- #
def open_website_from_phrase(phrase):
    site = phrase.strip().replace(" ", "")
    if not site:
        speak("Which website?")
        return
    if not site.startswith("http"):
        site = "https://" + site
    try:
        webbrowser.open(site)
        speak(f"Opening {site}")
    except Exception as e:
        print("Open website error:", e)
        speak("Could not open website.")

def open_app_by_name(name):
    apps = {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "firefox": r"C:\Program Files\Mozilla Firefox\firefox.exe",
        "word": r"C:\Program Files\Microsoft Office\\root\\Office16\\WINWORD.EXE"
    }
    key = name.lower().strip()
    path = apps.get(key)
    if path:
        try:
            os.startfile(path)
            speak(f"Opening {name}")
            return True
        except Exception as e:
            print("Open app error:", e)
            speak(f"Unable to open {name}")
            return False
    else:
        try:
            os.startfile(name)
            speak(f"Opening {name}")
            return True
        except Exception as e:
            print("Open app fallback error:", e)
            speak(f"I don't know how to open {name}.")
            return False

# ---------------- MAIN LOOP ---------------- #
def run_sara():
    speak("Hello! I’m SARA, your personal desktop assistant. How can I help you?")
    while True:
        command = take_command()
        if not command:
            continue

        # weather
        if 'weather' in command:
            if ' in ' in command:
                city = command.split(' in ')[-1].strip()
            else:
                speak("Which city?")
                city = take_command()
            get_weather(city)
            continue

        # play youtube
        if command.startswith('play '):
            song = command.replace('play', '', 1).strip()
            speak(f"Playing {song} on YouTube.")
            pywhatkit.playonyt(song)
            continue

        # time & date
        if 'time' in command and 'date' not in command:
            t = datetime.datetime.now().strftime('%I:%M %p')
            speak(f"The time is {t}")
            continue
        if 'date' in command:
            d = datetime.datetime.now().strftime('%A, %d %B %Y')
            speak(f"Today is {d}")
            continue

        # facts & quotes
        if 'fact' in command:
            speak(random.choice(facts))
            continue
        if 'quote' in command or 'motivate me' in command:
            speak(random.choice(quotes))
            continue

        # jokes
        if 'joke' in command:
            speak(pyjokes.get_joke())
            continue

        # calculator
        if 'calculate' in command or 'solve' in command or 'evaluate' in command:
            # If user says "calculate 5 plus 7" we try to extract the expression
            expr = command
            # remove the trigger words
            expr = re.sub(r'^(calculate|solve|evaluate)\s*', '', expr)
            res = calculate_expression(expr)
            if res is not None:
                speak(f"The answer is {res}")
            else:
                # ask the user to speak the exact expression
                speak("Please say the expression you want to calculate.")
                expr2 = take_command()
                res2 = calculate_expression(expr2)
                if res2 is not None:
                    speak(f"The answer is {res2}")
                else:
                    speak("Sorry, I couldn't calculate that.")
            continue

        # alarm / reminder
        if 'set alarm' in command or 'remind me' in command:
            speak("Please tell me the alarm time like 7:20 PM or 2130.")
            spoken_time = take_command()
            hm = parse_alarm_time(spoken_time)
            if not hm:
                speak("I couldn't understand that time. Try saying 7:20 PM.")
                continue
            speak("What should I remind you about at that time? Say 'nothing' to set a silent alarm.")
            message = take_command()
            if message and message.strip().lower() in ("nothing", "no", "none", "cancel"):
                message = ""
            if not message:
                message = f"Alarm! It's {datetime.datetime.now().strftime('%I:%M %p')}"
            threading.Thread(target=alarm_thread_worker, args=(hm, message), daemon=True).start()
            speak(f"Okay — reminder set for {hm}.")
            continue

        # volume control
        if 'increase volume' in command or 'volume up' in command:
            increase_system_volume(steps=3)
            continue
        if 'decrease volume' in command or 'volume down' in command:
            decrease_system_volume(steps=3)
            continue
        if 'mute' in command and 'un' not in command:
            mute_system_volume()
            continue
        if 'unmute' in command:
            mute_system_volume()
            continue

        # brightness control
        if 'brightness' in command:
            nums = re.findall(r'\d+', command)
            if nums:
                set_brightness(nums[0])
            else:
                speak("Please say a brightness percentage between zero and one hundred.")
            continue

        # send whatsapp
        if 'send whatsapp' in command or 'whatsapp' in command:
            send_whatsapp_message()
            continue

        # open website
        if command.startswith('open web ') or command.startswith('open website '):
            phrase = command.replace('open web', '', 1).replace('open website', '', 1).strip()
            open_website_from_phrase(phrase)
            continue

        # open app
        if command.startswith('open app ') or command.startswith('open '):
            app_phrase = command
            app_phrase = app_phrase.replace('open app', '', 1).replace('open', '', 1).strip()
            open_app_by_name(app_phrase)
            continue

        # wikipedia
        if command.startswith('who is') or command.startswith('what is'):
            topic = command.replace('who is', '', 1).replace('what is', '', 1).strip()
            try:
                summary = wikipedia.summary(topic, sentences=2)
                speak(summary)
            except Exception as e:
                print("Wikipedia error:", e)
                speak("Sorry, I couldn't find that on Wikipedia.")
            continue

        # exit
        if any(x in command for x in ['bye', 'exit', 'stop', 'goodbye']):
            speak("Goodbye! Have a nice day.")
            # ensure speech is completed then shut down TTS worker
            stop_tts_worker_and_wait()
            time.sleep(0.2)
            break

        # fallback
        speak("Sorry, I didn’t understand that. ")

if __name__ == "__main__":
    try:
        run_sara()
    except KeyboardInterrupt:
        stop_tts_worker_and_wait()
        print("Assistant terminated by user.")