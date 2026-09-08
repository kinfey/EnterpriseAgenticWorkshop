from solution import LRUCache


if __name__ == "__main__":
    c = LRUCache(2)
    c.put(1, 1); c.put(2, 2)
    assert c.get(1) == 1          # 1 is now MRU
    c.put(3, 3)                   # evicts key 2
    assert c.get(2) == -1
    c.put(4, 4)                   # evicts key 1
    assert c.get(1) == -1
    assert c.get(3) == 3
    assert c.get(4) == 4
    print("OK")
