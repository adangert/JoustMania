/**
 * AccelWaveform Component
 *
 * Canvas-based real-time acceleration waveform visualization.
 * Uses a ring buffer to store 10 seconds of 100Hz data for smooth rendering.
 */

export interface AccelSample {
  timestamp: number;
  x: number;
  y: number;
  z: number;
  magnitude: number;
}

export interface AccelWaveformOptions {
  /** Width of the canvas */
  width?: number;
  /** Height of the canvas */
  height?: number;
  /** Duration in seconds to display */
  durationSeconds?: number;
  /** Samples per second (Hz) */
  sampleRate?: number;
  /** Acceleration threshold for warning (yellow line) */
  warningThreshold?: number;
  /** Acceleration threshold for danger (red line) */
  dangerThreshold?: number;
  /** Show X, Y, Z components */
  showComponents?: boolean;
  /** Show magnitude */
  showMagnitude?: boolean;
}

const DEFAULT_OPTIONS: Required<AccelWaveformOptions> = {
  width: 600,
  height: 200,
  durationSeconds: 10,
  sampleRate: 100,
  warningThreshold: 1.5,
  dangerThreshold: 2.5,
  showComponents: false,
  showMagnitude: true,
};

/**
 * Ring buffer for efficient sample storage
 */
class RingBuffer<T> {
  private buffer: T[];
  private head: number = 0;
  private count: number = 0;

  constructor(public readonly capacity: number) {
    this.buffer = new Array(capacity);
  }

  push(item: T): void {
    this.buffer[this.head] = item;
    this.head = (this.head + 1) % this.capacity;
    if (this.count < this.capacity) {
      this.count++;
    }
  }

  get length(): number {
    return this.count;
  }

  /**
   * Get item at index (0 = oldest, length-1 = newest)
   */
  get(index: number): T | undefined {
    if (index < 0 || index >= this.count) return undefined;
    const bufferIndex = (this.head - this.count + index + this.capacity) % this.capacity;
    return this.buffer[bufferIndex];
  }

  /**
   * Get all items as array (oldest to newest)
   */
  toArray(): T[] {
    const result: T[] = [];
    for (let i = 0; i < this.count; i++) {
      const item = this.get(i);
      if (item !== undefined) {
        result.push(item);
      }
    }
    return result;
  }

  clear(): void {
    this.head = 0;
    this.count = 0;
  }
}

export class AccelWaveform {
  element: HTMLElement;
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private options: Required<AccelWaveformOptions>;
  private samples: RingBuffer<AccelSample>;
  private serial: string;
  private animationFrame: number | null = null;
  private lastRenderTime: number = 0;

  // Colors
  private readonly COLORS = {
    background: "#1a1a2e",
    grid: "#2a2a4e",
    magnitude: "#00ff88",
    x: "#ff6b6b",
    y: "#4ecdc4",
    z: "#45b7d1",
    warning: "#ffd93d",
    danger: "#ff6b6b",
    text: "#ffffff",
  };

  constructor(serial: string, options: AccelWaveformOptions = {}) {
    this.serial = serial;
    this.options = { ...DEFAULT_OPTIONS, ...options };

    // Calculate buffer capacity
    const capacity = this.options.durationSeconds * this.options.sampleRate;
    this.samples = new RingBuffer(capacity);

    this.element = this.createElement();
    this.canvas = this.element.querySelector("canvas")!;
    this.ctx = this.canvas.getContext("2d")!;

    // Set canvas size
    this.canvas.width = this.options.width;
    this.canvas.height = this.options.height;

    // Start render loop
    this.startRenderLoop();
  }

  private createElement(): HTMLElement {
    const container = document.createElement("div");
    container.className = "accel-waveform";
    container.innerHTML = `
      <div class="waveform-header">
        <span class="waveform-serial">Controller ${this.serial.slice(-4)}</span>
        <span class="waveform-value">--</span>
      </div>
      <canvas></canvas>
      <div class="waveform-legend">
        <span class="legend-item magnitude">Magnitude</span>
        ${this.options.showComponents ? `
          <span class="legend-item x">X</span>
          <span class="legend-item y">Y</span>
          <span class="legend-item z">Z</span>
        ` : ""}
      </div>
    `;
    return container;
  }

  /**
   * Add a sample to the waveform
   */
  addSample(sample: Omit<AccelSample, "timestamp">): void {
    this.samples.push({
      ...sample,
      timestamp: performance.now(),
    });

    // Update current value display
    const valueEl = this.element.querySelector(".waveform-value");
    if (valueEl) {
      valueEl.textContent = `${sample.magnitude.toFixed(2)}g`;
    }
  }

  /**
   * Add acceleration data from GameplayData
   */
  addFromGameplayData(accel: { x: number; y: number; z: number }): void {
    const magnitude = Math.sqrt(accel.x ** 2 + accel.y ** 2 + accel.z ** 2);
    this.addSample({
      x: accel.x,
      y: accel.y,
      z: accel.z,
      magnitude,
    });
  }

  private startRenderLoop(): void {
    const render = (timestamp: number) => {
      // Throttle to 60fps
      if (timestamp - this.lastRenderTime >= 16) {
        this.render();
        this.lastRenderTime = timestamp;
      }
      this.animationFrame = requestAnimationFrame(render);
    };
    this.animationFrame = requestAnimationFrame(render);
  }

  private render(): void {
    const { width, height } = this.options;
    const ctx = this.ctx;

    // Clear canvas
    ctx.fillStyle = this.COLORS.background;
    ctx.fillRect(0, 0, width, height);

    // Draw grid
    this.drawGrid();

    // Draw thresholds
    this.drawThresholds();

    // Draw waveforms
    const samples = this.samples.toArray();
    if (samples.length < 2) return;

    if (this.options.showMagnitude) {
      this.drawWaveform(samples, "magnitude", this.COLORS.magnitude);
    }

    if (this.options.showComponents) {
      this.drawWaveform(samples, "x", this.COLORS.x);
      this.drawWaveform(samples, "y", this.COLORS.y);
      this.drawWaveform(samples, "z", this.COLORS.z);
    }
  }

  private drawGrid(): void {
    const { width, height } = this.options;
    const ctx = this.ctx;

    ctx.strokeStyle = this.COLORS.grid;
    ctx.lineWidth = 1;

    // Horizontal lines (every 0.5g)
    const maxG = 4;
    const gStep = 0.5;
    for (let g = 0; g <= maxG; g += gStep) {
      const y = this.gToY(g);
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }

    // Vertical lines (every second)
    const secondWidth = width / this.options.durationSeconds;
    for (let s = 0; s <= this.options.durationSeconds; s++) {
      const x = width - s * secondWidth;
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }

    // Y-axis labels
    ctx.fillStyle = this.COLORS.text;
    ctx.font = "10px monospace";
    ctx.textAlign = "left";
    for (let g = 0; g <= maxG; g++) {
      const y = this.gToY(g);
      ctx.fillText(`${g}g`, 2, y - 2);
    }
  }

  private drawThresholds(): void {
    const { width, warningThreshold, dangerThreshold } = this.options;
    const ctx = this.ctx;

    // Warning threshold
    ctx.strokeStyle = this.COLORS.warning;
    ctx.lineWidth = 1;
    ctx.setLineDash([5, 5]);
    const warningY = this.gToY(warningThreshold);
    ctx.beginPath();
    ctx.moveTo(0, warningY);
    ctx.lineTo(width, warningY);
    ctx.stroke();

    // Danger threshold
    ctx.strokeStyle = this.COLORS.danger;
    const dangerY = this.gToY(dangerThreshold);
    ctx.beginPath();
    ctx.moveTo(0, dangerY);
    ctx.lineTo(width, dangerY);
    ctx.stroke();

    ctx.setLineDash([]);
  }

  private drawWaveform(
    samples: AccelSample[],
    field: "x" | "y" | "z" | "magnitude",
    color: string
  ): void {
    const { width, durationSeconds } = this.options;
    const ctx = this.ctx;

    if (samples.length < 2) return;

    ctx.strokeStyle = color;
    ctx.lineWidth = field === "magnitude" ? 2 : 1;
    ctx.beginPath();

    const now = performance.now();
    const durationMs = durationSeconds * 1000;
    let firstPoint = true;

    for (const sample of samples) {
      const age = now - sample.timestamp;
      if (age > durationMs) continue;

      const x = width - (age / durationMs) * width;
      const y = this.gToY(Math.abs(sample[field]));

      if (firstPoint) {
        ctx.moveTo(x, y);
        firstPoint = false;
      } else {
        ctx.lineTo(x, y);
      }
    }

    ctx.stroke();
  }

  private gToY(g: number): number {
    // Map 0-4g to height-0 (inverted Y)
    const maxG = 4;
    const margin = 20;
    const plotHeight = this.options.height - margin * 2;
    return margin + plotHeight * (1 - Math.min(g, maxG) / maxG);
  }

  /**
   * Clean up resources
   */
  destroy(): void {
    if (this.animationFrame !== null) {
      cancelAnimationFrame(this.animationFrame);
    }
    this.element.remove();
  }

  /**
   * Clear all samples
   */
  clear(): void {
    this.samples.clear();
  }
}

/**
 * CSS styles for the waveform component
 */
export const ACCEL_WAVEFORM_STYLES = `
.accel-waveform {
  background: #1a1a2e;
  border-radius: 8px;
  padding: 10px;
  margin: 10px 0;
}

.waveform-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 5px;
  font-size: 12px;
}

.waveform-serial {
  color: #888;
}

.waveform-value {
  color: #00ff88;
  font-weight: bold;
}

.waveform-legend {
  display: flex;
  gap: 15px;
  margin-top: 5px;
  font-size: 10px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.legend-item::before {
  content: '';
  display: inline-block;
  width: 12px;
  height: 3px;
  border-radius: 2px;
}

.legend-item.magnitude::before { background: #00ff88; }
.legend-item.x::before { background: #ff6b6b; }
.legend-item.y::before { background: #4ecdc4; }
.legend-item.z::before { background: #45b7d1; }
`;
