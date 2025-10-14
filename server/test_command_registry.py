"""Tests for the centralized command registry system."""

import pytest
from unittest.mock import Mock
from command_registry import (
    CommandRegistry, CommandMetadata, CommandArgument,
    PermissionLevel, ArgumentType, registry
)
from command_context import CommandContext


class TestCommandRegistry:
    """Test suite for the command registry system."""

    def setup_method(self):
        """Set up a fresh registry for each test."""
        self.registry = CommandRegistry()
        self.mock_emit = Mock()
        self.mock_ctx = Mock(spec=CommandContext)
        self.mock_ctx.message_out = "message"
        self.mock_ctx.sessions = {"test_sid": True}
        self.mock_ctx.admins = {"admin_sid"}

    def test_command_registration(self):
        """Test basic command registration."""
        @self.registry.command(
            name="test",
            description="A test command",
            permission=PermissionLevel.PUBLIC
        )
        def test_handler(ctx, sid, args, emit):
            return True

        # Check command was registered
        cmd = self.registry.get_command("test")
        assert cmd is not None
        assert cmd.name == "test"
        assert cmd.description == "A test command"
        assert cmd.permission == PermissionLevel.PUBLIC
        assert cmd.handler == test_handler

    def test_subcommand_registration(self):
        """Test subcommand registration."""
        @self.registry.command(
            name="parent",
            description="Parent command"
        )
        def parent_handler(ctx, sid, args, emit):
            return True

        @self.registry.subcommand(
            parent_name="parent",
            sub_name="sub",
            description="Subcommand"
        )
        def sub_handler(ctx, sid, args, emit):
            return True

        parent = self.registry.get_command("parent")
        assert "sub" in parent.subcommands
        assert parent.subcommands["sub"].description == "Subcommand"

    def test_alias_resolution(self):
        """Test command alias resolution."""
        @self.registry.command(
            name="original",
            aliases=["alias1", "alias2"]
        )
        def handler(ctx, sid, args, emit):
            return True

        # Test alias resolution
        cmd1 = self.registry.get_command("alias1")
        cmd2 = self.registry.get_command("original")
        assert cmd1 == cmd2

    def test_permission_checking_public(self):
        """Test public permission checking."""
        @self.registry.command(
            name="public_cmd",
            permission=PermissionLevel.PUBLIC
        )
        def handler(ctx, sid, args, emit):
            emit("message", {"type": "system", "content": "success"})
            return True

        # Should work without session
        result = self.registry.try_handle_slash(
            self.mock_ctx, None, "public_cmd", [], "", self.mock_emit
        )
        assert result is True
        self.mock_emit.assert_called_with("message", {"type": "system", "content": "success"})

    def test_permission_checking_authenticated(self):
        """Test authenticated permission checking."""
        @self.registry.command(
            name="auth_cmd",
            permission=PermissionLevel.AUTHENTICATED
        )
        def handler(ctx, sid, args, emit):
            emit("message", {"type": "system", "content": "success"})
            return True

        # Should fail without session
        result = self.registry.try_handle_slash(
            self.mock_ctx, "unknown_sid", "auth_cmd", [], "", self.mock_emit
        )
        assert result is True
        self.mock_emit.assert_called_with("message", {
            "type": "error", "content": "Please log in first."
        })

        # Should work with valid session
        self.mock_emit.reset_mock()
        result = self.registry.try_handle_slash(
            self.mock_ctx, "test_sid", "auth_cmd", [], "", self.mock_emit
        )
        assert result is True
        self.mock_emit.assert_called_with("message", {"type": "system", "content": "success"})

    def test_permission_checking_admin(self):
        """Test admin permission checking."""
        @self.registry.command(
            name="admin_cmd",
            permission=PermissionLevel.ADMIN
        )
        def handler(ctx, sid, args, emit):
            emit("message", {"type": "system", "content": "admin_success"})
            return True

        # Should fail for non-admin
        result = self.registry.try_handle_slash(
            self.mock_ctx, "test_sid", "admin_cmd", [], "", self.mock_emit
        )
        assert result is True
        self.mock_emit.assert_called_with("message", {
            "type": "error", "content": "Admin command. Admin rights required."
        })

        # Should work for admin
        self.mock_emit.reset_mock()
        result = self.registry.try_handle_slash(
            self.mock_ctx, "admin_sid", "admin_cmd", [], "", self.mock_emit
        )
        assert result is True
        self.mock_emit.assert_called_with("message", {
            "type": "system", "content": "admin_success"
        })

    def test_argument_parsing(self):
        """Test argument parsing and validation."""
        @self.registry.command(
            name="arg_test",
            arguments=[
                CommandArgument("required_arg", ArgumentType.STRING, "Required argument"),
                CommandArgument("optional_arg", ArgumentType.STRING, "Optional argument",
                                required=False, default="default")
            ]
        )
        def handler(ctx, sid, args, emit):
            content = f"required: {args['required_arg']}, optional: {args['optional_arg']}"
            emit("message", {"type": "system", "content": content})
            return True

        # Test with required arg only
        result = self.registry.try_handle_slash(
            self.mock_ctx, None, "arg_test", ["value1"], "", self.mock_emit
        )
        assert result is True
        self.mock_emit.assert_called_with("message", {
            "type": "system", "content": "required: value1, optional: default"
        })

        # Test with both args
        self.mock_emit.reset_mock()
        result = self.registry.try_handle_slash(
            self.mock_ctx, None, "arg_test", ["value1", "value2"], "", self.mock_emit
        )
        assert result is True
        self.mock_emit.assert_called_with("message", {
            "type": "system", "content": "required: value1, optional: value2"
        })

        # Test missing required arg (should show usage)
        self.mock_emit.reset_mock()
        result = self.registry.try_handle_slash(
            self.mock_ctx, None, "arg_test", [], "", self.mock_emit
        )
        assert result is True
        # Should emit usage text
        call_args = self.mock_emit.call_args
        assert call_args[0][0] == "message"
        message_data = call_args[0][1]
        assert message_data["type"] == "error"
        assert "Usage:" in message_data["content"]

    def test_subcommand_handling(self):
        """Test subcommand execution."""
        @self.registry.command(name="parent", description="Parent")
        def parent_handler(ctx, sid, args, emit):
            return True

        @self.registry.subcommand(
            parent_name="parent",
            sub_name="action",
            description="Subcommand action",
            arguments=[
                CommandArgument("param", ArgumentType.STRING, "Parameter")
            ]
        )
        def sub_handler(ctx, sid, args, emit):
            emit("message", {"type": "system", "content": f"sub action: {args['param']}"})
            return True

        # Test subcommand execution
        result = self.registry.try_handle_slash(
            self.mock_ctx, None, "parent", ["action", "test_value"], "", self.mock_emit
        )
        assert result is True
        self.mock_emit.assert_called_with("message", {
            "type": "system", "content": "sub action: test_value"
        })

    def test_unknown_command(self):
        """Test handling of unknown commands."""
        result = self.registry.try_handle_slash(
            self.mock_ctx, None, "unknown", [], "", self.mock_emit
        )
        assert result is False

    def test_usage_text_generation(self):
        """Test automatic usage text generation."""
        metadata = CommandMetadata(
            name="test",
            description="Test command",
            permission=PermissionLevel.PUBLIC,
            arguments=[
                CommandArgument("required", ArgumentType.STRING, "Required", required=True),
                CommandArgument("optional", ArgumentType.STRING, "Optional", required=False)
            ]
        )
        
        usage = metadata.generate_usage_text()
        assert usage == "Usage: /test <required> [optional]"

    def test_usage_text_with_subcommands(self):
        """Test usage text generation for commands with subcommands."""
        metadata = CommandMetadata(
            name="parent",
            description="Parent command",
            permission=PermissionLevel.PUBLIC,
            subcommands={
                "sub1": CommandMetadata("sub1", "First sub", PermissionLevel.PUBLIC),
                "sub2": CommandMetadata("sub2", "Second sub", PermissionLevel.PUBLIC)
            }
        )
        
        usage = metadata.generate_usage_text()
        assert "Usage: /parent <sub1|sub2>" in usage

    def test_help_text_generation(self):
        """Test comprehensive help text generation."""
        metadata = CommandMetadata(
            name="complex",
            description="A complex command",
            permission=PermissionLevel.PUBLIC,
            arguments=[
                CommandArgument("arg1", ArgumentType.STRING, "First argument"),
                CommandArgument("arg2", ArgumentType.STRING, "Second argument", required=False)
            ],
            aliases=["comp", "cx"]
        )
        
        help_text = metadata.generate_help_text()
        assert "**/complex**" in help_text
        assert "A complex command" in help_text
        assert "Usage:" in help_text
        assert "Arguments:" in help_text
        assert "First argument" in help_text
        assert "Aliases:" in help_text
        assert "comp, cx" in help_text


def test_global_registry_help_command():
    """Test the built-in help command on global registry."""
    mock_emit = Mock()
    mock_ctx = Mock(spec=CommandContext)
    mock_ctx.message_out = "message"
    mock_ctx.sessions = {}
    mock_ctx.admins = set()
    
    # Test general help
    result = registry.try_handle_slash(mock_ctx, None, "help", [], "", mock_emit)
    assert result is True
    
    # Should have been called with available commands
    call_args = mock_emit.call_args
    assert call_args[0][0] == "message"
    message_data = call_args[0][1]
    assert message_data["type"] == "system"
    content = message_data["content"]
    assert "Available commands:" in content or "No commands available." in content


if __name__ == "__main__":
    pytest.main([__file__])