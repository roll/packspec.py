# -*- coding: utf-8 -*-
from __future__ import division
from __future__ import print_function
from __future__ import absolute_import
from __future__ import unicode_literals

import io
import os
import re
import yaml
import click
import importlib
from functools import partial


# Module API

@click.command()
@click.argument('path', default='.')
def cli(path):
    specs = parse_specs(path)
    success = test_specs(specs)
    if not success:
        exit(1)


# Helpers

def parse_specs(path):
    # Maps
    specmap = {}
    hookmap = {}
    for root, dirnames, filenames in os.walk(path):
        for filename in filenames:
            if not filename.endswith('.yml') and filename != 'packspec.py':
                continue
            filepath = os.path.join(root, filename)
            filecont = io.open(filepath, encoding='utf-8').read()
            if filename == 'packspec.py':
                scope = {}
                exec(filecont, scope)
                for name, attr in scope.items():
                    if name.startswith('_'):
                        continue
                    hookmap[name] = attr
                continue
            spec = parse_spec(filecont)
            if not spec:
                continue
            if spec['package'] not in specmap:
                specmap[spec['package']] = spec
            else:
                specmap[spec['package']]['features'].extend(spec['features'])
    # Specs
    specs = [specmap[package] for package in sorted(specmap)]
    for spec in specs:
        for name, hook in hookmap.items():
            spec['variables'][name] = partial(hook, spec['variables'])
    return specs


def parse_spec(spec):
    # Package
    contents = yaml.load(spec)
    try:
        feature = parse_feature(contents[0])
        package = feature['result']
        assert feature['source'][0] == 'PACKAGE'
    except Exception:
        return None
    # Features
    features = []
    for feature in contents:
        feature = parse_feature(feature)
        features.append(feature)
    # Variables
    variables = {'PACKAGE': package}
    module = importlib.import_module(package)
    for name in dir(module):
        if name.startswith('_'):
            continue
        variables[name] = getattr(module, name)
    return {
        'package': package,
        'features': features,
        'variables': variables,
    }


def parse_feature(feature):
    left, right = list(feature.items())[0]
    # Left side
    match = re.match(r'^(?:([^=]*)=)?([^:]*)(?::{([^{}]*)})?$', left)
    target, source, filter = match.groups()
    if source:
        source = source.split('.')
    if filter:
        rules = filter.split(',')
        filter = '!py' in rules or not ('!' in filter or 'py' in rules)
    # Right side
    result = right
    params = None
    if isinstance(right, list):
        result = right[-1]
        params = right[:-1]
    # String repr
    string = '.'.join(source)
    if target:
        string = '%s=%s' % (target, string)
    if params:
        string = '%s(%s)' % (string, ', '.join(map(repr, params)))
    if not target:
        string = '%s == %s' % (string, repr(result))
    return {
        'string': string,
        'source': source,
        'params': params,
        'result': result,
        'target': target,
        'filter': filter,
    }


def test_specs(specs):
    success = True
    for spec in specs:
        spec_success = test_spec(spec)
        success = success and spec_success
    return success


def test_spec(spec):
    passed = 0
    amount = len(spec['features'])
    for feature in spec['features']:
        passed += test_feature(feature, spec['variables'])
    print('%s: %s/%s' % (spec['package'], passed, amount))
    success = (passed == amount)
    return success


def test_feature(feature, variables):
    # Filter
    if feature['filter']:
        print('(#) %s' % feature['string'])
        return True
    # Execute
    try:
        source = variables
        for name in feature['source']:
            getter = dict.get if isinstance(source, dict) else getattr
            source = getter(source, name)
        result = source
        if feature['params'] is not None:
            result = source(*feature['params'])
    except Exception:
        result = 'ERROR'
    # Assign
    if feature['target'] is not None:
        variables[feature['target']] = result
    # Verify
    success = result == feature['result'] or (result != 'ERROR' and feature['result'] == 'ANY')
    if success:
        print('(+) %s' % feature['string'])
    else:
        print('(-) %s # %s' % (feature['string'], repr(result)))
    return success


# Main program

if __name__ == '__main__':
    cli()
