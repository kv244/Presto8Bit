# Presto Bézier Swarm: Modular Engine (Dan Dare)

[![Build Status](https://github.com/kv244/Presto8Bit/actions/workflows/build.yml/badge.svg)](https://github.com/kv244/Presto8Bit/actions/workflows/build.yml)

![Screenshot 1](i1.jpg) ![Screenshot 2](i2.jpg)

A high-performance, object-oriented 2D space shooter engine for the **Pimoroni Presto (RP2350)**. This project demonstrates advanced MicroPython techniques including Inline Assembly, Viper emitters, and a dual-layer hardware-composed rendering system.

## 🌟 Game Features & Mechanics

*   **Dynamic Threat Scaling:** The game starts relatively easy, but passing 300 points triggers a progressive spawn rate scaler. Surviving past 900 points unleashes an absolute bullet hell (~30% chance for an alien ship every frame).
*   **Desperation Mode ("Last Stand"):** Taking a hit drops your score by 50 points. If your score crashes to 50 or below, the ship's systems automatically overdrive into Panic Mode. Fire rate quadruples, the laser pitch intensifies, and the ship gains a massive triple-spread beam!
*   **Smart Seeker Aliens:** While standard Aliens navigate the screen sweeping along randomized, pre-computed quadratic Bézier curves, roughly 15% of spawns are designated "Seekers." These ruthless AI pilots bypass curves and calculate live trajectories towards your ship's coordinates.
*   **Environment & Village Defense:** Protect the procedural village at the bottom of the screen. Alien ships and acidic rain (from drifting clouds) damage houses. If the village is in trouble (less than 6 houses left), the ship's priority shifts to cloud suppression.
*   **Game Over Engine:** Falling to 0 points completely halts the execution loop, blasts a Game Over UI screen, and triggers a full memory `__init__()` restart from scratch.

## 🚀 Advanced Combat Refinements

*   **Tactical "Cloud Eraser" Mode:** When the village is under siege and clouds are present, the ship automatically rotates 90 degrees to fire upwards.
    *   **Autonomous Glide:** The ship glides horizontally to align itself directly under the nearest cloud or celestial target.
    *   **Massive Spread:** Fires a 3-way spread normally, or a 7-way "Cloud Eraser" fan during boss fights.
    *   **Recovery Window:** After a cloud is destroyed, the ship gains a 2-second (100 frame) window to revert to horizontal and focus on alien combat before re-assessing cloud threats.
*   **"Nuclear" Emergency Protocol:** If score falls below 25, the ship can trigger a one-time screen wipe by shooting the moving **Sun** or **Moon**.
    *   **Seeker Lasers:** In danger mode, the ship launches a specialized seeker laser that targets the celestial body's X-coordinate.
    *   **Screen Wipe:** Successfully hitting the sun/moon destroys all active aliens, enemy lasers, and clouds simultaneously.
*   **Strategic Scoring:** Destroying a cloud yields **+10 points**. A successful Nuclear trigger grants a massive **+100 point** bonus.

## 🎨 Special Effects & Physics

*   **Cloud-Tethered Rain:** Atmospheric rain drops only spawn directly beneath active clouds. Clearing the sky stops the rain in those zones, providing a clear tactical benefit.
*   **Parallax Scrolling Cityscape:** The environment generates a multi-layer mountainous backdrop with randomized procedural houses. The foreground scrolling math runs at twice the speed of the background, creating high-speed parallax depth.
*   **Dynamic Time of Day:** The engine interpolates colors for Daytime, Sunset, and Midnight. The Sun now scrolls across the sky, eventually passing directly over the player for the "Nuclear" option, before rolling into night.
*   **Searchlight & Night Mask:** During night, a Viper-based scanline renderer dims the screen, while a searchlight effect follows the player ship.
*   **Buzzer Audio System:** Centralized timer management ensures distinct audio feedback for lasers, impacts, explosions, and the high-intensity "Nuclear" rumble without interrupt conflicts.

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

## 🛠 TODO / Future Extensibility
*   **Qwiic Joypad Support:** Integrate support for external I2C joypads.
*   **Power-up Drops:** Add collectible capsules dropped by destroyed Seekers.