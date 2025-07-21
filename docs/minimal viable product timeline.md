# The Solo Developer's Roadmap: A Phased Timeline for Building a MUD Revival MVP

This report provides a strategic, phase-by-phase development plan for a solo developer to construct a Minimum Viable Product (MVP) for a modern Multi-User Dungeon (MUD). The timeline is deliberately structured to manage technical complexity, mitigate common development risks, and establish tangible milestones. The order of operations prioritizes building a robust foundation before adding layers of functionality, ensuring a stable and scalable final product. The primary objective is to transform the detailed technical specification into an actionable roadmap, guiding the developer from initial project setup to a distributable, feature-complete MVP.

The following table presents a high-level overview of the entire project, breaking down the development effort into six distinct phases. This summary serves as a strategic map, offering a clear view of the workflow and time commitment required to bring the MUD revival to life.

**Table: Executive Summary: MVP Development Timeline**

| Phase                                                   | Estimated Duration | Status        |
| ------------------------------------------------------- | ------------------ | ------------- |
| Phase 1: Project Scaffolding & Architectural Foundation | Days 1-3           | ✅ Complete   |
| Phase 2: Core Systems & Offline Prototyping             | Days 4-9           | ✅ Complete   |
| Phase 3: Engineering the Client Interface               | Days 10-14         | ✅ Complete   |
| Phase 4: Forging the Peer-to-Peer Fabric                | Days 15-21         | ➡️ In Progress |
| Phase 5: Assembling the Complete MVP                    | Days 22-26         | ⬜ Not Started |
| Phase 6: Final Optimization & Distribution              | Days 27-30         | ⬜ Not Started |

## Phase 1: Project Scaffolding and Architectural Foundation (Estimated Duration: 3 Days) - ✅ Complete

The initial phase is dedicated to establishing a professional, scalable, and maintainable foundation before any game logic is written. The work performed here is a critical investment that yields significant returns throughout the project's lifecycle, particularly in simplifying long-term maintenance and preparing for potential open-source collaboration.1

### Task 1.1: Professional Git Repository Setup

The first action is to initialize a Git repository and establish a professional branching strategy based on the `git-flow` model. This involves creating two primary branches: `main` and `develop`. The `main` branch will be protected, reserved exclusively for stable, tagged releases. All integration of new features will occur on the `develop` branch. All development work itself must be performed on dedicated `feature/<feature-name>` branches, which are branched from `develop` and merged back via pull requests. This discipline prevents unstable code from contaminating the main development line.

Alongside the branching model, several essential repository artifacts must be created. A robust `.gitignore` file, specifically tailored for Godot projects, is required to ignore the `.godot/` cache directory, exported build files, and user-specific editor settings like `export_credentials.cfg`. A `.gitattributes` file should be configured to use Git LFS (Large File Storage) for any future binary assets, keeping the core repository lean. Finally, foundational documents like a `LICENSE` file (the permissive MIT License is recommended), a placeholder `README.md`, and a `CONTRIBUTING.md` file should be created.

Establishing these professional practices from day one, even for a solo project, is a strategic decision. The technical specification dedicates an entire section to this topic, signaling its importance beyond the MVP. For a solo developer, this process instills a discipline that prevents the accumulation of project management debt. Creating a `CONTRIBUTING.md` at the outset, for example, is an act of foresight. It designs the project for future success and collaboration, removing barriers for potential contributors and transforming a personal project into a potential open-source platform.

### Task 1.2: Implementing the Scalable Godot Project Structure

The project must adopt a "group by feature" directory structure, a best practice for scalable Godot projects that is superior to the default "group by type" layout. This involves creating a top-level `/src` directory to house all primary game code and assets. Within `/src`, feature-centric subdirectories like `/core` (for engine systems), `/features` (for game entities like players and items), and `/assets` will be created. This structure is self-documenting and dramatically lowers the cognitive load for anyone navigating the project.

As part of this setup, placeholder scripts for the core autoload singletons—`WorldDB.gd`, `CommandParser.gd`, and `NetworkManager.gd`—should be created in their respective `/src/core/` subdirectories. These scripts must then be added to the Godot project's autoload list in `Project -> Project Settings -> Autoload` to ensure they are globally accessible from the start.

### Task 1.3: Confirming Core Architectural Decisions

Before proceeding, the developer must formally adopt and document the core architectural decisions. The most critical of these is the use of a "Session Host" (or "listen server") model. In this architecture, one player's client acts as the authoritative server for the game session. This decision is a pragmatic necessity, driven by the design of Godot's high-level networking API and the need to avoid the immense complexity of distributed consensus algorithms that a true peer-to-peer authority model would require.

The developer must also internalize the defined MVP scope. A disciplined adherence to the "In Scope" and "Out of Scope" feature lists is paramount. This review acts as a crucial guardrail against scope creep, which is one of the most significant risks to the successful and timely completion of a solo development project.

## Phase 2: Core Systems and Offline Prototyping (Estimated Duration: 6 Days) - ✅ Complete

This phase is dedicated to building the "brain" of the MUD in a completely offline, non-graphical context. The objective is to engineer a fully testable, single-player game engine that runs entirely in the background, with its functionality validated through simple console output. This approach deliberately isolates game logic from all other concerns, such as user interface and networking.

### Task 2.1: Data-First Design: Implementing Custom Resources

Following a data-driven design philosophy, the core game entities will be modeled as custom Godot `Resource` objects. This approach separates game data from game logic, allowing content to be edited independently. The following GDScript files, defining the data schema, must be created:

- **RoomResource** (`res://src/features/world/room_resource.gd`): Defines a single location with properties for a unique `id`, a human-readable `name`, a long-form `description`, an `exits` dictionary mapping directions to other room IDs, and arrays for `item_ids` and `player_ids` present in the room.
    
- **ItemResource** (`res://src/features/items/item_resource.gd`): Defines a single object with properties for a unique `id`, a `name`, a `description`, an array of `keywords` for the parser, and a `properties` dictionary for flags like `can_be_taken`.
    
- **PlayerResource** (`res://src/features/player/player_data.gd`): Holds the state for a player, including their unique network `id`, chosen `name`, current `location_id`, and an array of `inventory_ids`.
    

### Task 2.2: Building and Populating the World Database

The `WorldDB.gd` autoload singleton will serve as the in-memory world database. Its implementation will include master dictionaries to hold all loaded resources (e.g., `var rooms = {}`, `var items = {}`) and functions to load all world data from `.tres` resource files at startup.

With the database structure in place, the developer can begin the first major content creation task: building the static MVP world. Using the Godot editor, this involves creating 10-20 `RoomResource` files and several `ItemResource` files. Each resource is saved as a `.tres` file and populated with names, descriptions, and properties. The rooms are then interconnected by populating their `exits` dictionaries with the IDs of adjacent rooms.

### Task 2.3: Implementing the Command Parser

The `CommandParser.gd` singleton is the heart of the user interface. The core `parse_command(player_id, input_text)` function will be implemented to tokenize the input string by splitting it into words. A `command_map` dictionary will be used to map command verbs and their abbreviations (e.g., "look", "l") to specific handler functions (e.g., `_handle_look`).

Initially, placeholder handler functions for all MVP commands (`look`, `get`, `drop`, `say`, etc.) will be created. These functions will use simple `print()` statements to output the action being taken (e.g., `print("Player", player_id, "is attempting to get an item.")`). This low-fidelity approach allows for immediate testing of the entire command parsing and game logic flow without any graphical interface, ensuring the core engine is sound before moving to the next phase. This strategic isolation of complexity means that any bug discovered at this stage is guaranteed to be a logic bug within `WorldDB` or `CommandParser`, dramatically reducing the search space for errors and accelerating development.

## Phase 3: Engineering the Client Interface (Estimated Duration: 5 Days) - ✅ Complete

With a functional offline engine, this phase focuses on constructing the "eyes and ears" of the game: the user-facing client. The culmination of this phase is a complete, playable, single-player vertical slice of the MUD. This milestone is critical, as it transforms the project from a collection of abstract scripts into a tangible, interactive experience.

### Task 3.1: Constructing the Main UI Scene (`Game.tscn`)

The main UI will be constructed in a new scene, `Game.tscn`, using Godot's standard `Control` nodes to ensure proper scaling and layout. The structure will consist of a root `Control` node, a `VBoxContainer` to stack elements vertically, a `ScrollContainer` to house the text log, and an `HBoxContainer` at the bottom for the input prompt and field.

The primary text console will be implemented using a `RichTextLabel` node named `TextLog`. Its `bbcode_enabled` property must be set to `true` to allow for inline text formatting, which is essential for differentiating room descriptions, player speech, and system messages with colors and styles. A helper function, such as `log(message)`, can be added to the main UI script to simplify the process of appending new, BBCode-formatted text to the log. Finally, a `LineEdit` node will be added to the `HBoxContainer` to capture all user command input.

### Task 3.2: Creating the Graphical Map View (`MapView.tscn`)

A secondary, graphical view will provide a minimalist representation of the player's surroundings. This will be built in a separate `MapView.tscn` scene to keep the project modular. To achieve a crisp, pixel-perfect retro aesthetic, a `SubViewportContainer` and `SubViewport` will be used to render the map at a fixed low resolution before scaling it up to fit its container.

The core of this view is a `TileMap` node. Its visual style is achieved by creating an ASCII `TileSet` from a single, small character atlas texture (such as one based on Code Page 437). In this scheme, characters like '@' represent the player and '#' represents walls. This approach is not only thematically appropriate but also extremely lightweight, contributing significantly to the project's aggressive 6-8 MB final build size target by avoiding numerous larger sprite assets. A `Camera2D` within the `SubViewport` will be scripted to remain centered on the player's tile.

### Task 3.3: Connecting the Wires (UI to Core Logic)

The final step of this phase is to connect the newly built UI to the offline engine. The `LineEdit` node's built-in `text_submitted` signal will be connected to a function in the main UI script, `_on_input_submitted(text)`. This function will take the user's input and pass it to the `CommandParser.parse_command()` function, using a hardcoded player ID for now (e.g., `0`).

The placeholder `print()` statements within the `CommandParser`'s handler functions must then be refactored. Instead of printing to the debug console, they will now return formatted strings, complete with BBCode for styling. The main UI script will receive these strings and pass them to its `log()` function to be displayed in the `RichTextLabel`. Completing this phase provides the first "playable" version of the game, a massive psychological boost that provides tangible proof of concept and invaluable motivation before tackling the complexities of networking.

## Phase 4: Forging the Peer-to-Peer Fabric (Estimated Duration: 7 Days) - ➡️ In Progress

This is the most technically demanding phase, where the single-player prototype is fundamentally re-architected into a host-authoritative multiplayer game. This process requires a significant shift in mindset, as the game is no longer a single program but two distinct entities: a "smart" host that holds the true game state and a "dumb" client that is merely a view and an input device.

### Task 4.1: Noray Integration and Network Management

The networking foundation begins with the installation of the `netfox.noray` addon, which must be enabled in the Project Settings. All interaction with this library will be encapsulated within the `NetworkManager.gd` autoload singleton. For development, this manager will be configured to use the public Noray server instance at `tomfol.io:8890`. A simple UI for hosting and joining sessions must also be created, allowing one player to generate and share their session `oid` and another to paste it to connect.

### Task 4.2: Implementing the Connection Lifecycle

The connection process follows a precise sequence. The "Host" functionality involves registering with the Noray server to receive a public `oid`, then setting up Godot's `MultiplayerAPI` to act as a server (`multiplayer.create_peer()`). The "Join" functionality involves the connecting client sending the host's `oid` to the Noray server. Noray then orchestrates a handshake, providing each peer with the other's public IP address to attempt a direct NAT punch-through connection. Once the direct link is established, the joining client finalizes its connection to the host within Godot's networking system.

### Task 4.3: The Great Refactor: Implementing the Authoritative RPC Flow

This is the most critical and labor-intensive task of the phase. The client's input handling must be completely refactored. Instead of calling the local `CommandParser`, the `_on_input_submitted` function will now use a Remote Procedure Call (RPC) to send the command string to the host for execution (e.g., `rpc_id(1, "execute_command", text)`), where `1` is the fixed network ID of the host.

Consequently, all game logic within the `CommandParser`'s handler functions must be protected by a check: `if not multiplayer.is_server(): return`. This ensures that game state modifications can only ever occur on the authoritative host. The results of commands are no longer returned directly; instead, the host uses targeted RPCs to send formatted strings and state updates back to the relevant clients, which then update their local views (the `RichTextLabel` and `TileMap`). This host-authoritative RPC model is the cornerstone of a secure and consistent multiplayer experience.

### Task 4.4: Player Spawning and Synchronization

To represent players in the world, a `player.tscn` scene will be created. A `MultiplayerSpawner` node will be added to the host's main scene, configured to automatically instantiate a networked copy of `player.tscn` for each new client that connects.

To keep player positions synchronized visually, a `MultiplayerSynchronizer` node will be added to the `player.tscn`. This powerful node is configured to automatically watch a property (like the player's position on the `TileMap`) and broadcast any changes from the host to all clients. When the host's `WorldDB` updates a player's location, the change is propagated, ensuring all players see characters move in real-time on their graphical maps.

## Phase 5: Assembling the Complete MVP (Estimated Duration: 5 Days) - ⬜ Not Started

With the complex networked architecture in place, this phase focuses on implementing the full suite of specified MVP gameplay features. The difficult foundational work of Phase 4 now pays off, as implementing new features becomes a matter of replicating a well-defined pattern rather than engineering new systems. The cognitive load is lower, and progress should feel rapid as features are ticked off the MVP list.

### Task 5.1: Implementing Observation and Interaction Commands

The core gameplay commands—`look`, `get`, and `drop`—must be fully implemented according to the MVP feature set. This involves writing the authoritative logic for each command in the `CommandParser` on the host. For example, when a player issues a `get` command, the host validates the action, modifies the state in `WorldDB` (moving an item's ID from a room's inventory to a player's inventory), and then sends RPCs to all affected clients to update their views. A message like "Player X picks up a longsword" should appear in the text log for everyone in the same room.

### Task 5.2: Implementing Communication Commands

The social commands—`say`, `tell`, and `shout`—are implemented next, each requiring a slightly different RPC pattern.

- **say**: The host receives the command via RPC, queries `WorldDB` to identify all players in the sender's current room, and then sends a new, targeted RPC containing the message to each of those players.
    
- **tell**: The host receives the RPC, looks up the target player's unique network ID, and sends a single, private RPC to only that player.
    
- **shout**: The host receives the RPC and then iterates through _all_ currently connected players, sending an RPC to each one to broadcast the message game-wide.
    

### Task 5.3: Implementing Player Information Commands

The player status commands—`who`, `inventory`, and `score`—are also implemented. These are generally simpler, involving a single client sending an RPC request to the host. The host gathers the requested information from `WorldDB` (e.g., a list of all online players or the contents of the requesting player's inventory) and sends it back in a single RPC to only the player who asked for it.

### Task 5.4: End-to-End Testing

Finally, all implemented features must be rigorously tested in a true multiplayer environment. This requires running at least two, and ideally three, instances of the game client simultaneously to test hosting, joining, and all interactions. Edge cases must be explored: What happens if two players attempt to `get` the same item simultaneously? How does the game handle a player disconnecting abruptly? This comprehensive testing validates the entire client-request -> host-execution -> client-update loop and ensures the MVP is stable.

## Phase 6: Final Optimization and Distribution (Estimated Duration: 4 Days) - ⬜ Not Started

This final phase is optional for creating a functional prototype but is mandatory for achieving the project's aggressive 6-8 MB client distribution target. This is a high-effort, high-reward process that should only be attempted after the MVP is functionally complete, tested, and stable. Attempting this process earlier introduces significant risk and can derail the project in compilation and configuration issues.

### Task 6.1: Preparing the Custom Compilation Environment

The first step is a one-time setup of the necessary build environment. This includes installing SCons, Python, and other build tools, and downloading the Godot source code that exactly matches the engine version used for development.

### Task 6.2: Systematic Minification and Compilation

A `custom.py` build file will be created to pass optimization flags to the SCons build system. The process of minification should be iterative and methodical:

1. Start with base optimization flags: `optimize="size"` and `lto="full"`.
    
2. Disable the entire 3D engine with `disable_3d="yes"`, which provides the single largest size reduction.
    
3. Disable other large, unnecessary core features like the Vulkan renderer (`vulkan="no"`) and VR support (`openxr="no"`).
    
4. Adopt a "whitelist" approach for modules: disable all optional modules by default with `modules_enabled_by_default="no"`, then explicitly re-enable only those that are essential, such as `module_gdscript_enabled="yes"` and `module_freetype_enabled="yes"`.
    

A critical note is that the `disable_advanced_gui="yes"` flag must _not_ be used. While it offers size savings, it removes the `RichTextLabel` node, which is a cornerstone of the client UI. Accepting the ~2 MB size penalty is a necessary engineering trade-off. After each major group of flags is added, a test compilation should be performed to ensure the engine still builds and the game remains functional. Finally, Godot's built-in Engine Compilation Configuration tool can be used to analyze the project and generate a final exclusion list of unused classes before the final compilation.

### Task 6.3: Post-Compilation Compression

Once the custom, minimalist export template is compiled, a final compression step can be applied. For Windows executables, the UPX (Ultimate Packer for Executables) command-line tool can reduce the final file size by over 60% by compressing the executable in-place. For web exports, Binaryen's `wasm-opt` tool can perform a similar size-optimization pass on the WebAssembly file.

The immense effort of this phase is justified by the results, as demonstrated in the following table. It quantifies the dramatic, cumulative impact of each optimization step, providing the motivation to see the process through.

**Table: Build Size Reduction Analysis**

|Optimization Step (Windows Target)|Uncompressed Size|Cumulative Reduction|Source|
|---|---|---|---|
|Default Export Template|92.8 MB|0%|1|
|+ `optimize="size"`, `lto="full"`|53.6 MB|42.2%|1|
|+ `disable_3d="yes"`|44.0 MB|52.6%|1|
|+ Disable Unnecessary Features (Vulkan, etc.)|33.6 MB|63.8%|1|
|+ Disable Unwanted Modules|29.8 MB|67.9%|1|
|+ Engine Compilation Configuration|21.0 MB|77.4%|1|
|**Final: Post-UPX Compression**|**~6.4 MB**|**~93.1%**|1|

## Conclusion: Beyond the MVP

By following this phased timeline, a solo developer can successfully navigate the complexities of building a modern MUD. The result is not only a functional, feature-complete MVP but also a project built upon a robust, scalable, and professional foundation. The deliberate separation of concerns—isolating core logic from the UI and networking—and the methodical, step-by-step integration of these systems is key to managing risk and maintaining momentum.

The foundational decisions made early in the process, such as the "Data-First" design using Godot Resources, the modular core systems, and the professional repository structure, are designed for longevity. This architecture is perfectly positioned to support post-MVP development, simplifying the addition of more complex systems like combat, NPCs, and quests. More importantly, the well-documented and cleanly structured project is prepared to attract a community of collaborators, fulfilling the ultimate vision of a true, community-driven MUD revival.