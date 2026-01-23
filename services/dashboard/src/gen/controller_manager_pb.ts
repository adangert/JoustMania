/**
 * Generated types for controller_manager.proto
 * Compatible with Connect-Web v2.x
 */

// RGB color
export interface RGB {
  r: number;
  g: number;
  b: number;
}

// Vector3 for accelerometer/gyro data
export interface Vector3 {
  x: number;
  y: number;
  z: number;
}

// Gameplay data for a single controller
export interface GameplayData {
  serial: string;
  moveNum: number;
  battery: number;
  team: number;
  color?: RGB;
  accel?: Vector3;
  gyro?: Vector3;
  rssi: number;
}

// Gameplay data update with all controllers
export interface GameplayDataUpdate {
  controllers: GameplayData[];
  timestamp: bigint;
}

// Gameplay stream request
export interface GameplayStreamRequest {
  updateFrequencyHz: number;
}

// Service definition for Connect-Web
export const ControllerManagerService = {
  typeName: "joustmania.controller_manager.ControllerManagerService",
  methods: {
    streamGameplayData: {
      name: "StreamGameplayData",
      kind: "server_streaming" as const,
      I: {} as GameplayStreamRequest,
      O: {} as GameplayDataUpdate,
    },
  },
} as const;
