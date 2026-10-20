"""The small expression language used by interlocks, preconditions and watchdog rules.

Expressions are parsed by this module's own recursive descent parser and evaluated over a
resolver. Nothing is ever passed to `eval`. Evaluation is three-valued. A reference the hub
can't read is unknown, and unknown never lets a command pass (spec section 7).
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Final

import pint

from openhal.spec.units import UnitError, convert, parse_quantity, parse_unit

MAX_LENGTH: Final = 256
MAX_DEPTH: Final = 16
KEYWORDS: Final = frozenset({"and", "or", "not", "true", "false"})
COMPARE_OPS: Final = ("==", "!=", "<=", ">=", "<", ">")

Tri = bool | None
"""Three-valued truth. None means unknown."""


class ExpressionError(ValueError):
    """An expression could not be parsed or does not fit the device it refers to."""


@dataclass(frozen=True, slots=True)
class Ref:
    """A reference to a channel, `name` on the same device or `device.name` on another."""

    device: str | None
    name: str

    def __str__(self) -> str:
        return f"{self.device}.{self.name}" if self.device else self.name


@dataclass(frozen=True, slots=True)
class Lit:
    """A literal. Quantities keep their unit, words are strings, true and false are booleans."""

    value: float | bool | str
    unit: str | None = None
    quoted: bool = False


@dataclass(frozen=True, slots=True)
class Compare:
    op: str
    left: Node
    right: Node


@dataclass(frozen=True, slots=True)
class Not:
    operand: Node


@dataclass(frozen=True, slots=True)
class And:
    operands: tuple[Node, ...]


@dataclass(frozen=True, slots=True)
class Or:
    operands: tuple[Node, ...]


Node = Ref | Lit | Compare | Not | And | Or


@dataclass(frozen=True, slots=True)
class Value:
    """What a resolver returns for a channel. `unit` is set for numeric channels."""

    value: float | bool | str
    unit: str | None = None


Resolver = Callable[[Ref], Value | None]
"""Returns the current value of a reference, or None when it is unknown."""

_TOKEN: Final = re.compile(
    r"""
    (?P<space>\s+)
  | (?P<op>==|!=|<=|>=|<|>)
  | (?P<lparen>\()
  | (?P<rparen>\))
  | (?P<string>'[^']{0,120}'|"[^"]{0,120}")
  | (?P<number>[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)
  | (?P<name>[A-Za-z_][A-Za-z0-9_-]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)
    """,
    re.VERBOSE,
)
_UNIT: Final = re.compile(r"\s*([A-Za-z%°µ][A-Za-z0-9%°µ/*^_]*(?:\s*/\s*[A-Za-z]+)?)")


@dataclass(frozen=True, slots=True)
class _Tok:
    kind: str
    text: str
    unit: str | None = None


def _tokenize(text: str) -> list[_Tok]:
    tokens: list[_Tok] = []
    pos = 0
    while pos < len(text):
        match = _TOKEN.match(text, pos)
        if not match or match.end() == pos:
            raise ExpressionError(f"Unexpected character {text[pos]!r} at position {pos}.")
        kind = match.lastgroup or ""
        pos = match.end()
        if kind == "space":
            continue
        if kind == "number":
            unit_match = _UNIT.match(text, pos)
            unit = None
            if unit_match and unit_match.group(1).lower() not in KEYWORDS:
                unit = unit_match.group(1).strip()
                pos = unit_match.end()
            tokens.append(_Tok("number", match.group(0), unit))
            continue
        tokens.append(_Tok(kind, match.group(0)))
    return tokens


class _Parser:
    def __init__(self, tokens: list[_Tok], channels: frozenset[str] | None) -> None:
        self.tokens = tokens
        self.pos = 0
        self.channels = channels

    def peek(self) -> _Tok | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self) -> _Tok:
        tok = self.peek()
        if tok is None:
            raise ExpressionError("The expression ends too early.")
        self.pos += 1
        return tok

    def keyword(self, word: str) -> bool:
        tok = self.peek()
        if tok is not None and tok.kind == "name" and tok.text.lower() == word:
            self.pos += 1
            return True
        return False

    def parse(self) -> Node:
        node = self.or_expr(0)
        if self.peek() is not None:
            raise ExpressionError(f"Unexpected {self.peek().text!r} after a complete expression.")  # type: ignore[union-attr]
        return node

    def _depth(self, depth: int) -> int:
        if depth > MAX_DEPTH:
            raise ExpressionError(f"Expressions may nest at most {MAX_DEPTH} levels.")
        return depth + 1

    def or_expr(self, depth: int) -> Node:
        depth = self._depth(depth)
        parts = [self.and_expr(depth)]
        while self.keyword("or"):
            parts.append(self.and_expr(depth))
        return parts[0] if len(parts) == 1 else Or(tuple(parts))

    def and_expr(self, depth: int) -> Node:
        depth = self._depth(depth)
        parts = [self.not_expr(depth)]
        while self.keyword("and"):
            parts.append(self.not_expr(depth))
        return parts[0] if len(parts) == 1 else And(tuple(parts))

    def not_expr(self, depth: int) -> Node:
        depth = self._depth(depth)
        if self.keyword("not"):
            return Not(self.not_expr(depth))
        return self.compare(depth)

    def compare(self, depth: int) -> Node:
        left = self.operand(depth)
        tok = self.peek()
        if tok is not None and tok.kind == "op":
            self.pos += 1
            return Compare(tok.text, left, self.operand(depth))
        return left

    def operand(self, depth: int) -> Node:
        depth = self._depth(depth)
        tok = self.take()
        if tok.kind == "lparen":
            inner = self.or_expr(depth)
            closing = self.take()
            if closing.kind != "rparen":
                raise ExpressionError("A parenthesis is not closed.")
            return inner
        if tok.kind == "number":
            number = float(tok.text)
            if not math.isfinite(number):
                raise ExpressionError("Numbers must be finite.")
            return Lit(number, tok.unit)
        if tok.kind == "string":
            return Lit(tok.text[1:-1], quoted=True)
        if tok.kind == "name":
            lowered = tok.text.lower()
            if lowered in ("true", "false"):
                return Lit(lowered == "true")
            if lowered in KEYWORDS:
                raise ExpressionError(f"Unexpected keyword {tok.text!r}.")
            if "." in tok.text:
                device, name = tok.text.split(".", 1)
                return Ref(device, name)
            if self.channels is None or tok.text in self.channels:
                return Ref(None, tok.text)
            return Lit(tok.text)
        raise ExpressionError(f"Unexpected {tok.text!r}.")


def parse(text: str, channels: frozenset[str] | set[str] | None = None) -> Node:
    """Parse an expression into a tree. Raises ExpressionError with a specific reason.

    `channels` names the owning device's channels. A bare name that is one of them becomes a
    channel reference, and any other bare name becomes a word literal (an enum value such as
    `idle`). Deciding this at parse time means an unknown channel value can only ever be unknown,
    never mistaken for a word. With `channels=None` every bare name is a channel reference.
    """
    if not isinstance(text, str) or not text.strip():
        raise ExpressionError("An expression can't be empty.")
    if len(text) > MAX_LENGTH:
        raise ExpressionError(f"Expressions may be at most {MAX_LENGTH} characters.")
    known = None if channels is None else frozenset(channels)
    return _Parser(_tokenize(text), known).parse()


@lru_cache(maxsize=4096)
def parse_cached(text: str, channels: frozenset[str]) -> Node:
    """Parse with a cache. Trees are immutable, so sharing them is safe."""
    return parse(text, channels)


def words(node: Node) -> list[tuple[str, Node | None]]:
    """Every bare word literal and the operand it is compared with (None when it stands alone).

    Quoted strings are explicit text and aren't included.
    """
    if isinstance(node, Lit):
        return [(node.value, None)] if isinstance(node.value, str) and not node.quoted else []
    if isinstance(node, Ref):
        return []
    if isinstance(node, Compare):
        found: list[tuple[str, Node | None]] = []
        for side, other in ((node.left, node.right), (node.right, node.left)):
            if isinstance(side, Lit) and isinstance(side.value, str) and not side.quoted:
                found.append((side.value, other))
        return found
    if isinstance(node, Not):
        return words(node.operand)
    result: list[tuple[str, Node | None]] = []
    for part in node.operands:
        result.extend(words(part))
    return result


def references(node: Node) -> set[Ref]:
    """Every channel reference in a tree."""
    if isinstance(node, Ref):
        return {node}
    if isinstance(node, Lit):
        return set()
    if isinstance(node, Compare):
        return references(node.left) | references(node.right)
    if isinstance(node, Not):
        return references(node.operand)
    found: set[Ref] = set()
    for part in node.operands:
        found |= references(part)
    return found


def _literal_quantity(lit: Lit) -> pint.Quantity | None:
    if isinstance(lit.value, bool | str):
        return None
    if lit.unit is None:
        return None
    return parse_quantity(f"{lit.value} {lit.unit}")


def _resolve(node: Node, resolver: Resolver) -> Value | None:
    if isinstance(node, Ref):
        return resolver(node)
    if isinstance(node, Lit):
        return Value(node.value, node.unit)
    raise ExpressionError("Comparisons take channels and values, not other comparisons.")


def _compare_numbers(op: str, left: float, right: float) -> bool:
    close = math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-12)
    return {
        "==": close,
        "!=": not close,
        "<": left < right and not close,
        "<=": left < right or close,
        ">": left > right and not close,
        ">=": left > right or close,
    }[op]


def _evaluate_compare(node: Compare, resolver: Resolver) -> Tri:
    left = _resolve(node.left, resolver)
    right = _resolve(node.right, resolver)
    if left is None or right is None:
        return None
    if isinstance(left.value, bool) or isinstance(right.value, bool):
        if node.op not in ("==", "!="):
            return None
        same = left.value == right.value and type(left.value) is type(right.value)
        return same if node.op == "==" else not same
    if isinstance(left.value, str) or isinstance(right.value, str):
        if node.op not in ("==", "!="):
            return None
        same = str(left.value) == str(right.value)
        return same if node.op == "==" else not same
    try:
        if left.unit is None and right.unit is None:
            return _compare_numbers(node.op, float(left.value), float(right.value))
        if left.unit is None or right.unit is None:
            return None
        right_in_left = convert(parse_quantity(f"{right.value} {right.unit}"), left.unit)
    except UnitError:
        return None
    return _compare_numbers(node.op, float(left.value), right_in_left)


def evaluate(node: Node, resolver: Resolver) -> Tri:
    """Evaluate a tree. Returns True, False, or None when any needed value is unknown."""
    if isinstance(node, Compare):
        return _evaluate_compare(node, resolver)
    if isinstance(node, Ref):
        found = resolver(node)
        return found.value if found is not None and isinstance(found.value, bool) else None
    if isinstance(node, Lit):
        return node.value if isinstance(node.value, bool) else None
    if isinstance(node, Not):
        inner = evaluate(node.operand, resolver)
        return None if inner is None else not inner
    results = [evaluate(part, resolver) for part in node.operands]
    if isinstance(node, And):
        if any(result is False for result in results):
            return False
        return None if any(result is None for result in results) else True
    if any(result is True for result in results):
        return True
    return None if any(result is None for result in results) else False


def check_units(node: Node, unit_of: Callable[[Ref], str | None]) -> None:
    """Check that every numeric literal compared with a quantity channel has a convertible unit."""
    if isinstance(node, Compare):
        for side, other in ((node.left, node.right), (node.right, node.left)):
            if isinstance(side, Ref) and isinstance(other, Lit):
                unit = unit_of(side)
                if unit is None or isinstance(other.value, bool | str):
                    continue
                if other.unit is None:
                    raise ExpressionError(f"{other.value:g} is compared with {side}, so it needs a unit ({unit}).")
                quantity = _literal_quantity(other)
                if quantity is None:
                    continue
                try:
                    convert(quantity, unit)
                except UnitError as exc:
                    raise ExpressionError(
                        f"{other.value:g} {other.unit} can't be compared with {side} in {unit}."
                    ) from exc
        return
    if isinstance(node, Not):
        check_units(node.operand, unit_of)
    elif isinstance(node, And | Or):
        for part in node.operands:
            check_units(part, unit_of)
    elif isinstance(node, Lit) and node.unit is not None:
        parse_unit(node.unit)
