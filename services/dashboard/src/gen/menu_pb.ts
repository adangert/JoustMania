/**
 * Generated types for menu.proto
 * Compatible with Connect-Web v2.x
 */

// Menu state enum
export enum MenuState {
  STOPPED = 0,
  RUNNING = 1,
  GAME_STARTING = 2,
}

// Start menu request
export interface StartMenuRequest {}

// Start menu response
export interface StartMenuResponse {
  success: boolean;
  error: string;
}

// Stop menu request
export interface StopMenuRequest {}

// Stop menu response
export interface StopMenuResponse {
  success: boolean;
  error: string;
}

// Get menu status request
export interface GetMenuStatusRequest {}

// Get menu status response
export interface GetMenuStatusResponse {
  state: MenuState;
  currentSelection: string;
  readyControllerCount: number;
  success: boolean;
  error: string;
}

// Stream menu events request
export interface StreamMenuEventsRequest {}

// Menu event
export interface MenuEvent {
  eventType: string;
  data: { [key: string]: string };
  timestamp: bigint;
}

// Process input request
export interface ProcessInputRequest {
  inputType: string;
  data: { [key: string]: string };
}

// Process input response
export interface ProcessInputResponse {
  success: boolean;
  error: string;
}

// Service definition for Connect-Web
export const MenuService = {
  typeName: "joustmania.menu.MenuService",
  methods: {
    startMenu: {
      name: "StartMenu",
      kind: "unary" as const,
      I: {} as StartMenuRequest,
      O: {} as StartMenuResponse,
    },
    stopMenu: {
      name: "StopMenu",
      kind: "unary" as const,
      I: {} as StopMenuRequest,
      O: {} as StopMenuResponse,
    },
    getMenuStatus: {
      name: "GetMenuStatus",
      kind: "unary" as const,
      I: {} as GetMenuStatusRequest,
      O: {} as GetMenuStatusResponse,
    },
    streamMenuEvents: {
      name: "StreamMenuEvents",
      kind: "server_streaming" as const,
      I: {} as StreamMenuEventsRequest,
      O: {} as MenuEvent,
    },
    processInput: {
      name: "ProcessInput",
      kind: "unary" as const,
      I: {} as ProcessInputRequest,
      O: {} as ProcessInputResponse,
    },
  },
} as const;
