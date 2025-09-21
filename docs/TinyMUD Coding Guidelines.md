# **Project MUD Revival: Contribution Guidelines (GDScript & Python)**

## **Section 1: The Guiding Philosophy: Code for Clarity and Community**

This document establishes the foundational principles and technical standards for all contributions to the MUD Revival project. The rules that follow apply to **both the GDScript client and the Python server codebase**. They are a cohesive system designed to foster a codebase that is reliable, maintainable, and, most importantly, accessible to developers of all skill levels. By adhering to these guidelines, we collectively build a project that is not only a functional game but also a welcoming learning environment.

### **1.1 Our Prime Directive: The Golden Rule of Contribution**

At the heart of our development philosophy lies a single, paramount principle that informs every other rule in this guide. All contributors must internalize and apply this Golden Rule:

**Your code should be self-documenting first, with comments explaining the *why*, not the *what*. Remember that you are writing code not just for yourself, but for any aspiring programmer of any skill level to fork and play with. Ask yourself, “Is this file not just functional, but elegantly self-explanatory when read at a glance?” If the code is difficult to comment on meaningfully, it is a sign that it needs to be refactored.**

This rule is a **Litmus Test for Clarity**. The goal is not to fill files with verbose, obvious comments like \# increment i by 1\. Such comments add noise, not value. The need for extensive comments often indicates that the code itself is the problem—it may be too complex, too long, or its intent may be obscured by poor naming and convoluted logic.

Therefore, the primary response to failing this litmus test is always to **refactor for clarity**. Improve variable names, break down large functions into smaller, single-purpose ones, and simplify the control flow. Make the code speak for itself. Once the code is as clear as it can be, comments should be reserved for explaining:

* High-level design intent and architectural decisions.  
* The purpose of a complex algorithm that cannot be simplified further.  
* The rationale for a non-obvious implementation choice (e.g., performance optimizations, security considerations).

### **1.2 Why We Adapt Safety-Critical Standards**

This project draws inspiration from the rigorous coding standards developed for safety-critical software, such as those from NASA's JPL. While a Multi-User Dungeon is not a space probe, the underlying philosophy of **reliability, predictability, and analyzability** is paramount for creating a stable, cheat-resistant, and scalable multiplayer game. This is true for the visual client and is even more critical for the authoritative server.

The rules in this guide are philosophical adaptations of these principles, tailored for the high-level, dynamic languages we use: GDScript and Python. For example, the C-centric rule "Avoid heap memory allocation after initialization" is adapted to our context as a mandate to manage resources predictably by loading all necessary assets at startup (on both client and server), preventing mid-game lag or slow API responses.

The "Ten Commandments" detailed in the next section are the result of this adaptation. Each one is designed to reduce cognitive load, prevent common categories of bugs, and make the codebase transparent and welcoming for all contributors.

## **Section 2: The Ten Commandments of MUD Revival Development**

This section presents the ten core technical rules that govern all code in this project. Adherence to these commandments is mandatory for all contributions.

| Commandment | Rationale |
| :---- | :---- |
| **I: Keep Control Flow Simple.** | Complex logic is hard to read, test, and debug. |
| **II: All Loops Must Be Bounded.** | Unterminated loops will freeze the client or block a server thread. |
| **III: Manage Resources Predictably.** | Load assets at startup, not during critical gameplay or request handling. |
| **IV: Functions Must Be Focused and Concise.** | Small, single-purpose functions are easier to understand, test, and reuse. |
| **V: Assert Preconditions and Postconditions.** | Fail-fast with assertions to catch logical errors at their source. |
| **VI: Restrict Data Scope.** | Limit data visibility to prevent unintended side effects and improve modularity. |
| **VII: Always Check Return Values.** | Never ignore potential error states or failure conditions returned by functions. |
| **VIII: Use Static Typing Rigorously.** | Catch type-mismatch errors during development, not at runtime. |
| **IX: Limit Complex Object References.** | Avoid tight coupling and violations of encapsulation (Law of Demeter). |
| **X: Lint Clean, Run Clean.** | Warnings and linter errors are potential bugs. A clean build is not optional. |

### **2.1 Commandment I: Keep Control Flow Simple**

**Rationale:** Code that is difficult to follow is difficult to verify. Complex control flow is a primary source of bugs.

**Implementation:**

* **Use Guard Clauses:** Handle error conditions and edge cases at the beginning of a function to avoid nesting the main logic. This flattens the code and makes the "happy path" clearer. This pattern applies equally to GDScript and Python.  
* **Favor match Statements:** For logic based on a single variable's state, a match statement (available in both GDScript and Python 3.10+) is often cleaner than long if/elif/else chains.  
* **Refactor Complexity:** If a function's flow is hard to follow, it's doing too much. Break it down into smaller helper functions.

### **2.2 Commandment II: All Loops Must Be Bounded and Verifiable**

**Rationale:** An unterminated loop is a catastrophic failure, consuming 100% of a CPU core on the client or server.

**Implementation:**

* **Prefer for Loops:** When iterating over a collection, always use a for loop. It is inherently bounded by the collection's size.  
* **Constrain while Loops:** while loops are permitted only if their termination condition can be proven by simple inspection (e.g., a counter reaching a boundary).  
* **No while true in Game Logic:** On the client, continuous logic belongs in Godot's \_process() or \_physics\_process() methods. On the server, long-running tasks must be managed by the application framework or a proper task queue, never a blocking while true loop in a request handler.

### **2.3 Commandment III: Manage Resources Predictably**

**Rationale:** Loading large resources or performing heavy I/O during active gameplay or request handling causes performance spikes (stuttering on the client, high latency on the server).

**Implementation:**

* **GDScript (Client):** All static game data (Resources, Scenes) must be loaded at startup using preload() or by loading them into a global singleton. Use of load() in performance-critical paths is forbidden.  
* **Python (Server):** All configuration, database connections, and large static data files must be loaded when the Flask application starts. Do not read configuration files or establish new database connections inside an API endpoint that handles player actions.

### **2.4 Commandment IV: Functions Must Be Focused and Concise**

**Rationale:** A function that is too long is doing too many things. Small functions are the building blocks of clean code.

**Implementation:**

* **Strict Length Guideline:** A function should rarely exceed **50 lines of code**, excluding comments and blank lines.  
* **Refactoring Trigger:** If a function grows beyond this limit, it is an immediate signal that it must be refactored into smaller, logically distinct helper functions.  
* **Files containing code should be roughly 70% Code, 30% comments:** If you are having difficulty hitting this comment quota, please consider refactoring the code.

### **2.5 Commandment V: Assert Preconditions and Postconditions**

**Rationale:** Assertions are a form of defensive programming that helps find bugs early. If an assumption is violated, the program halts in debug builds, pointing directly to the logical error.

**Implementation:**

* The assert() statement exists in both GDScript and Python and must be used liberally.  
* **Check Preconditions (Inputs):** At the beginning of a function, assert the validity of its arguments.  
  \# Python Server Example  
  def move\_player\_to\_room(player\_id: int, new\_room\_id: int):  
      \# Precondition: The player ID must be valid.  
      assert player\_id in world\_db.players, "Handler called with invalid player\_id."  
      \# ... function logic

* **Check Postconditions (Outcomes):** After a state-changing operation, assert that the state is what you expect.  
  \# GDScript Client Example  
  func \_move\_player\_sprite(new\_position: Vector2) \-\> void:  
  	\# ... logic to move the sprite ...

  	\# Postcondition: The sprite's position must now be the new position.  
  	assert(self.position \== new\_position, "Player sprite move failed.")

### **2.6 Commandment VI: Restrict Data Scope**

**Rationale:** The visibility of data should be limited to the smallest possible scope. Global state creates dependencies that are difficult to reason about.

**Implementation:**

* **Local by Default:** A variable must be declared in the narrowest possible scope.  
* **Private Members:** Use a leading underscore (\_) for all member variables and methods not intended for public use. This is a strong convention in both Python and GDScript. Other parts of the code must not access these private members directly.  
* **No Unnecessary Globals:** Shared state must be managed through well-defined service locators (like Godot singletons) or application context objects (like Flask's g or a dedicated context class), or passed explicitly as function arguments.

### **2.7 Commandment VII: Always Check Return Values**

**Rationale:** Ignoring a function's return value can mask failures that lead to critical bugs.

**Implementation:**

* **Mandatory Checks:** If a function can return a value indicating success or failure (e.g., null/None, false, an error code), the calling code *must* check this value and handle the failure case.  
  \# Python Server Example  
  item \= db.find\_item\_by\_name("sword")  
  if item is None:  
      \# Handle the "item not found" case.  
      return {"error": "You don't see that here."}, 404  
  \# Continue, knowing 'item' is a valid object.

* **Explicit Discard:** In the rare case that a return value is truly not needed, make this intent explicit. In GDScript, assign to var \_err. In Python, assign to \_. This signals to reviewers that the omission was deliberate.

### **2.8 Commandment VIII: Use Static Typing Rigorously**

**Rationale:** Dynamic typing defers type checking until runtime. Static typing and type hints allow errors to be caught during development, leading to more robust code.

**Implementation:**

* **Explicit Typing is the Default:** All variables, function arguments, and function return values *must* be declared with an explicit type.  
* **GDScript:** Use static typing for all declarations (e.g., var health: int \= 100, func apply\_damage(amount: int) \-\> bool:).  
* **Python:** Use standard type hints for all declarations (e.g., health: int \= 100, def apply\_damage(amount: int) \-\> bool:). Use a static analysis tool like mypy to verify types.  
* **Limit Type Inference:** Type inference (:= in GDScript, or untyped variables in Python) is only permitted when the type is unambiguously clear from the right-hand side of the assignment on the same line (e.g., my\_list: list\[str\] \= \[\], player\_name := "Aragorn").

### **2.9 Commandment IX: Limit Complex Object References**

**Rationale:** Long chains of method calls (a.get\_b().get\_c().get\_d()) create tight coupling and violate encapsulation, making the code brittle and hard to refactor.

**Implementation:**

* **No "Train Wrecks":** A method should only talk to its immediate "friends," not "friends of friends."  
  * **Bad:** mod \= player.get\_weapon().stats.damage\_modifier  
  * **Good:** mod \= player.get\_total\_damage\_modifier()  
* In the "Good" example, the Player class is responsible for calculating its own data, hiding the internal complexity. This makes the system more modular.

### **2.10 Commandment X: Lint Clean, Run Clean**

**Rationale:** Compiler warnings, static analysis errors, and linter messages are indicators of potential bugs. A disciplined development process treats warnings as errors.

**Implementation:**

* **Zero Warnings/Errors Policy:** All submitted code must be free of any warnings or errors from the Godot script editor and the Python linter/type checker (flake8, mypy).  
* **This includes, but is not limited to:** unused variables, shadowed names, unsafe property access on a potentially null/None reference.  
* **Zero Assertion Failures:** All assert() statements in the code must pass during testing. A contribution that causes an assertion to fail will be rejected.

## **Section 3: Style and Structure**

To ensure consistency, this project strictly adheres to the official style guides for each language. This reduces cognitive load and allows developers to focus on logic rather than formatting.

### **3.1 Naming Conventions**

| Element Type | GDScript Case | Python Case (PEP 8\) |
| :---- | :---- | :---- |
| Class Name | PascalCase | PascalCase |
| Function / Method | snake\_case | snake\_case |
| Variable | snake\_case | snake\_case |
| Constant | CONSTANT\_CASE | CONSTANT\_CASE |
| Signal (GDScript) | snake\_case | N/A |
| Enum Name | PascalCase | PascalCase |
| Enum Member | CONSTANT\_CASE | CONSTANT\_CASE |
| File Name | snake\_case.gd | snake\_case.py |

### **3.2 Code Order**

Predictable file structure makes code easier to navigate.

#### **GDScript File Order**

1. @tool, @icon annotations  
2. class\_name  
3. extends  
4. Documentation comment (\#\# Docstring)  
5. signal declarations  
6. enum definitions  
7. const definitions  
8. @export variables  
9. Public member variables  
10. Private member variables (\_ prefix)  
11. @onready variables  
12. Built-in virtual methods (\_init, \_ready, \_process, etc.)  
13. Public methods  
14. Private methods (\_ prefix)

#### **Python File Order (PEP 8\)**

1. Shebang line (if applicable)  
2. Module docstring  
3. Imports (standard library, then third-party, then local application)  
4. Module-level "dunder" names (\_\_author\_\_, \_\_version\_\_)  
5. Module-level constants  
6. Module-level variables  
7. Class definitions  
8. Top-level function definitions  
9. Main execution block (if \_\_name\_\_ \== "\_\_main\_\_":)

### **3.3 Formatting**

| Rule | GDScript | Python (PEP 8\) |
| :---- | :---- | :---- |
| **Indentation** | **Tabs** (Godot standard) | **4 Spaces** (Language requirement) |
| **Line Length** | Max **100 characters** | Max **99 characters** (per Black formatter) |
| **Blank Lines** | **Two** between functions/classes. **One** for logical sections inside functions. | **Two** between top-level functions/classes. **One** for logical sections inside methods. |
| **Spacing** | Single space around operators and after commas. | Single space around operators and after commas. |
| **Trailing Commas** | Recommended for multi-line collections. | Recommended for multi-line collections. |

