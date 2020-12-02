import dataclasses


@dataclasses.dataclass
class Crew:
    name: str
    abbr: str
    rank: str = ''
    merit: int = 0
    overflow: bool = False

