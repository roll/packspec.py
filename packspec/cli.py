# -*- coding: utf-8 -*-
from __future__ import division
from __future__ import print_function
from __future__ import absolute_import
from __future__ import unicode_literals

import io
import os
import re
import json
import yaml
import click
import importlib
from emoji import emojize
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
            spec['scope'][name] = partial(hook, spec['scope'])
    return specs


def parse_spec(spec):

    # Package
    contents = yaml.load(spec)
    try:
        feature = parse_feature(contents[0])
        package = feature['result']
        assert feature['assign'] == 'PACKAGE'
        assert not feature['skip']
    except Exception:
        return None

    # Features
    features = []
    for feature in contents:
        feature = parse_feature(feature)
        features.append(feature)

    # Scope
    scope = {}
    module = importlib.import_module(package)
    for name in dir(module):
        if name.startswith('_'):
            continue
        scope[name] = getattr(module, name)

    return {
        'package': package,
        'features': features,
        'scope': scope,
    }


def parse_feature(feature):
    left, right = list(feature.items())[0]

    # Left side
    call = False
    match = re.match(r'^(?:(.*):)?(?:([^=]*)=)?(.*)?$', left)
    skip, assign, property = match.groups()
    if skip:
        filters = skip.split(':')
        skip = (filters[0] == 'not') == ('py' in filters)
    if not assign and not property:
        raise Exception('Non-valid feature')
    if property and property.endswith('()'):
        property = property[:-2]
        call = True

    # Right side
    arguments = None
    result = right
    if call:
        arguments = right[:-1]
        result = right[-1]

    # Text repr
    text = property
    if assign:
        text = '%s = %s' % (assign, property or json.dumps(result))
    if arguments is not None:
        items = []
        for argument in arguments:
            item = parse_interpolation(argument)
            if not item:
                item = json.dumps(argument)
            items.append(item)
        text = '%s(%s)' % (text, ', '.join(items))
    if not assign:
        text = '%s == %s' % (text, json.dumps(result))

    return {
        'skip': skip,
        'assign': assign,
        'property': property,
        'arguments': arguments,
        'result': result,
        'text': text,
    }


def test_specs(specs):
    success = True
    message = click.style(emojize('\n :small_blue_diamond:  ', use_aliases=True), fg='blue', bold=True)
    message += click.style('Python\n', bold=True)
    click.echo(message)
    for spec in specs:
        spec_success = test_spec(spec)
        success = success and spec_success
    return success


def test_spec(spec):
    passed = 0
    amount = len(spec['features'])
    for feature in spec['features']:
        passed += test_feature(feature, spec['scope'])
    success = (passed == amount)
    message = click.style(emojize('\n :heavy_check_mark:  ', use_aliases=True), fg='green', bold=True)
    if not success:
        message = click.style(emojize('\n :x:  ', use_aliases=True), fg='red', bold=True)
    message += click.style('%s: %s/%s\n' % (spec['package'], passed, amount), bold=True)
    click.echo(message)
    return success


def test_feature(feature, scope):

    # Skip
    if feature['skip']:
        message = click.style(emojize(' :question:  ', use_aliases=True), fg='yellow')
        message += click.style('%s' % feature['text'])
        click.echo(message)
        return True

    # Execute
    result = feature['result']
    if feature['property']:
        try:
            owner = scope
            names = feature['property'].split('.')
            for name in names[:-1]:
                owner = get_property(owner, name)
            property = get_property(owner, names[-1])
            if feature['arguments'] is not None:
                arguments = []
                for argument in feature['arguments']:
                    name = parse_interpolation(argument)
                    if name:
                        argument = get_property(scope, name)
                    arguments.append(argument)
                result = property(*arguments)
            else:
                result = property
        except Exception:
            result = 'ERROR'

    # Assign
    if feature['assign']:
        owner = scope
        names = feature['assign'].split('.')
        for name in names[:-1]:
            owner = get_property(owner, name)
        if get_property(owner, names[-1]) is not None and names[-1].isupper():
            raise Exception('Can\'t update the constant "%s"' % names[-1])
        set_property(owner, names[-1], result)

    # Compare
    success = result == feature['result'] or (result != 'ERROR' and feature['result'] == 'ANY')
    if success:
        message = click.style(emojize(' :heavy_check_mark:  ', use_aliases=True), fg='green')
        message += click.style('%s' % feature['text'])
        click.echo(message)
    else:
        message = click.style(emojize(' :x:  ', use_aliases=True), fg='red')
        message += click.style('%s # %s' % (feature['text'], json.dumps(result)))
        click.echo(message)

    return success


def parse_interpolation(argument):
    if isinstance(argument, dict) and len(argument) == 1:
        left, right = list(argument.items())[0]
        if right is None:
            return left
    return None


def get_property(owner, name):
    if isinstance(owner, dict):
        return owner.get(name)
    return getattr(owner, name, None)


def set_property(owner, name, value):
    if isinstance(owner, dict):
        owner[name] = value
        return
    return setattr(owner, name, value)


# Main program

if __name__ == '__main__':
    cli()
