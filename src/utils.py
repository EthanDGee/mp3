def increment_no_wrap(index: int, max: int) -> int:
    if index + 1 <= max:
        return index + 1
    return index


def decrement_no_wrap(index: int) -> int:
    if index - 1 <= 0:
        return 0
    return index - 1
