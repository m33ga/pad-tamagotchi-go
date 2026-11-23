"""Measure the share of keys that change cache owners when a fourth node joins."""

from bisect import bisect_left
from hashlib import blake2b


def hash64(value: str) -> int:
    return int.from_bytes(blake2b(value.encode(), digest_size=8).digest(), "big")


def make_ring(node_count: int) -> tuple[list[int], list[int]]:
    entries = sorted(
        (hash64(f"cache-{node + 1}:{replica}"), node)
        for node in range(node_count)
        for replica in range(150)
    )
    return [point for point, _ in entries], [node for _, node in entries]


def owner(key: int, ring: tuple[list[int], list[int]]) -> int:
    points, owners = ring
    return owners[bisect_left(points, key) % len(points)]


def main() -> None:
    before, after = make_ring(3), make_ring(4)
    count = 100_000
    moved_ring = moved_modulo = 0
    for index in range(count):
        key = hash64(f"reply:{index}")
        moved_ring += owner(key, before) != owner(key, after)
        moved_modulo += key % 3 != key % 4
    print(f"Ring:   {moved_ring:>6,}/{count:,} ({moved_ring / count:.2%})")
    print(f"Modulo: {moved_modulo:>6,}/{count:,} ({moved_modulo / count:.2%})")


if __name__ == "__main__":
    main()
