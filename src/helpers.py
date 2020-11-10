from typing import List


def split_on_length_and_separator(string: str, length: int, separator: str) -> List[str]:
    ret = []
    while len(string) > length:
        idx = length-1
        while string[idx] != separator:
            if idx == 0:
                raise ValueError
            idx -= 1
        ret.append(string[:idx+1])
        string = string[idx+1:]
    ret.append(string)
    return ret

