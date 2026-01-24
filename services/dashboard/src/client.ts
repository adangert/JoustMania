/**
 * Simple Connect-protocol client for JoustMania services
 * Uses fetch with JSON encoding (Connect protocol supports JSON)
 */

import type {
  GameplayStreamRequest,
  GameplayDataUpdate,
} from "./gen/controller_manager_pb.js";
import type {
  ForceEndGameRequest,
  ForceEndGameResponse,
  StreamEventsRequest,
  GameEvent,
} from "./gen/game_coordinator_pb.js";
import type {
  GetSettingsRequest,
  GetSettingsResponse,
  GetSettingRequest,
  GetSettingResponse,
  UpdateSettingRequest,
  UpdateSettingResponse,
} from "./gen/settings_pb.js";
import type {
  ProcessInputRequest,
  ProcessInputResponse,
} from "./gen/menu_pb.js";

const BASE_URL = import.meta.env.DEV ? "" : window.location.origin;

// Generic unary call
async function unaryCall<Req, Res>(
  service: string,
  method: string,
  request: Req
): Promise<Res> {
  const url = `${BASE_URL}/${service}/${method}`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/connect+json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`RPC failed: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

// Generic server streaming call (uses Server-Sent Events style)
async function* serverStream<Req, Res>(
  service: string,
  method: string,
  request: Req
): AsyncGenerator<Res> {
  const url = `${BASE_URL}/${service}/${method}`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/connect+json",
      Accept: "application/connect+json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`RPC failed: ${response.status} ${response.statusText}`);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("No response body");
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Parse newline-delimited JSON messages
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.trim()) {
        try {
          const msg = JSON.parse(line);
          // Connect protocol wraps messages in { "result": ... } for streaming
          yield (msg.result || msg) as Res;
        } catch {
          // Skip malformed lines
        }
      }
    }
  }
}

// Controller Manager Client
export const controllerClient = {
  streamGameplayData(request: GameplayStreamRequest) {
    return serverStream<GameplayStreamRequest, GameplayDataUpdate>(
      "joustmania.controller_manager.ControllerManagerService",
      "StreamGameplayData",
      request
    );
  },
};

// Game Coordinator Client
export const gameClient = {
  forceEndGame(request: ForceEndGameRequest): Promise<ForceEndGameResponse> {
    return unaryCall(
      "joustmania.game_coordinator.GameCoordinatorService",
      "ForceEndGame",
      request
    );
  },
  streamGameEvents(request: StreamEventsRequest) {
    return serverStream<StreamEventsRequest, GameEvent>(
      "joustmania.game_coordinator.GameCoordinatorService",
      "StreamGameEvents",
      request
    );
  },
};

// Settings Client
export const settingsClient = {
  getSettings(request: GetSettingsRequest): Promise<GetSettingsResponse> {
    return unaryCall(
      "joustmania.settings.SettingsService",
      "GetSettings",
      request
    );
  },
  getSetting(request: GetSettingRequest): Promise<GetSettingResponse> {
    return unaryCall(
      "joustmania.settings.SettingsService",
      "GetSetting",
      request
    );
  },
  updateSetting(request: UpdateSettingRequest): Promise<UpdateSettingResponse> {
    return unaryCall(
      "joustmania.settings.SettingsService",
      "UpdateSetting",
      request
    );
  },
};

// Menu Client
export const menuClient = {
  processInput(request: ProcessInputRequest): Promise<ProcessInputResponse> {
    return unaryCall(
      "joustmania.menu.MenuService",
      "ProcessInput",
      request
    );
  },
};
