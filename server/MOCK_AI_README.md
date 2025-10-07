# MockAI — Testing AI Features Without API Calls

The MockAI system provides a comprehensive solution for testing AI-dependent features in TinyMUD without making actual API calls. This enables fast, deterministic tests and eliminates the need for API keys during development and CI.

## Quick Start

```python
from mock_ai import MockAIModel, create_dialogue_mock

# Simple usage
mock = MockAIModel("Default AI response")
mock.add_response_pattern(r"hello", "Hello back!")

response = mock.generate_content("Say hello to me")
print(response.text)  # "Hello back!"

# Use predefined mocks for common scenarios
dialogue_mock = create_dialogue_mock()
response = dialogue_mock.generate_content("Player greets NPC")
print(response.text)  # "Hello there, traveler! Welcome to our humble town."
```

## Core Components

### MockAIResponse
Mimics the Gemini AI response structure with a `.text` attribute.

```python
response = MockAIResponse("Test content")
assert response.text == "Test content"
```

### MockAIModel
The main mock class that provides pattern-based response generation.

```python
mock = MockAIModel(default_response="Default response")

# Add specific patterns
mock.add_response_pattern(r"create.*npc", '{"name": "Test NPC"}')
mock.add_error_pattern(r"error", ValueError("Test error"))

# Generate responses
response = mock.generate_content("Please create an NPC")  # Returns JSON
mock.generate_content("This should error")  # Raises ValueError
```

### Pattern Matching
- Patterns are regular expressions (case-insensitive)
- First matching pattern wins
- Error patterns are checked before response patterns
- Unmatched prompts return the default response

## Predefined Mocks

### NPC Generation Mock
```python
from mock_ai import create_npc_generation_mock

mock = create_npc_generation_mock()
response = mock.generate_content("Create a new character")
npc_data = json.loads(response.text)  # {"name": "Test Warrior", ...}
```

### GOAP Planning Mock
```python
from mock_ai import create_goap_planning_mock

mock = create_goap_planning_mock()
response = mock.generate_content("NPC needs to eat something")
actions = json.loads(response.text)  # [{"tool": "get_object", ...}, ...]
```

### Dialogue Mock
```python
from mock_ai import create_dialogue_mock

mock = create_dialogue_mock()
response = mock.generate_content("Player says hello")
# Returns conversational text, not JSON
```

### World Setup Mock
```python
from mock_ai import create_world_setup_mock

mock = create_world_setup_mock()
response = mock.generate_content("Create multiple rooms")
rooms = json.loads(response.text)  # [{"name": "Town Square", ...}, ...]
```

## Integration with Server Tests

### Method 1: Context Manager (Recommended)
```python
import server
from mock_ai import create_dialogue_mock, patch_server_model

def test_npc_dialogue():
    mock = create_dialogue_mock()
    
    with patch_server_model(server, mock) as patched_mock:
        # Server AI calls will use the mock
        # ... test code here ...
        
        # Verify mock was called
        assert patched_mock.call_count > 0
        assert patched_mock.was_called_with_pattern(r"hello")
    
    # Original models are automatically restored
```

### Method 2: Direct Assignment
```python
import server
from mock_ai import MockAIModel

def test_feature():
    original_model = server.model
    server.model = MockAIModel("Test response")
    
    try:
        # ... test code ...
        pass
    finally:
        server.model = original_model
```

## Advanced Usage

### Custom Response Patterns
```python
mock = MockAIModel()

# Complex regex patterns
mock.add_response_pattern(
    r"create\s+(npc|character)\s+.*(?:warrior|fighter)",
    '{"name": "Warrior", "class": "fighter"}'
)

# Multiple patterns for different scenarios
mock.add_response_pattern(r"greet|hello", "Greetings!")
mock.add_response_pattern(r"trade|buy|sell", "Let's make a deal!")
mock.add_response_pattern(r"goodbye|farewell", "Safe travels!")
```

### Error Simulation
```python
mock = MockAIModel()

# Simulate API failures
mock.add_error_pattern(r"api.*failure", ConnectionError("API is down"))
mock.add_error_pattern(r"invalid.*format", ValueError("Invalid JSON"))

# Test error handling
try:
    mock.generate_content("This should cause an API failure")
except ConnectionError:
    print("Error handling works!")
```

### Call History and Verification
```python
mock = MockAIModel()
mock.add_response_pattern(r"test", "Test response")

mock.generate_content("First test prompt")
mock.generate_content("Second test prompt")

# Check call history
assert mock.call_count == 2
assert mock.get_last_prompt() == "Second test prompt"
assert mock.was_called_with_pattern(r"test")

# Clear history for next test
mock.clear_patterns()
```

## JSON Response Handling

MockAI can return JSON wrapped in markdown code fences (like real Gemini):

```python
mock = MockAIModel()
json_response = '''```json
{
  "name": "Test Character",
  "description": "A test NPC"
}
```'''

mock.add_response_pattern(r"json", json_response)
response = mock.generate_content("Return some JSON data")

# Extract JSON using existing server patterns
import re
json_match = re.search(r'```json\s*\n(.*?)\n```', response.text, re.DOTALL)
if json_match:
    clean_json = json_match.group(1)
    data = json.loads(clean_json)
```

## Performance Benefits

MockAI provides significant performance improvements for tests:

- **Speed**: 100+ mock calls complete in milliseconds vs. seconds for real API calls
- **Reliability**: No network dependencies or API rate limits
- **Determinism**: Same input always produces same output
- **Cost**: Zero API costs during development and CI

## Best Practices

1. **Use predefined mocks** when possible - they're tested and cover common patterns
2. **Pattern order matters** - more specific patterns should come before general ones
3. **Test both success and failure** scenarios using error patterns
4. **Verify mock usage** in tests to ensure AI integration is actually being exercised
5. **Clear state between tests** to avoid test pollution
6. **Use word boundaries** in regex patterns to avoid partial matches

## Example Test Structure

```python
import pytest
from mock_ai import create_npc_generation_mock, patch_server_model

def test_npc_creation():
    """Test NPC creation with AI assistance."""
    import server
    
    # Set up test world
    setup_test_world(server)
    
    # Configure mock AI
    mock = create_npc_generation_mock()
    
    with patch_server_model(server, mock) as ai_mock:
        # Execute feature that uses AI
        result = server.create_npc_with_ai("tavern", "Create a friendly bartender")
        
        # Verify results
        assert result.success
        assert "bartender" in server.world.rooms["tavern"].npcs
        
        # Verify AI was used correctly
        assert ai_mock.call_count == 1
        assert ai_mock.was_called_with_pattern(r"create.*npc")
```

This testing approach ensures your AI features work correctly while maintaining fast, reliable test execution.