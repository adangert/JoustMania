"""
JoustMania Web UI Microservice

Provides HTTP/web interface for JoustMania. Acts as a gRPC client to
communicate with backend microservices.

Part of Phase 9 (Architecture Cleanup).
"""

import logging
import os
from multiprocessing import Process
from time import sleep

import grpc
import yaml
from flask import Flask, flash, redirect, render_template, request, url_for
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
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
from lib.system_metrics import start_system_metrics_collector_thread
from lib.types import Games
from proto import (
    menu_pb2,
    menu_pb2_grpc,
    settings_pb2,
    settings_pb2_grpc,
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
        "Random Modes (for Random game mode)",
        choices=[(game.name, game.pretty_name) for game in mode_options],
    )
    menu_voice = SelectField(
        "Menu voice pack",
        choices=[
            ("ivy", "Ivy"),
            ("aaron", "Aaron"),
        ],
        coerce=str,
    )
    play_audio = BooleanField("Enable audio playback")
    current_game = SelectField(
        "Current game mode",
        choices=[(game.name, game.pretty_name) for game in Games],
        coerce=str,
    )
    random_teams = BooleanField("Randomize team assignments (vs sequential)")


class GrpcClients:
    """Manager for gRPC client connections."""

    def __init__(self):
        # Service addresses from environment or defaults
        self.settings_addr = os.getenv("SETTINGS_SERVICE", "settings:50051")
        self.menu_addr = os.getenv("MENU_SERVICE", "menu:50054")

        # Initialize channels and stubs
        self.settings_channel = None
        self.settings_stub = None
        self.menu_channel = None
        self.menu_stub = None

        self.connect_all()

    def connect_all(self):
        """Establish connections to all services."""
        logger.info("Connecting to gRPC services...")

        # Settings service
        self.settings_channel = grpc.insecure_channel(self.settings_addr)
        self.settings_stub = settings_pb2_grpc.SettingsServiceStub(self.settings_channel)

        # Menu service
        self.menu_channel = grpc.insecure_channel(self.menu_addr)
        self.menu_stub = menu_pb2_grpc.MenuServiceStub(self.menu_channel)

        logger.info("Connected to all gRPC services")

    def close_all(self):
        """Close all gRPC connections."""
        logger.info("Closing gRPC connections...")
        if self.settings_channel:
            self.settings_channel.close()
        if self.menu_channel:
            self.menu_channel.close()


class WebUI:
    def __init__(self):
        self.app = Flask(
            __name__,
            template_folder="/app/services/webui/templates",
            static_folder="/app/services/webui/static",
        )
        self.app.secret_key = os.getenv("FLASK_SECRET_KEY", "MAGFest is a donut")
        self.port = int(os.getenv("WEBUI_PORT", "80"))

        # Initialize gRPC clients
        self.grpc = GrpcClients()

        # Register routes
        self.app.add_url_rule("/", "index", self.index)
        self.app.add_url_rule("/changemodestr", "change_mode_str", self.change_mode_str, methods=["POST"])
        self.app.add_url_rule("/startgame", "start_game", self.start_game)
        self.app.add_url_rule("/killgame", "kill_game", self.kill_game)
        self.app.add_url_rule("/updateStatus", "update", self.update)
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
        self.app.run(host="0.0.0.0", port=self.port, debug=False)

    def web_loop_with_debug(self):
        self.app.run(host="0.0.0.0", port=self.port, debug=True)

    def index(self):
        """Main page."""
        form = SettingsForm()
        return render_template("joustmania.html", form=form)

    def update(self):
        """Get current menu status (deprecated - WebUI is deprecated)."""
        # WebUI is deprecated - GetMenuStatus RPC has been removed
        # This endpoint is kept for backwards compatibility but returns stub data
        return {
            "state": "DEPRECATED",
            "current_selection": "",
            "ready_controller_count": 0,
            "error": "WebUI is deprecated - use StreamMenuEvents instead",
        }

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
                        play_audio=current_settings.get("play_audio", "true") == "true",
                        current_game=current_settings.get("current_game", "JoustFFA"),
                        random_teams=current_settings.get("random_teams", "true") == "true",
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

    # Start system metrics collection (Phase 61: extracted to lib/system_metrics.py)
    start_system_metrics_collector_thread(
        cpu_gauge=metrics.process_cpu_percent,
        memory_gauge=metrics.process_memory_mb,
        threads_gauge=metrics.process_threads,
    )

    webui = WebUI()

    logger.info(f"Web UI service ready on port {webui.port}")

    try:
        webui.web_loop()
    except KeyboardInterrupt:
        logger.info("Shutting down Web UI service...")
        webui.grpc.close_all()


if __name__ == "__main__":
    serve()
