/**
 * Controls Component
 *
 * Game mode selection and start/stop controls.
 */
interface ControlsOptions {
  onStartGame: () => void;
  onStopGame: () => void;
  onModeChange: (mode: string) => void;
}

export class Controls {
  private modeSelect: HTMLSelectElement;
  private startBtn: HTMLButtonElement;
  private stopBtn: HTMLButtonElement;
  private options: ControlsOptions;

  constructor(options: ControlsOptions) {
    this.options = options;

    this.modeSelect = document.getElementById("game-mode") as HTMLSelectElement;
    this.startBtn = document.getElementById("start-btn") as HTMLButtonElement;
    this.stopBtn = document.getElementById("stop-btn") as HTMLButtonElement;

    this.setupEventListeners();
  }

  private setupEventListeners() {
    this.modeSelect.addEventListener("change", () => {
      this.options.onModeChange(this.modeSelect.value);
    });

    this.startBtn.addEventListener("click", () => {
      this.options.onStartGame();
    });

    this.stopBtn.addEventListener("click", () => {
      this.options.onStopGame();
    });
  }

  getSelectedMode(): string {
    return this.modeSelect.value;
  }

  setGameRunning(running: boolean) {
    this.startBtn.disabled = running;
    this.stopBtn.disabled = !running;
    this.modeSelect.disabled = running;
  }
}
