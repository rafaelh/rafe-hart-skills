from lib.conflict import classify_collision, compute_partial_hash


class TestClassifyCollision:
    def test_dst_missing_is_clear(self, tmp_path):
        src = tmp_path / "src.jpg"
        src.write_bytes(b"hello")
        dst = tmp_path / "dst.jpg"
        assert classify_collision(src, dst) == "clear"

    def test_identical_content_is_duplicate(self, tmp_path):
        content = b"x" * 1000
        src = tmp_path / "src.jpg"
        dst = tmp_path / "dst.jpg"
        src.write_bytes(content)
        dst.write_bytes(content)
        assert classify_collision(src, dst) == "duplicate"

    def test_different_size_is_conflict(self, tmp_path):
        src = tmp_path / "src.jpg"
        dst = tmp_path / "dst.jpg"
        src.write_bytes(b"short")
        dst.write_bytes(b"a much longer payload than the source file")
        assert classify_collision(src, dst) == "conflict"

    def test_same_size_different_content_is_conflict(self, tmp_path):
        src = tmp_path / "src.jpg"
        dst = tmp_path / "dst.jpg"
        src.write_bytes(b"abcdefgh")
        dst.write_bytes(b"12345678")
        assert classify_collision(src, dst) == "conflict"

    def test_same_partial_hash_but_different_tail_is_conflict(self, tmp_path):
        # Two files with same first 64KB but different bytes after.
        head = b"X" * (1024 * 70)  # > PARTIAL_HASH_BYTES
        src = tmp_path / "src.bin"
        dst = tmp_path / "dst.bin"
        src.write_bytes(head + b"AAA")
        dst.write_bytes(head + b"BBB")
        # Sanity: same first 64KB
        assert compute_partial_hash(src) == compute_partial_hash(dst)
        # Files differ in the tail → conflict
        assert classify_collision(src, dst) == "conflict"
