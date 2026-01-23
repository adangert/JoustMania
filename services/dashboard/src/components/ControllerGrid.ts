/**
 * Controller Grid Component
 *
 * Displays a grid of controller cards with real-time updates.
 */
import { ControllerCard } from "./ControllerCard.js";
import type { GameplayData } from "../gen/controller_manager_pb.js";

export class ControllerGrid {
  private container: HTMLElement;
  private cards: Map<string, ControllerCard> = new Map();
  private isLoading = true;

  constructor(containerId: string) {
    const container = document.getElementById(containerId);
    if (!container) {
      throw new Error(`Container element not found: ${containerId}`);
    }
    this.container = container;
  }

  setLoading(loading: boolean) {
    this.isLoading = loading;
    if (loading) {
      this.container.innerHTML = '<div class="loading">Connecting to controller manager...</div>';
    }
  }

  setError(message: string) {
    this.container.innerHTML = `<div class="loading">${message}</div>`;
  }

  render(controllers: GameplayData[]) {
    if (this.isLoading) {
      this.isLoading = false;
      this.container.innerHTML = "";
    }

    // Track which controllers are still present
    const presentSerials = new Set(controllers.map((c) => c.serial));

    // Remove cards for disconnected controllers
    for (const [serial, card] of this.cards.entries()) {
      if (!presentSerials.has(serial)) {
        card.remove();
        this.cards.delete(serial);
      }
    }

    // Update or create cards for each controller
    for (const controller of controllers) {
      let card = this.cards.get(controller.serial);

      if (!card) {
        // Create new card
        card = new ControllerCard(controller.serial);
        this.container.appendChild(card.element);
        this.cards.set(controller.serial, card);
      }

      // Update card with new data
      card.update(controller);
    }

    // Show empty state if no controllers
    if (controllers.length === 0 && !this.isLoading) {
      if (!this.container.querySelector(".loading")) {
        this.container.innerHTML = '<div class="loading">No controllers connected</div>';
      }
    }
  }
}
