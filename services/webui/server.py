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

# OpenTelemetry instrumentation
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from wtforms import (
    BooleanField,
    FieldList,
    Form,
    SelectField,
    SelectMultipleField,
    widgets,
)

# Import core modules (use types to avoid psmove dependency)
from core.types import Games, Opts

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
from utils import colors

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
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
    move_can_be_admin = BooleanField("Allow Move to change settings")
    play_instructions = BooleanField("Play instructions before game start")
    play_audio = BooleanField("Play audio")
    red_on_kill = SelectField(
        "Kill notification", choices=[(True, "Red"), ("", "Dark")], coerce=bool
    )
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
    mode_selection = SelectField(
        "Mode selection",
        choices=[game.pretty_name for game in Games],
        coerce=str,
    )
    mode_options = [game for game in Games if game not in [Games.Random, Games.JoustTeams]]
    random_modes = MultiCheckboxField(
        "Random Modes", choices=[(game.name, game.pretty_name) for game in mode_options]
    )
    color_lock = BooleanField("Lock team colors")
    color_choices = [(color.name, color.name) for color in colors.team_color_list]
    color_lock_choices = FieldList(
        SelectField("", choices=color_choices, coerce=str), min_entries=9
    )
    random_teams = BooleanField("Randomize teams each round")
    force_all_start = BooleanField(
        "When force starting start with all or only those who pushed trigger"
    )
    random_team_size = SelectField(
        "size of random teams",
        choices=[(2, "2"), (3, "3"), (4, "4"), (5, "5"), (6, "6")],
        coerce=int,
    )


class GrpcClients:
    """Manager for gRPC client connections."""

    def __init__(self):
        # gRPC channel options for better performance and reliability
        channel_options = [
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
        ]

        # Service addresses from environment or defaults
        self.settings_addr = os.getenv("SETTINGS_SERVICE", "settings:50051")
        self.controller_mgr_addr = os.getenv(
            "CONTROLLER_MANAGER_SERVICE", "controller-manager:50052"
        )
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
        self.controller_stub = controller_manager_pb2_grpc.ControllerManagerServiceStub(
            self.controller_channel
        )

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
        self.app.secret_key = "MAGFest is a donut"

        # Initialize gRPC clients
        self.grpc = GrpcClients()

        # Register routes
        self.app.add_url_rule("/", "index", self.index)
        self.app.add_url_rule(
            "/changemodestr", "change_mode_str", self.change_mode_str, methods=["POST"]
        )
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
                req = menu_pb2.ProcessInputRequest(
                    input_type="web_command", data={"command": "startgame"}
                )
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
                req = menu_pb2.ProcessInputRequest(
                    input_type="web_command", data={"command": "killgame"}
                )
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
                    for controller in response.controllers:
                        battery_status[controller.serial] = controller.battery

                    span.set_attribute("controllers.count", len(battery_status))

                    return render_template(
                        "battery.html",
                        battery_status=battery_status,
                        levels=Opts.battery_levels_dict(),
                    )
                logger.error(f"GetControllers failed: {response.error}")
                return render_template(
                    "battery.html", battery_status={}, levels=Opts.battery_levels_dict()
                )

            except grpc.RpcError as e:
                logger.error(f"gRPC error in battery_status: {e}")
                return render_template(
                    "battery.html", battery_status={}, levels=Opts.battery_levels_dict()
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
            "sudo kill -3 $(ps aux | grep '[p]iparty' | awk '{print $2}') ; sudo supervisorctl stop joustmania ; sudo shutdown -H now "
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
            " sudo kill -3 $(ps aux | grep '[p]iparty' | awk '{print $2}') ; sudo supervisorctl stop joustmania ; sudo reboot now "
        )

    def settings(self):
        """Settings page."""
        with tracer.start_as_current_span("settings_page") as span:
            if request.method == "POST":
                # Update settings
                new_settings = SettingsForm(request.form).data
                self.web_settings_update(new_settings)
                return redirect(url_for("settings"))
            # Get current settings from Settings service
            try:
                req = settings_pb2.GetSettingsRequest()
                response = self.grpc.settings_stub.GetSettings(req, timeout=2.0)

                if response.success:
                    # Convert settings map to dict
                    current_settings = dict(response.settings)

                    # Parse color_lock_choices from settings
                    # (assuming it's stored as a complex structure)
                    temp_colors = current_settings.get(
                        "color_lock_choices", {2: [], 3: [], 4: []}
                    )
                    if isinstance(temp_colors, str):
                        # Parse from YAML string if stored that way
                        import yaml

                        temp_colors = yaml.safe_load(temp_colors)

                    temp_colors_flat = (
                        temp_colors.get(2, []) + temp_colors.get(3, []) + temp_colors.get(4, [])
                    )

                    settingsForm = SettingsForm(
                        sensitivity=int(current_settings.get("sensitivity", 1)),
                        red_on_kill=current_settings.get("red_on_kill", "false") == "true",
                        random_team_size=int(current_settings.get("random_team_size", 3)),
                        force_all_start=current_settings.get("force_all_start", "false")
                        == "true",
                        color_lock_choices=temp_colors_flat,
                    )

                    span.set_attribute("settings.loaded", True)
                    return render_template(
                        "settings.html", form=settingsForm, settings=current_settings
                    )
                logger.error(f"GetSettings failed: {response.error}")
                # Return default form
                return render_template("settings.html", form=SettingsForm(), settings={})

            except grpc.RpcError as e:
                logger.error(f"gRPC error in settings: {e}")
                return render_template("settings.html", form=SettingsForm(), settings={})

    def web_settings_update(self, web_settings):
        """Update settings via gRPC."""
        with tracer.start_as_current_span("update_settings") as span:
            colors_are_good = True

            # Process color lock choices
            temp_colors = {
                2: web_settings["color_lock_choices"][0:2],
                3: web_settings["color_lock_choices"][2:5],
                4: web_settings["color_lock_choices"][5:9],
            }

            # Validate no duplicate colors
            for key in temp_colors:
                colorset = temp_colors[key]
                if len(colorset) != len(set(colorset)):
                    colors_are_good = False
                    # Revert to previous colors (would need to fetch from service)
                    break

            # Prepare settings dict
            temp_settings = web_settings.copy()
            temp_settings["color_lock_choices"] = yaml.dump(temp_colors)

            if temp_settings.get("random_modes") == []:
                temp_settings["random_modes"] = [Games.JoustFFA.name]

            # Convert to string map for protobuf
            settings_map = {}
            for key, value in temp_settings.items():
                if isinstance(value, list):
                    settings_map[key] = yaml.dump(value)
                else:
                    settings_map[key] = str(value)

            try:
                # Update settings via gRPC
                req = settings_pb2.UpdateSettingsRequest(settings=settings_map)
                response = self.grpc.settings_stub.UpdateSettings(req, timeout=2.0)

                if response.success:
                    span.set_attribute("settings.updated", True)
                    if colors_are_good:
                        flash("Settings updated!")
                    else:
                        flash("Duplicate color lock colors! Other settings saved.")
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


def serve():
    """Start the Web UI service."""
    logger.info("Starting JoustMania Web UI service...")

    webui = WebUI()

    logger.info("Web UI service ready on port 80")

    try:
        webui.web_loop()
    except KeyboardInterrupt:
        logger.info("Shutting down Web UI service...")
        webui.grpc.close_all()


if __name__ == "__main__":
    serve()
