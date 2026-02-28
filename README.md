# Presto Bézier Swarm: Modular Engine (Dan Dare)

[![Build Status](https://github.com/kv244/Presto8Bit/actions/workflows/build.yml/badge.svg)](https://github.com/kv244/Presto8Bit/actions/workflows/build.yml)

A high-performance, object-oriented 2D space shooter engine for the **Pimoroni Presto (RP2350)**. This project demonstrates advanced MicroPython techniques including Inline Assembly, Viper emitters, and a dual-layer hardware-composed rendering system.

## 🌟 Game Features & Mechanics

*   **Dynamic Threat Scaling:** The game starts with a baseline difficulty, but passing 300 points triggers a progressive spawn rate scaler. Surviving past 900 points unleashes an absolute bullet hell (~30% chance for an alien ship every frame).
*   **Desperation Mode ("Last Stand"):** Taking a hit drops your score by 50 points (150 during boss fights!). If your score crashes to 50 or below, the ship's systems automatically overdrive into Panic Mode—fire rate quadruples, and projectiles enter a wide-angle spread.
*   **Smart Seeker Aliens:** While standard Aliens navigate pre-computed quadratic Bézier curves, roughly 15% are "Seekers" that use live vector math to track your ship's visual coordinates.
*   **Environment & Village Defense:** Protect the procedural village at the bottom. Alien ships and acidic rain damage houses. If the village is in trouble (< 6 houses), the ship's priority shifts to cloud suppression.
*   **Safe Restart Engine:** Falling to 0 points triggers a Game Over UI. Upon restart, the engine performs a complete pool wipe—clearing all aliens, lasers, and rain—to ensure a clean start with a **+550 point** mission bonus.

## 🚀 Advanced Combat & Smart Systems

*   **Proactive Target Selection & Angular Aiming:**
    *   **Nearest-Enemy Tracking:** The ship's computer continuously identifies the closest threat and calculates a precise trajectory.
    *   **Angular Ballistics:** Dan's ship can now fire at angles within a **-60 to 60 degree arc**, allowing for surgical strikes against enemies above or below the horizontal plane.
*   **Automated Night-time Halo Defense:**
    *   During the night, a high-intensity spotlight (halo) follows the ship. If an alien enters the **42-pixel radius** of this halo, the ship detects the intrusion and automatically triggers its weapons systems for immediate retaliation.
*   **Tactical "Cloud Eraser" Mode:**
    *   When the village is under siege, the ship rotates 90° to fire upwards.
    *   **Golden-Yellow Lasers:** Upward-firing lasers are now distinctively colored to separate cloud-clearing missions from alien combat.
    *   **Massive Spread:** Fires a 3-way spread normally, or a 7-way "Cloud Eraser" fan during boss fights.

## 👿 Elite Enemies & Boss Environs

*   **Elite Alien Variants:** 15% of standard spawns are "Elites"—drawn in red with **2 HP**. They require multiple hits to destroy but yield **double points (+20)**.
*   **Boss Fight: Contracting Circle (Center-Screen Showdown):**
    *   **Surge to Center:** Upon triggering (every 200 points), the ship immediately surges to the center-screen (x=160) to engage the swarm.
    *   **Encirclement Formation:** 16 boss aliens spawn in a perfect ring encircling the player. They use **Professional Vector Homing** to contract the circle inward simultaneously.
    *   **Weapon Overdrive:** During these encounters, the ship gains **+500 points** and its horizontal weapons enter Overdrive, discharging a massive **7-way spread** with ultra-fast firing cycles.

## 🎨 Special Effects & Physics

*   **Trajectory-Aligned Visuals:** Laser drawing is now synchronized with velocity vectors. Projectiles draw a "tail" pointing opposite to their flight path, making angled shots look sharp and accurate.
*   **Parallax Scrolling Cityscape:** Multi-layer mountainous backdrop with randomized procedural houses. The foreground scrolling runs twice as fast as the background for depth.
*   **Dynamic Time of Day:** Real-time interpolation between Daytime, Sunset, and Midnight.
*   **Searchlight & Night Mask:** Using a Viper-based scanline renderer to dim the world while maintaining a bright protective halo around the ship.

## 🚀 Performance Optimizations

### 1. Hardware Acceleration (`utils.py`)
To maintain high FPS on the RP2350, critical path routines use specialized emitters:
*   **`asm_lerp_unit`**: Uses **ARM Thumb-2 Inline Assembly** for color transitions.
*   **`get_bezier_point`**: A **Viper-optimized** quadratic Bézier solver using fixed-point math.
*   **`fast_dimmer`**: A Viper-based scanline renderer for lighting masks.

### 2. Dual-Layer Compositing
*   **Layer 0**: Static/Slow-moving background elements (Sky, Sun/Moon, Parallax Mountains, Clouds).
*   **Layer 1**: High-frequency gameplay elements (Aliens, Lasers, Particles, Ship).

## 🎮 How to Play
1. Upload all `.py` files to the root directory of your Presto.
2. Run `main.py` and launch `dandare.py`.
3. Protect the village! Use the "Nuclear" option (shoot the Sun/Moon) only when in absolute peril. High Score is saved to `highscore.txt`.