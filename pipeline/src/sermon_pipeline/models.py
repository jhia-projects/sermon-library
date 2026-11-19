"""Source-agnostic intermediate record produced by every RSS reader and scraper."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import date
from typing import Literal

Origin = Literal["rss", "scrape"]

# Fields that carry sermon data (everything except identity + provenance bookkeeping).
DATA_FIELDS: tuple[str, ...] = (
    "title",
    "date",
    "speaker",
    "series_name",
    "series_label_explicit",
    "passage_text",
    "listed_references",
    "audio_url",
    "video_url",
    "youtube_id",
    "duration_seconds",
    "image_url",
    "source_url",
    "series_url",
    "service_time",
)


@dataclass
class RawSermon:
    # Stable identifier the *source* uses for this recording (All Souls: media_id). Used to match
    # the same sermon across RSS and scraped pages, and as the basis of the published sermon id.
    source_key: str
    origin: Origin

    title: str | None = None
    date: date | None = None
    speaker: str | None = None
    series_name: str | None = None
    # True when the source labelled the series explicitly ("Series: X" / "X: subtitle"), False
    # when inferred from a bare description.
    series_label_explicit: bool = False
    # Primary scripture reference exactly as printed by the source, e.g. "Acts 12:19–24".
    passage_text: str | None = None
    # Every reference the source lists for the sermon, "; "-joined, e.g. "Psalm 22:1-21; Mark 15:16-32".
    # The feed only prints one (in the title); site listings can print several.
    listed_references: str | None = None
    audio_url: str | None = None
    video_url: str | None = None
    youtube_id: str | None = None
    duration_seconds: int | None = None
    image_url: str | None = None
    source_url: str | None = None
    series_url: str | None = None
    # Service time exactly as printed, e.g. "9.30am", "6pm" (St Helen's prints it per talk). Used
    # only to spot one sermon repeated at several services; never published.
    service_time: str | None = None

    # field name -> origin that supplied its value. Filled automatically in __post_init__.
    provenance: dict[str, Origin] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in DATA_FIELDS:
            if name not in self.provenance and _has_value(getattr(self, name)):
                self.provenance[name] = self.origin

    def values(self) -> dict[str, object]:
        return {f.name: getattr(self, f.name) for f in fields(self) if f.name in DATA_FIELDS}


def _has_value(v: object) -> bool:
    # False is a real value only for series_label_explicit when a series name exists; treat it as
    # "unset" so a scraped True can't be blocked by the default.
    return v is not None and v is not False and v != ""
