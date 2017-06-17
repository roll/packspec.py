# -*- coding: utf-8 -*-
from __future__ import division
from __future__ import print_function
from __future__ import absolute_import
from __future__ import unicode_literals

import io
import os
import re
import six
import copy
import glob
import json
import yaml
import click
import importlib
from emoji import emojize
from collections import OrderedDict


# Helpers

def parse_specs(path):

    # Paths
    paths = []
    if path is None:
        paths = glob.glob('packspec.*')
        if not paths:
            path = 'packspec'
    if os.path.isfile(path):
        paths = [path]
    elif os.path.isdir(path):
        for name in os.listdir(path):
            paths.append(os.path.join(path, name))

    # Specs
    specs = []
    for path in paths:
        spec = parse_spec(path)
        if spec:
            specs.append(spec)

    return specs


def parse_spec(path):

    # Documents
    if not path.endswith('.yml'):
        return None
    contents = io.open(path, encoding='utf-8').read()
    documents = list(yaml.load_all(contents))

    # Package
    feature = parse_feature(documents[0][0])
    if feature['skip']:
        return None
    package = feature['comment']

    # Features
    skip = False
    features = []
    for feature in documents[0]:
        feature = parse_feature(feature)
        features.append(feature)
        if feature['comment']:
            skip = feature['skip']
        feature['skip'] = skip or feature['skip']

    # Scope
    scope = {}
    scope['$import'] = builtin_import
    if len(documents) > 1 and documents[1].get('py'):
        user_scope = {}
        exec(documents[1].get('py'), user_scope)
        for name, attr in user_scope.items():
            if name.startswith('_'):
                continue
            scope['$%s' % name] = attr

    # Stats
    stats = {'features': 0, 'comments': 0, 'skipped': 0, 'tests': 0}
    for feature in features:
        stats['features'] += 1
        if feature['comment']:
            stats['comments'] += 1
        else:
            stats['tests'] += 1
            if feature['skip']:
                stats['skipped'] += 1

    return {
        'package': package,
        'features': features,
        'scope': scope,
        'stats': stats,
    }


def parse_feature(feature):

    # General
    if isinstance(feature, six.string_types):
        match = re.match(r'^(?:\((.*)\))?(\w.*)$', feature)
        skip, comment = match.groups()
        if skip:
            skip = 'py' not in skip.split('|')
        return {'assign': None, 'comment': comment, 'skip': skip}
    left, right = list(feature.items())[0]

    # Left side
    call = False
    match = re.match(r'^(?:\((.*)\))?(?:([^=]*)=)?([^=].*)?$', left)
    skip, assign, property = match.groups()
    if skip:
        skip = 'py' not in skip.split('|')
    if not assign and not property:
        raise Exception('Non-valid feature')
    if property:
        call = True
        if property.endswith('=='):
            property = property[:-2]
            call = False

    # Right side
    args = []
    kwargs = OrderedDict()
    result = right
    if call:
        result = None
        for item in right:
            if isinstance(item, dict) and len(item) == 1:
                item_left, item_right = list(item.items())[0]
                if item_left == '==':
                    result = item_right
                    continue
                if item_left.endswith('='):
                    kwargs[item_left[:-1]] = item_right
                    continue
            args.append(item)

    # Text repr
    text = property
    if assign:
        text = '%s = %s' % (assign, property or json.dumps(result, ensure_ascii=False))
    if call:
        items = []
        for item in args:
            items.append(json.dumps(item, ensure_ascii=False))
        for name, item in kwargs.items():
            items.append('%s=%s' % (name, json.dumps(item, ensure_ascii=False)))
        text = '%s(%s)' % (text, ', '.join(items))
    if result and not assign:
        text = '%s == %s' % (text, result if result == 'ERROR' else json.dumps(result, ensure_ascii=False))
    text = re.sub(r'{"([^{}]*?)": null}', r'\1', text)

    return {
        'comment': None,
        'skip': skip,
        'call': call,
        'assign': assign,
        'property': property,
        'args': args,
        'kwargs': kwargs,
        'result': result,
        'text': text,
    }


def test_specs(specs):

    # Message
    message = click.style(emojize('\n #  ', use_aliases=True))
    message += click.style('Python\n', bold=True)
    click.echo(message)

    # Test specs
    success = True
    for spec in specs:
        spec_success = test_spec(spec)
        success = success and spec_success

    return success


def test_spec(spec):

    # Message
    message = click.style(emojize(':heavy_minus_sign:'*3, use_aliases=True))
    click.echo(message)

    # Test spec
    passed = 0
    for feature in spec['features']:
        passed += test_feature(feature, spec['scope'])
    success = (passed == spec['stats']['features'])

    # Message
    color = 'green'
    message = click.style(emojize('\n :heavy_check_mark:  ', use_aliases=True), fg='green', bold=True)
    if not success:
        color = 'red'
        message = click.style(emojize('\n :x:  ', use_aliases=True), fg='red', bold=True)
    message += click.style('%s: %s/%s\n' % (spec['package'], passed - spec['stats']['comments'] - spec['stats']['skipped'], spec['stats']['tests'] - spec['stats']['skipped']), bold=True, fg=color)
    click.echo(message)

    return success


def test_feature(feature, scope):

    # Comment
    if feature['comment']:
        message = click.style(emojize('\n #  ', use_aliases=True))
        message += click.style('%s\n' % feature['comment'], bold=True)
        click.echo(message)
        return True

    # Skip
    if feature['skip']:
        message = click.style(emojize(' :heavy_minus_sign:  ', use_aliases=True), fg='yellow')
        message += click.style('%s' % feature['text'])
        click.echo(message)
        return True

    # Dereference
    feature = copy.deepcopy(feature)
    if feature['call']:
        feature['args'] = dereference_value(feature['args'], scope)
        feature['kwargs'] = dereference_value(feature['kwargs'], scope)
    feature['result'] = dereference_value(feature['result'], scope)

    # Execute
    exception = None
    result = feature['result']
    if feature['property']:
        try:
            property = scope
            for name in feature['property'].split('.'):
                property = get_property(property, name)
            if feature['call']:
                result = property(*feature['args'], **feature['kwargs'])
            else:
                result = property
            result = normalize_value(result)
        except Exception as exc:
            exception = exc
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
    success = result == feature['result'] if feature['result'] is not None else result != 'ERROR'
    if success:
        message = click.style(emojize(' :heavy_check_mark:  ', use_aliases=True), fg='green')
        message += click.style('%s' % feature['text'])
        click.echo(message)
    else:
        try:
            result_text = json.dumps(result)
        except TypeError:
            result_text = repr(result)
        message = click.style(emojize(' :x:  ', use_aliases=True), fg='red')
        message += click.style('%s\n' % feature['text'])
        if exception:
            message += click.style('Exception: %s' % exception, fg='red', bold=True)
        else:
            message += click.style('Assertion: %s != %s' % (result_text, json.dumps(feature['result'], ensure_ascii=False)), fg='red', bold=True)
        click.echo(message)

    return success


def builtin_import(package):
    attributes = {}
    module = importlib.import_module(package)
    for name in dir(module):
        if name.startswith('_'):
            continue
        attributes[name] = getattr(module, name)
    return attributes


def dereference_value(value, scope):
    value = copy.deepcopy(value)
    if isinstance(value, dict) and len(value) == 1 and list(value.values())[0] is None:
        result = scope
        for name in list(value.keys())[0].split('.'):
            result = get_property(result, name)
        value = result
    elif isinstance(value, dict):
        for key, item in value.items():
            value[key] = dereference_value(item, scope)
    elif isinstance(value, list):
        for index, item in enumerate(list(value)):
            value[index] = dereference_value(item, scope)
    return value


def normalize_value(value):
    if isinstance(value, tuple):
        value = list(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            value[key] = normalize_value(item)
    elif isinstance(value, list):
        for index, item in enumerate(list(value)):
            value[index] = normalize_value(item)
    return value


def get_property(owner, name):
    if isinstance(owner, dict):
        return owner.get(name)
    elif isinstance(owner, (list, tuple)):
        return owner[int(name)]
    return getattr(owner, name, None)


def set_property(owner, name, value):
    if isinstance(owner, dict):
        owner[name] = value
        return
    elif isinstance(owner, list):
        owner[int(name)] = value
        return
    return setattr(owner, name, value)


# Main program

@click.command()
@click.argument('path', required=False)
def cli(path):
    specs = parse_specs(path)
    success = test_specs(specs)
    if not success:
        exit(1)


if __name__ == '__main__':
    cli()
