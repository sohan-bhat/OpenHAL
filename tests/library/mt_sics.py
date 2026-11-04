"""A laboratory balance that answers MT-SICS level 0 and 1 commands, for the library file's tests.

Commands and replies follow Mettler Toledo's MT-SICS reference manual 30014405C. Every command
ends with CR LF, and so does every reply. Weights are right aligned in 10 characters.
"""

from __future__ import annotations

from dataclasses import dataclass

CONTENTS = """
3.2 Commands and responses
@ DASH Reset ........................................................................ 34
I4 DASH Serial number .............................................................. 37
S DASH Stable weight value ......................................................... 151
SI DASH Weight value immediately ................................................... 152
SIR DASH Weight value immediately and repeat ....................................... 153
T DASH Tare ........................................................................ 181
TA DASH Tare weight value .......................................................... 182
TAC DASH Clear tare weight value ................................................... 183
Z DASH Zero ........................................................................ 194
""".replace(" DASH ", " \N{EN DASH} ")
"""The MT-SICS command list as the contents of reference manual 30014405C print it, dashes and all."""


def _weight(value: float) -> str:
    return f"{value:10.2f}"


@dataclass
class Balance:
    load_g: float = 0.0
    zero_g: float = 0.0
    tare_g: float = 0.0
    stable: bool = True
    serial: str = "B021002593"
    overload_g: float = 220.0
    buffer: bytes = b""

    @property
    def net_g(self) -> float:
        return self.load_g - self.zero_g - self.tare_g

    def receive(self, data: bytes) -> bytes:
        self.buffer += data
        out = b""
        while b"\r\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\r\n", 1)
            out += (self.answer(line.decode("ascii")) + "\r\n").encode("ascii")
        return out

    def answer(self, command: str) -> str:
        if command == "I4":
            return f'I4 A "{self.serial}"'
        if command in ("S", "SI"):
            if self.load_g > self.overload_g:
                return "S +"
            if command == "S" and not self.stable:
                return "S I"
            return f"S {'S' if self.stable else 'D'} {_weight(self.net_g)} g"
        if command == "Z":
            if not self.stable:
                return "Z I"
            self.zero_g, self.tare_g = self.load_g, 0.0
            return "Z A"
        if command == "T":
            if not self.stable:
                return "T I"
            self.tare_g = self.load_g - self.zero_g
            return f"T S {_weight(self.tare_g)} g"
        if command == "TA":
            return f"TA A {_weight(self.tare_g)} g"
        if command == "TAC":
            self.tare_g = 0.0
            return "TAC A"
        return "ES"
