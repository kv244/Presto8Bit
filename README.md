# Presto Bézier Swarm: Modular Engine (Dan Dare)

[![Build Status](https://github.com/kv244/Presto8Bit/actions/workflows/build.yml/badge.svg)](https://github.com/kv244/Presto8Bit/actions/workflows/build.yml)

![Screenshot 1](i1.jpg) ![Screenshot 2](i2.jpg)

A high-performance, object-oriented 2D space shooter engine for the **Pimoroni Presto (RP2350)**. This project demonstrates advanced MicroPython techniques including Inline Assembly, Viper emitters, and a dual-layer hardware-composed rendering system.

## 🌟 Game Features & Mechanics

* **Dynamic Threat Scaling:** The game starts relatively easy, but passing 300 points triggers a progressive spawn rate scaler. Surviving past 900 points unleashes an absolute bullet hell (~30% chance for an alien ship every frame).
* **Desperation Mode ("Last Stand"):** Taking a hit drops your score by 50 points. If your score crashes to 50 or below (meaning you are one hit away from Game Over), the ship's systems automatically overdrive into Panic Mode. Fire rate quadruples, the laser pitch intensifies to 1500hz, and the ship gains a massive triple-spread beam!
* **Smart Seeker Aliens:** While standard Aliens navigate the screen sweeping along randomized, pre-computed quadratic Bézier curves, roughly 15% of spawns are designated "Seekers." These ruthless AI pilots bypass curves and calculate live trajectories towards your ship's coordinates.
* **Game Over Engine:** Falling to 0 points completely halts the execution loop, blasts a Game Over UI screen, and triggers a full memory `__init__()` restart from scratch.
* **Pixel Art Sprites:** Uses a custom grid-parsing engine to assemble multi-layer pixel art ships dynamically out of raw vectors instead of laggy bitmaps.

## 🎨 Special Effects

* **Parallax Scrolling Cityscape:** The environment generates a multi-layer mountainous backdrop with randomized procedural houses. The foreground scrolling math runs at twice the speed of the background, creating a genuine sense of deep parallax depth and flight.
* **Dynamic Time of Day:** The engine interpolates dynamically mapped colors for Daytime, Sunset, and Midnight. Procedural clouds drift across the sky, passing in front of a glowing Sun during the day, before the sky rolls dark to reveal a starry night sky and a wandering Moon.
* **Searchlight Cone:** During the night cycle, the rendering pipeline dynamically dims 'Layer 1' out with dense indigo scanlines, then punches a precise 0-alpha transparency `circle()` directly over the player ship, mimicking a high-beam searchlight cutting through the pitch-black night.
* **Animated Particle Splashes:** Raindrops that strike the bottom pixel grid line dynamically explode into "water splash" particles that execute complex math arcs under simulated gravity pulls!
* **Engine Flicker:** The ship outputs a continuous flickering randomized thrust particle cone for its engine output.
* **Buzzer Audio Overrides:** Heavy, localized frame-priority audio interrupts map distinct sounds to separate game actions: `1200hz` for Standard Lasers, `1500hz` for Panicked Lasers, `50hz-250hz` low grumbles for structural damage, and `2500hz` high-pitch squeals for exploded Aliens.

## 🚀 Performance Optimizations

### 1. Hardware Acceleration (`utils.py`)
To maintain a high frame rate on the RP2350, critical path routines use specialized emitters:
* **`asm_lerp_unit`**: Uses **ARM Thumb-2 Inline Assembly** to calculate color transitions. It uses 8-bit immediate math to bypass Python's object overhead.
* **`get_bezier_point`**: A **Viper-optimized** quadratic Bézier solver. It uses fixed-point math (`0-256`) and bit-shifting to avoid floating-point stalls.
* **`fast_dimmer`**: A Viper-based scanline renderer for the searchlight "night mask."

### 2. Dual-Layer Compositing
The engine utilizes the Presto's dual-buffer hardware:
* **Layer 0**: Static/Slow-moving background elements (Sun, Sky, Parallax Mountains, Clouds).
* **Layer 1**: High-frequency gameplay elements (Aliens, Lasers, Particles) and the transparency-based lighting mask cutouts.

### 3. Circular Collision Detection
Collision is calculated using squared Euclidean distance (`dx^2 + dy^2 < radius^2`). This avoids the expensive `sqrt()` operation while providing a more organic circular hitbox than generic AABB bounding blocks.

## 🎮 How to Play
1. Upload all `.py` files to the root directory of your Presto.
2. Run `main.py` (which acts as an App menu) and launch `dandare.py`.
3. The game polls the RTC; every hour on the hour, a Victory screen triggers and saves your High Score to `highscore.txt`.

## 🛠 TODO / Future Extensibility
* **Qwiic Joypad Support:** Integrate support for external I2C Qwiic joypads for physical ship movement controls.