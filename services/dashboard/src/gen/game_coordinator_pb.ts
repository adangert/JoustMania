/**
 * Generated types for game_coordinator.proto
 * Compatible with Connect-Web v2.x
 */

// Game state enum
export enum GameState {
  IDLE = 0,
  STARTING = 1,
  RUNNING = 2,
  ENDING = 3,
  ENDED = 4,
}

// Player info
export interface Player {
  serial: string;
  team: number;
  alive: boolean;
  score: number;
}

// Start game request
export interface StartGameRequest {
  gameName: string;
  players: Player[];
  settings: { [key: string]: string };
}

// Start game response
export interface StartGameResponse {
  success: boolean;
  error: string;
  gameId: string;
}

// Force end game request
export interface ForceEndGameRequest {
  reason: string;
}

// Force end game response
export interface ForceEndGameResponse {
  success: boolean;
  error: string;
}

// Stream events request
export interface StreamEventsRequest {}

// Game event
export interface GameEvent {
  eventType: string;
  data: { [key: string]: string };
  timestamp: bigint;
}

// Service definition for Connect-Web
export const GameCoordinatorService = {
  typeName: "joustmania.game_coordinator.GameCoordinatorService",
  methods: {
    startGame: {
      name: "StartGame",
      kind: "unary" as const,
      I: {} as StartGameRequest,
      O: {} as StartGameResponse,
    },
    forceEndGame: {
      name: "ForceEndGame",
      kind: "unary" as const,
      I: {} as ForceEndGameRequest,
      O: {} as ForceEndGameResponse,
    },
    streamGameEvents: {
      name: "StreamGameEvents",
      kind: "server_streaming" as const,
      I: {} as StreamEventsRequest,
      O: {} as GameEvent,
    },
  },
} as const;
