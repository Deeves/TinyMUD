# TinyMUD Code Style and Conventions

## Python Code Style
- **Type hints**: Use comprehensive type annotations (from typing import)
- **Docstrings**: Include detailed docstrings explaining purpose and return values
- **Comments**: ~70% code, ~30% comments ratio
- **Comment style**: Enthusiastic teaching voice explaining "why" not "what"
- **Function returns**: Services return tuples like (handled/ok, err, emits[, broadcasts])

## Naming Conventions
- **Functions**: snake_case
- **Classes**: PascalCase
- **Constants**: UPPER_SNAKE_CASE
- **Private functions**: Leading underscore _private_function()
- **File naming**: snake_case.py

## Architecture Patterns
- **Router pattern**: Commands flow through *_router.py → *_service.py → emit
- **CommandContext**: Pass CommandContext object instead of individual parameters  
- **Safe execution**: Use safe_call() from safe_utils.py instead of bare except blocks
- **Input parsing**: Use helpers from id_parse_utils for normalization
- **Fuzzy resolution**: Deterministic ordering (exact → ci-exact → unique prefix → unique substring)

## Error Handling
- Return structured error tuples rather than raising exceptions
- Use safe_call() for graceful degradation
- Provide helpful error messages with suggestions

## Testing
- Use pytest framework
- MockAI framework for deterministic AI testing
- Test service functions directly, not just integration
- Include edge cases and ambiguous input scenarios