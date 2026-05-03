from datetime import datetime
from pathlib import Path

from lib.strategy import Strategy


class TestComputeDate:
    def test_first_source_wins_when_present(self):
        strategy = Strategy(
            {"date_sources": ["exif:Composite:DateTimeOriginal", "mtime"]}
        )
        date, source = strategy.compute_date(
            primary={"path": "/p/img.cr2", "mtime": 1577836800.0},
            exif={"Composite:DateTimeOriginal": "2019:08:15 14:20:30"},
        )
        assert date == datetime(2019, 8, 15, 14, 20, 30)
        assert source == "exif:Composite:DateTimeOriginal"

    def test_falls_through_when_first_source_absent(self):
        strategy = Strategy(
            {"date_sources": ["exif:Composite:DateTimeOriginal", "exif:EXIF:CreateDate", "mtime"]}
        )
        date, source = strategy.compute_date(
            primary={"path": "/p/img.jpg", "mtime": 1577836800.0},
            exif={"EXIF:CreateDate": "2020:01:01 00:00:00"},
        )
        assert date == datetime(2020, 1, 1, 0, 0, 0)
        assert source == "exif:EXIF:CreateDate"

    def test_falls_through_to_mtime_when_no_exif(self):
        strategy = Strategy({"date_sources": ["exif:Composite:DateTimeOriginal", "mtime"]})
        date, source = strategy.compute_date(
            primary={"path": "/p/img.jpg", "mtime": 1577836800.0},  # 2020-01-01 UTC
            exif={},
        )
        assert source == "mtime"
        assert date is not None and date.year == 2020

    def test_returns_none_when_all_sources_exhausted(self):
        strategy = Strategy({"date_sources": ["exif:Composite:DateTimeOriginal"]})
        date, source = strategy.compute_date(primary={"path": "/p/img.jpg"}, exif={})
        assert date is None
        assert source is None


class TestComputeDateFromFilename:
    def test_android_pattern_with_time_extracts_datetime(self):
        strategy = Strategy(
            {
                "date_sources": ["filename:patterns", "mtime"],
                "filename_patterns": [r"IMG_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})"],
            }
        )
        date, source = strategy.compute_date(
            primary={"path": "/p/IMG_20190815_142030.jpg"},
            exif={},
        )
        assert date == datetime(2019, 8, 15, 14, 20, 30)
        assert source == "filename:patterns"

    def test_date_only_pattern_uses_midnight(self):
        strategy = Strategy(
            {
                "date_sources": ["filename:patterns", "mtime"],
                "filename_patterns": [r"(\d{4})-(\d{2})-(\d{2})"],
            }
        )
        date, source = strategy.compute_date(
            primary={"path": "/p/2019-08-15-anything.jpg"},
            exif={},
        )
        assert date == datetime(2019, 8, 15, 0, 0, 0)

    def test_falls_through_when_no_pattern_matches(self):
        strategy = Strategy(
            {
                "date_sources": ["filename:patterns", "mtime"],
                "filename_patterns": [r"IMG_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})"],
            }
        )
        date, source = strategy.compute_date(
            primary={"path": "/p/random.jpg", "mtime": 1577836800.0},
            exif={},
        )
        assert source == "mtime"


class TestSuspiciousDateDetection:
    def test_known_sentinel_dates_demoted_to_next_source(self):
        strategy = Strategy(
            {
                "date_sources": ["exif:Composite:DateTimeOriginal", "mtime"],
                "suspicious_dates": {"sentinels": ["1980-01-01", "2000-01-01"]},
            }
        )
        date, source = strategy.compute_date(
            primary={"path": "/p/img.jpg", "mtime": 1577836800.0},
            exif={"Composite:DateTimeOriginal": "1980:01:01 00:00:00"},
        )
        assert source == "mtime"

    def test_min_year_threshold_rejects_too_old_dates(self):
        strategy = Strategy(
            {
                "date_sources": ["exif:Composite:DateTimeOriginal", "mtime"],
                "suspicious_dates": {"min_year": 1995},
            }
        )
        date, source = strategy.compute_date(
            primary={"path": "/p/img.jpg", "mtime": 1577836800.0},
            exif={"Composite:DateTimeOriginal": "1985:08:15 14:20:30"},
        )
        assert source == "mtime"

    def test_future_date_rejected_when_reject_future_set(self):
        strategy = Strategy(
            {
                "date_sources": ["exif:Composite:DateTimeOriginal", "mtime"],
                "suspicious_dates": {"reject_future": True},
            }
        )
        date, source = strategy.compute_date(
            primary={"path": "/p/img.jpg", "mtime": 1577836800.0},
            exif={"Composite:DateTimeOriginal": "2099:08:15 14:20:30"},
        )
        assert source == "mtime"

    def test_legitimate_date_not_demoted(self):
        strategy = Strategy(
            {
                "date_sources": ["exif:Composite:DateTimeOriginal", "mtime"],
                "suspicious_dates": {"sentinels": ["1980-01-01"], "min_year": 1995, "reject_future": True},
            }
        )
        date, source = strategy.compute_date(
            primary={"path": "/p/img.jpg", "mtime": 1577836800.0},
            exif={"Composite:DateTimeOriginal": "2019:08:15 14:20:30"},
        )
        assert source == "exif:Composite:DateTimeOriginal"
        assert date == datetime(2019, 8, 15, 14, 20, 30)


class TestComputeDestinationDir:
    def test_default_template_yields_year_yearmonth_subfolder(self):
        strategy = Strategy({"path_template": "{year}/{year}-{month:02d}/"})
        result = strategy.compute_destination_dir(
            primary_ext=".jpg",
            date=datetime(2019, 8, 15),
            destination_root="/photos",
        )
        assert str(result).replace("\\", "/") == "/photos/2019/2019-08"

    def test_format_rule_overrides_path_template(self):
        strategy = Strategy(
            {
                "path_template": "{year}/{year}-{month:02d}/",
                "format_rules": {
                    "raw": {
                        "extensions": [".cr2", ".cr3"],
                        "path_template": "{year}/{year}-{month:02d}/RAW/",
                    },
                    "video": {
                        "extensions": [".mp4", ".mov"],
                        "path_template": "{year}/{year}-{month:02d}/Video/",
                    },
                },
            }
        )
        raw = strategy.compute_destination_dir(".cr2", datetime(2019, 8, 15), "/photos")
        video = strategy.compute_destination_dir(".mp4", datetime(2019, 8, 15), "/photos")
        image = strategy.compute_destination_dir(".jpg", datetime(2019, 8, 15), "/photos")
        assert str(raw).replace("\\", "/").endswith("2019-08/RAW")
        assert str(video).replace("\\", "/").endswith("2019-08/Video")
        assert str(image).replace("\\", "/").endswith("2019-08")


class TestComputeFilename:
    def test_no_rename_template_preserves_original_name(self):
        strategy = Strategy({"rename_template": None})
        result = strategy.compute_filename(
            original_name="IMG_1234.CR2",
            date=datetime(2019, 8, 15, 14, 20, 30),
        )
        assert result == "IMG_1234.CR2"

    def test_default_rename_template_prepends_iso_datetime(self):
        strategy = Strategy(
            {"rename_template": "{date:%Y-%m-%d_%H%M%S}_{original_stem}{ext}"}
        )
        result = strategy.compute_filename(
            original_name="IMG_1234.CR2",
            date=datetime(2019, 8, 15, 14, 20, 30),
        )
        assert result == "2019-08-15_142030_IMG_1234.CR2"

    def test_extension_case_preserved_in_renamed_output(self):
        strategy = Strategy(
            {"rename_template": "{date:%Y-%m-%d}_{original_stem}{ext}"}
        )
        result = strategy.compute_filename(
            original_name="img.JPG",
            date=datetime(2019, 8, 15),
        )
        # Ext preserves the original case as-is.
        assert result == "2019-08-15_img.JPG"


class TestPlanGroup:
    def _strategy(self, **overrides):
        config = {
            "date_sources": ["exif:Composite:DateTimeOriginal", "mtime"],
            "path_template": "{year}/{year}-{month:02d}/",
            "format_rules": {
                "raw": {"extensions": [".cr2"], "path_template": "{year}/{year}-{month:02d}/RAW/"},
            },
        }
        config.update(overrides)
        return Strategy(config)

    def test_normal_group_produces_move_row_with_destinations(self):
        strategy = self._strategy()
        primary = {"path": "/src/IMG_1234.CR2", "mtime": 1577836800.0}
        members = [primary, {"path": "/src/IMG_1234.JPG", "mtime": 1577836800.0}]
        group = {"primary": primary, "members": members, "stem": "IMG_1234"}
        exif_data = {"/src/IMG_1234.CR2": {"Composite:DateTimeOriginal": "2019:08:15 14:20:30"}}
        row = strategy.plan_group(group, exif_by_path=exif_data, destination_root="/dst")
        assert row["action"] == "move"
        assert row["date"] == "2019-08-15T14:20:30"
        assert row["date_source"] == "exif:Composite:DateTimeOriginal"
        assert row["primary_file"] == "/src/IMG_1234.CR2"
        dests = [d["dst"] for d in row["destination_files"]]
        assert all("2019-08/RAW" in d.replace("\\", "/") for d in dests)
        # Same number of source/destination entries
        assert len(row["destination_files"]) == 2

    def test_no_date_means_needs_review_action(self):
        strategy = Strategy(
            {
                "date_sources": ["exif:Composite:DateTimeOriginal"],  # no mtime fallback
                "path_template": "{year}/{year}-{month:02d}/",
                "review_paths": {"needs_review": "_needs-review/{reason}/"},
            }
        )
        primary = {"path": "/src/random.jpg", "mtime": None}
        group = {"primary": primary, "members": [primary], "stem": "random"}
        row = strategy.plan_group(group, exif_by_path={}, destination_root="/dst")
        assert row["action"] == "needs-review:no-date"
        # Destination should land somewhere under _needs-review/no-date/
        dest = row["destination_files"][0]["dst"].replace("\\", "/")
        assert "_needs-review" in dest

    def test_rename_template_applied_consistently_across_group_members(self):
        strategy = self._strategy(
            rename_template="{date:%Y-%m-%d_%H%M%S}_{original_stem}{ext}"
        )
        primary = {"path": "/src/IMG_1234.CR2", "mtime": 1577836800.0}
        members = [primary, {"path": "/src/IMG_1234.JPG"}, {"path": "/src/IMG_1234.xmp"}]
        group = {"primary": primary, "members": members, "stem": "IMG_1234"}
        exif_data = {"/src/IMG_1234.CR2": {"Composite:DateTimeOriginal": "2019:08:15 14:20:30"}}
        row = strategy.plan_group(group, exif_by_path=exif_data, destination_root="/dst")
        new_names = [Path(d["dst"]).name for d in row["destination_files"]]
        # All renamed with same date prefix and primary stem; original ext preserved per file.
        assert all(n.startswith("2019-08-15_142030_IMG_1234.") for n in new_names)
        exts = sorted(Path(n).suffix for n in new_names)
        assert exts == [".CR2", ".JPG", ".xmp"]
