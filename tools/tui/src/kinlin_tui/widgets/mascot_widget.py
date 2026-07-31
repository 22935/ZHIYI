"""Mascot widget rendering the role-themed ASCII sprite with mood and colour.

Also renders a dialogue bubble below the mascot that shows welcome messages
on first mount and mood-driven lines thereafter.
"""

from textual.widgets import Static
from textual.reactive import reactive
from rich.text import Text

from kinlin_tui.mascot import (
    CHARACTER_NAMES,
    MascotCharacter,
    MascotMood,
    WELCOME_BANNER,
    get_dialogue,
    get_mascot_text,
    MASCOT_FRAME_WIDTH,
)
from kinlin_tui.theme import RoleTheme, ROLE_COLORS

# RoleTheme -> MascotCharacter mapping
_ROLE_TO_CHARACTER = {
    RoleTheme.LAWYER: MascotCharacter.LAWYER,
    RoleTheme.TEACHER: MascotCharacter.TEACHER,
    RoleTheme.PROGRAMMER: MascotCharacter.PROGRAMMER,
    RoleTheme.WRITER: MascotCharacter.WRITER,
}

# Separator between mascot art and dialogue bubble
_DIALOG_SEP = "─" * MASCOT_FRAME_WIDTH


class MascotWidget(Static):
    """Renders the role-appropriate mascot with the current mood.

    Reactive attributes
    -------------------
    mood : MascotMood
        Current facial expression (IDLE, THINKING, WORKING, HAPPY, ERROR, WAITING).
    role : RoleTheme
        Current agent role — changes the character and accent colour.
    """

    mood: MascotMood = reactive(MascotMood.IDLE, layout=True)
    role: RoleTheme = reactive(RoleTheme.LAWYER, layout=True)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._show_welcome: bool = True

    def watch_mood(self, old: MascotMood, new: MascotMood) -> None:
        # Once the mood changes away from IDLE we stop showing the welcome banner.
        if new != MascotMood.IDLE:
            self._show_welcome = False
        self.refresh(layout=True)

    def watch_role(self, _old: RoleTheme, _new: RoleTheme) -> None:
        self.refresh(layout=True)

    def render(self) -> Text:
        character = _ROLE_TO_CHARACTER.get(self.role, MascotCharacter.LAWYER)
        mascot = get_mascot_text(mood=self.mood, character=character)
        accent = ROLE_COLORS.get(self.role, "#409EFF")
        name = CHARACTER_NAMES.get(character, "Mascot")

        if self._show_welcome and self.mood == MascotMood.IDLE:
            # Show the full welcome banner on first mount / role switch idle.
            banner_lines = WELCOME_BANNER.get(character, WELCOME_BANNER[MascotCharacter.LAWYER])
            dialogue_block = "\n".join(
                f"[bold {accent}]{line}[/]" for line in banner_lines
            )
        else:
            # Single interactive dialogue line.
            dialogue_text = get_dialogue(mood=self.mood, character=character)
            dialogue_block = f"[bold {accent}]{name}:[/] [italic]{dialogue_text}[/]"

        sep = f"[dim]{_DIALOG_SEP}[/]"
        return Text.from_markup(f"{mascot}\n{sep}\n{dialogue_block}")
