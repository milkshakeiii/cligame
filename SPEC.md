# Space Simulation - Game Specification

## Overview
A tick-based 3D space simulation featuring mining, scanning, and combat with ships ranging from small fighters (~1m) to massive capital ships (~1km). Large ships can carry and manufacture smaller ships.

### Design Goals
- **Slow-paced**: Designed for CLI/API interaction. Even slower than EVE Online - less twitchy, more strategic
- **Asynchronous-friendly**: Players can issue commands and receive terminal notifications
- **Scale matters**: 1000x size difference between smallest and largest ships

## Ship Size Classes (Homeworld-inspired)
- **Strike Craft** - Fighters, bombers, scouts (~1-50m)
- **Corvettes** - Small multi-crew vessels (~50-150m)
- **Frigates** - Mid-size workhorses (~200-400m)
- **Destroyers** - Heavy combat ships (~500-700m)
- **Cruisers** - Major warships (~800-1200m)
- **Carriers/Motherships** - Largest vessels (1km+), production capable

## Internal Volume System
Ships have a total internal volume determined by hull size. This volume is allocated between modules:
- **Engines** - Thrust/speed (motherships need huge investment here to not be slow)
- **Cargo Bays** - Store ore and resources
- **Docking Bays** - Hangar space for carrying smaller vessels (docked ships are safe from targeting)
- **Resource Drop-off** - Allows other ships to transfer ore to you
- **Factories** - Production capability (limited by factory size)
- **Reactors** - Energy generation and capacitor size
- **Mining Lasers** - Extract ore from asteroids
- *TBD: Weapons, shields, sensors*

## Resources

### Ore
- Single ore type (expandable later)
- Obtained by mining asteroids
- Used directly for ship construction (no intermediate refining for now)

### Energy
- *TBD: Generation (reactors), storage (batteries), consumption model*

## Production
- Factories can build any ship up to their size limit
- Production can occur while moving
- Production consumes energy and ore

## Control Scheme (EVE Online-inspired, but slower)
Players interact via CLI or web API. The pace is deliberately slow to accommodate asynchronous input.

### Movement Commands
- **Approach** - Move toward a target
- **Orbit** - Maintain circular orbit around target at specified range
- **Keep at range** - Maintain distance from target
- **Dock** - Enter an allied ship's docking bay (if they have space)
- **Transfer resources** - Approach ship with drop-off module, transfer ore

### Module Activation
- Modules cycle on/off
- Each module has a cycle time (slower than EVE - less twitchy)
- Modules consume capacitor when active

## Energy (Capacitor)
EVE Online-style capacitor system:
- Ships have a capacitor pool (size based on reactor modules)
- Regenerates over time (fastest regen around 25-30% capacity)
- Modules drain capacitor when cycling
- Capacitor depleted = modules go offline
- Overall slower/less twitchy than EVE

## Modules
Modules fill volume and provide capabilities. Each has:
- Volume requirement
- Capacitor consumption per cycle
- Cycle time

### Module Types
- **Engines** - Provide thrust (always on? or toggled?)
- **Reactors** - Increase capacitor size and regen
- **Cargo Bay** - Store ore/resources
- **Docking Bay** - Store smaller ships
- **Resource Drop-off** - Accept ore transfers from other ships
- **Factory** - Build ships up to size limit
- **Mining Laser** - Extract ore from asteroids
- *TBD: Weapons, shields, sensors*

## Mining
- Any ship with mining laser modules can mine
- Mining lasers cycle, consuming cap and extracting ore from asteroids
- Ore stored in cargo bays
- To offload: approach ship with resource drop-off module and transfer

## Scanning & Detection
Players operate in an emulated terminal environment. Fog of war exists - you only see what your sensors detect.

### Active Scanning
- Scanner modules perform active scans
- Consumes capacitor
- Better modules = more information (ship type → loadout → heading → etc.)

### Passive Detection
- Detection modules can run passively
- Players subscribe to alerts: "notify me when a ship larger than 10m appears"
- Messages written to terminal when conditions match

### Stealth
- Ships can reduce their detectability
- *TBD: Stealth mechanics, signature radius, etc.*

## Combat
*TBD - weapon types, damage model, electronic warfare*

## Multiplayer
*TBD - shared universe vs instances, player interaction, factions*
