from packspec import cli


# Tests

def test_packspec():
    features = cli.parse_specs('tests/packspec.yml')
    valid = cli.test_specs(features)
    assert valid
