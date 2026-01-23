/**
 * Generated types for settings.proto
 * Compatible with Connect-Web v2.x
 */

// Get settings request
export interface GetSettingsRequest {}

// Get settings response
export interface GetSettingsResponse {
  settings: { [key: string]: string };
  success: boolean;
  error: string;
}

// Get setting request
export interface GetSettingRequest {
  key: string;
}

// Get setting response
export interface GetSettingResponse {
  key: string;
  value: string;
  success: boolean;
  error: string;
}

// Update setting request
export interface UpdateSettingRequest {
  key: string;
  value: string;
  source: string;
}

// Update setting response
export interface UpdateSettingResponse {
  success: boolean;
  error: string;
  oldValue: string;
  newValue: string;
}

// Subscribe request
export interface SubscribeRequest {
  keys: string[];
}

// Setting change event
export interface SettingChangeEvent {
  key: string;
  oldValue: string;
  newValue: string;
  source: string;
  timestamp: bigint;
}

// Service definition for Connect-Web
export const SettingsService = {
  typeName: "joustmania.settings.SettingsService",
  methods: {
    getSettings: {
      name: "GetSettings",
      kind: "unary" as const,
      I: {} as GetSettingsRequest,
      O: {} as GetSettingsResponse,
    },
    getSetting: {
      name: "GetSetting",
      kind: "unary" as const,
      I: {} as GetSettingRequest,
      O: {} as GetSettingResponse,
    },
    updateSetting: {
      name: "UpdateSetting",
      kind: "unary" as const,
      I: {} as UpdateSettingRequest,
      O: {} as UpdateSettingResponse,
    },
    subscribeToChanges: {
      name: "SubscribeToChanges",
      kind: "server_streaming" as const,
      I: {} as SubscribeRequest,
      O: {} as SettingChangeEvent,
    },
  },
} as const;
