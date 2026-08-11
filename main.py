import re
import threading
import time
from collections import deque

from kivy.app import App
from kivy.clock import Clock
from kivy.graphics import Color, Line, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget


# ============================================================
# CONFIGURATION
# ============================================================

APP_TITLE = "IoT Weather Monitor"

MAX_GRAPH_POINTS = 60

HC05_NAME = "HC-05"

# HC-05 Bluetooth Classic Serial Port Profile UUID
SPP_UUID = "00001101-0000-1000-8000-00805F9B34FB"


# ============================================================
# COLORS
# ============================================================

BG = (0.043, 0.067, 0.090, 1)
CARD = (0.082, 0.114, 0.149, 1)
CARD2 = (0.106, 0.149, 0.196, 1)

TEXT = (1, 1, 1, 1)
MUTED = (0.60, 0.66, 0.71, 1)

ACCENT = (0.22, 0.74, 0.97, 1)
GREEN = (0.13, 0.77, 0.37, 1)
RED = (0.94, 0.27, 0.27, 1)
YELLOW = (0.98, 0.80, 0.08, 1)
PURPLE = (0.65, 0.55, 0.98, 1)


# ============================================================
# ANDROID IMPORTS
# ============================================================

ANDROID = False

try:
    from jnius import autoclass

    BluetoothAdapter = autoclass(
        "android.bluetooth.BluetoothAdapter"
    )

    UUID = autoclass(
        "java.util.UUID"
    )

    ANDROID = True

except Exception as error:
    print("Android Bluetooth API unavailable:", error)


# ============================================================
# CARD BACKGROUND
# ============================================================

class Card(BoxLayout):

    def __init__(self, **kwargs):

        super().__init__(**kwargs)

        self.padding = dp(12)

        with self.canvas.before:

            Color(*CARD)

            self.background = RoundedRectangle(
                pos=self.pos,
                size=self.size,
                radius=[dp(12)]
            )

        self.bind(
            pos=self.update_background,
            size=self.update_background
        )

    def update_background(self, *args):

        self.background.pos = self.pos
        self.background.size = self.size


# ============================================================
# GRAPH WIDGET
# ============================================================

class GraphWidget(Widget):

    def __init__(
        self,
        data,
        title="",
        unit="",
        graph_color=ACCENT,
        **kwargs
    ):

        super().__init__(**kwargs)

        self.data = data
        self.title = title
        self.unit = unit
        self.graph_color = graph_color

        self.bind(
            pos=self.redraw,
            size=self.redraw
        )

        Clock.schedule_interval(
            self.redraw,
            0.5
        )

    def redraw(self, *args):

        self.canvas.clear()

        width = self.width
        height = self.height

        if width < dp(100) or height < dp(80):

            return

        left = dp(35)
        right = dp(10)
        top = dp(20)
        bottom = dp(20)

        graph_width = width - left - right
        graph_height = height - top - bottom

        # ----------------------------------------------------
        # BACKGROUND
        # ----------------------------------------------------

        with self.canvas:

            Color(*CARD)

            RoundedRectangle(
                pos=self.pos,
                size=self.size,
                radius=[dp(10)]
            )

            # ------------------------------------------------
            # GRID
            # ------------------------------------------------

            Color(
                MUTED[0],
                MUTED[1],
                MUTED[2],
                0.18
            )

            for i in range(5):

                y = (
                    self.y
                    + bottom
                    + graph_height * i / 4
                )

                Line(
                    points=[
                        self.x + left,
                        y,
                        self.x + width - right,
                        y
                    ],
                    width=0.7
                )

            values = list(self.data)

            if len(values) < 2:

                continue_label = Label(
                    text=""
                )

                return

            minimum = min(values)
            maximum = max(values)

            if minimum == maximum:

                minimum -= 1
                maximum += 1

            # ------------------------------------------------
            # GRAPH LINE
            # ------------------------------------------------

            points = []

            count = len(values)

            for index, value in enumerate(values):

                x = (
                    self.x
                    + left
                    + (
                        index / (count - 1)
                    ) * graph_width
                )

                normalized = (
                    value - minimum
                ) / (
                    maximum - minimum
                )

                y = (
                    self.y
                    + bottom
                    + normalized * graph_height
                )

                points.extend([x, y])

            Color(*self.graph_color)

            Line(
                points=points,
                width=2.5,
                joint="round"
            )


# ============================================================
# MAIN APP
# ============================================================

class WeatherMonitor(App):

    def __init__(self, **kwargs):

        super().__init__(**kwargs)

        # ----------------------------------------------------
        # BLUETOOTH
        # ----------------------------------------------------

        self.bluetooth_socket = None

        self.bluetooth_device = None

        self.connected = False

        self.stop_thread = False

        self.bluetooth_thread = None

        # ----------------------------------------------------
        # SENSOR VALUES
        # ----------------------------------------------------

        self.temperature = None
        self.humidity = None
        self.light = None
        self.luminous_intensity = None

        self.day_night = "--"
        self.status = "--"

        self.last_data = "--"

        # ----------------------------------------------------
        # GRAPH DATA
        # ----------------------------------------------------

        self.temperature_history = deque(
            maxlen=MAX_GRAPH_POINTS
        )

        self.humidity_history = deque(
            maxlen=MAX_GRAPH_POINTS
        )

        self.light_history = deque(
            maxlen=MAX_GRAPH_POINTS
        )

        # ----------------------------------------------------
        # UI REFERENCES
        # ----------------------------------------------------

        self.temperature_label = None
        self.humidity_label = None
        self.light_label = None
        self.lux_label = None
        self.environment_label = None
        self.status_label = None

        self.connection_label = None
        self.connect_button = None
        self.data_label = None

    # ========================================================
    # BUILD
    # ========================================================

    def build(self):

        self.title = APP_TITLE

        root = BoxLayout(
            orientation="vertical",
            spacing=dp(8),
            padding=dp(10)
        )

        root.canvas.before.add(
            Color(*BG)
        )

        # ====================================================
        # HEADER
        # ====================================================

        header = BoxLayout(
            size_hint_y=None,
            height=dp(65),
            spacing=dp(8)
        )

        title = Label(
            text="🌦  IoT WEATHER MONITOR",
            font_size=dp(22),
            bold=True,
            color=TEXT,
            halign="left",
            valign="middle"
        )

        title.bind(
            size=lambda instance, value:
            setattr(
                instance,
                "text_size",
                value
            )
        )

        header.add_widget(title)

        self.connection_label = Label(
            text="● DISCONNECTED",
            font_size=dp(12),
            bold=True,
            color=RED,
            size_hint_x=None,
            width=dp(135)
        )

        header.add_widget(
            self.connection_label
        )

        root.add_widget(header)

        # ====================================================
        # CONNECTION PANEL
        # ====================================================

        connection = Card(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(60),
            spacing=dp(8)
        )

        device_label = Label(
            text="HC-05",
            font_size=dp(15),
            bold=True,
            color=TEXT
        )

        connection.add_widget(device_label)

        self.connect_button = Button(
            text="🔗 CONNECT",
            font_size=dp(14),
            bold=True,
            background_normal="",
            background_color=GREEN,
            color=TEXT,
            size_hint_x=None,
            width=dp(145)
        )

        self.connect_button.bind(
            on_press=self.toggle_connection
        )

        connection.add_widget(
            self.connect_button
        )

        root.add_widget(connection)

        # ====================================================
        # SCROLL AREA
        # ====================================================

        scroll = ScrollView(
            do_scroll_x=False
        )

        content = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            size_hint_y=None
        )

        content.bind(
            minimum_height=content.setter(
                "height"
            )
        )

        # ====================================================
        # SENSOR CARDS
        # ====================================================

        cards = GridLayout(
            cols=2,
            spacing=dp(8),
            size_hint_y=None
        )

        cards.bind(
            minimum_height=cards.setter(
                "height"
            )
        )

        self.temperature_label = (
            self.create_sensor_card(
                cards,
                "🌡 TEMPERATURE",
                "-- °C"
            )
        )

        self.humidity_label = (
            self.create_sensor_card(
                cards,
                "💧 HUMIDITY",
                "-- %"
            )
        )

        self.light_label = (
            self.create_sensor_card(
                cards,
                "☀ LIGHT LEVEL",
                "--"
            )
        )

        self.lux_label = (
            self.create_sensor_card(
                cards,
                "💡 LUMINOUS INTENSITY",
                "-- lx"
            )
        )

        self.environment_label = (
            self.create_sensor_card(
                cards,
                "🌤 ENVIRONMENT",
                "--"
            )
        )

        self.status_label = (
            self.create_sensor_card(
                cards,
                "⚡ STATUS",
                "--"
            )
        )

        content.add_widget(cards)

        # ====================================================
        # GRAPHS
        # ====================================================

        graph_title = Label(
            text="📈 LIVE SENSOR GRAPHS",
            font_size=dp(17),
            bold=True,
            color=TEXT,
            size_hint_y=None,
            height=dp(40)
        )

        content.add_widget(graph_title)

        self.temperature_graph = GraphWidget(
            self.temperature_history,
            "Temperature",
            "°C",
            ACCENT,
            size_hint_y=None,
            height=dp(190)
        )

        content.add_widget(
            self.temperature_graph
        )

        self.humidity_graph = GraphWidget(
            self.humidity_history,
            "Humidity",
            "%",
            PURPLE,
            size_hint_y=None,
            height=dp(190)
        )

        content.add_widget(
            self.humidity_graph
        )

        self.light_graph = GraphWidget(
            self.light_history,
            "Light",
            "ADC",
            YELLOW,
            size_hint_y=None,
            height=dp(190)
        )

        content.add_widget(
            self.light_graph
        )

        # ====================================================
        # LAST DATA
        # ====================================================

        self.data_label = Label(
            text="Waiting for HC-05 data...",
            font_size=dp(11),
            color=MUTED,
            size_hint_y=None,
            height=dp(45),
            halign="left",
            valign="middle"
        )

        self.data_label.bind(
            size=lambda instance, value:
            setattr(
                instance,
                "text_size",
                value
            )
        )

        content.add_widget(
            self.data_label
        )

        scroll.add_widget(content)

        root.add_widget(scroll)

        # ====================================================
        # STARTUP
        # ====================================================

        Clock.schedule_once(
            self.check_bluetooth,
            1
        )

        return root

    # ========================================================
    # SENSOR CARD
    # ========================================================

    def create_sensor_card(
        self,
        parent,
        title,
        value
    ):

        card = Card(
            orientation="vertical",
            size_hint_y=None,
            height=dp(100)
        )

        title_label = Label(
            text=title,
            font_size=dp(11),
            bold=True,
            color=MUTED,
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(30)
        )

        title_label.bind(
            size=lambda instance, value:
            setattr(
                instance,
                "text_size",
                value
            )
        )

        card.add_widget(
            title_label
        )

        value_label = Label(
            text=value,
            font_size=dp(21),
            bold=True,
            color=TEXT,
            halign="left",
            valign="middle"
        )

        value_label.bind(
            size=lambda instance, value:
            setattr(
                instance,
                "text_size",
                value
            )
        )

        card.add_widget(
            value_label
        )

        parent.add_widget(card)

        return value_label

    # ========================================================
    # CHECK BLUETOOTH
    # ========================================================

    def check_bluetooth(self, *args):

        if not ANDROID:

            self.connection_label.text = (
                "ANDROID ONLY"
            )

            self.connection_label.color = YELLOW

            self.connect_button.disabled = True

            return

        try:

            adapter = BluetoothAdapter.getDefaultAdapter()

            if adapter is None:

                self.connection_label.text = (
                    "NO BLUETOOTH"
                )

                self.connection_label.color = RED

                self.connect_button.disabled = True

                return

            if not adapter.isEnabled():

                self.connection_label.text = (
                    "BLUETOOTH OFF"
                )

                self.connection_label.color = YELLOW

                self.connect_button.disabled = False

                return

            self.connection_label.text = (
                "● READY"
            )

            self.connection_label.color = YELLOW

        except Exception as error:

            print(
                "Bluetooth check error:",
                error
            )

    # ========================================================
    # TOGGLE CONNECTION
    # ========================================================

    def toggle_connection(self, *args):

        if self.connected:

            self.disconnect()

        else:

            self.connect_hc05()

    # ========================================================
    # CONNECT HC-05
    # ========================================================

    def connect_hc05(self):

        if not ANDROID:

            return

        self.connection_label.text = (
            "● CONNECTING..."
        )

        self.connection_label.color = YELLOW

        self.connect_button.text = (
            "CONNECTING..."
        )

        thread = threading.Thread(
            target=self.bluetooth_connect_worker,
            daemon=True
        )

        thread.start()

    # ========================================================
    # BLUETOOTH WORKER
    # ========================================================

    def bluetooth_connect_worker(self):

        try:

            adapter = (
                BluetoothAdapter
                .getDefaultAdapter()
            )

            if not adapter.isEnabled():

                raise Exception(
                    "Bluetooth is turned off."
                )

            paired_devices = (
                adapter.getBondedDevices()
            )

            device = None

            iterator = paired_devices.iterator()

            while iterator.hasNext():

                candidate = iterator.next()

                name = str(
                    candidate.getName()
                )

                print(
                    "Paired device:",
                    name
                )

                if (
                    name.upper()
                    == HC05_NAME.upper()
                ):

                    device = candidate

                    break

            if device is None:

                raise Exception(
                    "HC-05 is not paired with this phone."
                )

            self.bluetooth_device = device

            uuid = UUID.fromString(
                SPP_UUID
            )

            socket = (
                device.createRfcommSocketToServiceRecord(
                    uuid
                )
            )

            adapter.cancelDiscovery()

            socket.connect()

            self.bluetooth_socket = socket

            self.connected = True

            self.stop_thread = False

            Clock.schedule_once(
                self.connection_success,
                0
            )

            self.bluetooth_thread = threading.Thread(
                target=self.bluetooth_reader,
                daemon=True
            )

            self.bluetooth_thread.start()

        except Exception as error:

            print(
                "Bluetooth connection error:",
                error
            )

            Clock.schedule_once(
                lambda dt:
                self.connection_failed(
                    str(error)
                ),
                0
            )

    # ========================================================
    # CONNECTION SUCCESS
    # ========================================================

    def connection_success(self, *args):

        self.connection_label.text = (
            "● HC-05 CONNECTED"
        )

        self.connection_label.color = GREEN

        self.connect_button.text = (
            "⛓ DISCONNECT"
        )

        self.connect_button.background_color = RED

        self.data_label.text = (
            "Connected — waiting for sensor data..."
        )

    # ========================================================
    # CONNECTION FAILED
    # ========================================================

    def connection_failed(
        self,
        error
    ):

        self.connected = False

        self.connect_button.text = (
            "🔗 CONNECT"
        )

        self.connect_button.background_color = GREEN

        self.connection_label.text = (
            "● CONNECTION FAILED"
        )

        self.connection_label.color = RED

        self.data_label.text = (
            "Bluetooth error: "
            + error
        )

    # ========================================================
    # BLUETOOTH READER
    # ========================================================

    def bluetooth_reader(self):

        buffer = ""

        while (
            self.connected
            and not self.stop_thread
        ):

            try:

                if self.bluetooth_socket is None:

                    break

                input_stream = (
                    self.bluetooth_socket
                    .getInputStream()
                )

                data = input_stream.read()

                if data == -1:

                    break

                character = chr(
                    data
                )

                if character in (
                    "\n",
                    "\r"
                ):

                    line = buffer.strip()

                    buffer = ""

                    if line:

                        Clock.schedule_once(
                            lambda dt,
                            received=line:
                            self.process_data(
                                received
                            ),
                            0
                        )

                else:

                    buffer += character

            except Exception as error:

                print(
                    "Bluetooth read error:",
                    error
                )

                Clock.schedule_once(
                    lambda dt:
                    self.connection_lost(
                        str(error)
                    ),
                    0
                )

                break

    # ========================================================
    # PROCESS SENSOR DATA
    # ========================================================

    def process_data(
        self,
        line
    ):

        print(
            "Received:",
            line
        )

        self.last_data = line

        self.data_label.text = (
            "RX: " + line
        )

        if ":" not in line:

            return

        try:

            key, value = line.split(
                ":",
                1
            )

            key = key.strip().lower()

            value = value.strip()

            # ------------------------------------------------
            # TEMPERATURE
            # ------------------------------------------------

            if key == "temperature":

                number = self.extract_number(
                    value
                )

                if number is not None:

                    self.temperature = number

                    self.temperature_label.text = (
                        f"{number:.1f} °C"
                    )

                    self.temperature_history.append(
                        number
                    )

            # ------------------------------------------------
            # HUMIDITY
            # ------------------------------------------------

            elif key == "humidity":

                number = self.extract_number(
                    value
                )

                if number is not None:

                    self.humidity = number

                    self.humidity_label.text = (
                        f"{number:.1f} %"
                    )

                    self.humidity_history.append(
                        number
                    )

            # ------------------------------------------------
            # LIGHT
            # ------------------------------------------------

            elif key == "light":

                number = self.extract_number(
                    value
                )

                if number is not None:

                    self.light = number

                    self.light_label.text = (
                        f"{number:.0f}"
                    )

                    self.light_history.append(
                        number
                    )

            # ------------------------------------------------
            # LUMINOUS INTENSITY
            # ------------------------------------------------

            elif key in (
                "luminous intensity",
                "luminous"
            ):

                number = self.extract_number(
                    value
                )

                if number is not None:

                    self.luminous_intensity = number

                    self.lux_label.text = (
                        f"{number:.0f} lx"
                    )

            # ------------------------------------------------
            # DAY / NIGHT
            # ------------------------------------------------

            elif key in (
                "day/night",
                "environment"
            ):

                self.day_night = value

                self.environment_label.text = (
                    value
                )

            # ------------------------------------------------
            # STATUS
            # ------------------------------------------------

            elif key == "status":

                self.status = value

                self.status_label.text = (
                    value
                )

        except Exception as error:

            print(
                "Processing error:",
                error
            )

    # ========================================================
    # EXTRACT NUMBER
    # ========================================================

    def extract_number(
        self,
        text
    ):

        match = re.search(
            r"-?\d+(?:\.\d+)?",
            text
        )

        if match:

            try:

                return float(
                    match.group()
                )

            except ValueError:

                return None

        return None

    # ========================================================
    # CONNECTION LOST
    # ========================================================

    def connection_lost(
        self,
        error=""
    ):

        self.disconnect()

        self.connection_label.text = (
            "● CONNECTION LOST"
        )

        self.connection_label.color = RED

        if error:

            self.data_label.text = (
                "Connection lost: "
                + error
            )

        else:

            self.data_label.text = (
                "HC-05 connection lost."
            )

    # ========================================================
    # DISCONNECT
    # ========================================================

    def disconnect(self):

        self.stop_thread = True

        self.connected = False

        try:

            if self.bluetooth_socket:

                self.bluetooth_socket.close()

        except Exception:
            pass

        self.bluetooth_socket = None

        self.connect_button.text = (
            "🔗 CONNECT"
        )

        self.connect_button.background_color = (
            GREEN
        )

        self.connection_label.text = (
            "● DISCONNECTED"
        )

        self.connection_label.color = RED

    # ========================================================
    # APP STOP
    # ========================================================

    def on_stop(self):

        self.disconnect()


# ============================================================
# START APPLICATION
# ============================================================

if __name__ == "__main__":

    WeatherMonitor().run()