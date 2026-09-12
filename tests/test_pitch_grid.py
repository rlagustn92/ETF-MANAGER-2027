"""pitch_grid.py 슬롯 격자 테스트 (FM 풍 세로 전술판, 5칸 x 6라인 + GK 1칸 = 26슬롯)."""

import pitch_grid


def test_slot_count_and_uniqueness():
    slots = pitch_grid.all_slots()
    assert len(slots) == 26            # 5*5(ST/AM/MC/DM/DF) + 1(GK)
    assert len(set(slots)) == 26


def test_gk_row_has_single_center_slot():
    gk_slots = [s for s in pitch_grid.all_slots() if s.startswith("GK-")]
    assert gk_slots == ["GK-C"]


def test_orientation_gk_is_bottom_attack_is_top():
    gk_y = pitch_grid.center("GK-C")[1]
    st_y = pitch_grid.center("ST-C")[1]
    assert gk_y > st_y       # y 는 화면 기준 0=위(공격) ~ 1=아래(우리 골문)
    assert gk_y > 0.85
    assert st_y < 0.20


def test_center_and_nearest_roundtrip():
    for s in pitch_grid.all_slots():
        x, y = pitch_grid.center(s)
        assert pitch_grid.nearest(x, y) == s


def test_group_mapping():
    assert pitch_grid.group_of("ST-C") == "ATTACK"
    assert pitch_grid.group_of("AM-L") == "ATTACK"
    assert pitch_grid.group_of("MC-C") == "MIDFIELD"
    assert pitch_grid.group_of("DM-R") == "MIDFIELD"
    assert pitch_grid.group_of("DF-CL") == "DEFENSE"
    assert pitch_grid.group_of("GK-C") == "GOALKEEPER"


def test_first_free_slot_prefers_requested_row_center_first():
    slot = pitch_grid.first_free_slot(set(), preferred_row="ST")
    assert slot == "ST-C"


def test_first_free_slot_skips_occupied_and_spills_to_next_row():
    used = {f"ST-{c}" for c in ["C", "CL", "CR", "L", "R"]}   # ST 라인 가득 참
    slot = pitch_grid.first_free_slot(used, preferred_row="ST")
    assert slot is not None
    assert not slot.startswith("ST-")


def test_first_free_slot_none_when_full():
    used = set(pitch_grid.all_slots())
    assert pitch_grid.first_free_slot(used) is None


def test_is_slot_validates():
    assert pitch_grid.is_slot("MC-C") is True
    assert pitch_grid.is_slot("GK-L") is False   # GK 라인엔 L 없음
    assert pitch_grid.is_slot("") is False
    assert pitch_grid.is_slot(None) is False
    assert pitch_grid.is_slot("XX-C") is False


def test_guess_row_has_sane_defaults():
    assert pitch_grid.guess_row("QQQ") == "AM"
    assert pitch_grid.guess_row("SGOV") == "GK"
    assert pitch_grid.guess_row("TLT") == "DF"
    assert pitch_grid.guess_row("UNKNOWN_TICKER") == "MC"
