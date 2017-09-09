from packspec import cli


# Tests

def test_packspec():
    specs = cli.parse_specs('tests/packspec.yml')
    valid = cli.test_specs(specs)
    assert valid


def test_packspec_assertion_fail():
    specs = cli.parse_specs('tests/packspec.yml')
    specs[0]['features'] = specs[0]['features'][0:3]
    specs[0]['features'][-1]['result'] = 'FAIL'
    valid = cli.test_specs(specs)
    assert not valid


def test_packspec_exception_fail():
    specs = cli.parse_specs('tests/packspec.yml')
    specs[0]['features'] = specs[0]['features'][0:3]
    specs[0]['features'][-1]['call'] = True
    valid = cli.test_specs(specs)
    assert not valid
