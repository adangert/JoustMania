"""
JoustMania Web UI Microservice

Provides HTTP/web interface for JoustMania. Acts as a gRPC client to
communicate with backend microservices.

Part of Phase 9 (Architecture Cleanup).
"""

import logging
import os
import threading
from multiprocessing import Process
from time import sleep

import grpc
import psutil
import yaml
from flask import Flask, flash, redirect, render_template, request, url_for

# OpenTelemetry instrumentation
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Prometheus metrics (Phase 38)
from prometheus_client import start_http_server
from wtforms import (
    BooleanField,
    Form,
    IntegerField,
    SelectField,
    SelectMultipleField,
    widgets,
)

from lib import colors

# Import core modules (use types to avoid psmove dependency)
from lib.types import Games, Opts

# Import protobuf definitions
from proto import (
    controller_manager_pb2,
    controller_manager_pb2_grpc,
    menu_pb2,
    menu_pb2_grpc,
    settings_pb2,
    settings_pb2_grpc,
    supervisor_pb2_grpc,
)
from services.webui import metrics

# Configure logging with environment variable support
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Suppress Flask werkzeug logs
log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)

# OpenTelemetry setup
resource = Resource(attributes={"service.name": os.getenv("OTEL_SERVICE_NAME", "webui-service")})
trace.set_tracer_provider(TracerProvider(resource=resource))
tracer = trace.get_tracer(__name__)

# Configure OTLP exporter
otlp_exporter = OTLPSpanExporter(
    endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"),
    insecure=True,
)
trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(otlp_exporter))

# Instrument gRPC client
GrpcInstrumentorClient().instrument()


class MultiCheckboxField(SelectMultipleField):
    """
    A multiple-select, except displays a list of checkboxes.

    Iterating the field will produce subfields, allowing custom rendering of
    the enclosed checkbox fields.
    """

    widget = widgets.ListWidget(prefix_label=True)
    option_widget = widgets.CheckboxInput()


class SettingsForm(Form):
    """Settings form with actively used settings (Phase 32 cleanup)."""

    sensitivity = SelectField(
        "Move sensitivity",
        choices=[
            (0, "Ultra High"),
            (1, "High"),
            (2, "Medium"),
            (3, "Low"),
            (4, "Ultra Low"),
        ],
        coerce=int,
    )
    instructions = BooleanField("Play instructions before game start")
    num_teams = SelectField(
        "Number of teams",
        choices=[(2, "2"), (3, "3"), (4, "4"), (5, "5"), (6, "6")],
        coerce=int,
    )
    force_all_start = BooleanField("When force starting, start with all controllers (not just ready ones)")
    nonstop_time_limit = IntegerField(
        "Nonstop Joust time limit in seconds (0 = no limit)",
        default=0,
    )
    mode_options = [game for game in Games if game not in [Games.Random, Games.JoustTeams]]
    random_modes = MultiCheckboxField(
        "Random Modes (for future Random game mode)",
        choices=[(game.name, game.pretty_name) for game in mode_options],
    )
    menu_voice = SelectField(
        "Menu voice pack (for future multi-language support)",
        choices=[
            ("ivy", "Ivy (English)"),
            ("en", "English"),
            ("es", "Spanish"),
            ("fr", "French"),
            ("de", "German"),
        ],
        coerce=str,
    )


class GrpcClients:
    """Manager for gRPC client connections."""

    def __init__(self):
        # gRPC channel options for better performance and reliability
        [
            # Keep-alive settings to detect dead connections
            ("grpc.keepalive_time_ms", 30000),  # Send keepalive ping every 30s
            ("grpc.keepalive_timeout_ms", 5000),  # Wait 5s for keepalive ack
            ("grpc.keepalive_permit_without_calls", True),  # Allow keepalive pings when no calls
            ("grpc.http2.max_pings_without_data", 2),  # Allow 2 pings without data
            # Connection and timeout settings
            ("grpc.initial_reconnect_backoff_ms", 1000),  # 1s initial backoff
            ("grpc.max_reconnect_backoff_ms", 5000),  # 5s max backoff
            # Message size limits (10MB for large messages)
            ("grpc.max_receive_message_length", 10 * 1024 * 1024),
            ("grpc.max_send_message_length", 10 * 1024 * 1024),
            # Compression (Phase 26 - Performance)
            ("grpc.default_compression_algorithm", grpc.Compression.Gzip),
            ("grpc.grpc.default_compression_level", grpc.Compression.Gzip),
        ]

        # Service addresses from environment or defaults
        self.settings_addr = os.getenv("SETTINGS_SERVICE", "settings:50051")
        self.controller_mgr_addr = os.getenv("CONTROLLER_MANAGER_SERVICE", "controller-manager:50052")
        self.menu_addr = os.getenv("MENU_SERVICE", "menu:50054")
        self.supervisor_addr = os.getenv("SUPERVISOR_SERVICE", "supervisor:50055")

        # Initialize channels and stubs
        self.settings_channel = None
        self.settings_stub = None
        self.controller_channel = None
        self.controller_stub = None
        self.menu_channel = None
        self.menu_stub = None
        self.supervisor_channel = None
        self.supervisor_stub = None

        self.connect_all()

    def connect_all(self):
        """Establish connections to all services."""
        logger.info("Connecting to gRPC services...")

        # Settings service
        self.settings_channel = grpc.insecure_channel(self.settings_addr)
        self.settings_stub = settings_pb2_grpc.SettingsServiceStub(self.settings_channel)

        # ControllerManager service
        self.controller_channel = grpc.insecure_channel(self.controller_mgr_addr)
        self.controller_stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(self.controller_channel)

        # Menu service
        self.menu_channel = grpc.insecure_channel(self.menu_addr)
        self.menu_stub = menu_pb2_grpc.MenuServiceStub(self.menu_channel)

        # Supervisor service
        self.supervisor_channel = grpc.insecure_channel(self.supervisor_addr)
        self.supervisor_stub = supervisor_pb2_grpc.SupervisorServiceStub(self.supervisor_channel)

        logger.info("Connected to all gRPC services")

    def close_all(self):
        """Close all gRPC connections."""
        logger.info("Closing gRPC connections...")
        if self.settings_channel:
            self.settings_channel.close()
        if self.controller_channel:
            self.controller_channel.close()
        if self.menu_channel:
            self.menu_channel.close()
        if self.supervisor_channel:
            self.supervisor_channel.close()


class WebUI:
    def __init__(self):
        self.app = Flask(
            __name__,
            template_folder="/app/services/webui/templates",
            static_folder="/app/services/webui/static",
        )
        self.app.secret_key = os.getenv("FLASK_SECRET_KEY", "MAGFest is a donut")

        # Initialize gRPC clients
        self.grpc = GrpcClients()

        # Register routes
        self.app.add_url_rule("/", "index", self.index)
        self.app.add_url_rule("/changemodestr", "change_mode_str", self.change_mode_str, methods=["POST"])
        self.app.add_url_rule("/startgame", "start_game", self.start_game)
        self.app.add_url_rule("/killgame", "kill_game", self.kill_game)
        self.app.add_url_rule("/updateStatus", "update", self.update)
        self.app.add_url_rule("/battery", "battery_status", self.battery_status)
        self.app.add_url_rule("/settings", "settings", self.settings, methods=["GET", "POST"])
        self.app.add_url_rule("/rand<num_teams>", "randomize", self.randomize_teams)
        self.app.add_url_rule("/power", "power", self.power)
        self.app.add_url_rule("/reboot8675309", "reboot", self.reboot)
        self.app.add_url_rule("/shutdown8675309", "shutdown", self.shutdown)
        self.app.add_url_rule("/shutdown", "shutdown_lastscreen", self.shutdown_lastscreen)
        self.app.add_url_rule("/health", "health", self.health)

        # Instrument Flask app
        FlaskInstrumentor().instrument_app(self.app)

    def web_loop(self):
        self.app.run(host="0.0.0.0", port=80, debug=False)

    def web_loop_with_debug(self):
        self.app.run(host="0.0.0.0", port=80, debug=True)

    def index(self):
        """Main page."""
        form = SettingsForm()
        return render_template("joustmania.html", form=form)

    def update(self):
        """Get current menu status."""
        with tracer.start_as_current_span("update_status") as span:
            try:
                # Get menu status
                request = menu_pb2.GetMenuStatusRequest()
                response = self.grpc.menu_stub.GetMenuStatus(request, timeout=2.0)

                if response.success:
                    status = {
                        "state": menu_pb2.MenuState.Name(response.state),
                        "current_selection": response.current_selection,
                        "ready_controller_count": response.ready_controller_count,
                    }
                    span.set_attribute("status.state", status["state"])
                    return status
                logger.error(f"GetMenuStatus failed: {response.error}")
                return {"error": response.error}

            except grpc.RpcError as e:
                logger.error(f"gRPC error in update: {e}")
                return {"error": str(e)}

    def change_mode_str(self):
        """Change game mode selection."""
        with tracer.start_as_current_span("change_mode") as span:
            mode_name = request.form.get("mode_selection")
            if not mode_name:
                return "{'status': 'Error', 'message': 'No mode selected'}"

            span.set_attribute("mode.name", mode_name)

            try:
                # Send ProcessInput to Menu service
                req = menu_pb2.ProcessInputRequest(
                    input_type="web_command",
                    data={"command": "changemodestr", "mode": mode_name},
                )
                response = self.grpc.menu_stub.ProcessInput(req, timeout=2.0)

                if response.success:
                    return "{'status': 'OK'}"
                return f"{{'status': 'Error', 'message': '{response.error}'}}"

            except grpc.RpcError as e:
                logger.error(f"gRPC error in change_mode_str: {e}")
                return f"{{'status': 'Error', 'message': '{str(e)}'}}"

    def start_game(self):
        """Start a game."""
        with tracer.start_as_current_span("start_game"):
            try:
                req = menu_pb2.ProcessInputRequest(input_type="web_command", data={"command": "startgame"})
                response = self.grpc.menu_stub.ProcessInput(req, timeout=2.0)

                if response.success:
                    return "{'status':'OK'}"
                return f"{{'status':'Error','message':'{response.error}'}}"

            except grpc.RpcError as e:
                logger.error(f"gRPC error in start_game: {e}")
                return f"{{'status':'Error','message':'{str(e)}'}}"

    def kill_game(self):
        """Kill current game."""
        with tracer.start_as_current_span("kill_game"):
            try:
                req = menu_pb2.ProcessInputRequest(input_type="web_command", data={"command": "killgame"})
                response = self.grpc.menu_stub.ProcessInput(req, timeout=2.0)

                if response.success:
                    return "{'status':'OK'}"
                return f"{{'status':'Error','message':'{response.error}'}}"

            except grpc.RpcError as e:
                logger.error(f"gRPC error in kill_game: {e}")
                return f"{{'status':'Error','message':'{str(e)}'}}"

    def battery_status(self):
        """Get controller battery status."""
        with tracer.start_as_current_span("battery_status") as span:
            try:
                # Get controllers from ControllerManager
                req = controller_manager_pb2.GetControllersRequest()
                response = self.grpc.controller_stub.GetControllers(req, timeout=2.0)

                if response.success:
                    # Build battery status dict
                    battery_status = {}
                    rssi_display = {}  # Phase 48: RSSI display text
                    rssi_classes = {}  # Phase 48: CSS classes for RSSI

                    for controller in response.controllers:
                        battery_status[controller.serial] = controller.battery

                        # Phase 48: Add RSSI display
                        rssi = controller.rssi
                        if rssi == 0:
                            rssi_display[controller.serial] = "USB"
                            rssi_classes[controller.serial] = "rssi-usb"
                        elif rssi >= -55:
                            rssi_display[controller.serial] = f"{rssi} dBm (Excellent)"
                            rssi_classes[controller.serial] = "rssi-excellent"
                        elif rssi >= -70:
                            rssi_display[controller.serial] = f"{rssi} dBm (Good)"
                            rssi_classes[controller.serial] = "rssi-good"
                        elif rssi >= -80:
                            rssi_display[controller.serial] = f"{rssi} dBm (Fair)"
                            rssi_classes[controller.serial] = "rssi-fair"
                        else:
                            rssi_display[controller.serial] = f"{rssi} dBm (Poor)"
                            rssi_classes[controller.serial] = "rssi-poor"

                    span.set_attribute("controllers.count", len(battery_status))

                    return render_template(
                        "battery.html",
                        battery_status=battery_status,
                        rssi_display=rssi_display,
                        rssi_classes=rssi_classes,
                        levels=Opts.battery_levels_dict(),
                    )
                logger.error(f"GetControllers failed: {response.error}")
                return render_template(
                    "battery.html",
                    battery_status={},
                    rssi_display={},
                    rssi_classes={},
                    levels=Opts.battery_levels_dict(),
                )

            except grpc.RpcError as e:
                logger.error(f"gRPC error in battery_status: {e}")
                return render_template(
                    "battery.html",
                    battery_status={},
                    rssi_display={},
                    rssi_classes={},
                    levels=Opts.battery_levels_dict(),
                )

    def power(self):
        """Power management page."""
        return render_template("power.html")

    def shutdown(self):
        """Shutdown system."""
        with tracer.start_as_current_span("shutdown"):
            Process(target=self.shutdown_proc).start()
            # use redirect to conceal the url for tripping the shutdown
            return redirect(url_for("shutdown_lastscreen"))

    def shutdown_proc(self):
        """Background process for shutdown."""
        sleep(2)
        os.system(
            "sudo kill -3 $(ps aux | grep '[p]iparty' | awk '{print $2}') ; "
            "sudo supervisorctl stop joustmania ; sudo shutdown -H now "
        )

    def shutdown_lastscreen(self):
        """Shutdown confirmation page."""
        return render_template("shutdown.html")

    def health(self):
        """Health check endpoint."""
        return {"status": "healthy", "service": "webui"}, 200

    def reboot(self):
        """Reboot system."""
        with tracer.start_as_current_span("reboot"):
            Process(target=self.reboot_proc).start()
            return redirect(url_for("index"))

    def reboot_proc(self):
        """Background process for reboot."""
        sleep(2)
        os.system(
            " sudo kill -3 $(ps aux | grep '[p]iparty' | awk '{print $2}') ; "
            "sudo supervisorctl stop joustmania ; sudo reboot now "
        )

    def settings(self):
        """Settings page."""
        with tracer.start_as_current_span("settings_page") as span:
            if request.method == "POST":
                # Update settings
                new_settings = SettingsForm(request.form).data
                self.web_settings_update(new_settings)
                return redirect(url_for("settings"))
            # Get current settings from Settings service (Phase 32 - simplified)
            try:
                req = settings_pb2.GetSettingsRequest()
                response = self.grpc.settings_stub.GetSettings(req, timeout=2.0)

                if response.success:
                    # Convert settings map to dict
                    current_settings = dict(response.settings)

                    # Parse random_modes from YAML if needed
                    random_modes_value = current_settings.get("random_modes", "[]")
                    if isinstance(random_modes_value, str):
                        import yaml

                        random_modes_list = yaml.safe_load(random_modes_value)
                    else:
                        random_modes_list = random_modes_value

                    settings_form = SettingsForm(
                        sensitivity=int(current_settings.get("sensitivity", 2)),
                        instructions=current_settings.get("instructions", "true") == "true",
                        num_teams=int(current_settings.get("num_teams", 2)),
                        force_all_start=current_settings.get("force_all_start", "false") == "true",
                        nonstop_time_limit=int(current_settings.get("nonstop_time_limit", 0)),
                        random_modes=random_modes_list,
                        menu_voice=current_settings.get("menu_voice", "ivy"),
                    )

                    span.set_attribute("settings.loaded", True)
                    return render_template("settings.html", form=settings_form, settings=current_settings)
                logger.error(f"GetSettings failed: {response.error}")
                # Return default form
                return render_template("settings.html", form=SettingsForm(), settings={})

            except grpc.RpcError as e:
                logger.error(f"gRPC error in settings: {e}")
                return render_template("settings.html", form=SettingsForm(), settings={})

    def web_settings_update(self, web_settings):
        """Update settings via gRPC (Phase 32 - simplified)."""
        with tracer.start_as_current_span("update_settings") as span:
            # Convert to string map for protobuf
            settings_map = {}
            for key, value in web_settings.items():
                # Skip csrf_token and other form metadata
                if key.startswith("csrf"):
                    continue

                # Handle list values (like random_modes)
                if isinstance(value, list):
                    if not value:  # Empty list
                        settings_map[key] = yaml.dump(["JoustFFA"])  # Default to at least one mode
                    else:
                        settings_map[key] = yaml.dump(value)
                else:
                    settings_map[key] = str(value)

            try:
                # Update settings via gRPC
                req = settings_pb2.UpdateSettingsRequest(settings=settings_map)
                response = self.grpc.settings_stub.UpdateSettings(req, timeout=2.0)

                if response.success:
                    span.set_attribute("settings.updated", True)
                    flash("Settings updated!")
                else:
                    logger.error(f"UpdateSettings failed: {response.error}")
                    flash(f"Error updating settings: {response.error}")

            except grpc.RpcError as e:
                logger.error(f"gRPC error in web_settings_update: {e}")
                flash(f"Error updating settings: {str(e)}")

    def randomize_teams(self, num_teams):
        """Generate random team colors."""
        with tracer.start_as_current_span("randomize_teams") as span:
            if num_teams not in "234":
                return "what are you doing here?"
            num_teams = int(num_teams)
            team_colors = colors.generate_team_colors(num_teams)
            team_colors = [color.name for color in team_colors]
            span.set_attribute("teams.count", num_teams)
            return str(team_colors).replace("'", '"')  # JSON is dumb and demands double quotes


def serve(metrics_port=8000):
    """Start the Web UI service."""
    logger.info("Starting JoustMania Web UI service...")

    # Start Prometheus metrics HTTP server (Phase 38)
    start_http_server(metrics_port)
    logger.info(f"Prometheus metrics available at http://0.0.0.0:{metrics_port}/metrics")

    # Start system metrics collection thread (Phase 38)
    def collect_system_metrics():
        """Background thread to collect system metrics every 10 seconds."""
        import time

        process = psutil.Process()
        while True:
            try:
                metrics.process_cpu_percent.set(process.cpu_percent(interval=None))
                metrics.process_memory_mb.set(process.memory_info().rss / 1024 / 1024)
                metrics.process_threads.set(process.num_threads())
            except Exception as e:
                logger.error(f"Error collecting system metrics: {e}")
            time.sleep(10.0)

    metrics_thread = threading.Thread(target=collect_system_metrics, daemon=True)
    metrics_thread.start()

    webui = WebUI()

    logger.info("Web UI service ready on port 80")

    try:
        webui.web_loop()
    except KeyboardInterrupt:
        logger.info("Shutting down Web UI service...")
        webui.grpc.close_all()


if __name__ == "__main__":
    serve()
