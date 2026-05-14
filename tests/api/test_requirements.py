from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent


def test_requirements_have_upper_bounds():
    """Enforce upper-bound caps for packages where major-version breaks are known risks.

    `anthropic` is intentionally NOT capped — see requirements.txt:6-8 comment:
    "Never pin an upper cap — Claude API evolves fast; old SDKs break features."
    Breaking incident: <0.50.0 cap (commit f3f2974) caused output_config failure.
    """
    reqs = {}
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = line.split("=", 1)[0].split("<", 1)[0].split(">", 1)[0].strip().lower()
        reqs[name] = line

    # `anthropic` deliberately omitted per the documented intent above.
    for name in ("telethon", "flask"):
        assert "<" in reqs[name], f"{name} requirement must specify an upper bound: {reqs[name]}"
