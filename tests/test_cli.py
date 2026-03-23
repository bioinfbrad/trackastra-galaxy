from trackastra_galaxy.cli import build_parser, parse_coords


def test_parser_exists():
    parser = build_parser()
    assert parser is not None


def test_parse_coords_comma():
    assert parse_coords("0,1,2") == [0, 1, 2]


def test_parse_coords_space():
    assert parse_coords("0 1 2") == [0, 1, 2]
