"""
Non-path constants.

Includes classification categories, media extensions, schema definitions,
and update exceptions.
"""

class UpdateCancelled(Exception):
    """Raised when the user cancels an in-progress updater download."""

CSV_COLUMNS = ["id", "heading", "text", "image_path", "video_path", "label", "multi_category",
               "source", "source_category", "category", "annotator", "annotation_confidence",
               "additional_notes", "timestamp"]

CATEGORIES = ["", "Politics", "Health", "Science", "Technology", "Sports",
              "Entertainment", "Religion", "Education", "Environment",
              "International", "Miscellaneous"]

MULTI_CATEGORIES = ["Misinformation", "Satire", "Clickbait"]

DETAILED_STATS_COLUMNS = ["Total", "Real", "Fake", "Misinfo", "Satire", "Clickbait"]
DETAILED_STATS_METRICS = [
    "Total Items", "Total Images", "Total Videos",
    "Text Only", "Image Only", "Video Only",
    "Text + Image", "Text + Video", "Image + Video", "Text + Image + Video"
]

MIN_TEXT_LENGTH = 30

SOURCE_CATEGORIES = ["", "News Channel", "Newspaper", "Facebook", "Tiktok",
                     "Twitter", "Instagram", "Reddit", "YouTube",
                     "Blog", "Website", "Miscellaneous"]

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp")
VIDEO_EXTENSIONS = (".mp4", ".avi", ".mov", ".mkv", ".webm")
