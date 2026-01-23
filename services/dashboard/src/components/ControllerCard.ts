/**
 * Controller Card Component
 *
 * Displays a single controller with LED color, battery, accelerometer visualization.
 */
import type { GameplayData, RGB } from "../gen/controller_manager_pb.js";

export class ControllerCard {
  element: HTMLElement;
  private serial: string;
  private ledElement: HTMLElement;
  private batteryElement: HTMLElement;
  private accelDot: HTMLElement;
  private statusBadge: HTMLElement;

  constructor(serial: string) {
    this.serial = serial;
    this.element = this.createElement();

    this.ledElement = this.element.querySelector(".led-color")!;
    this.batteryElement = this.element.querySelector(".battery-level")!;
    this.accelDot = this.element.querySelector(".accel-dot")!;
    this.statusBadge = this.element.querySelector(".status-badge")!;
  }

  private createElement(): HTMLElement {
    const card = document.createElement("div");
    card.className = "controller-card connected";
    card.innerHTML = `
      <div class="controller-id">P${this.getShortId()}</div>
      <div class="led-color"></div>
      <div class="battery-bar">
        <div class="battery-level high" style="width: 100%"></div>
      </div>
      <div class="accel-viz">
        <div class="accel-dot"></div>
      </div>
      <div class="status-badge connected">Connected</div>
    `;
    return card;
  }

  private getShortId(): string {
    // Use last 4 characters of serial as short ID
    return this.serial.slice(-4);
  }

  update(data: GameplayData) {
    // Update LED color
    this.updateLedColor(data.color);

    // Update battery level
    this.updateBattery(data.battery);

    // Update accelerometer visualization
    this.updateAccelerometer(data.accel);

    // Update status based on team (team -1 = admin, team 0 = dead)
    this.updateStatus(data.team);
  }

  private updateLedColor(color: RGB | undefined) {
    if (!color) {
      this.ledElement.style.backgroundColor = "#333";
      this.ledElement.style.setProperty("--led-glow", "transparent");
      return;
    }

    const r = color.r;
    const g = color.g;
    const b = color.b;
    const colorStr = `rgb(${r}, ${g}, ${b})`;
    const glowStr = `rgba(${r}, ${g}, ${b}, 0.6)`;

    this.ledElement.style.backgroundColor = colorStr;
    this.ledElement.style.setProperty("--led-glow", glowStr);
    this.ledElement.style.boxShadow = `0 0 20px ${glowStr}`;
  }

  private updateBattery(level: number) {
    // Battery level is 0-5, convert to percentage
    const percent = Math.min(100, Math.max(0, (level / 5) * 100));
    this.batteryElement.style.width = `${percent}%`;

    // Update color based on level
    this.batteryElement.classList.remove("high", "medium", "low");
    if (percent > 50) {
      this.batteryElement.classList.add("high");
    } else if (percent > 20) {
      this.batteryElement.classList.add("medium");
    } else {
      this.batteryElement.classList.add("low");
    }
  }

  private updateAccelerometer(accel: { x: number; y: number; z: number } | undefined) {
    if (!accel) return;

    // Map accelerometer values to dot position
    // Typical values are -1 to 1 g, multiply for visual effect
    const maxOffset = 15; // pixels from center
    const x = Math.max(-maxOffset, Math.min(maxOffset, accel.x * 10));
    const y = Math.max(-maxOffset, Math.min(maxOffset, accel.z * 10)); // Use z for vertical

    this.accelDot.style.transform = `translate(calc(-50% + ${x}px), calc(-50% + ${y}px))`;
  }

  private updateStatus(team: number) {
    this.element.classList.remove("alive", "dead", "admin");
    this.statusBadge.classList.remove("connected", "alive", "dead", "admin");

    if (team === -1) {
      // Admin mode
      this.element.classList.add("admin");
      this.statusBadge.classList.add("admin");
      this.statusBadge.textContent = "Admin";
    } else if (team === 0) {
      // Dead or not in game
      this.element.classList.add("dead");
      this.statusBadge.classList.add("dead");
      this.statusBadge.textContent = "Dead";
    } else {
      // Alive
      this.element.classList.add("alive");
      this.statusBadge.classList.add("alive");
      this.statusBadge.textContent = team > 0 ? `Team ${team}` : "Alive";
    }
  }

  remove() {
    this.element.remove();
  }
}
