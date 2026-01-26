/**
 * Game Status Component
 *
 * Displays game state, player counts, and recent events.
 */
export class GameStatus {
  private readonly stateElement: HTMLElement;
  private readonly playerCountElement: HTMLElement;
  private readonly aliveCountElement: HTMLElement;
  private readonly eventLogElement: HTMLElement;

  constructor() {
    this.stateElement = document.getElementById("game-state")!;
    this.playerCountElement = document.getElementById("player-count")!;
    this.aliveCountElement = document.getElementById("alive-count")!;
    this.eventLogElement = document.getElementById("event-log")!;
  }

  updateState(state: string) {
    this.stateElement.innerHTML = `Game: <strong>${state}</strong>`;
  }

  updatePlayerCount(total: number, alive: number) {
    this.playerCountElement.innerHTML = `Players: <strong>${total}</strong> connected`;
    this.aliveCountElement.innerHTML = `Alive: <strong>${alive > 0 ? alive : "-"}</strong>`;
  }

  updateEvents(events: string[]) {
    this.eventLogElement.innerHTML = events
      .map((event) => `<div class="event-item">${event}</div>`)
      .join("");
  }
}
