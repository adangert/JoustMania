/**
 * JoustMania Dashboard - Main Entry Point
 *
 * Real-time controller visualization and game controls using Connect-Web.
 */
import { controllerClient, gameClient, menuClient, settingsClient } from "./client.js";
import { ControllerGrid } from "./components/ControllerGrid.js";
import { GameStatus } from "./components/GameStatus.js";
import { Controls } from "./components/Controls.js";
import type { GameplayData } from "./gen/controller_manager_pb.js";

// State
interface AppState {
  controllers: Map<string, GameplayData>;
  gameState: string;
  alivePlayers: number;
  totalPlayers: number;
  events: string[];
  isStreaming: boolean;
}

const state: AppState = {
  controllers: new Map(),
  gameState: "Idle",
  alivePlayers: 0,
  totalPlayers: 0,
  events: [],
  isStreaming: false,
};

// Components
let controllerGrid: ControllerGrid;
let gameStatus: GameStatus;
let controls: Controls;

// Initialize the dashboard
async function init() {
  console.log("JoustMania Dashboard initializing...");

  // Initialize components
  controllerGrid = new ControllerGrid("controller-grid");
  gameStatus = new GameStatus();
  controls = new Controls({
    onStartGame: handleStartGame,
    onStopGame: handleStopGame,
    onModeChange: handleModeChange,
  });

  // Set up tab navigation
  setupTabs();

  // Set up settings modal
  setupSettingsModal();

  // Start streaming controller data
  startControllerStream();

  // Start streaming game events
  startGameEventStream();

  console.log("Dashboard initialized");
}

// Tab navigation
function setupTabs() {
  const tabButtons = document.querySelectorAll(".tab-btn");
  const tabPanels = document.querySelectorAll(".tab-panel");

  tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const tabId = (btn as HTMLElement).dataset.tab;
      if (!tabId) return;

      // Update button states
      tabButtons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");

      // Update panel visibility
      tabPanels.forEach((panel) => {
        panel.classList.remove("active");
        if (panel.id === `tab-${tabId}`) {
          panel.classList.add("active");
        }
      });

      console.log(`Switched to tab: ${tabId}`);
    });
  });
}

// Stream controller data at 30Hz
async function startControllerStream() {
  if (state.isStreaming) return;
  state.isStreaming = true;

  controllerGrid.setLoading(false);

  try {
    const stream = controllerClient.streamGameplayData({
      updateFrequencyHz: 30,
    });

    for await (const update of stream) {
      // Update controller state
      state.controllers.clear();
      for (const controller of update.controllers) {
        state.controllers.set(controller.serial, controller);
      }

      state.totalPlayers = update.controllers.length;

      // Render controllers
      controllerGrid.render(Array.from(state.controllers.values()));
      gameStatus.updatePlayerCount(state.totalPlayers, state.alivePlayers);
    }
  } catch (error) {
    console.error("Controller stream error:", error);
    state.isStreaming = false;
    controllerGrid.setError("Connection lost. Retrying...");

    // Retry after delay
    setTimeout(startControllerStream, 2000);
  }
}

// Stream game events
async function startGameEventStream() {
  try {
    const stream = gameClient.streamGameEvents({});

    for await (const event of stream) {
      handleGameEvent(event);
    }
  } catch (error) {
    console.error("Game event stream error:", error);
    // Retry after delay
    setTimeout(startGameEventStream, 2000);
  }
}

// Handle game events
function handleGameEvent(event: { eventType: string; data: { [key: string]: string }; timestamp: bigint }) {
  const eventType = event.eventType;
  const data = event.data;

  // Update state based on event type
  switch (eventType) {
    case "game_start":
      state.gameState = "Running";
      state.alivePlayers = state.totalPlayers;
      controls.setGameRunning(true);
      addEvent("Game started!");
      break;

    case "game_end": {
      state.gameState = "Ended";
      controls.setGameRunning(false);
      const winner = data["winner"] || "Unknown";
      addEvent(`Game ended! Winner: ${winner}`);
      break;
    }

    case "player_death": {
      state.alivePlayers = Math.max(0, state.alivePlayers - 1);
      const player = data["serial"]?.slice(-4) || "???";
      addEvent(`Player ${player} eliminated`);
      break;
    }

    case "countdown":
      state.gameState = "Starting";
      addEvent("Countdown...");
      break;

    default:
      console.log("Unknown event:", eventType, data);
  }

  gameStatus.updateState(state.gameState);
  gameStatus.updatePlayerCount(state.totalPlayers, state.alivePlayers);
}

// Add event to the log
function addEvent(text: string) {
  state.events.unshift(text);
  if (state.events.length > 5) {
    state.events.pop();
  }
  gameStatus.updateEvents(state.events);
}

// Game controls
async function handleStartGame() {
  const mode = controls.getSelectedMode();
  console.log("Starting game:", mode);

  try {
    // Use menu service to process start command
    await menuClient.processInput({
      inputType: "web_command",
      data: { command: "start_game", mode },
    });
    addEvent(`Starting ${mode}...`);
  } catch (error) {
    console.error("Failed to start game:", error);
    addEvent("Failed to start game");
  }
}

async function handleStopGame() {
  console.log("Stopping game");

  try {
    await gameClient.forceEndGame({
      reason: "Dashboard stop button",
    });
    addEvent("Game stopped");
  } catch (error) {
    console.error("Failed to stop game:", error);
    addEvent("Failed to stop game");
  }
}

function handleModeChange(mode: string) {
  console.log("Mode changed to:", mode);
}

// Settings modal
function setupSettingsModal() {
  const settingsBtn = document.getElementById("settings-btn");
  const settingsModal = document.getElementById("settings-modal");
  const closeSettings = document.getElementById("close-settings");

  settingsBtn?.addEventListener("click", async () => {
    settingsModal?.classList.remove("hidden");
    await loadSettings();
  });

  closeSettings?.addEventListener("click", () => {
    settingsModal?.classList.add("hidden");
  });

  settingsModal?.addEventListener("click", (e) => {
    if (e.target === settingsModal) {
      settingsModal.classList.add("hidden");
    }
  });
}

async function loadSettings() {
  const settingsList = document.getElementById("settings-list");
  if (!settingsList) return;

  try {
    const response = await settingsClient.getSettings({});
    if (!response.success) {
      settingsList.innerHTML = `<div class="error">Failed to load settings: ${response.error}</div>`;
      return;
    }

    settingsList.innerHTML = "";
    for (const [key, value] of Object.entries(response.settings)) {
      const item = document.createElement("div");
      item.className = "setting-item";
      item.innerHTML = `
        <label>${formatSettingKey(key)}</label>
        <input type="text" value="${value}" data-key="${key}" />
      `;
      settingsList.appendChild(item);

      // Handle setting change
      const input = item.querySelector("input");
      input?.addEventListener("change", async (e) => {
        const target = e.target as HTMLInputElement;
        const settingKey = target.dataset.key!;
        const newValue = target.value;

        try {
          await settingsClient.updateSetting({
            key: settingKey,
            value: newValue,
            source: "dashboard",
          });
        } catch (error) {
          console.error("Failed to update setting:", error);
          // Revert to old value
          const oldResponse = await settingsClient.getSetting({ key: settingKey });
          if (oldResponse.success) {
            target.value = oldResponse.value;
          }
        }
      });
    }
  } catch (error) {
    console.error("Failed to load settings:", error);
    settingsList.innerHTML = '<div class="error">Failed to connect to settings service</div>';
  }
}

function formatSettingKey(key: string): string {
  // Convert snake_case or camelCase to Title Case
  return key
    .replaceAll("_", " ")
    .replace(/([A-Z])/g, " $1")
    .replace(/^./, (str) => str.toUpperCase())
    .trim();
}

// Start the app
await init();
