"""
AgentOS TUI mascots — four role-themed ASCII companions with colour-filled bodies.

Characters
---------
- YI ZAI   (lawyer)    — Go-stone sprite, deep-blue body, blue-white eyes.
- ZHI BAO  (teacher)   — owl scholar, deep-purple body, golden eyes.
- JUAN JUAN (writer)   — open-book sprite, warm cream body, round glasses.
- DOU DOU  (programmer)— pixel sprite, terminal-black body, neon-cyan eyes.

Each character has 6 mood frames rendered with Rich/Textual BBCode colour tags
so they can be dropped directly into a ``RichLog`` or ``Static`` widget.
"""

from __future__ import annotations

import random
from enum import Enum
from typing import Dict, List

from rich.markup import escape
from rich.text import Text

# ═══════════════════════════════════════════════════════════════════════════
# Dialogue / welcome-message system  (forward declarations)
# ═══════════════════════════════════════════════════════════════════════════

# Per-character welcome banner — populated by _build_dialogue_pools().
WELCOME_BANNER: dict[MascotCharacter, list[str]] = {}

# Mood-driven dialogue pools — populated by _build_dialogue_pools().
_DIALOGUE_POOL: dict[MascotCharacter, dict[MascotMood, list[str]]] = {}


# ═══════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════


class MascotMood(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    WORKING = "working"
    HAPPY = "happy"
    ERROR = "error"
    WAITING = "waiting"


class MascotCharacter(str, Enum):
    LAWYER = "lawyer"
    TEACHER = "teacher"
    PROGRAMMER = "programmer"
    WRITER = "writer"


def get_dialogue(
    mood: MascotMood = MascotMood.IDLE,
    character: MascotCharacter = MascotCharacter.LAWYER,
) -> str:
    """Return a single random dialogue line for *mood* and *character*.

    Falls back to the IDLE pool if *mood* has no lines for this character.
    """
    pool = _DIALOGUE_POOL.get(character, _DIALOGUE_POOL[MascotCharacter.LAWYER])
    candidates = pool.get(mood, pool.get(MascotMood.IDLE, ["你好！"]))
    return random.choice(candidates)


# ═══════════════════════════════════════════════════════════════════════════
# Colour palettes
# ═══════════════════════════════════════════════════════════════════════════

PALETTES: Dict[MascotCharacter, Dict[str, str]] = {
    MascotCharacter.LAWYER: {
        "outline": "#409EFF",
        "body": "#1a2744",
        "eye": "#c0caf5",
        "mouth": "#e6a23c",
        "cheek": "#ff6b9d",
        "icon": "#ffd700",
    },
    MascotCharacter.TEACHER: {
        "outline": "#9B59B6",
        "body": "#2d1b69",
        "eye": "#ffd700",
        "mouth": "#e6a23c",
        "feather": "#67c23a",
        "beak": "#e6a23c",
        "belly": "#c792ea",
        "gem": "#58a6ff",
        "icon": "#ffd700",
    },
    MascotCharacter.WRITER: {
        "outline": "#E6A23C",
        "body": "#fff3cd",
        "glasses": "#8B4513",
        "lens": "#ffffff",
        "eye": "#5D4037",
        "mouth": "#ff69b4",
        "page": "#d4a574",
        "spine": "#E6A23C",
        "spark": "#67c23a",
        "icon": "#ff69b4",
    },
    MascotCharacter.PROGRAMMER: {
        "outline": "#9B59B6",
        "body": "#0d1117",
        "eye": "#00ffff",
        "mouth": "#c792ea",
        "antenna": "#58a6ff",
        "hand": "#c792ea",
        "led_ok": "#67c23a",
        "led_warn": "#e6a23c",
        "led_err": "#f56c6c",
        "base": "#30363d",
        "icon": "#c792ea",
    },
}


def _c(color_key: str, pal: Dict[str, str]) -> str:
    """Shortcut: ``[bold <colour>]`` tag for a palette key."""
    return f"[bold {pal[color_key]}]"


def _cf(color_key: str, pal: Dict[str, str], text: str) -> str:
    """Wraps *text* in a bold colour tag, returns plain text if empty."""
    if not text:
        return text
    return f"[bold {pal[color_key]}]{escape(text)}[/]"


# ═══════════════════════════════════════════════════════════════════════════
# Frames — each is a list[str] with inline Rich/Textual colour markup.
# ═══════════════════════════════════════════════════════════════════════════

_F: Dict[MascotCharacter, Dict[MascotMood, List[str]]] = {}


# ── YI ZAI · Lawyer · Go-stone sprite ─────────────────────────────────────

_YI = MascotCharacter.LAWYER
_P = PALETTES[_YI]
_F[_YI] = {}

_F[_YI][MascotMood.IDLE] = [
    f"    {_c('outline',_P)}.-~~~-.[/]    ",
    f"  {_c('outline',_P)}.'{_c('body',_P)}       {_c('outline',_P)}'.[/]  ",
    f" {_c('outline',_P)}/{_c('body',_P)}  {_c('eye',_P)}o     o{_c('body',_P)}  {_c('outline',_P)}\\[/] ",
    f"{_c('outline',_P)}|{_c('body',_P)}      {_c('mouth',_P)}v{_c('body',_P)}      {_c('outline',_P)}|[/]",
    f"{_c('outline',_P)}|{_c('body',_P)}   {_c('outline',_P)}\\\\{_c('mouth',_P)}_____/{_c('outline',_P)}/[/]{_c('body',_P)}   {_c('outline',_P)}|[/]",
    f" {_c('outline',_P)}\\\\{_c('body',_P)}           {_c('outline',_P)}/[/] ",
    f"  {_c('outline',_P)}'._     _.'[/]  ",
    f"    {_c('outline',_P)}'---'[/]     ",
    f"     {_c('icon',_P)}balance-scale[/]     ",
]

_F[_YI][MascotMood.THINKING] = [
    f"    {_c('outline',_P)}.-~~~-.[/]    ",
    f"  {_c('outline',_P)}.'{_c('body',_P)}       {_c('outline',_P)}'.[/]  ",
    f" {_c('outline',_P)}/{_c('body',_P)}  {_c('eye',_P)}u     u{_c('body',_P)}  {_c('outline',_P)}\\[/] ",
    f"{_c('outline',_P)}|{_c('body',_P)}      {_c('mouth',_P)}~{_c('body',_P)}      {_c('outline',_P)}|[/]",
    f"{_c('outline',_P)}|{_c('body',_P)}    {_c('cheek',_P)}. . .{_c('body',_P)}    {_c('outline',_P)}|[/]",
    f" {_c('outline',_P)}\\\\{_c('body',_P)}           {_c('outline',_P)}/[/] ",
    f"  {_c('outline',_P)}'._     _.'[/]  ",
    f"    {_c('outline',_P)}'---'[/]     ",
    f"     {_c('icon',_P)}scroll[/]     ",
]

_F[_YI][MascotMood.WORKING] = [
    f"    {_c('outline',_P)}.-~~~-.[/]    ",
    f"  {_c('outline',_P)}.'{_c('body',_P)}       {_c('outline',_P)}'.[/]  ",
    f" {_c('outline',_P)}/{_c('body',_P)}  {_c('eye',_P)}*     *{_c('body',_P)}  {_c('outline',_P)}\\[/] ",
    f"{_c('outline',_P)}|{_c('body',_P)}      {_c('mouth',_P)}o{_c('body',_P)}      {_c('outline',_P)}|[/]",
    f"{_c('outline',_P)}|{_c('body',_P)}   {_c('outline',_P)}/-----\\[/]{_c('body',_P)}   {_c('outline',_P)}|[/]",
    f" {_c('outline',_P)}\\\\{_c('body',_P)}           {_c('outline',_P)}/[/] ",
    f"  {_c('outline',_P)}'._     _.'[/]  ",
    f"    {_c('outline',_P)}'---'[/]     ",
    f"     {_c('icon',_P)}bolt[/]     ",
]

_F[_YI][MascotMood.HAPPY] = [
    f"    {_c('outline',_P)}.-~~~-.[/]    ",
    f"  {_c('outline',_P)}.'{_c('body',_P)}       {_c('outline',_P)}'.[/]  ",
    f" {_c('outline',_P)}/{_c('body',_P)}  {_c('eye',_P)}^     ^{_c('body',_P)}  {_c('outline',_P)}\\[/] ",
    f"{_c('outline',_P)}|{_c('body',_P)}      {_c('mouth',_P)}v{_c('body',_P)}      {_c('outline',_P)}|[/]",
    f"{_c('outline',_P)}|{_c('body',_P)}   {_c('outline',_P)}\\\\{_c('mouth',_P)}_____/{_c('outline',_P)}/[/]{_c('body',_P)}   {_c('outline',_P)}|[/]",
    f" {_c('outline',_P)}\\\\{_c('body',_P)}           {_c('outline',_P)}/[/] ",
    f"  {_c('outline',_P)}'._     _.'[/]  ",
    f"    {_c('outline',_P)}'---'[/]     ",
    f"     {_c('icon',_P)}star[/]     ",
]

_F[_YI][MascotMood.ERROR] = [
    f"    {_c('outline',_P)}.-~~~-.[/]    ",
    f"  {_c('outline',_P)}.'{_c('body',_P)}       {_c('outline',_P)}'.[/]  ",
    f" {_c('outline',_P)}/{_c('body',_P)}  {_c('eye',_P)}>     <{_c('body',_P)}  {_c('outline',_P)}\\[/] ",
    f"{_c('outline',_P)}|{_c('body',_P)}      {_c('mouth',_P)}-{_c('body',_P)}      {_c('outline',_P)}|[/]",
    f"{_c('outline',_P)}|{_c('body',_P)}    {_c('cheek',_P)}-----{_c('body',_P)}    {_c('outline',_P)}|[/]",
    f" {_c('outline',_P)}\\\\{_c('body',_P)}           {_c('outline',_P)}/[/] ",
    f"  {_c('outline',_P)}'._     _.'[/]  ",
    f"    {_c('outline',_P)}'---'[/]     ",
    f"     {_c('icon',_P)}cross-mark[/]     ",
]

_F[_YI][MascotMood.WAITING] = [
    f"    {_c('outline',_P)}.-~~~-.[/]    ",
    f"  {_c('outline',_P)}.'{_c('body',_P)}       {_c('outline',_P)}'.[/]  ",
    f" {_c('outline',_P)}/{_c('body',_P)}  {_c('eye',_P)}.     .{_c('body',_P)}  {_c('outline',_P)}\\[/] ",
    f"{_c('outline',_P)}|{_c('body',_P)}      {_c('mouth',_P)}?{_c('body',_P)}      {_c('outline',_P)}|[/]",
    f"{_c('outline',_P)}|{_c('body',_P)}    {_c('cheek',_P)}_____[/]{_c('body',_P)}    {_c('outline',_P)}|[/]",
    f" {_c('outline',_P)}\\\\{_c('body',_P)}           {_c('outline',_P)}/[/] ",
    f"  {_c('outline',_P)}'._     _.'[/]  ",
    f"    {_c('outline',_P)}'---'[/]     ",
    f"     {_c('icon',_P)}hourglass[/]     ",
]


# ── ZHI BAO · Teacher · Owl scholar ───────────────────────────────────────

_ZB = MascotCharacter.TEACHER
_P = PALETTES[_ZB]
_F[_ZB] = {}

_F[_ZB][MascotMood.IDLE] = [
    f"     {_c('outline',_P)}.-.-.{_c('body',_P)}.{_c('outline',_P)}.-.-.[/]     ",
    f"   {_c('outline',_P)}.'{_c('body',_P)} {_c('eye',_P)}o     o{_c('body',_P)} {_c('outline',_P)}'.[/]   ",
    f"  {_c('outline',_P)}|{_c('body',_P)}  {_c('gem',_P)}diamond-2{_c('body',_P)}  {_c('outline',_P)}|[/]  ",
    f"  {_c('outline',_P)}|{_c('body',_P)}  {_c('mouth',_P)}------{_c('body',_P)}  {_c('outline',_P)}|[/]  ",
    f"   {_c('outline',_P)}\\\\{_c('belly',_P)}_________{_c('outline',_P)}/[/]   ",
    f"    {_c('outline',_P)}||{_c('feather',_P)}     {_c('outline',_P)}||[/]    ",
    f"    {_c('beak',_P)}__{_c('outline',_P)}||{_c('beak',_P)}_____||{_c('outline',_P)}[/]    ",
    f"        {_c('beak',_P)}~~~~~[/]        ",
    f"       {_c('icon',_P)}books[/]       ",
]

_F[_ZB][MascotMood.THINKING] = [
    f"     {_c('outline',_P)}.-.-.{_c('body',_P)}.{_c('outline',_P)}.-.-.[/]     ",
    f"   {_c('outline',_P)}.'{_c('body',_P)} {_c('eye',_P)}u     u{_c('body',_P)} {_c('outline',_P)}'.[/]   ",
    f"  {_c('outline',_P)}|{_c('body',_P)}  {_c('gem',_P)}diamond-2{_c('body',_P)}  {_c('outline',_P)}|[/]  ",
    f"  {_c('outline',_P)}|{_c('body',_P)}  {_c('mouth',_P)}......{_c('body',_P)}  {_c('outline',_P)}|[/]  ",
    f"   {_c('outline',_P)}\\\\{_c('belly',_P)}_________>{_c('outline',_P)}/[/]   ",
    f"    {_c('outline',_P)}||{_c('feather',_P)}     {_c('outline',_P)}||[/]    ",
    f"    {_c('beak',_P)}__{_c('outline',_P)}||{_c('beak',_P)}_____||{_c('outline',_P)}[/]    ",
    f"        {_c('beak',_P)}~~~~~[/]        ",
    f"       {_c('icon',_P)}thinking-face[/]       ",
]

_F[_ZB][MascotMood.WORKING] = [
    f"     {_c('outline',_P)}.-.-.{_c('body',_P)}.{_c('outline',_P)}.-.-.[/]     ",
    f"   {_c('outline',_P)}.'{_c('body',_P)} {_c('eye',_P)}*     *{_c('body',_P)} {_c('outline',_P)}'.[/]   ",
    f"  {_c('outline',_P)}|{_c('body',_P)}  {_c('gem',_P)}diamond-2{_c('body',_P)}  {_c('outline',_P)}|[/]  ",
    f"  {_c('outline',_P)}|{_c('body',_P)}  {_c('mouth',_P)}o-o-o-o{_c('body',_P)}  {_c('outline',_P)}|[/]  ",
    f"   {_c('outline',_P)}\\\\{_c('belly',_P)}_________>{_c('outline',_P)}/[/]   ",
    f"    {_c('outline',_P)}||{_c('feather',_P)}  ||  {_c('outline',_P)}||[/]    ",
    f"    {_c('beak',_P)}__{_c('outline',_P)}||{_c('beak',_P)}_____||{_c('outline',_P)}[/]    ",
    f"        {_c('beak',_P)}~~~~~[/]        ",
    f"       {_c('icon',_P)}graduation-cap[/]       ",
]

_F[_ZB][MascotMood.HAPPY] = [
    f"     {_c('outline',_P)}.-.-.{_c('body',_P)}.{_c('outline',_P)}.-.-.[/]     ",
    f"   {_c('outline',_P)}.'{_c('body',_P)} {_c('eye',_P)}^     ^{_c('body',_P)} {_c('outline',_P)}'.[/]   ",
    f"  {_c('outline',_P)}|{_c('body',_P)}  {_c('gem',_P)}diamond-2{_c('body',_P)}  {_c('outline',_P)}|[/]  ",
    f"  {_c('outline',_P)}|{_c('body',_P)}  {_c('mouth',_P)}v--v--v{_c('body',_P)}  {_c('outline',_P)}|[/]  ",
    f"   {_c('outline',_P)}\\\\{_c('belly',_P)}_________>{_c('outline',_P)}/[/]   ",
    f"    {_c('outline',_P)}||{_c('feather',_P)}  ^^  {_c('outline',_P)}||[/]    ",
    f"    {_c('beak',_P)}__{_c('outline',_P)}||{_c('beak',_P)}_____||{_c('outline',_P)}[/]    ",
    f"        {_c('beak',_P)}~~~~~[/]        ",
    f"       {_c('icon',_P)}star-struck[/]       ",
]

_F[_ZB][MascotMood.ERROR] = [
    f"     {_c('outline',_P)}.-.-.{_c('body',_P)}.{_c('outline',_P)}.-.-.[/]     ",
    f"   {_c('outline',_P)}.'{_c('body',_P)} {_c('eye',_P)}>     <{_c('body',_P)} {_c('outline',_P)}'.[/]   ",
    f"  {_c('outline',_P)}|{_c('body',_P)}  {_c('gem',_P)}diamond-2{_c('body',_P)}  {_c('outline',_P)}|[/]  ",
    f"  {_c('outline',_P)}|{_c('body',_P)}  {_c('mouth',_P)}-..-..-{_c('body',_P)}  {_c('outline',_P)}|[/]  ",
    f"   {_c('outline',_P)}\\\\{_c('belly',_P)}_________>{_c('outline',_P)}/[/]   ",
    f"    {_c('outline',_P)}||{_c('feather',_P)}  xx  {_c('outline',_P)}||[/]    ",
    f"    {_c('beak',_P)}__{_c('outline',_P)}||{_c('beak',_P)}_____||{_c('outline',_P)}[/]    ",
    f"        {_c('beak',_P)}~~~~~[/]        ",
    f"       {_c('icon',_P)}no-entry[/]       ",
]

_F[_ZB][MascotMood.WAITING] = [
    f"     {_c('outline',_P)}.-.-.{_c('body',_P)}.{_c('outline',_P)}.-.-.[/]     ",
    f"   {_c('outline',_P)}.'{_c('body',_P)} {_c('eye',_P)}.     .{_c('body',_P)} {_c('outline',_P)}'.[/]   ",
    f"  {_c('outline',_P)}|{_c('body',_P)}  {_c('gem',_P)}diamond-2{_c('body',_P)}  {_c('outline',_P)}|[/]  ",
    f"  {_c('outline',_P)}|{_c('body',_P)}  {_c('mouth',_P)}?--?--?{_c('body',_P)}  {_c('outline',_P)}|[/]  ",
    f"   {_c('outline',_P)}\\\\{_c('belly',_P)}_________>{_c('outline',_P)}/[/]   ",
    f"    {_c('outline',_P)}||{_c('feather',_P)}  ??  {_c('outline',_P)}||[/]    ",
    f"    {_c('beak',_P)}__{_c('outline',_P)}||{_c('beak',_P)}_____||{_c('outline',_P)}[/]    ",
    f"        {_c('beak',_P)}~~~~~[/]        ",
    f"       {_c('icon',_P)}hourglass[/]       ",
]


# ── JUAN JUAN · Writer · Open-book sprite ─────────────────────────────────

_JJ = MascotCharacter.WRITER
_P = PALETTES[_JJ]
_F[_JJ] = {}

_F[_JJ][MascotMood.IDLE] = [
    f"  {_c('spine',_P)}.===============.[/]  ",
    f"  {_c('spine',_P)}||{_c('page',_P)}~~~~~~~~~~~~~{_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}||{_c('body',_P)} {_c('glasses',_P)}.-{_c('lens',_P)} o   o {_c('glasses',_P)}-.[/]{_c('body',_P)} {_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}||{_c('body',_P)} {_c('glasses',_P)}| {_c('lens',_P)}   {_c('mouth',_P)}v{_c('lens',_P)}    {_c('glasses',_P)}|[/]{_c('body',_P)} {_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}||{_c('body',_P)} {_c('glasses',_P)}'-{_c('lens',_P)}       {_c('glasses',_P)}-'[/]{_c('body',_P)} {_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}||{_c('page',_P)}_____________>{_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}'==============='[/]  ",
    f"      {_c('mouth',_P)}~~~~~~~~[/]      ",
    f"      {_c('icon',_P)}open-book[/]      ",
]

_F[_JJ][MascotMood.THINKING] = [
    f"  {_c('spine',_P)}.===============.[/]  ",
    f"  {_c('spine',_P)}||{_c('page',_P)}~~~~~~~~~~~~~{_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}||{_c('body',_P)} {_c('glasses',_P)}.-{_c('lens',_P)} u   u {_c('glasses',_P)}-.[/]{_c('body',_P)} {_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}||{_c('body',_P)} {_c('glasses',_P)}| {_c('lens',_P)}   {_c('mouth',_P)}~{_c('lens',_P)}    {_c('glasses',_P)}|[/]{_c('body',_P)} {_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}||{_c('body',_P)} {_c('glasses',_P)}'-{_c('lens',_P)}       {_c('glasses',_P)}-'[/]{_c('body',_P)} {_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}||{_c('page',_P)} {_c('spark',_P)}*{_c('page',_P)} {_c('spark',_P)}*{_c('page',_P)} {_c('spark',_P)}*{_c('page',_P)} {_c('spark',_P)}*{_c('page',_P)} {_c('spark',_P)}*[/]{_c('page',_P)} {_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}'==============='[/]  ",
    f"      {_c('mouth',_P)}~~~~~~~~[/]      ",
    f"      {_c('icon',_P)}thought-balloon[/]      ",
]

_F[_JJ][MascotMood.WORKING] = [
    f"  {_c('spine',_P)}.===============.[/]  ",
    f"  {_c('spine',_P)}||{_c('page',_P)}~~~~~~~~~~~~~{_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}||{_c('body',_P)} {_c('glasses',_P)}.-{_c('lens',_P)} *   * {_c('glasses',_P)}-.[/]{_c('body',_P)} {_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}||{_c('body',_P)} {_c('glasses',_P)}| {_c('lens',_P)}   {_c('mouth',_P)}O{_c('lens',_P)}    {_c('glasses',_P)}|[/]{_c('body',_P)} {_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}||{_c('body',_P)} {_c('glasses',_P)}'-{_c('lens',_P)}       {_c('glasses',_P)}-'[/]{_c('body',_P)} {_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}||{_c('page',_P)} {_c('spark',_P)}*  *  *  *  *[/]{_c('page',_P)} {_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}'==============='[/]  ",
    f"      {_c('mouth',_P)}~~~~~~~~[/]      ",
    f"      {_c('icon',_P)}sparkles[/]      ",
]

_F[_JJ][MascotMood.HAPPY] = [
    f"  {_c('spine',_P)}.===============.[/]  ",
    f"  {_c('spine',_P)}||{_c('page',_P)}~~~~~~~~~~~~~{_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}||{_c('body',_P)} {_c('glasses',_P)}.-{_c('lens',_P)} ^   ^ {_c('glasses',_P)}-.[/]{_c('body',_P)} {_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}||{_c('body',_P)} {_c('glasses',_P)}| {_c('lens',_P)}   {_c('mouth',_P)}V{_c('lens',_P)}    {_c('glasses',_P)}|[/]{_c('body',_P)} {_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}||{_c('body',_P)} {_c('glasses',_P)}'-{_c('lens',_P)}       {_c('glasses',_P)}-'[/]{_c('body',_P)} {_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}||{_c('page',_P)}~~~~~~~~~~~~~{_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}'==============='[/]  ",
    f"      {_c('mouth',_P)}~~~~~~~~[/]      ",
    f"      {_c('icon',_P)}party-popper[/]      ",
]

_F[_JJ][MascotMood.ERROR] = [
    f"  {_c('spine',_P)}.===============.[/]  ",
    f"  {_c('spine',_P)}||{_c('page',_P)}~~~~~~~~~~~~~{_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}||{_c('body',_P)} {_c('glasses',_P)}.-{_c('lens',_P)} x   x {_c('glasses',_P)}-.[/]{_c('body',_P)} {_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}||{_c('body',_P)} {_c('glasses',_P)}| {_c('lens',_P)}   {_c('mouth',_P)}n{_c('lens',_P)}    {_c('glasses',_P)}|[/]{_c('body',_P)} {_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}||{_c('body',_P)} {_c('glasses',_P)}'-{_c('lens',_P)}       {_c('glasses',_P)}-'[/]{_c('body',_P)} {_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}||{_c('page',_P)}~~~~~~~~~~~~~{_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}'==============='[/]  ",
    f"      {_c('mouth',_P)}~~~~~~~~[/]      ",
    f"      {_c('icon',_P)}broken-heart[/]      ",
]

_F[_JJ][MascotMood.WAITING] = [
    f"  {_c('spine',_P)}.===============.[/]  ",
    f"  {_c('spine',_P)}||{_c('page',_P)}~~~~~~~~~~~~~{_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}||{_c('body',_P)} {_c('glasses',_P)}.-{_c('lens',_P)} .   . {_c('glasses',_P)}-.[/]{_c('body',_P)} {_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}||{_c('body',_P)} {_c('glasses',_P)}| {_c('lens',_P)}   {_c('mouth',_P)}?{_c('lens',_P)}    {_c('glasses',_P)}|[/]{_c('body',_P)} {_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}||{_c('body',_P)} {_c('glasses',_P)}'-{_c('lens',_P)}       {_c('glasses',_P)}-'[/]{_c('body',_P)} {_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}||{_c('page',_P)}~~~~~~~~~~~~~{_c('spine',_P)}||[/]  ",
    f"  {_c('spine',_P)}'==============='[/]  ",
    f"      {_c('mouth',_P)}~~~~~~~~[/]      ",
    f"      {_c('icon',_P)}hourglass[/]      ",
]


# ── DOU DOU · Programmer · Pixel sprite ────────────────────────────────────

_DD = MascotCharacter.PROGRAMMER
_P = PALETTES[_DD]
_F[_DD] = {}

_F[_DD][MascotMood.IDLE] = [
    f"     {_c('antenna',_P)}_|_[/]     ",
    f"   {_c('outline',_P)}.-------.[/]   ",
    f"  {_c('outline',_P)}|{_c('body',_P)} {_c('eye',_P)}o     o{_c('body',_P)} {_c('outline',_P)}|[/]  ",
    f"  {_c('outline',_P)}|{_c('body',_P)}  {_c('led_ok',_P)}diamond[/]{_c('body',_P)}  {_c('outline',_P)}|[/]  ",
    f"  {_c('outline',_P)}|{_c('body',_P)}  {_c('mouth',_P)}------{_c('body',_P)}  {_c('outline',_P)}|[/]  ",
    f"  {_c('outline',_P)}|{_c('body',_P)} {_c('hand',_P)}__{_c('body',_P)} {_c('hand',_P)}__{_c('body',_P)} {_c('outline',_P)}|[/]  ",
    f"   {_c('outline',_P)}'-------'[/]   ",
    f"    {_c('base',_P)}||     ||[/]    ",
    f"    {_c('icon',_P)}coffee[/]    ",
]

_F[_DD][MascotMood.THINKING] = [
    f"     {_c('antenna',_P)}_|_[/]     ",
    f"   {_c('outline',_P)}.-------.[/]   ",
    f"  {_c('outline',_P)}|{_c('body',_P)} {_c('eye',_P)}u     u{_c('body',_P)} {_c('outline',_P)}|[/]  ",
    f"  {_c('outline',_P)}|{_c('body',_P)}  {_c('led_warn',_P)}diamond[/]{_c('body',_P)}  {_c('outline',_P)}|[/]  ",
    f"  {_c('outline',_P)}|{_c('body',_P)}  {_c('mouth',_P)}......{_c('body',_P)}  {_c('outline',_P)}|[/]  ",
    f"  {_c('outline',_P)}|{_c('body',_P)} {_c('hand',_P)}__{_c('body',_P)} {_c('hand',_P)}__{_c('body',_P)} {_c('outline',_P)}|[/]  ",
    f"   {_c('outline',_P)}'-------'[/]   ",
    f"    {_c('base',_P)}||     ||[/]    ",
    f"    {_c('icon',_P)}electric-light-bulb[/]    ",
]

_F[_DD][MascotMood.WORKING] = [
    f"     {_c('antenna',_P)}_|_[/]     ",
    f"   {_c('outline',_P)}.-------.[/]   ",
    f"  {_c('outline',_P)}|{_c('body',_P)} {_c('eye',_P)}*     *{_c('body',_P)} {_c('outline',_P)}|[/]  ",
    f"  {_c('outline',_P)}|{_c('body',_P)}  {_c('led_warn',_P)}diamond[/]{_c('body',_P)}  {_c('outline',_P)}|[/]  ",
    f"  {_c('outline',_P)}|{_c('body',_P)}  {_c('mouth',_P)}o-o-o-o{_c('body',_P)}  {_c('outline',_P)}|[/]  ",
    f"  {_c('outline',_P)}|{_c('body',_P)} {_c('hand',_P)}/\\{_c('body',_P)} {_c('hand',_P)}/\\{_c('body',_P)} {_c('outline',_P)}|[/]  ",
    f"   {_c('outline',_P)}'-------'[/]   ",
    f"    {_c('base',_P)}||     ||[/]    ",
    f"    {_c('icon',_P)}gear[/]    ",
]

_F[_DD][MascotMood.HAPPY] = [
    f"     {_c('antenna',_P)}_|_[/]     ",
    f"   {_c('outline',_P)}.-------.[/]   ",
    f"  {_c('outline',_P)}|{_c('body',_P)} {_c('eye',_P)}^     ^{_c('body',_P)} {_c('outline',_P)}|[/]  ",
    f"  {_c('outline',_P)}|{_c('body',_P)}  {_c('led_ok',_P)}diamond[/]{_c('body',_P)}  {_c('outline',_P)}|[/]  ",
    f"  {_c('outline',_P)}|{_c('body',_P)}  {_c('mouth',_P)}v--v--v{_c('body',_P)}  {_c('outline',_P)}|[/]  ",
    f"  {_c('outline',_P)}|{_c('body',_P)} {_c('hand',_P)}^^{_c('body',_P)} {_c('hand',_P)}^^{_c('body',_P)} {_c('outline',_P)}|[/]  ",
    f"   {_c('outline',_P)}'-------'[/]   ",
    f"    {_c('base',_P)}||     ||[/]    ",
    f"    {_c('icon',_P)}check-mark-button[/]    ",
]

_F[_DD][MascotMood.ERROR] = [
    f"     {_c('antenna',_P)}_|_[/]     ",
    f"   {_c('outline',_P)}.-------.[/]   ",
    f"  {_c('outline',_P)}|{_c('body',_P)} {_c('eye',_P)}>     <{_c('body',_P)} {_c('outline',_P)}|[/]  ",
    f"  {_c('outline',_P)}|{_c('body',_P)}  {_c('led_err',_P)}diamond[/]{_c('body',_P)}  {_c('outline',_P)}|[/]  ",
    f"  {_c('outline',_P)}|{_c('body',_P)}  {_c('mouth',_P)}------{_c('body',_P)}  {_c('outline',_P)}|[/]  ",
    f"  {_c('outline',_P)}|{_c('body',_P)} {_c('hand',_P)}xx{_c('body',_P)} {_c('hand',_P)}xx{_c('body',_P)} {_c('outline',_P)}|[/]  ",
    f"   {_c('outline',_P)}'-------'[/]   ",
    f"    {_c('base',_P)}||     ||[/]    ",
    f"    {_c('icon',_P)}collision[/]    ",
]

_F[_DD][MascotMood.WAITING] = [
    f"     {_c('antenna',_P)}_|_[/]     ",
    f"   {_c('outline',_P)}.-------.[/]   ",
    f"  {_c('outline',_P)}|{_c('body',_P)} {_c('eye',_P)}.     .{_c('body',_P)} {_c('outline',_P)}|[/]  ",
    f"  {_c('outline',_P)}|{_c('body',_P)}  {_c('led_warn',_P)}diamond[/]{_c('body',_P)}  {_c('outline',_P)}|[/]  ",
    f"  {_c('outline',_P)}|{_c('body',_P)}  {_c('mouth',_P)}???{_c('body',_P)}  {_c('outline',_P)}|[/]  ",
    f"  {_c('outline',_P)}|{_c('body',_P)} {_c('hand',_P)}__{_c('body',_P)} {_c('hand',_P)}__{_c('body',_P)} {_c('outline',_P)}|[/]  ",
    f"   {_c('outline',_P)}'-------'[/]   ",
    f"    {_c('base',_P)}||     ||[/]    ",
    f"    {_c('icon',_P)}magnifying-glass-tilted-left[/]    ",
]


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════

MASCOT_FRAME_HEIGHT = 9
MASCOT_FRAME_WIDTH = 24

_ICON_LABELS: Dict[MascotCharacter, Dict[MascotMood, str]] = {
    MascotCharacter.LAWYER: {
        MascotMood.IDLE: "scale",
        MascotMood.THINKING: "scroll",
        MascotMood.WORKING: "bolt",
        MascotMood.HAPPY: "star",
        MascotMood.ERROR: "error",
        MascotMood.WAITING: "wait",
    },
    MascotCharacter.TEACHER: {
        MascotMood.IDLE: "books",
        MascotMood.THINKING: "think",
        MascotMood.WORKING: "teach",
        MascotMood.HAPPY: "star",
        MascotMood.ERROR: "error",
        MascotMood.WAITING: "wait",
    },
    MascotCharacter.WRITER: {
        MascotMood.IDLE: "book",
        MascotMood.THINKING: "idea",
        MascotMood.WORKING: "write",
        MascotMood.HAPPY: "party",
        MascotMood.ERROR: "error",
        MascotMood.WAITING: "wait",
    },
    MascotCharacter.PROGRAMMER: {
        MascotMood.IDLE: "coffee",
        MascotMood.THINKING: "idea",
        MascotMood.WORKING: "gear",
        MascotMood.HAPPY: "ok",
        MascotMood.ERROR: "error",
        MascotMood.WAITING: "search",
    },
}


def _plain(line: str) -> str:
    """Return the visible text produced by a Rich-markup line."""
    return Text.from_markup(line).plain


def _escape_backslashes_before_markup(line: str) -> str:
    """Keep literal backslashes from escaping following Rich markup tags."""
    chars: list[str] = []
    for index, char in enumerate(line):
        if (
            char == "\\"
            and index + 1 < len(line)
            and line[index + 1] == "["
            and (index == 0 or line[index - 1] != "\\")
        ):
            chars.append("\\\\")
        else:
            chars.append(char)
    return "".join(chars)


def _center_markup_line(line: str, width: int = MASCOT_FRAME_WIDTH) -> str:
    """Pad a markup line to a fixed visible width."""
    visible_width = len(_plain(line))
    if visible_width >= width:
        return line
    left = (width - visible_width) // 2
    right = width - visible_width - left
    return f"{' ' * left}{line}{' ' * right}"


def _normalise_frames() -> None:
    """Make every mascot frame a fixed-size rectangle for stable TUI layout."""
    for character, frames in _F.items():
        palette = PALETTES[character]
        for mood, frame in frames.items():
            fixed_frame = list(frame[:MASCOT_FRAME_HEIGHT])
            while len(fixed_frame) < MASCOT_FRAME_HEIGHT:
                fixed_frame.append("")

            fixed_frame[-1] = _cf("icon", palette, _ICON_LABELS[character][mood])
            frames[mood] = [
                _center_markup_line(_escape_backslashes_before_markup(line))
                for line in fixed_frame
            ]


_normalise_frames()


CHARACTER_NAMES: Dict[MascotCharacter, str] = {
    MascotCharacter.LAWYER: "Yi Zai",
    MascotCharacter.TEACHER: "Zhi Bao",
    MascotCharacter.WRITER: "Juan Juan",
    MascotCharacter.PROGRAMMER: "Dou Dou",
}


def get_mascot(
    mood: MascotMood = MascotMood.IDLE,
    character: MascotCharacter = MascotCharacter.LAWYER,
) -> List[str]:
    """Return the Rich-markup frame lines for *mood* and *character*."""
    frames = _F.get(character, _F[MascotCharacter.LAWYER])
    return frames.get(mood, frames[MascotMood.IDLE])


def get_mascot_text(
    mood: MascotMood = MascotMood.IDLE,
    character: MascotCharacter = MascotCharacter.LAWYER,
) -> str:
    """Return the full mascot frame as a newline-joined Rich-markup string."""
    return "\n".join(get_mascot(mood, character))


# ═══════════════════════════════════════════════════════════════════════════
# Dialogue pool builder (called at module import)
# ═══════════════════════════════════════════════════════════════════════════


def _build_dialogue_pools() -> None:
    """Populate ``WELCOME_BANNER`` and ``_DIALOGUE_POOL`` for every character."""

    # -- Welcome banners ----------------------------------------------------
    WELCOME_BANNER[MascotCharacter.LAWYER] = [
        "欢迎使用 AgentOS！",
        "我是 律仔，您的智能法律顾问 ⚖️",
        "F2 切换角色  ·  输入问题开始对话",
    ]
    WELCOME_BANNER[MascotCharacter.TEACHER] = [
        "欢迎使用 AgentOS！",
        "我是 知宝，您的专属导师 📚",
        "F2 切换角色  ·  输入问题开始对话",
    ]
    WELCOME_BANNER[MascotCharacter.WRITER] = [
        "欢迎使用 AgentOS！",
        "我是 卷卷，您的创意写作伙伴 ✍️",
        "F2 切换角色  ·  输入问题开始对话",
    ]
    WELCOME_BANNER[MascotCharacter.PROGRAMMER] = [
        "欢迎使用 AgentOS！",
        "我是 豆豆，您的编程助手 💻",
        "F2 切换角色  ·  输入问题开始对话",
    ]

    # -- Mood-driven dialogue pools -----------------------------------------

    _LAW = MascotCharacter.LAWYER
    _DIALOGUE_POOL[_LAW] = {
        MascotMood.IDLE: [
            "有什么法律问题需要咨询？",
            "律仔随时为您服务！",
            "您好，请问有什么可以帮助您的？",
            "点击输入框，开始对话吧~",
            "法律条文、合同审查… 我都在行！",
        ],
        MascotMood.THINKING: [
            "正在查阅相关法条… 📖",
            "让我想想这个问题… 🤔",
            "正在分析法律要点…",
            "梳理一下案件思路…",
            "查阅判例中，请稍候…",
        ],
        MascotMood.WORKING: [
            "正在为您审查合同条款… ⚡",
            "处理中，马上就好！",
            "律仔正在全力工作中…",
            "正在检索相关法律依据…",
        ],
        MascotMood.HAPPY: [
            "问题解决了！ ✅",
            "希望能帮到您！ 😊",
            "还有什么需要吗？",
            "很高兴为您服务！",
            "搞定！有问必答~",
        ],
        MascotMood.ERROR: [
            "抱歉，出了点问题… ❌",
            "好像遇到了一些困难 😥",
            "请稍后再试，或切换角色重试…",
            "这个问题有点棘手…",
        ],
        MascotMood.WAITING: [
            "等待中… ⏳",
            "正在等待您的输入…",
            "有什么我可以帮您的吗？",
            "嗯…您还在吗？",
        ],
    }

    _ZB = MascotCharacter.TEACHER
    _DIALOGUE_POOL[_ZB] = {
        MascotMood.IDLE: [
            "有什么问题想学习探讨的？",
            "知宝在此，请多多指教！",
            "今天想学点什么呢？",
            "知识的大门随时为您敞开~",
        ],
        MascotMood.THINKING: [
            "让我整理一下知识点… 🤔",
            "这个问题值得深入思考…",
            "查阅学术资料中… 📖",
            "梳理一下教学思路…",
        ],
        MascotMood.WORKING: [
            "正在准备教学内容… ⚡",
            "分析中，请稍等！",
            "知宝正在为您备课…",
        ],
        MascotMood.HAPPY: [
            "找到了最佳解答！ ✅",
            "希望能帮到您！ 😊",
            "教学相长，我也学到了！",
            "还有什么想探讨的吗？",
        ],
        MascotMood.ERROR: [
            "这个问题超出我的知识范围了… ❌",
            "好像有些困惑 😥",
            "我们换个角度试试？",
        ],
        MascotMood.WAITING: [
            "等待您的问题中… ⏳",
            "尽管问，不用客气~",
            "知宝随时准备着…",
        ],
    }

    _JJ = MascotCharacter.WRITER
    _DIALOGUE_POOL[_JJ] = {
        MascotMood.IDLE: [
            "今天想写点什么？",
            "卷卷在此，灵感无限！",
            "创意写作、文案润色…交给我！",
            "打开文档，开始创作吧~ ✨",
        ],
        MascotMood.THINKING: [
            "正在构思创意… 🤔",
            "让我想想怎么润色…",
            "灵感正在酝酿中… ✨",
            "寻找最佳的表达方式…",
        ],
        MascotMood.WORKING: [
            "正在奋笔疾书中… ✍️",
            "创作中，马上就好！",
            "文字正在流淌… ⚡",
        ],
        MascotMood.HAPPY: [
            "大作已成！ ✅",
            "希望能帮到您！ 😊",
            "文字的魅力无穷无尽~",
            "还有什么需要润色的吗？",
        ],
        MascotMood.ERROR: [
            "哎呀，笔断了… ❌",
            "创作遇到了瓶颈 😥",
            "换个话题也许会有灵感…",
        ],
        MascotMood.WAITING: [
            "等待您的创意… ⏳",
            "有什么想写的吗？",
            "卷卷已经准备好了…",
        ],
    }

    _DD = MascotCharacter.PROGRAMMER
    _DIALOGUE_POOL[_DD] = {
        MascotMood.IDLE: [
            "有什么代码需要帮忙的？",
            "豆豆在线，随时接单！",
            "Bug 修复、代码审查… 统统搞定！",
            "输入你的需求，开始编码吧~ ⌨️",
        ],
        MascotMood.THINKING: [
            "正在分析代码逻辑… 🤔",
            "让我想想最优解…",
            "算法优化中… 📊",
            "debug 模式启动… 🔍",
        ],
        MascotMood.WORKING: [
            "正在编译中… ⚡",
            "代码生成中，请稍候！",
            "豆豆正在全力 coding… 💻",
            "git commit -m '正在努力…'",
        ],
        MascotMood.HAPPY: [
            "编译通过，零 Bug！ ✅",
            "希望能帮到您！ 😊",
            "代码写得不错吧？",
            "还有什么需要优化的吗？",
        ],
        MascotMood.ERROR: [
            "哎呀，Segmentation fault… ❌",
            "遇到异常了 😥",
            "Stack overflow！换个思路试试…",
        ],
        MascotMood.WAITING: [
            "等待您的指令… ⏳",
            "豆豆待命中，随时可以开工~",
            "有什么新需求吗？",
        ],
    }


_build_dialogue_pools()
