import pytest
import requests

from pipeline import manual
from pipeline.manual import SPECS, ManualDataError, load_all, validate_text

SPEC = {s.name: s for s in SPECS}
INJ_HEAD = ",".join(SPEC["injuries"].columns)
DEPTH_HEAD = ",".join(SPEC["depth_chart"].columns)


def write_templates(d, **rows):
    for s in SPECS:
        body = ",".join(s.columns) + "\n" + "".join(r + "\n" for r in rows.get(s.name, []))
        (d / f"{s.name}.csv").write_text(body)


def test_header_only_templates_are_valid(tmp_path):
    write_templates(tmp_path)
    loaded = load_all(tmp_path)
    assert {k: len(v.rows) for k, v in loaded.items()} == {s.name: 0 for s in SPECS}


def test_good_rows_are_normalized():
    text = INJ_HEAD + "\nTennessee,A Player,qb, Questionable ,ankle,2026-11-01,,https://x.org/a,4,2026-11-02,team release\n\n"
    l = validate_text(SPEC["injuries"], text, known_teams={"Tennessee"})
    r = l.rows[0]
    assert (r["position"], r["status"], r["impact_rating"], str(r["date_reported"])) == ("QB", "questionable", 4, "2026-11-01")
    assert l.warnings == []


def test_errors_name_row_column_and_fix():
    text = INJ_HEAD + "\nTennessee,B,QB,maybe,,11/01/2026,,example.com,9,,\n"
    with pytest.raises(ManualDataError) as e:
        validate_text(SPEC["injuries"], text)
    msg = str(e.value)
    for frag in ["row 2, column 'status'", "Use one of", "row 2, column 'date_reported'", "YYYY-MM-DD",
                 "row 2, column 'impact_rating'", "row 2, column 'source': is required", "row 2, column 'last_updated': is required",
                 "row 2, column 'source_url': must start with http"]:
        assert frag in msg, frag


def test_header_mismatch_is_explained():
    with pytest.raises(ManualDataError, match=r"(?s)Missing column\(s\): source.*Unexpected column\(s\): sorce"):
        validate_text(SPEC["injuries"], INJ_HEAD.replace(",source", ",sorce") + "\n")


def test_depth_chart_rules_and_unknown_team_warning():
    ok = DEPTH_HEAD + "\nTennessee,Offense,qb,1,P One,7,rs-so,6-3,215,85,,2026-11-02,own notes\n" \
                      "Tenn,offense,QB,2,P Two,,,,,,,2026-11-02,own notes\n"
    l = validate_text(SPEC["depth_chart"], ok, known_teams={"Tennessee"})
    assert l.rows[0]["position_group"] == "offense" and l.rows[0]["class"] == "RS-SO"
    assert any("team 'Tenn'" in w for w in l.warnings)
    bad = DEPTH_HEAD + "\nTennessee,offense,QB,0,P,7,SO,6 ft,215,150,,2026-11-02,x\n"
    with pytest.raises(ManualDataError) as e:
        validate_text(SPEC["depth_chart"], bad)
    assert "'string': must be 1" in str(e.value) and "'height'" in str(e.value) and "'snap_pct'" in str(e.value)


def test_all_files_reported_together(tmp_path):
    write_templates(tmp_path, injuries=["Tennessee,X,QB,out,,bad,,,3,2026-11-02,src"],
                    schemes=["Tennessee,offence,Spread,,,,,,,,2026-11-02,src"])
    with pytest.raises(ManualDataError) as e:
        load_all(tmp_path)
    assert "injuries.csv" in str(e.value) and "schemes.csv" in str(e.value)


class _Resp:
    def __init__(self, text, ok=True):
        self.content, self.ok = text.encode(), ok

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError("404")


def test_google_sheet_overrides_local_and_falls_back(tmp_path, monkeypatch):
    write_templates(tmp_path)
    sheet = INJ_HEAD + "\nTennessee,S Player,WR,out,knee,2026-11-01,,,2,2026-11-02,sheet\n"
    monkeypatch.setenv("SHEET_INJURIES_URL", "https://docs.google.com/x/pub?output=csv")
    monkeypatch.setattr(manual.requests, "get", lambda url, timeout: _Resp(sheet))
    l = load_all(tmp_path)["injuries"]
    assert l.origin == "Google Sheet" and l.rows[0]["player"] == "S Player"
    monkeypatch.setattr(manual.requests, "get", lambda url, timeout: _Resp("", ok=False))
    l = load_all(tmp_path)["injuries"]
    assert l.origin == "local file" and l.rows == [] and "could not download" in l.warnings[0]
