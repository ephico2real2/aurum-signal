from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent


def test_requirements_have_upper_bounds():
    reqs = {}
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = line.split("=", 1)[0].split("<", 1)[0].split(">", 1)[0].strip().lower()
        reqs[name] = line

    for name in ("anthropic", "telethon", "flask"):
        assert "<" in reqs[name]
