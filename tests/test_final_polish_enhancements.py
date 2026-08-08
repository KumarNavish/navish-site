from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


def test_final_copy_polish_is_loaded_and_bounded() -> None:
    html = (STATIC / "index.html").read_text()
    script = (STATIC / "polish14-enhancements.js").read_text()

    assert '/assets/polish14-enhancements.js?v=polish14' in html
    assert '.attention-reasons li' in script
    assert '.opportunity-copy > p' in script
    assert '.role-conversion-main li' in script
    assert 'MutationObserver' in script
    assert 'while\\b' in script
    assert 'fetch(' not in script
    assert '/api/' not in script
